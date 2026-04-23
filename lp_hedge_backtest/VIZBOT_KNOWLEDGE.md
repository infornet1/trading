# VIZBOT Knowledge Base — Platform Features & Bot Internals
# Auto-loaded by the AI assistant. Keep up to date with each release.
# Last updated: 2026-04-23 (M2-39 bug fix: external_close path now counts toward circuit breaker)

---

## Bot Engines: V1 vs V2

### V1 Engine (live_hedge_bot.py)
- Stop-loss is evaluated **in software**: the bot polls price every ~30s and calls `market_close()` when SL is breached.
- Risk: if the bot process crashes while a hedge is open, there is NO protection — the short stays open unmanaged until manually closed.
- Identified by a **V1 (grey badge)** on the admin dashboard bot card.

### V2 Engine (live_hedge_bot_v2.py)
- **Native SL**: placed as a standalone trigger order on HL (`tpsl="sl"`, `grouping="na"`) immediately after every hedge opens. Triggers even if bot process is dead. Uses whole-dollar rounding; `limit_px = trigger * 1.03` (3% above, ensures fill).
- **Native TP**: placed as a standalone trigger order on HL (`tpsl="tp"`, `grouping="na"`) at open when `TP_PCT` is configured. `limit_px = trigger * 0.97` (3% below, buys back at discount). Both native orders are cancelled before any code-path market close to prevent double-fill. **Live-validated 2026-04-22:** Config 20 `hedge_opened` at 13:48 UTC confirmed `tp_oid: 392796553319` in event details.
- Includes **crash recovery**: on startup the bot checks for any open position on the HL wallet. If found, it re-adopts it — sets `hedge_active=True`, finds existing native SL/TP orders or places fresh ones, and continues monitoring.
- Includes **LP reconciler**: a background job runs hourly to verify each Uniswap V3 NFT still has liquidity. If LP was removed or NFT burned while the bot was stopped, the reconciler marks the config `inactive` in DB, logs an event, stops the process, and emails the admin.
- **Circuit breaker (M2-39)**: after 3 consecutive SL-type closes, re-entry is paused for 20 min. Counter increments on `sl_hit`, `trailing_stop`, **and `external_close`** (native HL trigger fired before software poll — the most common SL path). Resets on `tp_hit`. Fires a `circuit_breaker` DB event and email. Status line shows `🔴 CIRCUIT BREAKER (Xs)`. Bug fixed 2026-04-23: original code missed the external_close paths.
- **External-close cooldown (M2-40)**: when native SL fires on HL between polls (`external_close`), a 5-min cooldown blocks re-entry before the reentry guard logic runs. Prevents immediate re-entry into the same choppy conditions. Status line shows `⏸️ EXT COOLDOWN (Xs)`. **Live-validated 2026-04-22:** native SL fired at 13:57 UTC on Config 20; `stopped` event logged with `cooldown: 300`; reentry guard cleared 31s later but cooldown held until 14:02:46 UTC.
- Identified by a **V2 (green badge)** on the admin dashboard bot card.
- Native SL uses a 1-second settle delay after market open to allow HL to register the fill before the SL order is submitted.

---

## Bot Modes

### LP Defensor — Alcista (Aragan / Avaro)
- Monitors a Uniswap V3 LP position (identified by NFT token ID).
- When ETH price falls **from above** into the configured trigger range, the bot opens a SHORT on Hyperliquid to hedge impermanent loss.
- When price recovers above the upper trigger or hits TP/SL/trailing stop, the hedge is closed.
- Parameters: hedge_ratio (% of LP notional to hedge), leverage (1–20x), SL%, TP%, trailing stop, auto-rearm.
- Current active mode only: **from_above** (Alcista). Bajista (from_below) mode is disabled — coming soon.

### FURY Mode (live_fury_bot.py)
- Standalone RSI + ATR momentum bot. Does NOT require an LP position.
- Trades ETH (or any configured symbol) on Hyperliquid based on RSI crossovers with multi-timeframe gates.
- Entry conditions: RSI(9) crosses below long threshold (default 35) = LONG; crosses above short threshold (default 65) = SHORT. Minimum 3 gates must align.
- SL set via ATR multiplier (default 1.5×ATR). TP set as a risk-reward multiple of the SL distance.
- Has circuit breaker: after N consecutive losses in a session, halts trading for the day.
- **Backtest results: ETH ✅ (profitable, paper trading live). BTC ❌ (do not deploy).**
- Supports paper trade mode (no real orders, simulated balance).

### Whale Tracker Mode (live_whale_bot.py)
- Reads Hyperliquid leaderboard top-N traders (default 50) every poll interval (default 30s).
- Tracks position changes: new positions, size increases/decreases, flips, closures.
- Filters by minimum notional size (default $50,000 USD).
- Can also track specific wallet addresses (CUSTOM_ADDRESSES).
- Can filter by specific assets (WATCH_ASSETS).
- Signals are displayed on the Whale Signals panel (public endpoint: `/bots/public-whale-signals`).
- Resource footprint: ~2.2% CPU + ~87 MB RAM per whale bot process.
- Admin can pause/resume all whale bots via the **⏸ Pausar Whales / ▶ Activar Whales** button in the Whale Tracker section of the admin dashboard. This frees ~6.6% CPU + ~261 MB RAM.

---

## Reentry Guard (M2-23)

After a hedge is closed by SL (sl_hit) or trailing stop (trailing_stop):
- A **reentry guard** is set at the SL-close price to prevent immediately re-entering a trade on a whipsaw bounce.
- The guard price is shown as a **🔒 $X amber pill** on the idle bot card in the admin dashboard.

**Guard is cleared (bot re-arms) under TWO conditions:**
1. **Price goes above the guard price** — the price bounced back above where the SL fired, safe to re-arm from above.
2. **Price drops below the SL-close price** — price continued falling past the SL level (downside move confirmed, not a whipsaw). Bot re-arms safely in this scenario too.

This two-condition logic (added M2-23, 2026-04-17) prevents a 1-hour+ exposure window that existed when price stayed between trigger and guard after an SL hit.

---

## Bot Events — What They Mean

| Event | Meaning |
|-------|---------|
| `started` | Bot process launched, LP position synced from chain |
| `hedge_opened` | SHORT opened on Hyperliquid. Details: entry price, SL, size, leverage |
| `breakeven` | SL moved to breakeven level (entry price) |
| `sl_hit` | Native or software SL triggered — hedge closed. Reentry guard set |
| `trailing_stop` | Trailing stop fired — hedge closed with profit. Reentry guard set |
| `tp_hit` | Take profit hit — hedge closed at full profit target |
| `reentry_guard_cleared` | Reentry guard lifted — bot is re-armed and watching for next entry |
| `stopped` | Hedge stopped. Details `reason` field distinguishes: `"manual"` = clean API shutdown; `"external_close"` = HL position disappeared (native SL fired or manual close on HL); `"auto_rearm_disabled"` = hedge closed and AUTO_REARM=off. Process stays alive for `external_close` if AUTO_REARM=on. |
| `error` | Non-fatal error — details in event. Bot continues running |
| `lp_removed` | LP reconciler detected liquidity = 0 on the NFT. Bot stopped, config marked inactive |
| `lp_burned` | LP reconciler detected NFT was burned. Bot stopped, config marked inactive |
| `orphan_recovered` | Bot found an open position on startup (crash recovery) — re-adopted it |
| `fury_entry` | FURY bot opened a position (RSI signal) |
| `fury_sl` | FURY bot hit stop-loss |
| `fury_tp` | FURY bot hit take profit |
| `fury_circuit_breaker` | FURY bot halted for the day after too many consecutive losses |
| `whale_new_position` | Whale tracker detected a new position from a tracked wallet |
| `whale_closed` | A tracked whale closed their position |
| `whale_size_increase` | A tracked whale increased position size |
| `whale_size_decrease` | A tracked whale reduced position size |
| `whale_flip` | A tracked whale flipped direction (long→short or short→long) |
| `whale_snapshot` | Periodic snapshot of all tracked whale positions |

---

## Bot Parameters Reference

### LP Hedge V1 & V2 (live_hedge_bot.py / live_hedge_bot_v2.py)
| Parameter | Env var | Default | Description |
|-----------|---------|---------|-------------|
| NFT token ID | UNISWAP_NFT_ID | — | Uniswap V3 LP position to hedge |
| Check interval | CHECK_INTERVAL | 30s | How often bot polls price |
| Trigger offset | TRIGGER_OFFSET_PCT | 0.5% | Extra buffer inside range before opening hedge |
| Hedge ratio | HEDGE_RATIO | 50% | % of LP notional to hedge on Hyperliquid |
| Leverage | TARGET_LEVERAGE | 10× | Leverage for hedge SHORT |
| Stop-loss | SL_PCT | 0.5% | % above entry price to close hedge at loss |
| Breakeven | BREAKEVEN_PCT | 1.0% | Move SL to entry when hedge profit reaches this % |
| Trailing stop | TRAIL_PCT | 1.5% | Trailing stop distance once breakeven is hit |
| Reentry buffer | REENTRY_BUFFER_PCT | 0.5% | Extra buffer above trigger to re-arm after guard clears |
| Take profit | TP_PCT | (none) | Optional fixed TP % from entry |
| Trailing stop on/off | TRAILING_STOP | on | Enable trailing stop after breakeven |
| Auto rearm | AUTO_REARM | on | Automatically re-arm after hedge closes |

### FURY Bot (live_fury_bot.py)
| Parameter | Env var | Default | Description |
|-----------|---------|---------|-------------|
| Symbol | FURY_SYMBOL | ETH | Asset to trade on Hyperliquid |
| RSI period | FURY_RSI_PERIOD | 9 | RSI lookback period |
| RSI long threshold | FURY_RSI_LONG_TH | 35 | RSI below this = LONG signal |
| RSI short threshold | FURY_RSI_SHORT_TH | 65 | RSI above this = SHORT signal |
| ATR period | FURY_ATR_PERIOD | 12 | ATR lookback for SL sizing |
| ATR multiplier | FURY_ATR_MULT | 1.5× | SL = ATR × this multiplier |
| Max leverage | FURY_LEVERAGE_MAX | 12× | Maximum leverage for entries |
| Risk per trade | FURY_RISK_PCT | 2.0% | % of balance to risk per trade |
| Min gates | FURY_MIN_GATES | 3 | Minimum timeframe confirmations required |
| Check interval | CHECK_INTERVAL | 60s | How often bot checks for signals |

### Whale Tracker Bot (live_whale_bot.py)
| Parameter | Env var | Default | Description |
|-----------|---------|---------|-------------|
| Top N traders | LEADERBOARD_TOP_N | 50 | How many leaderboard positions to track |
| Min notional | MIN_NOTIONAL_USD | $50,000 | Ignore positions smaller than this |
| Poll interval | POLL_INTERVAL | 30s | How often to fetch leaderboard data |
| Custom addresses | CUSTOM_ADDRESSES | (none) | Comma-separated wallets to always track |
| Watch assets | WATCH_ASSETS | (none) | Only show signals for these assets |
| WebSocket mode | USE_WEBSOCKET | off | Use WebSocket feed instead of polling |
| OI spike threshold | OI_SPIKE_THRESHOLD | 3% | Alert threshold for open interest spike |

---

## Admin Dashboard Features (2026-04-17)

- **V1/V2 engine badge**: each bot card shows a green V2 or grey V1 badge derived from the `started` event details.
- **🔒 Reentry guard pill**: when a bot's hedge was recently closed and the guard is active, an amber pill shows the guard price on the idle card.
- **LP Hedge / Whale Tracker sections**: bot cards are split into two independent sections. LP bots always shown first. Each section has its own Running/Stopped collapsible subsection.
- **⏸ Pausar Whales / ▶ Activar Whales button**: in the Whale Tracker section header. Stops or starts all whale bot processes. Freed resources: ~6.6% CPU + ~261 MB RAM.
- **Per-event labels**: all event types have human-readable labels and color-coded icons in the event history timeline.

---

## LP Reconciler (Background Job)

Runs every hour as an asyncio background task inside the API process.

- Scans all `active=True` aragan/avaro bot configs.
- For each config, reads the Uniswap V3 NFT on-chain to check liquidity.
- **If liquidity = 0** (LP removed): logs `lp_removed` event, stops bot process, marks config `active=False`, emails admin.
- **If NFT burned**: logs `lp_burned` event, same response.
- Purpose: catches LP removals that happen while the bot process is stopped (the bot itself can only detect this while running).

---

## Platform Principles

- **No silent overrides**: VIZNIAGO never adjusts user config parameters in the background. If a value is out of recommended range, the UI shows a warning — the user decides. (e.g. SL < 0.5% shows a warning but is allowed.)
- **Alpha status**: platform is in active development. Some features are marked "Próximamente" (coming soon).
- **Admin-only endpoints**: `/admin/*` routes require wallet-based auth with an admin wallet address.
