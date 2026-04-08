# VIZNIAGO Whale Intelligence Agent — Architecture & Build Plan
> Feature documentation — v1.0 (2026-03-29)
> Status: **Planning · Not yet implemented**

---

## 1. Overview

The Whale Intelligence Agent is a persistent background service that sits on top of the
existing VIZNIAGO WHALE tracker. While the tracker detects *what* whales are doing right now,
the Intelligence Agent answers *why it matters* — by maintaining a 90-day behavioral history
per wallet, detecting recurrent patterns, and enriching every whale signal with a scored,
classified, human-readable intelligence brief.

**Primary output:** every `whale_new_position` or `whale_flip` signal gains an `intel` block:

```json
{
  "intel": {
    "score": 78,
    "confidence": 65,
    "classification": "accumulate",
    "alert_tier": "HIGH",
    "historical_match": "Wallet opened BTC LONG $210K on 2026-01-14 → +$47K in 3.2h",
    "wallet_win_rate_30d": 0.71,
    "wallet_avg_hold_minutes": 195,
    "patterns_triggered": ["leverage_spike", "historical_edge"],
    "convergence_count": 2
  }
}
```

**No private keys. No trading.** Read-only Hyperliquid Info API only — same as the tracker.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│               whale_intelligence_agent.py                    │
│       (standalone process, independent of bot subprocesses)  │
│                                                              │
│  ┌───────────────┐  ┌───────────────┐  ┌─────────────────┐  │
│  │ HistoryStore  │  │ PatternEngine │  │ SignalEnricher  │  │
│  │ (SQLite TSdb) │  │ (rules +      │  │ (combines       │  │
│  │ fills/90d +   │  │  z-score)     │  │  signal +       │  │
│  │ fingerprints  │  │               │  │  fingerprint +  │  │
│  └──────┬────────┘  └──────┬────────┘  │  patterns)      │  │
│         └──────────────────┴───────────┴────────┬─────────┘  │
│                                                 │             │
│                          ┌──────────────────────▼──────────┐ │
│                          │     IntelligenceEvent            │ │
│                          │  {score, confidence,             │ │
│                          │   classification, alert_tier,    │ │
│                          │   historical_match, patterns}    │ │
│                          └──────────────────────┬──────────┘ │
└─────────────────────────────────────────────────┼────────────┘
                                                  │
                      ┌───────────────────────────▼──────────────┐
                      │   data_cache/whale_intel.db  (SQLite)     │
                      │   intelligence_signals table              │
                      │   polled every 5s by BotManager           │
                      └───────────────────────────┬──────────────┘
                                                  │
                      ┌───────────────────────────▼──────────────┐
                      │   FastAPI  GET /whale/intelligence        │
                      │   WebSocket push → Dashboard intel feed   │
                      └──────────────────────────────────────────┘
```

### Why a separate process

The intelligence agent is stateful (90-day fill history per wallet) and compute-heavier
than the tracker. Running it as an independent process means:
- Tracker crash does not affect intelligence service and vice versa
- Can be restarted or redeployed without API downtime
- Natural scaling path: move to separate machine with no code changes

### Data flow

```
HL /userFills (per wallet)  ──▶  HistoryStore.ingest_fills()
                                        │
                                        ▼
                             whale_fingerprints built/updated
                             (win_rate, avg_hold, preferred_assets…)
                                        │
                        New signal from whale_tracker
                                        │
                                        ▼
                             SignalEnricher.enrich(signal, wallet)
                               ├── PatternEngine.run_detectors()
                               ├── HistoryStore.find_historical_match()
                               └── compute score + confidence
                                        │
                                        ▼
                             intelligence_signals INSERT (consumed=0)
                                        │
                                 BotManager polls (5s)
                                        │
                                        ▼
                             WebSocket push → Dashboard
```

---

## 3. Component Specifications

### 3.1 HistoryStore (`src/whale/history_store.py`)

**Storage:** `data_cache/whale_intel.db` (SQLite, already in `.gitignore` via `data_cache/`)

#### Schema

```sql
-- Rolling 90-day fill history per wallet
CREATE TABLE whale_fills (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    address       TEXT NOT NULL,
    asset         TEXT NOT NULL,
    side          TEXT NOT NULL,          -- LONG | SHORT
    size_usd      REAL NOT NULL,
    entry_px      REAL,
    exit_px       REAL,                   -- NULL until closed
    pnl_usd       REAL,                   -- NULL until closed
    hold_minutes  REAL,                   -- NULL until closed
    ts            TEXT NOT NULL,          -- ISO-8601
    fill_type     TEXT NOT NULL           -- open | close | reduce | flip
);
CREATE INDEX idx_fills_addr_ts ON whale_fills (address, ts DESC);

-- Behavioral fingerprint per wallet, rebuilt on every poll cycle
CREATE TABLE whale_fingerprints (
    address               TEXT PRIMARY KEY,
    updated_at            TEXT NOT NULL,
    win_rate_7d           REAL,
    win_rate_30d          REAL,
    avg_hold_minutes      REAL,
    avg_size_usd          REAL,
    std_size_usd          REAL,
    avg_leverage          REAL,
    preferred_assets      TEXT,           -- JSON array, sorted by frequency
    flip_frequency        REAL,           -- flips per day (last 30d)
    max_drawdown_pct      REAL,
    total_trades_90d      INTEGER,
    p90_size_usd          REAL            -- 90th percentile position size
);

-- Scored intelligence events, consumed by BotManager
CREATE TABLE intelligence_signals (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    address               TEXT NOT NULL,
    asset                 TEXT,
    ts                    TEXT NOT NULL,
    signal_score          INTEGER NOT NULL,   -- 0–100
    confidence            INTEGER NOT NULL,   -- 0–100
    classification        TEXT NOT NULL,      -- accumulate|distribute|hedge|arbitrage|unknown
    alert_tier            TEXT NOT NULL,      -- CRITICAL|HIGH|MEDIUM|LOW
    patterns_triggered    TEXT,              -- JSON array
    historical_match      TEXT,              -- human-readable string or NULL
    enrichment            TEXT,              -- full JSON blob
    consumed              INTEGER DEFAULT 0  -- 0=pending, 1=pushed to WS
);
CREATE INDEX idx_intel_consumed ON intelligence_signals (consumed, ts DESC);
```

#### Key methods

| Method | Description |
|--------|-------------|
| `ingest_fills(address, fills_json)` | Parse HL `/userFills` response, upsert into `whale_fills`, trim to 90 days |
| `build_fingerprint(address)` | Compute all stats from `whale_fills`, upsert into `whale_fingerprints` |
| `get_fingerprint(address)` | Return fingerprint dict or None |
| `find_historical_match(address, asset, side, size_usd)` | Find closest prior trade (same asset+side, size within 50%) and its outcome |
| `pop_unconsumed(limit=20)` | Fetch and mark consumed `intelligence_signals` rows for BotManager |

---

### 3.2 PatternEngine (`src/whale/pattern_engine.py`)

#### Rule-based detectors

| Detector | Trigger condition | Pattern label |
|----------|------------------|---------------|
| **Accumulation burst** | ≥3 opening fills, same asset, within 2h, no closes | `accumulation_burst` |
| **Distribution cascade** | ≥2 reduce/close fills, same asset, within 1h | `distribution_cascade` |
| **Leverage spike** | Current leverage > wallet mean + 2σ | `leverage_spike` |
| **Size anomaly** | Position size > wallet 90th percentile historical size | `size_anomaly` |
| **Pre-flip quiet** | No fills > 4h, then sudden position opposing prior | `reversal_setup` |
| **Repeat winner** | Same asset+side that wallet won ≥70% of last 10 trades | `historical_edge` |
| **Wallet convergence** | ≥3 top-100 wallets open same asset+side within 30 min | `convergence` |
| **Hedged book** | Long + short open simultaneously on different assets | `market_neutral` |

Convergence is cross-wallet and requires the full watched cohort — PatternEngine receives
the full `current_positions` snapshot from the agent loop.

#### Scoring formula

```
z_score    = (current_size_usd - wallet_mean_size) / max(wallet_std_size, 1)
rule_bonus = sum of per-detector weights (leverage_spike=+15, historical_edge=+20,
             accumulation_burst=+10, size_anomaly=+10, convergence=+25)
score      = clamp(50 + z_score*10 + rule_bonus, 0, 100)
confidence = sigmoid(n_historical_trades / 10) * 100
```

`sigmoid(x) = 1 / (1 + exp(-x + 3))` — reaches 50% at 3 trades, 90% at ~10 trades.

#### Classification logic

```
if market_neutral in patterns         → "hedge"
elif accumulation_burst in patterns   → "accumulate"
elif distribution_cascade in patterns → "distribute"
elif size_anomaly and z_score > 2     → "accumulate" (size-driven)
elif reversal_setup in patterns       → "distribute"
else                                  → "unknown"
```

#### Alert tier thresholds

| Tier | Condition | Dashboard treatment |
|------|-----------|---------------------|
| **CRITICAL** | score ≥ 80 AND convergence ≥ 3 AND size > $1M | Red pulsing border |
| **HIGH** | score ≥ 65 OR convergence ≥ 2 | Cyan highlight |
| **MEDIUM** | score 41–64 OR `historical_edge` triggered | Amber badge |
| **LOW** | score ≤ 40 | Gray, no badge |

---

### 3.3 SignalEnricher (`src/whale/signal_enricher.py`)

Orchestrates HistoryStore + PatternEngine and writes the result to `intelligence_signals`.

```python
def enrich(signal: WhaleSignal, fingerprint: dict, all_current_positions: dict) -> dict:
    patterns   = PatternEngine.run_detectors(signal, fingerprint, all_current_positions)
    score, confidence = PatternEngine.compute_score(signal, fingerprint, patterns)
    tier       = PatternEngine.alert_tier(score, patterns)
    cls        = PatternEngine.classify(patterns, score)
    hist_match = HistoryStore.find_historical_match(
                     signal.address, signal.asset, signal.side, signal.size_usd)
    return IntelligenceEvent(
        address=signal.address, asset=signal.asset, ts=signal.ts,
        signal_score=score, confidence=confidence, classification=cls,
        alert_tier=tier, patterns_triggered=patterns,
        historical_match=hist_match, enrichment=signal.to_dict()
    )
```

---

### 3.4 Main agent loop (`whale_intelligence_agent.py`)

```
on startup:
    for each watched_address:
        fills = _hl_post({"type":"userFills","user":address})  # full history
        HistoryStore.ingest_fills(address, fills)
        HistoryStore.build_fingerprint(address)

every POLL_INTERVAL seconds:
    signals = WhaleTracker.poll_all()           # reuse existing tracker
    for signal in signals:
        if signal.event_type in (new_position, flip, size_increase):
            fp = HistoryStore.get_fingerprint(signal.address)
            if fp:
                intel = SignalEnricher.enrich(signal, fp, current_positions)
                HistoryStore.insert_intelligence_signal(intel)

every 3600 seconds:
    rebuild all fingerprints                    # refresh win rates
    trim whale_fills older than 90 days

auto-recovery:
    wraps main loop in try/except with exponential backoff (max 5 min)
    writes heartbeat to data_cache/whale_intel_heartbeat.txt every 60s
```

**Env vars:**

| Var | Default | Description |
|-----|---------|-------------|
| `INTEL_POLL_INTERVAL` | 30 | Seconds between enrichment cycles |
| `INTEL_MIN_SCORE` | 40 | Minimum score to persist intelligence event |
| `INTEL_FILL_HISTORY_DAYS` | 90 | Days of fill history to retain |
| `INTEL_CONVERGENCE_WINDOW_MIN` | 30 | Minutes window for convergence detection |

---

## 4. Files to Create / Modify

### New files

| File | Purpose |
|------|---------|
| `src/whale/history_store.py` | SQLite HistoryStore — fill ingestion, fingerprint builder, signal writer |
| `src/whale/pattern_engine.py` | All rule detectors + z-score scorer + classifier + tier logic |
| `src/whale/signal_enricher.py` | Orchestrates HistoryStore + PatternEngine → IntelligenceEvent |
| `whale_intelligence_agent.py` | Main agent process loop with auto-recovery |
| `migrations/add_whale_intelligence.sql` | Creates `whale_intel.db` schema (SQLite, not MariaDB) |
| `api/routers/whale_intel.py` | `GET /whale/intelligence?limit=&min_score=&asset=&tier=` |

### Modified files

| File | Change |
|------|--------|
| `api/bot_manager.py` | Poll `intelligence_signals` every 5s, push `whale_intel` events via WebSocket |
| `api/models.py` | Add `whale_intel` to `BotEvent.event_type` enum |
| `landing/dashboard/dashboard.js` | Render intel badge in signal rows; convergence panel in whale section |
| `landing/dashboard/dashboard.css` | Score badge styles (tiered colors), convergence panel styles |
| `landing/i18n.js` | Keys for intel panel labels |

---

## 5. Dashboard Signal Row — Enhanced Layout

When an `intel` block is present, the signal card gains a third row:

```
┌─────────────────────────────────────────────────────────────────────┐
│ NEW POSITION   BTC   ▲ LONG   $247,000   @ 95,420   14:32:01       │
│ 20x CROSS   Liq $89,200   Mrg $17,600   ROE +2.1%                  │
│ ⚡ Score 78   65% conf   ACCUMULATE   "Won 7/10 similar BTC longs" │
└─────────────────────────────────────────────────────────────────────┘
```

Score badge color scale:
- 0–40 → gray (LOW)
- 41–65 → amber (MEDIUM)
- 66–80 → cyan (HIGH)
- 81–100 → green pulse (CRITICAL)

### Convergence Panel (new)

A dedicated **Convergence Alerts** card in the whale section shows cross-wallet pile-ins:

```
🐋 CONVERGENCE ALERT — BTC LONG
4 top-100 wallets opened within 17 min · Total $2.1M notional
Wallets: 0x1a2b… (Rank #3) · 0x9f8e… (Rank #7) · 0x4d5e… (Rank #12) · 0x7c8d… (Rank #31)
```

---

## 6. API Endpoint

```http
GET /whale/intelligence?limit=50&min_score=40&asset=BTC&tier=HIGH
Authorization: Bearer <jwt>
```

Response:
```json
{
  "items": [
    {
      "id": 42,
      "address": "0x1a2b3c4d...",
      "asset": "BTC",
      "ts": "2026-03-29T14:32:01Z",
      "signal_score": 78,
      "confidence": 65,
      "classification": "accumulate",
      "alert_tier": "HIGH",
      "patterns_triggered": ["leverage_spike", "historical_edge"],
      "historical_match": "Wallet opened BTC LONG $210K on 2026-01-14 → +$47K in 3.2h",
      "wallet_win_rate_30d": 0.71,
      "wallet_avg_hold_minutes": 195
    }
  ],
  "total": 1
}
```

---

## 7. Build Phases

### Phase 1 — MVP (implement first)

1. `history_store.py` + SQLite schema — fill ingestion + fingerprint builder
2. `pattern_engine.py` — 4 core detectors: `leverage_spike`, `historical_edge`, `convergence`, `accumulation_burst`
3. `signal_enricher.py` + `whale_intelligence_agent.py` main loop
4. `api/routers/whale_intel.py` endpoint
5. Dashboard: intel badge on signal rows (third line)
6. Dashboard: convergence panel

### Phase 2 — Depth (after 30+ days of real data)

- Add remaining detectors: `distribution_cascade`, `reversal_setup`, `market_neutral`
- Backtesting framework: replay 90-day fill history through pattern engine, compare
  predicted classifications vs actual outcomes (win/loss after N hours)
- Telegram CRITICAL tier alerts (reuse supervisor email notifier architecture)
- Persistent watchlist: user-pinned addresses tracked at higher frequency

### Phase 3 — Scale (post-alpha)

- Lightweight ML classifier trained on Phase 2 backtested labels
- Vector similarity search for historical match (replace current range filter)
- Time-of-day signal adjustment (some patterns are more reliable at specific UTC hours)
- Multi-timeframe scoring (15m / 1h / 4h pattern windows)

---

## 8. Open Decisions

| Question | Options | Recommendation |
|----------|---------|---------------|
| Alert delivery | Dashboard-only vs. Telegram for CRITICAL | Add Telegram in Phase 2 — reuse existing supervisor notifier |
| Wallet cohort size | Top 50 (current) vs. Top 100–200 | Use Top 100 for convergence detection; Top 50 for deep fingerprints |
| SQLite vs. MariaDB for intel store | SQLite (simpler, no migration) vs. MariaDB (unified) | SQLite for Phase 1 — MariaDB in Phase 3 when scaling |
| Backtest timing | Build now vs. after data accumulation | Defer full backtest to Phase 2; build the framework in Phase 1 |
| Suppress low-quality wallets | Filter wallets where `accountValue >> totalNtlPos` (market-neutral) | Yes — mark as `hedge` classification, exclude from copy signals |

---

## 9. Known Limitations

- **Cold start:** fingerprints require at least 5–10 historical trades to be meaningful.
  `confidence` field will be low for new wallets until history accumulates.
- **HL fill history depth:** Hyperliquid `/userFills` returns fills as far back as the
  wallet is active, but older fills may have incomplete `pnl` fields.
- **No mempool:** Hyperliquid is its own L1 — no pre-chain signal is possible.
  Fastest signal remains the WebSocket `userFills` subscription at ~100–500ms.
- **Leaderboard churn:** top-100 composition shifts weekly. Fingerprints for wallets
  that drop off the leaderboard should be retained (and still enriched) but not actively
  refreshed unless re-added.
- **Pattern false positives:** rule-based detectors will trigger on noise until tuned
  against real data. The `confidence` score (sigmoid of trade count) is the primary
  guard against acting on thin history.
