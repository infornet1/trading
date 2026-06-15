# VIZNIAGO Grid Trading — Product Plan

> New VIZNAGO DeFi mode: automated grid bot on Hyperliquid perpetuals.
> Status: **Preliminary planning** — 2026-06-15

---

## What is Grid Trading?

A grid bot divides a price range into N evenly-spaced levels and maintains a ladder of orders:

- **Buy orders** sit at every level below the current price.
- **Sell orders** sit at every level above the current price.
- When a buy order fills → immediately place a sell one level higher.
- When a sell order fills → immediately place a buy one level lower.
- Profit = the grid spread × number of round trips completed.

On Hyperliquid **perpetuals**, each grid step is a leveraged position open/close cycle, not a spot trade. This amplifies the profit per step — and the risk per step.

---

## How it fits in VIZNAGO

| Mode | Requires LP | Direction | Signal source |
|------|-------------|-----------|---------------|
| Defensor Bajista/Alcista | ✅ Yes | SHORT on down moves | LP range breach |
| FURY | ❌ No | LONG or SHORT | RSI + ATR momentum |
| Whale | ❌ No | Mirrors whale | Leaderboard tracker |
| Signal Lab | ❌ No | Per signal | Telegram channel |
| **Grid** | ❌ No | Both (configurable) | Price ladder — always on |

Grid is fundamentally different from all existing modes: it is **passive and symmetric** — it profits from the market oscillating, not from catching directional moves. It pairs naturally with LP positions (LP earns fees in-range; Grid earns spread on the same oscillations) but can run standalone.

---

## Two operating modes

### Neutral Grid (default)
Balanced buy and sell orders around current price. No net directional exposure when fully deployed. Best for: clearly defined ranging market with bounded volatility.

### Directional Grid (long-bias / short-bias)
Skews the ladder — more orders on one side. A `long_bias` grid places buy levels closer together and sell levels wider, accumulating a net long position if price dips. Useful when you have a view but still want to capture oscillation profit.

---

## Key parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `GRID_SYMBOL` | HL perpetual asset | `ETH` |
| `GRID_LOWER` | Bottom of range | `$1,500` |
| `GRID_UPPER` | Top of range | `$2,500` |
| `GRID_N` | Number of grid levels | `20` |
| `GRID_SIZE_USD` | Notional per grid step | `$15` |
| `GRID_LEVERAGE` | Leverage per order | `3x` |
| `GRID_MODE` | `neutral` / `long_bias` / `short_bias` | `neutral` |
| `GRID_MAX_LOSS_USD` | Circuit breaker — total loss before pause | `$50` |
| `GRID_FUNDING_GATE` | Pause if funding rate > threshold (avoid heavy funding cost) | `0.05%` |

Auto-calculated at start:
- `grid_spacing = (UPPER − LOWER) / N`
- `total_margin = N × GRID_SIZE_USD / GRID_LEVERAGE`

---

## Risk profile

| Risk | Description | Mitigation |
|------|-------------|------------|
| **Trending market** | Price breaks below LOWER or above UPPER — all orders on one side fill, creating a large uncovered position | Circuit breaker (`GRID_MAX_LOSS_USD`) + pause on range break |
| **Funding accumulation** | Open positions on HL accrue funding every 8h. Many levels open = meaningful cost in strong trending markets | `GRID_FUNDING_GATE` pauses grid when funding exceeds threshold |
| **Capital lock** | All N grid levels require margin reserved simultaneously. Thin wallet = fewer active levels | Pre-flight margin check at startup; scales N down if insufficient |
| **HL order limits** | HL has a max open-orders cap per account. Wide grid with many levels can hit it | Enforce `N ≤ 40` hard cap; shared wallet needs headroom for other bot SL/TP orders |
| **Restart gap** | Bot restart during volatile move may miss fills and leave the ladder out of sync | State persistence (JSON) + startup reconciliation against HL open orders |

---

## Technical design

### Fill detection — WebSocket (mandatory)
Grid profitability depends on re-ordering within milliseconds of a fill. REST polling (30s) is too slow — a fast move can skip multiple levels. The bot must subscribe to the HL WebSocket `userFills` or `orderUpdates` stream.

### Order lifecycle
```
Place N/2 buy orders below mid  +  N/2 sell orders above mid
         ↓
WebSocket: fill event received
         ↓
If buy filled at level L  →  close (book profit) + open sell at level L+1
If sell filled at level L →  close (book profit) + open buy at level L-1
         ↓
Repeat indefinitely within range
```

### State persistence
Every fill + reorder is written to a JSON state file (mirroring LP Defensor's `bot_state/`):
```json
{
  "symbol": "ETH",
  "lower": 1500, "upper": 2500, "n": 20, "spacing": 50,
  "active_orders": { "buy": [...OIDs...], "sell": [...OIDs...] },
  "completed_cycles": 42,
  "gross_pnl_usdc": 18.32,
  "funding_paid_usdc": -2.10,
  "net_pnl_usdc": 16.22
}
```

On restart: load state → reconcile against HL open orders → re-place any missing levels.

### BotManager integration
Runs as a subprocess spawned by `BotManager`, mode=`'grid'` in `bot_configs`. New DB columns:
- `grid_lower`, `grid_upper`, `grid_n`, `grid_size_usd`, `grid_mode`, `grid_max_loss`

Bot event types: `grid_cycle_complete` (profit per round trip), `grid_reorder`, `grid_paused` (circuit breaker), `grid_range_break`.

---

## Build phases

| Phase | Description | Effort |
|-------|-------------|--------|
| **0 — Research + backtest** | Backtester: simulate grid on ETH historical OHLCV. Tune: N, spacing, leverage, funding drag. Validate neutral vs directional modes. | 1 week |
| **1 — Grid engine** | `live_grid_bot.py` — startup order placement, WebSocket fill detection, reorder logic, state file. Paper trade first. | 1 week |
| **2 — Resilience** | Restart reconciliation, HL order-limit guard, funding gate, circuit breaker, email alerts on pause/break. | 3 days |
| **3 — BotManager wiring** | `mode='grid'` in API + DB migration, BotManager spawns grid subprocess, admin dashboard grid card. | 3 days |
| **4 — Dashboard UI** | Visual grid overlay: price ladder with buy/sell levels shown as horizontal lines, P&L per level, completed cycles counter, net P&L after funding. | 1 week |
| **5 — Risk controls** | Auto-pause on trend break (price exits range), dynamic range adjustment (shift grid when market drifts), funding threshold gate. | 3 days |
| **6 — SaaS gating** | Grid as a Pro-tier feature: max N, leverage cap, and symbol whitelist enforced per plan. | 1 day |

**Total estimate: ~4 weeks** from Phase 0 to Phase 4 (MVP dashboard).

---

## Open questions before Phase 0

1. **Target asset(s)**: ETH-only first (known range behavior), or multi-asset from the start?
2. **Capital per grid**: the $10 test-notional floor may be too tight for a multi-level grid. Minimum viable wallet size?
3. **Leverage**: higher leverage = more profit per step but larger funding drag on open positions. 3x appears safe for ETH; BTC needs its own calibration.
4. **LP + Grid combo**: does running Grid on the same HL wallet as Defensor create a conflict? (Both manage positions on ETH — need wallet isolation or conflict guard.)
5. **Range selection UX**: manual range entry vs auto-derived from LP bounds vs Claude Vision chart analysis (like the ETH LP Range Advisor)?

---

## Relationship to existing features

- **LP Defensor + Grid (same pool)**: Grid captures the same ETH oscillations the LP earns fees on. Together they could produce a "double yield" — LP fees + grid spread — on the same capital range. Needs conflict-guard analysis (two bots, one wallet vs separate wallets).
- **LP Range Advisor**: the ETH chart analysis already outputs a range (lower/upper/width). That output could pre-fill Grid's `GRID_LOWER` / `GRID_UPPER` parameters automatically.
- **Signal Lab**: fully independent — different order flow, different wallet, no conflict.

---

*Next step: answer the open questions above, then kick off Phase 0 backtesting.*
