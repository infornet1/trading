# VIZNAGO FURY — SaaS Option B: Hosted LP Hedge Bot Service
> Architecture & Implementation Plan — v1.0 Draft (2026-03-19)
> Status: **Pending Final Review**

---

## 1. Goal

Allow any user to connect their wallet to the VIZNAGO FURY dashboard, select a
Uniswap v3 LP position, configure hedge parameters, and activate a managed Bot
Aragan/Avaro instance — without running anything locally.

Revenue model: monthly subscription paid in USDC on Arbitrum (crypto-first),
Stripe as secondary option once validated.

---

## 2. Architecture Overview

```
User (Browser + Rabby Wallet)
        │
        │  1. Sign message → JWT issued (no password)
        │  2. Submit LP position + hedge config via dashboard
        │  3. WebSocket streams live bot events back to UI
        │
        ▼
┌─────────────────────────────────────────────────┐
│  FastAPI App  (venv, port 8001, systemd)        │
│  ├── Auth module     (EIP-712 wallet signature) │
│  ├── Bot config CRUD (MariaDB)                  │
│  ├── Bot Manager     (subprocess per user)      │
│  └── WebSocket hub   (in-memory, alpha)         │
└─────────────────────────────────────────────────┘
        │                        │
        ▼                        ▼
  MariaDB                  Bot Processes
  (already running)        (Python subprocesses)
  viznago_dev/prod         ├── user_A: live_hedge_bot.py
                           ├── user_B: live_hedge_bot.py
                           └── user_C: ...
                                    │
                                    ▼
                             Hyperliquid API
                             (user's own API key)
```

**Key principles:**
- No Docker for alpha — uses existing MariaDB + venv on the droplet
- No private keys ever stored — only Hyperliquid API keys (encrypted at rest)
- Per-user bots are Python subprocesses, not containers
- Redis deferred to post-alpha (in-memory WebSocket hub sufficient for MVP)

---

## 3. Infrastructure: What's Already There

| Component | Status | Detail |
|---|---|---|
| Ubuntu droplet | ✅ Running | `dev.ueipab.edu.ve` |
| nginx | ✅ Running | SSL termination, static files |
| MariaDB 11.8 | ✅ Running | Port 3306, used by FreeScount |
| Python venv | ✅ Ready | `/var/www/dev/trading/lp_hedge_backtest/venv/` |
| live_hedge_bot.service | ✅ Live | systemd, uptime 4+ days |
| pydantic v2 | ✅ Installed | FastAPI-ready |
| hyperliquid-python-sdk | ✅ Installed | Bot trades |
| Disk | ⚠️ 79% used | 11 GB free — monitor |
| RAM | ✅ 1.9 GB free | Comfortable for alpha |

## 3.1 What Needs to Be Added

```bash
# New databases in existing MariaDB (no new service)
CREATE DATABASE viznago_dev;
CREATE DATABASE viznago_prod;

# New Python packages in existing venv
venv/bin/pip install \
    fastapi \
    uvicorn[standard] \
    sqlalchemy[asyncio] \
    aiomysql \
    python-jose[cryptography] \
    cryptography \
    passlib[bcrypt]
```

No Redis, no PostgreSQL, no Docker for alpha.

---

## 4. Authentication — Wallet Signature (No Password)

Users prove wallet ownership by signing a challenge. No email/password required.

```
1. GET  /auth/nonce?address=0xABC
        → server stores nonce, returns: { nonce: "abc123" }

2. Rabby signs message:
        "Sign in to VIZNAGO FURY\nNonce: abc123\nChain: 42161"

3. POST /auth/verify { address, signature }
        → server recovers signer address via eth_account
        → if address matches → return JWT (24h expiry)

4. All API calls: Authorization: Bearer <jwt>
```

- JWT signed with `SECRET_KEY` from `.env`
- No session storage — stateless
- Wallet address IS the user identity (primary key)

---

## 5. Database Schema (MariaDB)

```sql
-- Users (wallet = identity)
CREATE TABLE users (
    address         VARCHAR(42) PRIMARY KEY,   -- 0x...
    plan            ENUM('free','starter','pro') DEFAULT 'free',
    created_at      DATETIME DEFAULT NOW(),
    last_seen       DATETIME
);

-- Bot configurations (one per LP position per user)
CREATE TABLE bot_configs (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    user_address    VARCHAR(42) NOT NULL REFERENCES users(address),
    chain_id        INT NOT NULL,               -- 42161 = Arbitrum
    nft_token_id    VARCHAR(78) NOT NULL,        -- Uniswap v3 NFT id
    pair            VARCHAR(20) NOT NULL,        -- e.g. ETH/USDC
    lower_bound     DECIMAL(20,8) NOT NULL,
    upper_bound     DECIMAL(20,8) NOT NULL,
    trigger_pct     DECIMAL(5,2) DEFAULT -0.50, -- % below floor
    hedge_ratio     DECIMAL(5,2) DEFAULT 50.00, -- % of volatile capital
    hedge_exchange  VARCHAR(20) DEFAULT 'hyperliquid',
    hl_api_key      TEXT,                        -- AES-256 encrypted
    hl_wallet_addr  VARCHAR(42),
    mode            ENUM('aragan','avaro') DEFAULT 'aragan',
    active          BOOLEAN DEFAULT FALSE,
    created_at      DATETIME DEFAULT NOW(),
    updated_at      DATETIME DEFAULT NOW() ON UPDATE NOW()
);

-- Bot events (audit trail + dashboard history)
CREATE TABLE bot_events (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    config_id       INT NOT NULL REFERENCES bot_configs(id),
    event_type      ENUM('started','hedge_opened','breakeven',
                         'tp_hit','sl_hit','stopped','error'),
    price_at_event  DECIMAL(20,8),
    pnl             DECIMAL(20,8),
    details         JSON,
    ts              DATETIME DEFAULT NOW()
);

-- Subscriptions (on-chain USDC payment proof)
CREATE TABLE subscriptions (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    user_address    VARCHAR(42) NOT NULL REFERENCES users(address),
    plan            ENUM('starter','pro') NOT NULL,
    active_until    DATETIME NOT NULL,
    payment_tx_hash VARCHAR(66),                 -- on-chain tx
    created_at      DATETIME DEFAULT NOW()
);
```

---

## 6. API Endpoints (FastAPI)

```
AUTH
  GET  /auth/nonce?address=         → nonce for signing
  POST /auth/verify                 → { address, signature } → JWT

BOTS
  GET  /bots                        → list caller's bot configs
  POST /bots                        → create new bot config
  PUT  /bots/{id}                   → update config (only if inactive)
  DELETE /bots/{id}                 → delete config (stops first)
  POST /bots/{id}/start             → spawn bot subprocess
  POST /bots/{id}/stop              → terminate subprocess
  GET  /bots/{id}/status            → { running, pid, last_event }
  GET  /bots/{id}/events            → event history (paginated)

REALTIME
  WS   /ws/{bot_id}                 → live event stream to dashboard

SUBSCRIPTION
  GET  /subscription                → current plan + expiry
  POST /subscription/verify         → { tx_hash } → verify on-chain USDC payment
```

All endpoints except `/auth/*` require `Authorization: Bearer <jwt>`.

---

## 7. Bot Manager

Each active user bot runs as an **isolated Python subprocess**. The API process
owns the lifecycle:

```python
class BotManager:
    _procs: dict[int, subprocess.Popen] = {}  # config_id → process

    async def start(self, config_id: int, config: dict):
        if config_id in self._procs:
            return  # already running
        env = {
            **os.environ,
            "NFT_TOKEN_ID":  config["nft_token_id"],
            "LOWER_BOUND":   str(config["lower_bound"]),
            "UPPER_BOUND":   str(config["upper_bound"]),
            "TRIGGER_PCT":   str(config["trigger_pct"]),
            "HEDGE_RATIO":   str(config["hedge_ratio"]),
            "HL_API_KEY":    decrypt(config["hl_api_key"]),  # AES-256
            "HL_WALLET":     config["hl_wallet_addr"],
            "BOT_MODE":      config["mode"],
            "CONFIG_ID":     str(config_id),
        }
        proc = subprocess.Popen(
            [VENV_PYTHON, BOT_SCRIPT],
            env=env, stdout=PIPE, stderr=STDOUT
        )
        self._procs[config_id] = proc
        asyncio.create_task(self._tail(config_id, proc))

    async def stop(self, config_id: int):
        proc = self._procs.pop(config_id, None)
        if proc:
            proc.terminate()

    async def _tail(self, config_id, proc):
        # Parse stdout → write bot_events to DB
        # → push to WebSocket subscribers
        ...
```

**Prerequisite:** `live_hedge_bot.py` must be refactored to read all config
from environment variables (currently hardcoded). This is Step 2 of the build.

---

## 8. Subscription Plans

| Plan | Price | Active Bots | Check Interval | Alerts |
|---|---|---|---|---|
| Free | $0 | 0 (monitor only) | — | — |
| Starter | $29 USDC/mo | 1 | 30s | Email |
| Pro | $79 USDC/mo | 5 | 10s | Email + Telegram |

**Payment flow (crypto-first):**
1. User sends USDC to treasury wallet on Arbitrum
2. Posts `tx_hash` to `POST /subscription/verify`
3. API reads tx on-chain (via public RPC), confirms amount + recipient
4. Activates plan until `now + 30 days`

Stripe added as secondary option post-alpha.

---

## 9. Golden Rules (Enforced in Bot Code)

These rules from Bootcamp Cripto 2026 are enforced server-side regardless
of user config — not just UI hints:

- **BTC: NEVER short** — bot refuses to open SHORT on BTC pairs
- **ETH:** long + short OK (Bot Aragan + Avaro modes)
- **Hedge wallet:** 10–20% of pool value maximum
- **API key only:** Hyperliquid API key stored, never private key
- **Min deposit:** $10 hedge balance enforced before bot starts

---

## 10. Dashboard Changes Required (Phase 4)

Each position card gains a collapsible **"Enable Protection"** drawer:

```
[Position Card — WETH/USDC · IN RANGE]
────────────────────────────────────────────
[ ▼ Enable Bot Protection ]

  Mode:         ● Aragan (hedge only)  ○ Avaro (+long)
  Trigger:      [ -0.5 ]% below lower bound
  Hedge size:   [ 50 ]% of volatile capital
  Exchange:     [ Hyperliquid ▼ ]
  HL API Key:   [ •••••••••••••••• ]
  HL Wallet:    [ 0xABC... ]

  [ Activate Protection ]
────────────────────────────────────────────
Status:     🟢 ACTIVE — Last check: 12s ago
Last event: Hedge opened @ $1,791.20 · P&L: +$42.10
[ Event history ▼ ]
```

- Config form sends `POST /bots` → `POST /bots/{id}/start`
- WebSocket `/ws/{bot_id}` updates status + last event in real time
- Subscription gate: Free users see the form but "Activate" prompts upgrade

---

## 11. Security Checklist

| Risk | Mitigation |
|---|---|
| HL API key exposure | AES-256 encrypted at rest; decrypted only in subprocess env, never returned via API |
| JWT theft | Short expiry (24h); wallet re-sign to renew |
| SQL injection | SQLAlchemy ORM parameterised queries throughout |
| BTC short violation | Hard-coded block in bot code, not just UI |
| Runaway bot process | Watchdog: if process exits unexpectedly → mark inactive + email user |
| Shared DB with FreeScount | Separate DB user `viznago` with no access to FreeScount tables |
| Root process risk | FastAPI service runs as dedicated `viznago` system user, not root |

---

## 12. Implementation Phases

| Step | Scope | Effort |
|---|---|---|
| **1** | MariaDB: create databases + user + schema | 1–2 hrs |
| **2** | `live_hedge_bot.py` refactor: all config from env vars | 1 day |
| **3** | FastAPI skeleton + auth (nonce + JWT + `/auth/*`) | 1 day |
| **4** | Bot config CRUD endpoints + DB models | 1 day |
| **5** | Bot Manager (spawn/stop/tail subprocesses) | 2 days |
| **6** | WebSocket live event stream | 1 day |
| **7** | Dashboard Phase 4 (config drawer + WS client) | 2–3 days |
| **8** | Subscription + USDC on-chain payment verification | 1–2 days |
| **9** | Email alerts per user (reuse existing email setup) | 1 day |
| **10** | Alpha test with 3–5 real users | ongoing |

**Estimated MVP: 2–3 weeks** from Step 1 start.

---

## 13. Post-Alpha Upgrade Path

When alpha is validated and revenue justifies it:

```
New production droplet (4GB RAM recommended)
└── Docker Compose
    ├── postgres:16-alpine   (migrate from MariaDB)
    ├── redis:7-alpine       (WebSocket pub/sub at scale)
    ├── api                  (FastAPI containerised)
    ├── nginx                (with certbot)
    └── monitoring           (Prometheus + Grafana)
```

Migration is low-friction:
- `mysqldump` → import to Postgres (pgloader tool)
- FastAPI env vars unchanged
- Docker Compose wraps what's already working

---

## 14. Open Decisions (For Review)

- [ ] Confirm treasury wallet address for USDC subscription payments
- [ ] Confirm Telegram bot token for Pro plan alerts (or defer to post-alpha)
- [ ] Confirm `viznago` Linux system user creation (replaces current `root` bot)
- [ ] Free plan: monitor-only dashboard OR 7-day free trial with 1 active bot?
- [ ] Starter plan price point: $29/mo — confirm or adjust

---

*VIZNAGO FURY — Bootcamp Cripto 2026 · LP + Perps Hedge Strategy*
