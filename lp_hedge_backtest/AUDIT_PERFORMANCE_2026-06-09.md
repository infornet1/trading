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

**H2 — Daily loss cap miscalibrated.** `_DAILY_LOSS_CAP_USD = -5.00` vs ~$15 real per-stop loss at 1.5% SL × ~$1k notional → even one genuine stop ends the trading day. Fix: scale cap to sizing (e.g., 3× expected per-stop loss) or per-config param. ⏳ Pending.

**H3 — Transient RPC error kills bot permanently.** `fetch_position_bounds` does `sys.exit(1)` on any exception (also called from idle-loop refresh). Crash rc=1 → `bot_manager` sets `active=False` → protection silently OFF until manual re-arm. Fix: retry with backoff; only exit at initial startup; in-loop keep old bounds. ⏳ Pending.

**H4 — Naked position if SL placement fails after fill (Signal Lab).** `signal_executor.py:174-179` places SL once, never validates the response; `sl_order_id=NULL` stored silently, breakeven monitor skips the row. Fix: validate, retry once, else market-close entry + loud alert. ⏳ Pending.

**H5 — SMTP blocks order execution.** `listener.py::save_signal` awaits the "Nueva señal" email (1–5s) BEFORE `create_task(_auto_execute_signal)`. Fix: launch execute task first, email in background. ⏳ Pending.

### MEDIUM

- **M1 — 30s REST polling vs WebSocket.** `all_mids()` poll; entries/trail react up to 30s late. Native SL covers downside. Fix: `Info` WS `allMids` subscription. ⏳
- **M2 — 1% slippage tolerance vs 1.5% stop distance.** `market_open(slippage=0.01)` both modules; no stale-price check before sending. Fix: 0.3% + one re-quote retry; skip if price already past SL. ⏳
- **M3 — Auto-execute one-shot.** IOC miss → signal permanently `cancelled` (signal #52). Fix: 2–3 retries with fresh price inside tolerance. ⏳
- **M4 — Redundant REST + serial wallets.** 3 read calls per order (`user_state`, `spot_user_state`, `meta()` — cacheable); wallets execute sequentially. Fix: cache `meta()`, `asyncio.gather` wallets. ⏳
- **M5 — Stats ignore fees/funding.** `signal_lab.py::_calc_pnl` = raw × leverage, idealized fallback to signal levels; source win-rates are gross. Also `exec_leverage`/`exec_size_usdt` never saved. ⏳
- **M6 — Standalone update matching.** Non-reply stop/target applies to most recent open signal in thread — can close the wrong trade. Fix: require pair match when present. ⏳
- **M7 — Frequent restarts wipe trail state.** 59 orphan recoveries vs 15 starts; recovery resets `breakeven_reached`/`short_min_price` (native SL order survives). Fix: persist trail state; investigate restart frequency. ⏳

### LOW

- **L1** — Trail cancel+replace on every tick-min, no min-move threshold (brief no-SL window + API churn). Gate at ≥0.1% SL move.
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

**Recommended order:** H1 ✅ → H2 → H3 → H5 + H4 → M1/M2.
