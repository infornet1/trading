# VIZNAGO WHALE — Hyperliquid Whale Tracker
> Feature documentation — v1.0 (2026-03-29)
> Status: **Complete · Live in Dashboard + Admin Panel**

---

## 1. Overview

VIZNAGO WHALE is a standalone bot mode that monitors Hyperliquid's top leaderboard traders
and user-specified addresses for large position changes. It detects whale entries, exits,
side flips, and size increases in near real-time, emitting structured signals that appear
live in the dashboard.

Unlike the Defensor Bajista / FURY modes, Whale Tracker requires **no LP position and no
private keys** — it uses Hyperliquid's fully public read-only Info API.

**Primary use case:** identify when a large profitable trader opens or changes a position,
then manually or automatically replicate it at scaled-down size (copy trading).

---

## 2. Architecture

```
[HL Leaderboard API]  ──┐
[HL Info API]           │──▶  WhaleTracker engine   ──▶  [EVENT] JSON lines
[HL WebSocket fills]  ──┘     (src/whale/whale_tracker.py)
                                        │
                                        ▼
                              live_whale_bot.py  (subprocess)
                                        │
                              ┌─────────┴──────────┐
                              ▼                    ▼
                         BotManager          BotEvent DB
                         (pub/sub)           (whale_* events)
                              │
                    ┌─────────┴──────────┐
                    ▼                    ▼
              WebSocket              Dashboard
              (/ws/{id})         whale-signals panel
```

**Two detection modes:**

| Mode | How | Latency | Best for |
|------|-----|---------|----------|
| **Poll** (default) | Snapshots every N seconds, diffs position state | ~30s | Swing trades, position monitoring |
| **WebSocket** (`USE_WEBSOCKET=1`) | Subscribes to `userFills` feed per address | ~100–500ms | Copy-trade signals, scalping follows |

---

## 3. Signal Types

| Event | Description | When to act |
|-------|-------------|-------------|
| `whale_new_position` | Whale opened a new position above min notional | Primary copy-trade trigger |
| `whale_closed` | Whale fully exited a position | Exit your copy if still open |
| `whale_flip` | Whale reversed direction (long → short or vice versa) | High-conviction reversal signal |
| `whale_size_increase` | Whale added ≥10% to an existing position | Optional scale-in signal |
| `whale_size_decrease` | Whale reduced ≥10% of an existing position | Consider partial exit |
| `whale_snapshot` | Periodic top-5 positions summary | Dashboard/monitoring only |
| `oi_spike` | Open Interest jumped ≥3% in one interval | Leading whale accumulation signal |

---

## 4. Files Added / Modified

### New files
| File | Purpose |
|------|---------|
| `src/whale/__init__.py` | Package marker |
| `src/whale/whale_tracker.py` | Core engine: leaderboard fetch, position diffing, OI monitoring, WS subscriptions |
| `live_whale_bot.py` | Subprocess bot — runs as `mode='whale'` config |
| `migrations/add_whale_tracker.sql` | DB migration (columns + enum values + index) |

### Modified files
| File | Change |
|------|--------|
| `api/models.py` | Added `whale` to `mode` Enum; 5 new `whale_*` columns on `BotConfig`; 7 new whale event types on `BotEvent` |
| `api/bot_manager.py` | `WHALE_BOT_SCRIPT` path; whale event map; whale env var injection in `start()` |
| `api/routers/bots.py` | `mode='whale'` validation; whale fields in create/update/start; `GET /{id}/whale-signals` endpoint; no API key required for whale mode |
| `api/routers/admin.py` | `whale_bots` counter in `/admin/overview` stats |
| `landing/dashboard/index.html` | `#whale-section` div |
| `landing/dashboard/dashboard.js` | `saas.whaleSignals` state; whale panel in `renderLiveBots()`; `renderWhaleSection()` with launch form; `launchWhaleBot()`, `stopWhaleBot()`, `restartWhaleBot()`, `deleteWhaleBot()`; `updateWhaleSignalDisplay()` live feed; whale signal seeding from API on load |
| `landing/dashboard/dashboard.css` | `.whale-signal-row`, `.whale-signals-panel`, `.whale-sig-*` styles; whale form styles |
| `landing/admin/index.html` | `🐋 Whale Bots` stat card |
| `landing/admin/admin.js` | Whale bots counter; `🐋 WHALE` mode badge in pool cards |
| `landing/i18n.js` | 7 new `whale.*` keys in ES + EN |

---

## 5. Database Migration

Run once on any new environment:

```bash
mysql -u viznago -p <database> < migrations/add_whale_tracker.sql
```

**What it applies:**
- 5 new columns on `bot_configs`: `whale_top_n`, `whale_min_notional`, `whale_poll_interval`, `whale_custom_addresses`, `whale_watch_assets`
- `whale` added to `mode` ENUM on `bot_configs`
- 7 new values added to `event_type` ENUM on `bot_events`
- Index `idx_bot_events_whale` on `(config_id, event_type, ts DESC)` for the whale-signals endpoint

> **Note:** `paper_trade` column may also need to be added on older installs:
> ```sql
> ALTER TABLE bot_configs ADD COLUMN IF NOT EXISTS paper_trade TINYINT(1) NOT NULL DEFAULT 0;
> ```

---

## 6. Configuration Reference

All parameters are set via the dashboard form or passed as env vars when running directly.

| Parameter | Env var | Default | Description |
|-----------|---------|---------|-------------|
| Leaderboard Top N | `LEADERBOARD_TOP_N` | 50 | How many top HL traders to watch |
| Min Notional USD | `MIN_NOTIONAL_USD` | 50000 | Minimum position size to emit a signal |
| Poll Interval | `POLL_INTERVAL` | 30 | Seconds between full snapshot polls |
| Watch Assets | `WATCH_ASSETS` | *(all)* | Comma-separated filter e.g. `BTC,ETH` |
| Custom Addresses | `CUSTOM_ADDRESSES` | *(none)* | Extra 0x addresses beyond the leaderboard |
| WebSocket mode | `USE_WEBSOCKET` | 0 | `1` = subscribe to `userFills` WS per address |
| OI Spike Threshold | `OI_SPIKE_THRESHOLD` | 0.03 | OI delta % that triggers `oi_spike` event |
| Paper Trade | `PAPER_TRADE` | 0 | `1` = read-only, no trading (always safe for whale mode) |

---

## 7. API Endpoints

### Create a whale bot config
```http
POST /bots
Authorization: Bearer <jwt>

{
  "mode": "whale",
  "chain_id": 42161,
  "nft_token_id": "whale-<timestamp>",
  "pair": "WHALE",
  "lower_bound": 0,
  "upper_bound": 0,
  "whale_top_n": 30,
  "whale_min_notional": 100000,
  "whale_poll_interval": 30,
  "whale_watch_assets": "BTC,ETH",
  "paper_trade": true
}
```

### Start / stop
```http
POST /bots/{id}/start
POST /bots/{id}/stop
```

### Get recent whale signals
```http
GET /bots/{id}/whale-signals?limit=50&asset=BTC&event_type=new_position
```

Returns the last N whale signal events stored in `bot_events`, newest first.
Filterable by `asset` and `event_type` (without the `whale_` prefix).

---

## 8. Copy Trading — Risk Guidelines

Based on research into HL leaderboard behavior (Q1 2026):

### Position sizing
Never copy the whale's raw notional. Apply the same risk framework as FURY:

```
risk_usd        = account_balance × RISK_PCT       # recommend 1% for copy trades
stop_distance   = ATR(14) × 1.5
copy_size_usd   = risk_usd / (stop_distance / entry_price)
```

### Only copy opening fills
The `ws_fill` event (WebSocket mode) includes a `fill_dir` field:
- `"Open Long"` / `"Open Short"` → **copy signal**
- `"Close Long"` / `"Close Short"` → ignore (whale is exiting, not entering)

### Circuit breakers for copy positions
| Condition | Action |
|-----------|--------|
| Whale has 3 consecutive losing trades | Pause copying that address for 24h |
| Copy position open > 8 hours | Force close regardless of P&L |
| Same asset already open in FURY | Reduce copy size 50% (concentration risk) |
| Copy trade lag > 1 second | Skip trade |

### Realistic expectations
- Whale alpha captured after fees and lag: **40–60%** of whale's P&L per trade
- HL taker fee: 0.035% per side → 0.07% round-trip
- Only viable if whale's average hold time > 30 minutes and position size > $500K

---

## 9. Running Directly (without SaaS API)

```bash
# Poll mode (simplest)
POLL_INTERVAL=30 \
MIN_NOTIONAL_USD=100000 \
LEADERBOARD_TOP_N=30 \
WATCH_ASSETS=BTC,ETH \
PAPER_TRADE=1 \
python3 live_whale_bot.py

# WebSocket mode (real-time)
USE_WEBSOCKET=1 \
MIN_NOTIONAL_USD=100000 \
CUSTOM_ADDRESSES=0xABC...,0xDEF... \
PAPER_TRADE=1 \
python3 live_whale_bot.py
```

Signals are printed as `[EVENT] {...}` JSON lines and as human-readable log lines:

```
[WHALE] 🐋 NEW [Rank #3] 0x1a2b3c4d… | BTC LONG $247,000 @ 95,420.00 | 10x | uPnL $0
[WHALE] 🔄 FLIP [Rank #7] 0x9f8e7d6c… | ETH SHORT $180,500 (Δ +$360,000) @ 1,992.40 | 15x
[WHALE] 📈 ADDING [Rank #2] 0x4d5e6f7a… | BTC LONG $310,000 (Δ +$62,000) @ 95,800.00 | 10x
```

---

## 10. Known Limitations

- **Leaderboard lag:** HL leaderboard is updated periodically — top addresses may not reflect intraday leaders. Cross-check with `portfolio` endpoint for recent PnL before trusting a new address.
- **No fill attribution in `trades` feed:** Anonymous fills on the public trades WS cannot be linked to a specific wallet without polling `userFills` separately.
- **Hedged books:** Some top leaderboard wallets run market-neutral strategies (long + short on different sub-accounts). Their directional fills are not true alpha — filter out wallets where `accountValue` >> `totalNtlPos`.
- **WS subscription limit:** Subscribing to too many addresses simultaneously may cause silent drops. Keep `LEADERBOARD_TOP_N` ≤ 50 in WS mode; use poll mode for larger watchlists.
- **Rate limits:** HL REST API throttles at ~1200 req/min per IP. With top_n=50 and poll_interval=30, each cycle makes ~52 requests (1 leaderboard + 1 all_mids + 50 user_state). This is well within limits.
