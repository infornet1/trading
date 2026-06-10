# Performance & Profitability Audit — LP Defensor + Signal Lab

**Date:** 2026-06-09 · **Auditor:** Claude Code (Fable 5) · **Scope:** latency, execution quality, hedge logic, signal quality, reliability.

## Module map

**LP Defensor (V2, live — Config 17):** `live_hedge_bot_v2.py`
Arbitrum RPC (`fetch_position_bounds`, 4h idle refresh) + HL REST `all_mids()` poll (30s) → entry triggers (`from_above` / `below_range`) → `open_hedge()` → `market_open` + native HL stop-market SL (+TP) → `manage_active_hedge()` trail via cancel+replace → close via code or native trigger on HL. Supervised by `api/bot_manager.py` (subprocess + stdout `[EVENT]` → `bot_events` → WS).

**Signal Lab (live):** `telegram_listener/listener.py` (Telethon push) → `signal_parser.py` → `signal_events` → `_auto_execute_signal()` → `api/signal_executor.py::place_hl_order` (market entry + native SL + split TPs) → background: breakeven monitor (60s), `api/signal_reconciler.py` (5min), `api/signal_expiry.py` (4h pending expiry). Cron watchdog restarts listener within 60s.

## Key evidence (Config 17, bot_events 2026-04-11 → 2026-06-09)

| Metric | Value |
|---|---|
| hedge_opened | 90 |
| breakeven reached (trade ≥1% in profit, trail armed) | 62 |
| closes caught in-code (sl_hit + trailing_stop) | 6 + 8 |
| closes logged `stopped` / reason `external_close` | **75 / 75 (100%)** |
| circuit_breaker fires | 13 |
| orphan_recovered (restart with open short) | 59 vs only 15 clean starts |
| closes last 30 days | 55 (~1.8/day) |

Native SL/TP triggers on HL always fire before the 30s poll catches the level → virtually **every** close is "external", and all were booked as losses (see H1).

## Findings (prioritized)

### HIGH

**H1 — External closes always counted as losses. ✅ FIXED 2026-06-09**
`live_hedge_bot_v2.py` — `close_hedge` None-branch and `_sync_hl_position` called `_on_stop_event(price)` with `is_win=False` unconditionally, and `_on_stop_event` booked a worst-case `notional × SL_PCT + fees` loss (~$15 at current sizing) per close. With 62/90 trades reaching breakeven, many wins fed the circuit breaker and the -$5 daily cap (one close of ANY kind = paused until UTC midnight → LP unhedged).
*Fix applied:* new `_classify_external_close(sl_oid, tp_oid)` reads `info.user_fills()` since `open_time`, matches buy-back fill OIDs against the native SL/TP order IDs, computes real net P&L (incl. 0.045% taker × 2). `_on_stop_event(price, is_win, pnl_usd)` now uses actual P&L; wins reset the streak AND offset the daily net-loss cap. Fallback to the old conservative estimate if fills can't be read. Orphan recovery now sets `open_time` so recovered positions classify too. Events/emails include `{reason, close_px, pnl_usd, pnl_pct, is_win}`.
*Caveat:* fills are wallet-wide — a manual ETH trade on the same wallet within the window pollutes the weighted close price (see L2).
*Requires bot restart to take effect.*

**H2 — Daily loss cap miscalibrated. ✅ FIXED 2026-06-09**
Flat `-$5` cap vs ~$15 real per-stop loss at 1.5% SL × ~$1k notional → even one genuine stop ended the trading day.
*Fix applied:* `_daily_loss_cap()` — dynamic cap = `DAILY_LOSS_CAP_STOPS` (default 3) × expected single-stop loss at current sizing, $5 magnitude floor; `DAILY_LOSS_CAP_USD` env var overrides with a fixed value. CB event/email now shows net loss vs cap.

**H3 — Transient RPC error kills bot permanently. ✅ FIXED 2026-06-09**
`fetch_position_bounds` did `sys.exit(1)` on any exception (also called from idle-loop refresh). Crash rc=1 → `bot_manager` sets `active=False` → protection silently OFF until manual re-arm.
*Fix applied:* 3 retries with 5s/10s backoff; `fatal=True` only at initial startup; in-loop refresh failure keeps previous bounds and retries in 10 min, logging an `error` event.

**H6 — Trigger orders invisible to `info.open_orders` (found during H2/H3 deploy). ✅ FIXED 2026-06-09**
HL's basic `openOrders` endpoint omits `triggerPx`/`orderType` (verified live: the active SL @ $1670 returned both as `None`); only `frontend_open_orders` includes them. Three code paths filtered on those fields and therefore **never matched any trigger order**:
1. `live_hedge_bot_v2.py::_reconcile_on_startup` — existing SL never found → **duplicate SL placed on every one of the 59 orphan recoveries**.
2. `listener.py::_close_hl_position` — SL/TP never cancelled before market close → orphan reduce-only triggers lingered after close (could close a future position on the same coin unexpectedly).
3. `listener.py::_fetch_orphan_report` — existing SL never detected → emergency SL duplicated it.
*Fix applied:* all three switched to `info.frontend_open_orders`. Note: dashboard HL-position panels (`admin.py:601`, `signal_lab.py:857`) use `limitPx`/`reduceOnly` which ARE present — they work, but display the SL *limit* price (trigger×1.03) instead of the trigger price (e.g., $1720 shown vs $1670 actual) → tracked as **M8**, minor display fix.

**H4 — Naked position if SL placement fails after fill (Signal Lab). ✅ FIXED 2026-06-09**
`signal_executor.py` placed the SL once and never validated the response; a rejected SL was stored silently as `sl_order_id=NULL` (breakeven monitor then skips the row) — naked leveraged position.
*Fix applied:* SL placement verified, retried once; if still failing the entry is market-closed immediately and the failure email (existing path) reports it. Active for auto-execute after listener restart; the **manual** execute path (API) picks it up at the next API restart — bundle with the M1/M2 deploy.

**H5 — SMTP blocks order execution. ✅ FIXED 2026-06-09**
`listener.py::save_signal` awaited the "Nueva señal" email (1–5s SMTP) BEFORE launching `_auto_execute_signal`.
*Fix applied:* auto-execute task launches first; the email is fire-and-forget off the execution path. Per-wallet result emails inside the wallet loop still serialize wallet #2 — that's M4 (gather).

### MEDIUM

- **M1 — 30s REST polling vs WebSocket. ✅ FIXED 2026-06-10.** Bot subscribes to WS `allMids` (sub-second push); main loop ticks every 3s while the feed is fresh, falls back to 30s REST automatically if the WS goes stale (>15s). `USE_WS_PRICE=0` reverts fully; `WS_TICK_SECS` tunes cadence. Status line throttled to 30s and shows the price source (`ws`/`rest`).
- **M2 — 1% slippage tolerance vs 1.5% stop distance. ✅ FIXED 2026-06-10.** Both modules: slippage cap 0.3% (`MAX_SLIPPAGE_PCT` / `SIGNAL_MAX_SLIPPAGE_PCT`) with one re-quote retry on an IOC miss; fill status now actually verified (top-level "ok" ≠ filled). LP bot anchors entry/SL/breakeven on the **actual fill price** instead of the poll price. Signal executor adds a stale-price guard: entry rejected if the mid is already beyond the signal SL or drifted >1% past the signal entry (`SIGNAL_MAX_ENTRY_DRIFT_PCT`).
- **M3 — Auto-execute one-shot.** IOC miss → signal permanently `cancelled` (signal #52). Fix: 2–3 retries with fresh price inside tolerance. ⏳
- **M4 — Redundant REST + serial wallets.** 3 read calls per order (`user_state`, `spot_user_state`, `meta()` — cacheable); wallets execute sequentially. Fix: cache `meta()`, `asyncio.gather` wallets. ⏳
- **M5 — Stats ignore fees + exec params never saved. ✅ FIXED 2026-06-10.** All three P&L calcs (`signal_lab.py::_calc_pnl`, admin monitor exec rows, reconciler emails) now net of HL taker fees (0.045% × 2 round trip, × leverage). Auto-executions record `exec_leverage` + `exec_size_usdt` (actual notional = size × fill) — real $ P&L per trade is now computable. Admin `has_overrides` redefined: ✏️ only when exec leverage ≠ signal leverage.
- **M6 — Standalone update matching.** Non-reply stop/target applies to most recent open signal in thread — can close the wrong trade. Fix: require pair match when present. ⏳
- **M7 — Frequent restarts wipe trail state. ✅ FIXED 2026-06-10.**
  *Persistence:* trail state (`breakeven_reached`, `short_min_price`, `current_sl_price`, `open_time`, BE%) saved atomically to `bot_state/hedge_state_{config}.json` on open/breakeven/trail-move, cleared on close, restored at recovery when entry (±0.1%) and size match the live HL position; `trail_restored` flag added to `orphan_recovered` events.
  *Restart-frequency investigation:* NOT crashes. systemd `NRestarts=0` (zero service crashes); 12 manual deploy restarts + 3 host reboots since Apr 11; per-bot admin restarts (M2-28 endpoint) and dashboard re-arms account for the rest. Recoveries cluster exactly on heavy dev-session days (May 3: 11, May 14: 8, May 31: 6 — all documented work sessions). Conclusion: deploy churn, now harmless with persistence. Recommendation stands: batch deploys, prefer idle windows.

### LOW

- **L1** — Trail cancel+replace on every tick-min, no min-move threshold (brief no-SL window + API churn). ✅ FIXED 2026-06-10 (bundled with M1): replace only when the SL improves ≥0.1%.
- **L2** — `market_close("ETH")` closes the entire wallet ETH position, including manual trades sharing the wallet. Close by recorded size, `reduce_only`.
- **L3** — ATR breakeven includes the in-progress hourly candle (mild repaint). Drop partial candle.
- **L4** — Failed price fetch → syncs run with `price or 0` → `reentry_guard_price=0` on a real close at that moment.
- **L5** — Reconciler/breakeven monitor build a new `Info` client per row; no 429 backoff anywhere (current volume far below HL limits — hygiene only).

## Fee vs IL assessment

~1.8 round-trips/day; 0.09% taker round-trip ≈ $0.9 per ~$1k hedge notional ≈ $27/mo — reasonable insurance on a ~$2k LP. The real cost was the inverse of over-trading: H1/H2 pauses left the LP **unhedged** after the first close of the day. Entry/trail parameters (0.5% offset, 1.5% SL/trail, ATR breakeven) look sane — 62/90 opens reaching breakeven says entry quality is good.

## Restart requirements

| Fixes | Apply via |
|---|---|
| H1 (done), H2, H3, M1, M2-LP, M7, L1–L4 | `live_hedge_bot_v2.py` → **bot restart** (native HL SL persists on-exchange during restart; zero protection gap, only trail state resets if restarted mid-hedge) |
| H4, H5, M3, M4, M6, L5 | listener restart only — LP untouched |
| M5 | API reload (bots respawn; check manual trade on Config 17 wallet first) |

- **M8** — HL position panels show SL/TP *limit* px instead of trigger px (`admin.py`/`signal_lab.py` `_fetch_one`); switch to `frontend_open_orders` and read `triggerPx`. Display-only.

**Recommended order:** H1 ✅ → H2 ✅ → H3 ✅ → H6 ✅ (bot restarted 2026-06-09) → H5 ✅ + H4 ✅ (listener restarted 2026-06-09) → M1 ✅ + M2 ✅ + L1 ✅ (API + listener restarted 2026-06-10) → M5 ✅ + M7 ✅ (API + listener restarted 2026-06-10). Remaining: M3, M4, M6, M8, L2–L5.
