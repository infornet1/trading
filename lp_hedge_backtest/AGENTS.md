# AGENTS.md — VIZNIAGO.finance

Concise context for AI coding agents working on this repository.

---

## 1. Project overview

**VIZNIAGO.finance** is a DeFi SaaS that protects Uniswap v3 concentrated-liquidity positions by automatically hedging with Hyperliquid perpetual futures. It also runs standalone trading bots (FURY RSI, Whale Tracker) and a Signal Lab that copy-trades Telegram signals.

| Component | Location |
|---|---|
| Backtesting engine | `src/` |
| Live trading bots | `live_hedge_bot*.py`, `live_fury_bot.py`, `live_whale_bot.py` |
| FastAPI SaaS backend | `api/` |
| Static frontend | `landing/` |
| Telegram signal listener | `telegram_listener/` |
| DB migrations | `migrations/alembic/` (new) + inline migrations in `api/main.py` (legacy) |

Production API runs as systemd service `viznago_api` on `127.0.0.1:8001`, proxied by nginx at `https://dev.ueipab.edu.ve/trading/lp-hedge/api/`.

Dashboard URL: `https://dev.ueipab.edu.ve/trading/lp-hedge/dashboard/index.html`

---

## 2. Tech stack

- **Python 3.14** (venv at `./venv/`)
- **FastAPI** + **Pydantic v2** + **SQLAlchemy 2.x async** (`aiomysql`)
- **MariaDB** (`viznago_dev` / `viznago_prod`)
- **Hyperliquid Python SDK** for perps
- **Telethon** for Telegram MTProto
- **ethers.js** for frontend wallet + on-chain reads
- **Alembic** for DB migrations (introduced 2026-07-16)

---

## 3. Repository conventions

### Branching
- Default branch: `master`
- Feature work: create `feature/<name>` branches
- Tag baseline before risky deploys: `git tag -a pre-<feature> -m "..."`
  - Example baseline tag in this repo: `pre-profitability-dashboard`

### Commits
- Prefix commits logically: `feat(...)`, `fix(...)`, `docs(...)`, `refactor(...)`
- Keep commits atomic and small

### Code style
- Existing code mixes Spanish/English. Prefer English for new code; keep user-facing i18n strings bilingual via `landing/i18n.js`.
- Avoid bare `except Exception: pass`. Log or re-raise typed errors.
- Do not commit secrets, `.env` files, or local state (`bot_state/`, `backups/`, `data_cache/`).
  - `backups/` is already in `.gitignore`.

### DB changes
- **Use Alembic** for schema changes. See `migrations/alembic/`.
- Keep migrations additive and backward-compatible when live bots are running.
- Always backup the DB before running migrations: `mysqldump -u viznago -p<pass> viznago_dev > backups/...`
- Sync URL for Alembic: env var `DB_URL` is coerced from `mysql+aiomysql` → `mysql+pymysql` in `migrations/alembic/env.py`.

---

## 4. Key architectural rules

### Live trading safety
- Real HL positions are open. Any API restart kills and respawns bot subprocesses.
- Bot state is file-persisted in `bot_state/hedge_state_{config_id}.json`.
- Never modify `live_hedge_bot_v2.py` event output format without updating `api/bot_manager.py` parser.
- Never drop or rename columns on tables that live code reads/writes.

### Feature flags
- Centralized in `api/config.py`.
- Current flags:
  - `PERFORMANCE_DASHBOARD_ENABLED` — controls profitability dashboard, `/performance/*` endpoints, and wallet snapshot worker.

### Configuration
- Read env vars; never hardcode secrets.
- API env file: `api/.env` (not committed).
- Systemd service loads `api/.env` via `EnvironmentFile`.

---

## 5. How to run / test

### Activate venv
```bash
source venv/bin/activate
```

### Run API locally
```bash
uvicorn api.main:app --host 127.0.0.1 --port 8001 --reload
```

### Run Alembic
```bash
export DB_URL="mysql+aiomysql://viznago:<pass>@localhost/viznago_dev"
alembic upgrade head          # apply migrations
alembic downgrade -1          # rollback one
alembic revision --autogenerate -m "message"  # generate new migration
```

### Restart production API
```bash
systemctl restart viznago_api
journalctl -u viznago_api -f
```

### Syntax checks
```bash
# Python
find api -name "*.py" -exec python -m py_compile {} \;

# JavaScript
node --check landing/dashboard/profitability.js
node --check landing/dashboard/dashboard.js
```

---

## 6. Important files for agents

| File | Why it matters |
|---|---|
| `api/main.py` | FastAPI lifespan: DB migrations, background workers, bot auto-restart. |
| `api/bot_manager.py` | Spawns bot subprocesses; parses `[EVENT]` lines into `BotEvent` and `BotTrade`. |
| `api/models.py` | SQLAlchemy ORM — single source of truth for tables. |
| `api/config.py` | Feature flags. |
| `api/routers/performance.py` | Profitability dashboard endpoints. |
| `api/routers/admin.py` | Admin endpoints including `/admin/performance`. |
| `api/performance_worker.py` | Wallet snapshot background task. |
| `api/signal_reconciler.py` | Reconciles Signal Lab closes with HL fills. |
| `scripts/backfill_bot_trades.py` | One-off backfill from `bot_events` to `bot_trades`. |
| `src/reporting/metrics.py` | Backtest risk metrics (Sharpe, Sortino, drawdown). |
| `landing/dashboard/profitability.js` | Performance tab frontend logic. |
| `landing/i18n.js` | Bilingual translation keys. |

---

## 7. Recent major changes (2026-07-16)

### Profitability Dashboard
- New tables: `bot_trades`, `wallet_snapshots`
- `signal_executions` extended with P&L columns (`realized_pnl_usd`, `fees_usd`, `closed_at`, `exit_reason`)
- Alembic migration: `8f300e110022`
- Backfilled 902 historical trades on 2026-07-16
- Feature flag: `PERFORMANCE_DASHBOARD_ENABLED=true` in `api/.env`
- Dashboard tab: **Rendimiento / Performance** at `landing/dashboard/index.html`
- Endpoints: `/performance/summary`, `/performance/equity-curve`, `/performance/trades`, `/performance/breakdown`, `/performance/export`
- Admin endpoint: `/admin/performance`

See `IMPLEMENTATION_PLAN_PROFITABILITY_DASHBOARD.md` and `VIZBOT_KNOWLEDGE.md` for full details.

---

## 8. Common pitfalls

- **`api/main.py` inline migrations** run on every startup. They are idempotent but noisy; prefer Alembic for new changes.
- **No automated tests** exist yet. Validate manually with `TestClient` or staging.
- **CORS origins** default to dev domain + localhost; tighten for prod.
- **API runs as root** currently; planned migration to non-root user.
- **`requirements.txt`** was incomplete before 2026-07-16; install from active venv when in doubt.

---

## 9. Rollback references

```bash
# Code rollback to pre-dashboard baseline
git checkout pre-profitability-dashboard

# DB rollback one migration
alembic downgrade -1

# Full DB restore (requires backup)
mysql -u viznago -p<pass> viznago_dev < backups/viznago_dev_pre_pd_YYYYMMDD_HHMMSS.sql
```

---

## 10. Questions?

If unclear on scope, always prefer the safer path:
1. Additive DB changes only.
2. Feature-flag new functionality.
3. Restart API only when necessary and during low-activity windows.
4. Backup DB before schema changes.
