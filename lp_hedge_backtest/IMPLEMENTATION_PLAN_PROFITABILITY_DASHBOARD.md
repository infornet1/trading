# Implementation Plan: User Profitability Dashboard

**Status:** D1 + D2 deployed — D3 pending  
**Owner:** TBD  
**Target release:** TBD  
**Last updated:** 2026-07-16

---

## 1. Objective

Transform the VIZNIAGO dashboard from a **bot monitor** into a **performance product** by giving users a unified, time-series view of realized and unrealized P&L across LP Defensor, FURY, Whale Tracker, and Signal Lab.

### Success criteria
- [ ] User can see net realized P&L, unrealized P&L, win rate, profit factor, max drawdown, Sharpe/Sortino, fees, and funding on one screen.
- [ ] User can view an equity curve and drawdown chart for any date range.
- [ ] User can browse a paginated trade journal with entry/exit prices, size, fees, funding, and exit reason.
- [ ] User can export trade history as CSV.
- [ ] Admin can see platform-wide aggregate profitability metrics.

---

## 2. Why now

- The dashboard currently answers *“what is my bot doing?”* but not *“am I making money?”*.
- `BotEvent.pnl` mixes percentages, USD, and unrealized values with inconsistent semantics.
- Realized P&L, IL attribution, fees, and funding are buried inside `BotEvent.details` JSON.
- `src/reporting/metrics.py` already computes Sharpe/Sortino/drawdown for backtests but is not wired to live data.
- Signal Lab P&L is estimated from signal levels, not actual Hyperliquid fills.
- A profitability dashboard reduces churn and supports paid-tier conversion.

---

## 3. Current state

### Data model
| Table | Relevant fields | P&L support today |
|---|---|---|
| `User` | `address`, `plan`, `created_at`, `last_seen` | None |
| `BotConfig` | pool config, mode, leverage | No capital or cost basis |
| `BotEvent` | `event_type`, `price_at_event`, `pnl`, `details` | Single nullable `pnl`; semantics differ by mode; IL attr in JSON |
| `Subscription` | `amount_usdc`, `active_until` | Cost stored, not joined to profit |
| `SignalExecution` | `fill_price`, `close_price`, `exec_size_usdt`, `outcome` | `close_price` rarely populated; no `realized_pnl_usd` |

### Existing endpoints
- `GET /bots/{id}/events` — raw events, no aggregation.
- `GET /bots/{id}/status` — last event only.
- `GET /bots/{id}/hl-position` — live unrealized P&L.
- `GET /signal-lab/history` — estimated P&L, win rate on signals.
- `GET /admin/overview` — platform ops stats, no profitability.

### Frontend
- `landing/dashboard/index.html` + `dashboard.js` are vanilla JS.
- No chart library loaded.
- Tabs: **Activas / Historial**.
- Per-event P&L shown in log, no aggregate view.

---

## 4. Proposed solution

Build a new **Performance / Rendimiento** tab in the dashboard backed by:
1. A normalized `bot_trades` table built from closed `BotEvent` pairs.
2. A `wallet_snapshots` table for equity-curve time series.
3. New `/performance/*` API endpoints.
4. A lightweight charting library and new frontend section.

---

## 5. Implementation phases

### Phase 1 — Data foundation (estimated 1–2 days)

#### 5.1.1 Schema additions
- [ ] Add `BotTrade` model to `api/models.py`.
- [ ] Add `WalletSnapshot` model to `api/models.py`.
- [ ] Extend `SignalExecution` with `realized_pnl_usd`, `fees_usd`, `closed_at`, `exit_reason`.
- [ ] Create Alembic migration or update `api/main.py` startup schema to add new tables/columns.

```python
# api/models.py — proposed additions

class BotTrade(Base):
    __tablename__ = "bot_trades"
    id = Column(Integer, primary_key=True)
    config_id = Column(Integer, ForeignKey("bot_configs.id"), index=True)
    user_address = Column(String(42), index=True)
    mode = Column(String(20))          # aragan, avaro, fury, whale
    pair = Column(String(20))
    side = Column(String(10))          # short / long
    entry_price = Column(Numeric(20, 8))
    exit_price = Column(Numeric(20, 8))
    size_usd = Column(Numeric(20, 4))
    realized_pnl_usd = Column(Numeric(20, 4))
    fees_usd = Column(Numeric(20, 4))
    funding_usd = Column(Numeric(20, 4))
    il_offset_usd = Column(Numeric(20, 4))
    net_pnl_usd = Column(Numeric(20, 4))
    exit_reason = Column(String(30))
    opened_at = Column(DateTime)
    closed_at = Column(DateTime)

class WalletSnapshot(Base):
    __tablename__ = "wallet_snapshots"
    id = Column(Integer, primary_key=True)
    user_address = Column(String(42), index=True)
    wallet_addr = Column(String(42), index=True)
    source = Column(String(20))        # bot, signal_lab
    balance_usdc = Column(Numeric(20, 4))
    margin_used_usdc = Column(Numeric(20, 4))
    snapshot_at = Column(DateTime, index=True)
```

#### 5.1.2 Backfill `bot_trades` from existing events
- [ ] Write a one-off backfill script (e.g. `scripts/backfill_bot_trades.py`).  *(deferred to D3)*
- [ ] Pair `hedge_opened` events with `tp_hit` / `sl_hit` / `trailing_stop` / `hedge_closed` events per `config_id`.
- [ ] Extract from `details` JSON: `entry_price`, `exit_price`, `size`, `fees`, `funding`, `lp_chg_pct`, `hedge_offset_pct`, `net_pct`.
- [ ] Insert one `BotTrade` row per closed round-trip.
- [ ] Flag rows with incomplete data (`is_estimate = True`) for transparency.

#### 5.1.3 Real-time trade recorder
- [x] Update `api/bot_manager.py` event parser to upsert `BotTrade` rows when close events are received.
- [ ] Keep backfill script idempotent so it can be re-run safely.

#### 5.1.4 Wallet snapshot background task
- [ ] Add a background task in `api/main.py` (or `api/performance_worker.py`) running every 15 minutes.
- [ ] For each active bot config, fetch HL `user_state` and store `account_value`, `total_margin_used`.
- [ ] For each Signal Lab registered wallet, do the same.
- [ ] Store snapshot with `user_address`, `wallet_addr`, `source`, `snapshot_at`.

---

### Phase 2 — API endpoints (estimated 1–2 days)

Create a new router `api/routers/performance.py` and register it in `api/main.py`.

| Endpoint | Status |
|---|---|
| `GET /performance/summary?from=&to=` | ✅ Implemented |
| `GET /performance/equity-curve?from=&to=&granularity=day` | ✅ Implemented |
| `GET /performance/trades?from=&to=&limit=100&offset=0` | ✅ Implemented |
| `GET /performance/breakdown?by=pair\|mode\|month` | ✅ Implemented |
| `GET /performance/export?format=csv&from=&to=` | ✅ Implemented |

#### 5.2.1 `GET /performance/summary`
Return:
```json
{
  "net_realized_pnl_usd": "1234.56",
  "unrealized_pnl_usd": "-234.50",
  "total_return_pct": "8.45",
  "win_rate_pct": "62.5",
  "profit_factor": "1.84",
  "max_drawdown_pct": "-5.20",
  "sharpe_ratio": "1.12",
  "sortino_ratio": "1.65",
  "total_fees_usd": "345.00",
  "total_funding_usd": "-123.00",
  "subscription_cost_usd": "199.00",
  "total_trades": 48,
  "winning_trades": 30,
  "losing_trades": 18
}
```

#### 5.2.2 `GET /performance/equity-curve`
Return:
```json
[
  {"ts": "2026-07-01T00:00:00", "equity": "14500.00", "drawdown_pct": "0.00"},
  {"ts": "2026-07-02T00:00:00", "equity": "14750.00", "drawdown_pct": "0.00"},
  ...
]
```

#### 5.2.3 `GET /performance/trades`
Return paginated `BotTrade` rows plus normalized Signal Lab rows.

#### 5.2.4 `GET /performance/breakdown`
Support `by=bot`, `by=pair`, `by=month`, `by=product`.

#### 5.2.5 `GET /performance/export`
Generate CSV in-memory and stream the response.

#### 5.2.6 Aggregation implementation notes
- Use `WalletSnapshot` to build equity curve and drawdown.
- `src/reporting/metrics.py::calculate_metrics()` to be wired in D3 for Sharpe/Sortino.
- Win rate = count(`realized_pnl_usd > 0`) / total closed trades.
- Profit factor = sum(gains) / abs(sum(losses)).
- Unrealized P&L = sum of live HL positions from existing endpoints.
- Capital deployed = earliest `WalletSnapshot.balance_usdc` or user-configured tracked capital.

---

### Phase 3 — Signal Lab realized P&L fix (deferred to D3)

- [ ] Update `api/signal_reconciler.py` or signal executor to fetch actual HL fills via `user_fills()` when a signal closes.
- [ ] Populate `SignalExecution.close_price`, `realized_pnl_usd`, `fees_usd`, `closed_at`, `exit_reason`.
- [ ] Until fills are available, dashboard shows "estimated" badge for signal P&L.

---

### Phase 4 — Frontend MVP (estimated 2–3 days)

#### 5.4.1 Dashboard tab (D2 done — D3 will wire data)
- [x] Add **Rendimiento / Performance** tab in `landing/dashboard/index.html` (hidden behind flag).
- [x] Load chart library via CDN (Lightweight Charts™).
- [ ] Render KPI cards, equity curve, drawdown, breakdown tables, trade journal.
- [ ] Wire API calls in `landing/dashboard/profitability.js`.
- [ ] Enable tab when `PERFORMANCE_DASHBOARD_ENABLED=true`.

#### 5.4.2 New JS module
- [ ] Create `landing/dashboard/profitability.js` with functions:
  - `loadProfitSummary(from, to)`
  - `loadEquityCurve(from, to, granularity)`
  - `loadTradeJournal(page, limit)`
  - `loadBreakdown(by)`
  - `exportCSV()`
  - `renderSummaryCards(data)`
  - `renderEquityChart(series)`
  - `renderDrawdownChart(series)`
  - `renderTradeTable(trades)`

#### 5.4.3 UI layout
```
[Rendimiento tab]
├── Date range picker
├── KPI grid (6 cards)
├── Equity curve chart
├── Drawdown chart + Monthly P&L bar chart
├── Breakdown tabs: [By Bot] [By Pair] [By Month] [By Product]
└── Trade journal table with [Export CSV]
```

#### 5.4.4 Styles
- [ ] Add KPI, chart container, and trade-table styles to `landing/dashboard/dashboard.css`.
- [ ] Reuse existing color variables from `landing/global.css`.

#### 5.4.5 i18n
- [ ] Add translation keys to `landing/i18n.js` for both `es` and `en`:
  - `performance`, `netRealizedPnl`, `unrealizedPnl`, `totalReturn`, `winRate`, `profitFactor`, `maxDrawdown`, `sharpeRatio`, `sortinoRatio`, `feesPaid`, `fundingPaid`, `subscriptionCost`, `tradeJournal`, `exportCsv`, `dataEstimated`.

---

### Phase 5 — Admin view (estimated 0.5–1 day)

- [ ] Extend `GET /admin/overview` or add `GET /admin/performance`.
- [ ] Return platform-wide aggregate: total realized P&L, total AUM, active bots, win rate, top pairs.
- [ ] Useful for investor updates and internal monitoring.

---

### Phase 6 — Testing & rollout (estimated 1–2 days)

- [ ] Write unit tests for aggregation functions.
- [ ] Seed test `BotEvent` rows and verify backfill script output.
- [ ] Test new endpoints with FastAPI `TestClient`.
- [ ] Test frontend on desktop and mobile.
- [ ] Run backfill on a copy of production data and validate totals.
- [ ] Deploy behind feature flag or to a staging environment first.
- [ ] Announce to users with in-dashboard tooltip.

---

## 6. Files to modify

| File | Change |
|---|---|
| `api/models.py` | Add `BotTrade`, `WalletSnapshot`; extend `SignalExecution` |
| `api/database.py` | Ensure new tables are created (or add Alembic migration) |
| `api/main.py` | Register new router; add wallet snapshot background task |
| `api/routers/performance.py` | New performance endpoints |
| `api/bot_manager.py` | Write `BotTrade` rows on close events |
| `api/signal_reconciler.py` | Populate realized P&L on signal close |
| `src/reporting/metrics.py` | Reuse for risk metrics |
| `scripts/backfill_bot_trades.py` | One-off backfill script |
| `landing/dashboard/index.html` | Add Performance tab and chart library CDN |
| `landing/dashboard/dashboard.js` | Tab wiring and state |
| `landing/dashboard/profitability.js` | New module |
| `landing/dashboard/dashboard.css` | New styles |
| `landing/i18n.js` | New translation keys |
| `api/routers/admin.py` | Optional admin aggregate view |

---

## 7. Open questions

1. **Capital definition.** Should total return % use earliest wallet balance, peak balance, or user-configured tracked capital?
2. **Backfill scope.** How far back should we backfill? All historical `BotEvent` rows or only from a cutoff date?
3. **Data estimates.** Should the dashboard show an "estimated" badge when `close_price` is missing or `details` JSON is incomplete?
4. **Multi-wallet users.** Should the default view aggregate all user wallets or default to a primary wallet?
5. **Feature flag.** Should this be released to a beta group first?
6. **Caching.** Should summary endpoints be cached for 1–5 minutes to protect the DB?

---

## 8. Acceptance checklist

- [ ] New tables exist and are populated.
- [ ] Backfill script runs successfully and is idempotent.
- [ ] `/performance/summary` returns accurate KPIs for a test user.
- [ ] Equity curve chart renders correctly with date range filter.
- [ ] Trade journal shows paginated closed trades with correct P&L, fees, funding.
- [ ] CSV export works and matches the table view.
- [ ] i18n labels display in Spanish and English.
- [ ] Mobile layout is usable.
- [ ] Admin aggregate view is available.
- [ ] No regressions in existing dashboard tabs.

---

## 9. Notes

- This plan intentionally avoids changing existing live bot logic beyond adding event-persistence hooks; the main bot behavior remains unchanged.
- The dashboard should default to showing **realized P&L** as the primary number to avoid misleading users with volatile unrealized marks.
- Signal Lab estimated P&L should be clearly labeled until actual fills are integrated.
