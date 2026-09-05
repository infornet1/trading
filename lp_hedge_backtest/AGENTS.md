# AGENTS.md — VIZNIAGO.finance

Concise context for AI coding agents working on this repository.

---

## ⚠️ Note to future Claude Code CLI sessions

The `.claude/settings.local.json` file that was previously in this repository has been **removed and relocated** as part of a security hardening on 2026-07-16. It is now stored outside the repo at:

```
/root/.claude-settings-local-backup.json
```

- `.claude/` has been added to `.gitignore` and must never be committed.
- If you need Claude-specific settings, do not recreate `settings.local.json` inside the repo.
- The secrets that were in that file were rotated on 2026-07-16: `SECRET_KEY`, `ENCRYPTION_KEY`, and the MariaDB `viznago` password.
- All encrypted HL API keys (`bot_configs.hl_api_key`) and Signal Lab private keys (`signal_wallets.hl_secret_key`) were re-encrypted with the new `ENCRYPTION_KEY`.
- Hardcoded DB password fallbacks were removed from `api/database.py`, `migrations/alembic/env.py`, `telegram_listener/listener.py`, and `telegram_listener/test_signal_lab.py`.
- If you see references to the old secrets anywhere, rotate again immediately.

---

## 1. Project overview

**VIZNIAGO.finance** is a DeFi SaaS that protects Uniswap v3 concentrated-liquidity positions by automatically hedging with Hyperliquid perpetual futures. It also runs standalone trading bots (FURY RSI, Whale Tracker) and a Signal Lab that copy-trades Telegram signals.

| Component | Location |
|---|---|
| Backtesting engine | `src/` |
| Live trading bots | `live_hedge_bot*.py`, `live_fury_bot.py`, `live_whale_bot.py`, `live_polymarket_bot.py` |
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
| `api/signal_expiry.py` | Sole owner of signal expiry (7 h cutoff, every 15 min). |
| `api/signal_executor.py` | Places HL entry + native SL/TP for Signal Lab. Holds `_round_px()` and the sizing/leverage-cap logic. |
| `scripts/backfill_bot_trades.py` | One-off backfill from `bot_events` to `bot_trades`. |
| `scripts/backfill_signal_close_pnl.py` | One-off: fills dashboard P&L columns on listener-closed executions. |
| `scripts/fix_signal_pnl_leverage.py` | One-off: removes the double-counted leverage factor from stored P&L. |
| `src/reporting/metrics.py` | Backtest risk metrics (Sharpe, Sortino, drawdown). |
| `landing/dashboard/profitability.js` | Performance tab frontend logic. |
| `landing/i18n.js` | Bilingual translation keys. |

---

## 7. Recent major changes (2026-07-16)

### Security hardening
- `.claude/` added to `.gitignore`; local `settings.local.json` removed from repo.
- Hardcoded DB fallback removed from `api/database.py`; `DB_URL` is now required via env.
- API service runs as non-root `viznago` user (systemd `User=viznago`).
- Basic per-IP rate limiting added to `/auth/*`, `/admin/*`, and `/performance/*` endpoints.
- `api/.env`, `bot_state/`, `data_cache/`, `backups/` set to `root:webdev` group permissions. ⚠️ This stranded pre-existing files that the API writes: the directories are group-writable but individual `root:webdev 644` files are not, so the API (now `viznago`) can read them and not overwrite them. `data_cache/reconciler_state.json` failed hourly for ~4 weeks before this was noticed on 2026-08-11.
- Project email config is encrypted at `/var/www/dev/trading/lp_hedge_email_config.json` and loaded via `api/email_config.py` / `api/email_encrypt.py`.
- Shared monorepo email config `/var/www/dev/trading/email_config.json` is now encrypted with Fernet. A root-level loader (`/var/www/dev/trading/email_config_loader.py`) decrypts it for all sibling projects (ADX, scalping, supervisor, BTC notifier). `/var/www/dev/trading/.env.email` supplies `ENCRYPTION_KEY` to systemd services.
- `api/.env.email` (ignored by Git) overrides `EMAIL_CONFIG_PATH` so the LP hedge service and bot subprocesses use the encrypted project config.
- WebSocket JWT query params (`/ws/{id}?token=...`) are redacted from uvicorn access logs via `api/logging_filters.py`.
- Systemd unit file version-controlled at `deploy/viznago_api.service` and symlinked into `/etc/systemd/system/`.
- pytest suite under `tests/`: auth, encrypted email config loading, profitability dashboard (DB mocked), `telegram_listener.signal_parser`, `api.bot_manager` state/event mapping, listener retry helpers, and `api.models._utcnow()`. Run with `./venv/bin/python -m pytest tests/`.

### Fresh clone / deployment notes
- The `adx_strategy_v2` directory is a Git submodule (`infornet1/Andromeda`). After cloning, run:
  ```bash
  git submodule update --init --recursive
  ```
- `email_config.json` is **not tracked** in Git. On a new server, create and encrypt it with:
  ```bash
  export ENCRYPTION_KEY=<key>
  /var/www/dev/trading/lp_hedge_backtest/venv/bin/python - <<'PY'
  import json, sys
  sys.path.insert(0, '/var/www/dev/trading/lp_hedge_backtest')
  from api.email_encrypt import encrypt_email_config
  plain = { ... }  # smtp_server, smtp_port, smtp_username, smtp_password, sender_email
  with open('/var/www/dev/trading/email_config.json', 'w') as f:
      json.dump(encrypt_email_config(plain), f, indent=2)
  PY
  ```
- Ensure `/var/www/dev/trading/.env.email` exists and contains `ENCRYPTION_KEY`.
- Ensure all consumer services load `/var/www/dev/trading/.env.email` via `EnvironmentFile`.

### Profitability Dashboard
- New tables: `bot_trades`, `wallet_snapshots`
- `signal_executions` extended with P&L columns (`realized_pnl_usd`, `fees_usd`, `closed_at`, `exit_reason`)
- Alembic migration: `8f300e110022`
- Backfilled 902 historical bot trades on 2026-07-16
- Backfilled 82 closed Signal Lab executions on 2026-07-16; `api/signal_reconciler.py` now stores gross `realized_pnl_usd` with fees tracked separately — ⚠️ but with a leverage double-count that made every dollar figure 3×–60× too large until **2026-08-11**; see "Signal Lab correctness fixes" below before trusting any P&L number recorded before that date
- Cleaned up `bot_trades` estimates on 2026-07-16: deleted 31 empty `stopped` noise rows, enriched 380 whale estimates with `funding_usd`/`net_pnl_usd`/`pair`, and hardened `api/bot_manager.py` + `scripts/backfill_bot_trades.py` to skip future whale closed-only and empty stopped estimates
- Profitability dashboard (`api/routers/performance.py`) and admin aggregate (`api/routers/admin.py`) now exclude `is_estimate = TRUE` bot_trades from main KPIs; an `include_estimates=true` query param and dashboard toggle let users view the enriched whale estimate rows separately
- Feature flag: `PERFORMANCE_DASHBOARD_ENABLED=true` in `api/.env`
- Dashboard tab: **Rendimiento / Performance** at `landing/dashboard/index.html`
- Endpoints: `/performance/summary`, `/performance/equity-curve`, `/performance/trades`, `/performance/breakdown`, `/performance/export`
- Admin endpoint: `/admin/performance`

See `IMPLEMENTATION_PLAN_PROFITABILITY_DASHBOARD.md` and `VIZBOT_KNOWLEDGE.md` for full details.

### Maintenance / code quality (2026-07-17)
- Replaced all `datetime.utcnow()` calls with `datetime.now(timezone.utc)` equivalents in tracked Python files, including `api/models.py` default/onupdate callables (deprecated in Python 3.14).
- Signal Lab auto-execute retry logic (`telegram_listener/listener.py`) now uses exponential backoff (2s / 4s / 8s) and explicitly handles `502 Bad Gateway`.
- pytest suite expanded to 48 tests covering auth, email config, performance dashboard, signal parser, bot manager state, listener retry helpers, and the `api.models._utcnow()` helper.
- Stale `live_hedge_bot.service` / `viznago_api.service` files removed from the project root; bot lifecycle is exclusively `api/bot_manager.py` subprocesses.
- `adx_strategy_v2` registered as a Git submodule; `logs/` inside it ignored.
- `api/.env.email` permissions hardened to `root:webdev 640`.

### Operations (2026-08-02)
- Diagnosed a silent Telegram listener outage (~3.5 days, since 2026-07-30 ~21:12 UTC): the process was alive but stuck on a half-open Telegram connection, so no signals were parsed and no Signal Lab emails were sent. The listener was restarted via the watchdog and verified healthy.
- Hardened against recurrence: `telegram_listener/listener.py` now runs a `_heartbeat` task that pings Telegram (`functions.PingRequest`) and logs `HEARTBEAT ok` every 15 min, exiting with `os._exit(1)` if the ping fails; `telegram_listener/watchdog.sh` now kills any running listener whose log is stale for >30 min (`MAX_STALE_MIN`) and restarts it. Manual recovery procedure kept in "Common pitfalls" below as a fallback.

### Polymarket TP/SL bot (2026-08-02)
- New bot mode `polymarket`: buys a Polymarket outcome token (CLOB V2, Polygon) and auto-exits at a take-profit or synthetic stop-loss.
- Bot script: `live_polymarket_bot.py` (env-var config, `[EVENT]` contract, `PAPER_TRADE=1`, crash-safe state in `bot_state/poly_state_{config_id}.json` — a respawned bot resumes monitoring instead of re-buying).
- SDK: official `py-clob-client-v2` (CLOB V1 was archived 2026-04-28 — do not use `py-clob-client`).
- The Polygon private key is stored in the existing `hl_api_key` column (Fernet-encrypted) and the funder address in `hl_wallet_addr`; the frontend uses synthetic `nft_token_id = 'poly-<timestamp>'`, `chain_id = 137`, `pair = 'POLY'`.
- Schema: Alembic migration `b2c4d6e8f0a1` — `bot_configs.mode` enum + `polymarket_*` columns, `bot_events.event_type` + `poly_entry`/`poly_tp`/`poly_sl`.
- Events flow through `api/bot_manager.py` (`_EVENT_MAP`, `OPEN_EVENTS`/`CLOSE_EVENTS`) into `bot_trades` and the profitability dashboard like other bots.
- Feature flag: `POLYMARKET_BOT_ENABLED` in `api/config.py` / `api/.env`.
- Frontend: `landing/polymarket/` (mirrors the whale page; nav links added to all product pages).
- Tests: `tests/test_polymarket_bot.py` (event map, router validation, TP/SL helpers).
- Setup / ops notes:
  - No Polymarket API-key signup needed — the SDK derives API creds from the Polygon private key on first start.
  - Paper mode needs no credentials. Live credentials are entered per-bot in the launch form (funder address + private key), not in any `.env`.
  - Funder address = the address holding USDC on Polygon; for polymarket.com accounts this is the **Polymarket proxy wallet**, not the user's EOA.
  - The funder wallet needs USDC on Polygon and a one-time **USDC allowance approval** to the Polymarket exchange contract (already done for any wallet that has traded on polymarket.com; the bot does not set approvals itself — a first-order failure on a fresh wallet is likely this).
  - On Stop the bot leaves the position open and keeps its state file; Restart resumes monitoring. It never emits `stopped` (that would falsely close the open `bot_trades` row).

### Signal Lab correctness fixes (2026-08-09 → 2026-08-11)

Four bugs found by two health checks. **None was visible in logs or service checks** — every one was
caught by reconciling the database against Hyperliquid. Commits `6f4bb7a` and `920383e`.

**1. Breakeven monitor failed open (`6f4bb7a`).** The monitor inferred "TP1 filled" from the order's
absence in `open_orders`, and its helper caught every exception and returned an empty set — so a single
HL 502 looked like every TP1 filling at once, and the monitor cancelled the real stop-loss on four live
positions to place a tighter one at entry. `breakeven_applied` was then set regardless of outcome, so it
never retried. Positions survived only because the replacement order also 502'd.
- `_tp1_order_status()` now reads the real status via `query_order_by_oid` and returns `None` on any
  error, unknown oid, or malformed reply. Only `"filled"` acts.
- `_move_sl_to_breakeven()` **places the breakeven stop before cancelling the original** and validates
  the order response. A failed placement can no longer leave a position naked.
- `breakeven_applied` is set only on a settled outcome, with 3 bounded retries.
- Verified in production 2026-08-11 when TP1 came back `'reduceOnlyCanceled'` — a status not explicitly
  enumerated — and the fail-closed default correctly left the stop alone.
- ⚠️ The 18 pre-fix "SL → breakeven" successes in the log were never audited; some fired spuriously and
  scratched trades early. Distrust pre-2026-08-09 breakeven outcomes.

**2. Channel-driven closes wrote no dashboard P&L (`6f4bb7a`).** `_auto_close_signal` wrote only
`close_price`; the other four columns came solely from `api/signal_reconciler.py`. Because
`api/routers/performance.py` filters on `closed_at`, every close driven by a channel update was invisible
to `/performance/*`. Now writes all four columns. 12 executions repaired by
`scripts/backfill_signal_close_pnl.py`.

**3. Realized P&L was inflated by the leverage factor (`920383e`) — the most consequential of the four.**
`exec_size_usdt` is the **notional** (`size × fill_price`), so leverage is already embedded in it, but
every writer multiplied by leverage again. The dashboard overstated every dollar figure by 3×–60× from
the day it shipped (2026-07-16) until 2026-08-11.
- Caught by comparing to HL `closedPnl`: exec 137 (DOT, 10×) stored `+2.6560`, HL reported `+0.2657`.
  The ratio equalled the leverage on every row.
- Fixed in `api/signal_reconciler.py`, `telegram_listener/listener.py` (`_close_pnl_usd`, which now takes
  **no leverage argument at all**), and `scripts/backfill_signal_close_pnl.py`.
- **Corrected lifetime Signal Lab: gross +1.85 / fees 1.06 / net +$0.79 across 116 executions, 52 wins /
  64 losses** — previously displayed as +$36.79. Post-fix values match HL to ±$0.0002.
- Repaired by `scripts/fix_signal_pnl_leverage.py` (dry-run default). Rows with a recorded notional are
  recomputed from first principles rather than divided, because `exec_leverage` frequently differs from
  `signal.leverage` (HL caps leverage per asset) and the writers disagreed on which to use. The 46 pre-M5
  rows have no stored notional and are verified against the old formula before being divided, so anything
  of unknown provenance is skipped rather than guessed at.

**4. HL rejected trigger prices with >5 significant figures (`920383e`).** BTC signal 93 quoted a stop of
`65682.1`; HL rejected both attempts with `Invalid TP/SL price. asset=0`, H4 closed the entry at market,
and the signal was skipped. Latent for months because every earlier BTC stop was a round number. New
`_round_px()` in `api/signal_executor.py` snaps SL/TP1/TP2 onto HL's rules before the guards read them.

**5. LPReconciler could not write its state file.** `data_cache/reconciler_state.json` was left
`root:webdev` by the 2026-07-16 hardening that moved the API to the `viznago` user, so the hourly
overwrite failed with `[Errno 13]` from 2026-07-16 to 2026-08-11. Fixed with `chown viznago:webdev`.

### Performance pass (2026-08-15)

Repo-wide performance audit + fixes. Baseline tag: `pre-perf-pass`. No live-trading logic or the
`[EVENT]` wire format changed.

**1. Startup safety (`api/main.py`).** Removed three stale inline migrations: an unconditional
`ALTER TABLE bot_events MODIFY COLUMN event_type ENUM(...)` that rebuilt the whole table on every
restart **and omitted `poly_entry`/`poly_tp`/`poly_sl`** (it would have silently stripped polymarket
event types if it ever succeeded — that enum is owned solely by Alembic `b2c4d6e8f0a1` now), plus two
`DROP INDEX` statements and a duplicate `ADD UNIQUE KEY` that failed and logged on every startup.

**2. Indexes (Alembic `c3a7f19d2e54`, mirrored in `api/models.py`).** `signal_executions` previously
had **zero** non-PK indexes. Added: `signal_executions(user_address)` and `(outcome, close_price)`,
`bot_trades(user_address, closed_at)`, `bot_events(config_id, ts)`,
`signal_events(status, received_at)`. Verified with EXPLAIN.

**3. SQL-side aggregations.** `/performance/summary`, `/performance/breakdown`, `/admin/performance`
no longer hydrate entire tables to aggregate in Python — they use `SUM`/`COUNT`/`CASE` and `GROUP BY`
(response shapes unchanged). `/admin/overview` went from 4 queries per bot config (including loading
**all** historical `hedge_opened` JSON into Python) to 4 constant queries
(`ROW_NUMBER() OVER (PARTITION BY config_id …)` + `SUM(JSON_EXTRACT(details,'$.notional'))`).
`/signal-lab/history` went from up to 201 queries to one window-function query. `/performance/export`
is now capped at 10 000 rows.

**4. Signal expiry ownership.** `GET /signal-lab/signals` no longer runs an UPDATE+COMMIT on a read
endpoint; expiry is owned solely by the `api/signal_expiry.py` sweeper, whose cutoff was aligned
4h → 7h to match what the endpoint used to apply.

**5. Worker external-API waste.** `api/performance_worker.py` reuses one shared `Info` client
(previously ~2 extra HL meta REST calls per wallet per 15-min cycle) and fetches balances with
`asyncio.gather`. `api/signal_reconciler.py` groups open executions by wallet — one `user_state` +
one `user_fills_by_time` per wallet per scan (concurrently), instead of per-execution full
`user_fills` (~2000-row) fetches. ⚠️ `userFillsByTime` returns fills **oldest-first** while
`userFills` returns newest-first; the reconciler reverses to preserve its last-match-wins scan.

**6. SMTP off the event loop.** Admin alert emails in `api/lp_reconciler.py` and
`api/bot_manager.py` (`_notify_admin_lp_gone`) now send via `asyncio.to_thread` with
`smtplib.SMTP(..., timeout=15)`; a slow SMTP server can no longer stall the API event loop.

**7. Bot-event write amplification (`api/bot_manager.py`).** `BotConfig` metadata
(user_address/pair/mode) is cached at bot start instead of re-SELECTed per `[EVENT]` line (DB
fallback retained). `whale_snapshot` and V2's `bounds_refreshed` events are now WebSocket-only —
no `bot_events` rows (`_SKIP_DB_EVENTS`); `bounds_refreshed` was previously misfiled as `error`.

**8. Frontend leak (`landing/dashboard/profitability.js`).** The equity chart is a lazy singleton
reused via `series.setData(...)` with a single `resize` listener; previously every refresh leaked a
LightweightCharts instance + window listener.

### UX pass (2026-08-15)

Follow-up to the performance pass: a frontend/backend/bot UX audit, fixes landed the same day.

**Backend / bot manager**
- **Fixed a severe auto-restart bug:** `_auto_restart_bots` built its config dict inline and dropped
  `paper_trade`, all `polymarket_*` keys, and the gate/tuning columns — after any API restart a paper
  bot respawned **LIVE** and a polymarket bot respawned with an empty token id. All three launch paths
  now share `build_start_config(cfg)` in `api/bot_manager.py`.
- Bot crashes now persist a `BotEvent(event_type="error")` with `details.msg = "process exited rc=N"`
  plus a 20-line stdout ring buffer; `/bots/{id}/status` exposes `last_seen`, `seconds_since_output`,
  and `last_error` so the UI can distinguish "alive but quiet" from "hung".
- `stop()`/`shutdown()` no longer block the event loop (`asyncio.to_thread(proc.wait, …)`).
- `/bots/{id}/events` returns `{total, rows, limit, offset}` (was a bare list — frontend tolerates
  both); `/performance/trades` and `/signal-lab/history` gained `total` (history also gained `offset`);
  `/performance/export` sends `X-Total-Rows` + `X-Truncated` headers.
- HL SDK read endpoints (`/bots/hl-balance`, `/bots/{id}/hl-position`, signal-lab balance/positions,
  admin balance/positions) wrapped in `asyncio.wait_for(…, timeout=10)` — they previously could hang
  forever on a stuck HL API.
- Missing `Authorization` header is now 401 (was FastAPI's default 403, which the frontend didn't
  treat as session-expired); 429 responses carry `Retry-After`.
- Unknown `[EVENT]` labels still map to `error` but keep the original label in `details.event_label`;
  `live_polymarket_bot.py` now uses `details.msg` like the other bots.

**Frontend — dashboard (`landing/dashboard/`)**
- Equity chart fix: 15-min snapshots were mapped to date-only strings → duplicate Lightweight-Charts
  `time` keys threw and killed the whole Performance tab render. Now deduped to one point per day,
  and chart failures are isolated (`Promise.allSettled` + try/catch).
- CSV export now uses `fetch` + Bearer + blob download (`window.open` always 401'd) and surfaces the
  `X-Truncated` notice; `API_BASE` fallback typo `lp_hedge` → `lp-hedge` fixed.
- Trade-journal Prev/Next buttons update after every load (Prev was permanently disabled); the
  Performance tab refreshes on tab switch, shows a spinner + "last updated" time, and an inline error
  banner instead of unhandled rejections.
- Stop-confirm and gas modals are i18n'd (ES/EN) and close on Escape; drawer inputs (incl. the HL
  private key field) survive auto-refresh re-renders; paper hedge bots show a PAPER tag instead of
  LIVE; WS status pill in bot panels; error events render `details.msg`.

**Frontend — whale / polymarket pages**
- The ES/EN toggle actually works now (page-local `I18N` maps using the `vf_lang` localStorage key —
  consolidate into `landing/i18n.js` later; keys already prefixed `whale.*`/`poly.*`).
- Polymarket feed backfills history from `/bots/{id}/events` on load (was empty after every reload).
- Stop/restart buttons have busy states; Stop confirms with truthful copy (Polymarket: position stays
  OPEN, bot only stops monitoring). Both pages handle `accountsChanged`/`chainChanged`, show a WS
  status indicator, swallow the duplicate 401 error banner, and render `details.msg` in their feeds.

**Tests:** 110 (was 101) — new coverage for `build_start_config`, unknown-label preservation,
missing-credential 401, and the rate limiter's `Retry-After`.

### Admin page gaps closed (2026-08-16)

- **Platform performance section** in `landing/admin/` — first UI for `GET /admin/performance`
  (KPIs + bots-vs-signal-lab breakdown; participates in the existing refresh loop).
- **Bulk whale-bot buttons** ("⏸ Detener bots whale" / "▶ Iniciar bots whale") wired to the
  previously UI-less `POST /admin/stop-whale-bots` / `start-whale-bots`.
- **`/admin/overview` bot entries** now carry `last_seen`, `seconds_since_output`, and `last_error`
  (latest persisted `error` event's `details.msg`, one window-function query for all configs — the
  constant-query-count property is preserved). The admin cards render "última salida hace Xmin",
  flag >30 min silence on running bots as a possible hang, and show the crash reason on dead bots.
- The last two unguarded HL SDK calls (`_fetch_hl_data` and the signal-lab monitor's per-wallet
  fetch) now have the same 10 s `asyncio.wait_for` guard as the rest.
- Known gap: `/admin/performance` has no `profit_factor` key (needs gross profit/loss sums), so the
  admin card shows `—` for profit factor until the backend adds it.

### Environments sync (2026-09-05)

- **`viznago_prod` DB provisioned**: it existed but was completely empty (no tables). Loaded the
  full `viznago_dev` schema (structure only, no data) and stamped `alembic_version` at head
  (`c3a7f19d2e54`). No service uses it yet — it is now ready as a prod-schema placeholder.

---

## 8. Common pitfalls

- **`api/main.py` inline migrations** run on every startup. They are additive-only `ADD COLUMN IF NOT EXISTS` / `CREATE TABLE IF NOT EXISTS` statements (the table-rebuilding enum `MODIFY` and the always-failing `DROP INDEX` statements were removed 2026-08-15); prefer Alembic for new changes. The `bot_events.event_type` enum is owned by Alembic — never MODIFY it inline.
- **Not all bot events are persisted.** `whale_snapshot` and `bounds_refreshed` are WebSocket-only (`_SKIP_DB_EVENTS` in `api/bot_manager.py`); unknown labels still persist as `error`, now with the original label kept in `details.event_label`. Don't add a DB query expecting those rows.
- **Bot launch config dict has a single source of truth.** `build_start_config(cfg)` in `api/bot_manager.py` builds the full config dict from a `BotConfig` row and is used by all three launch paths (`POST /bots/{id}/start`, `POST /admin/restart/{id}`, startup auto-restart). Never rebuild this dict at a call site — a dropped key once respawned paper bots LIVE after an API restart.
- **`/bots/{id}/events` returns an envelope** `{total, rows, limit, offset}`, not a bare list.
- **Automated tests** are under `tests/` — **110 as of 2026-08-15**, and they run in under a second. Run `./venv/bin/python -m pytest tests/` before deploying changes.
- **`exec_size_usdt` is the NOTIONAL, not margin.** It is `size × fill_price`, so leverage is already inside it. Dollar P&L is `exec_size_usdt × price_return` and fees are `exec_size_usdt × 0.0009` — **never multiply either by leverage.** Doing so is the 2026-08-11 bug that overstated the dashboard by 3×–60×. (A *percentage* return on margin legitimately does multiply by leverage — that is a different quantity from a dollar figure. Don't conflate them.)
- **`exec_leverage` ≠ `signal.leverage`.** HL caps leverage per asset (`maxLeverage` in `meta().universe`) and the executor silently uses `min(requested, max)`. Never assume they match; prefer `exec_leverage` for what actually executed.
- **Hyperliquid price precision.** Perp prices accept **at most 5 significant figures**, and at most `6 - szDecimals` decimal places; whole numbers are always valid. A channel stop like BTC `65682.1` is rejected with `Invalid TP/SL price. asset=0` — where `asset=0` is merely HL's index for BTC, not a failed lookup. Use `_round_px()` in `api/signal_executor.py` for any manually-priced order. Entry orders need no rounding: `market_open()` derives its own price.
- **Never infer a fill from an order's absence, and never let an error look like a state.** `open_orders` failing, or an oid missing from it, does not mean the order filled. Query the order's actual status and return `None` on error so callers can skip. An unknown state must never be treated as an actionable one — this is what cancelled four live stop-losses on 2026-08-09.
- **Reconcile stored money against HL, not just against the logs.** Every P&L bug found so far was invisible to service checks and log greps, and obvious the moment `signal_executions.realized_pnl_usd` was compared to `closedPnl` in HL `userFills`. Do this in every health check. A constant ratio between stored and actual is the tell.
- **Verify a fill via HL `userFills`**, never via order presence or the `breakeven_applied` flag. Both have lied.
- **Process ownership differs by component.** The API and the LP bot subprocesses run as **`viznago`**; the Telegram listener runs as **`root`** (started by the cron watchdog). So a root-owned file under `data_cache/` may be correct (`lp_range_latest.json`, written by the listener) or a bug (`reconciler_state.json`, written by the API). Check which process writes a file before "fixing" its ownership.
- **CORS origins** default to dev domain + localhost; tighten for prod.
- **API runs as `viznago`**; use `deploy/viznago_api.service` for the unit file.
- **`requirements.txt`** is now complete and generated from the active venv (`pip freeze`). Use it for fresh installs; `requirements-dev.txt` adds the test runner.
- **Pydantic V2 models** should use `model_config = ConfigDict(from_attributes=True)` instead of the deprecated `class Config: from_attributes = True`.
- **Avoid `datetime.utcnow()`** — it is deprecated in Python 3.14. Use `datetime.now(timezone.utc).replace(tzinfo=None)` where the DB stores naive UTC timestamps.
- **Telegram listener watchdog** (`telegram_listener/watchdog.sh`) sources `api/.env` so crash-alert emails can decrypt the SMTP config. If you edit `api/.env`, the running listener still needs a watchdog restart to pick up new secrets.
- **Hyperliquid 502s** are retried automatically (`_place_with_retry` in the listener) with exponential backoff (2s / 4s / 8s). They are usually transient; escalate only if they become frequent or persist beyond a few minutes.
- **Telegram listener stale-connection hang (auto-mitigated since 2026-08-02).** A dead-but-half-open Telegram connection (`Server closed the connection: 0 bytes read...` in `logs/listener.log`) can leave the process alive but receiving nothing. The listener now pings Telegram and logs `HEARTBEAT ok` every 15 min, and exits if the ping fails; the watchdog kills and restarts it if the log is stale >30 min. Manual fallback if that ever fails: `kill <pid>` and let the watchdog cron restart it within a minute. Verify recovery: fresh `Ready. Waiting for messages...` + `HEARTBEAT ok` lines plus an ESTABLISHED socket to `149.154.*` (`ss -tnp | grep <new_pid>`). Signals posted during any outage are missed and must be recovered manually from channel history.

---

## 9. Rollback references

```bash
# Code rollback to pre-dashboard baseline
git checkout pre-profitability-dashboard

# DB rollback one migration
export DB_URL="mysql+aiomysql://viznago:<pass>@localhost/viznago_dev"
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
5. Never commit `.env`, `email_config.json`, `.claude/settings*.json`, or local state.
6. Run the API as the `viznago` user, not root.
