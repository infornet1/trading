# VIZNAGO FURY — SaaS Option B: Hosted LP Hedge Bot Service
> Architecture & Implementation Plan — v1.3 (2026-03-20)
> Status: **Steps 0–7 Complete · Step 8 (Subscriptions) Pending**

---

## 1. Goal

Allow any user to connect their wallet to the VIZNAGO FURY dashboard, select a
Uniswap v3 LP position, configure hedge parameters, and activate a managed Bot
Defensor Bajista/Avaro instance — without running anything locally.

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
        "Sign in to VIZNAGO FURY\nNonce: abc123"

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
- **ETH:** long + short OK (Defensor Bajista + Avaro modes)
- **Hedge wallet:** 10–20% of pool value maximum
- **API key only:** Hyperliquid API key stored, never private key
- **Min deposit:** $10 hedge balance enforced before bot starts

---

## 10. Dashboard — Build Status

### ✅ Phase 1: Wallet Connect (complete — 2026-03-19)
- Rabby / MetaMask / EIP-1193 wallet connection
- Chain detection (Arbitrum, Ethereum, Base) with pill switcher
- Auto-reconnect on page reload, listener deduplication
- Navbar: address badge, chain badge, disconnect

### ✅ Phase 2: On-Chain Position Fetching (complete — 2026-03-19)
- NonfungiblePositionManager `balanceOf` + `tokenOfOwnerByIndex` + `positions()`
- Pool `slot0()` for current tick; tick-to-price math (accounts for stable/volatile ordering)
- In-range / out-low / out-high / closed status per NFT
- Range bar visual, % through range, fees owed (tokensOwed0/1)
- Price ticker: ETH/USDC + BTC/USDT via CoinGecko (30 s refresh)

### ✅ Phase 3: Dashboard UX Enhancements (complete — 2026-03-20)

**Bilingual (ES/EN):**
- `landing/i18n.js` — full TRANSLATIONS object (~170 keys each language)
- `window.t(key)`, `window.setLanguage()`, `applyTranslations()`
- `data-i18n` / `data-i18n-html` / `data-i18n-placeholder` attributes throughout
- ES/EN toggle in both navbars; preference persisted in `localStorage (vf_lang)`

**Watch Address (read-only mode):**
- Enter any `0x…` address + pick chain → loads positions without wallet connection
- Public RPC with multi-endpoint fallback per chain (4-second probe + timeout):
  - Arbitrum: `arb1.arbitrum.io` → Ankr → llamarpc → BlastAPI
  - Ethereum: `cloudflare-eth` → Ankr → llamarpc
  - Base: `mainnet.base.org` → Ankr → llamarpc
- `0x` prefix cell + chain select + Watch button (shows `…` while probing)
- `👁 WATCHING` badge in wallet summary; chain pills switch RPC directly
- Styled as a card with neon cyan top-accent bar, matching brand system

**Active / History Tabs:**
- Tab bar below wallet summary with per-tab count badges
- **Active** — positions with liquidity (`in-range`, `out-low`, `out-high`)
- **History** — zero-liquidity / removed positions
- Instant filtering (no re-fetch); separate empty states per tab
- `ws-count` reflects currently visible tab

### ✅ Phase 4: Bot Protection Drawer (complete — 2026-03-20)

Each position card gains a collapsible **"Enable Protection"** drawer:

**Implemented in `landing/dashboard/dashboard.js` + `dashboard.css` + `i18n.js`:**

- **Auth flow**: wallet sign-in button in drawer → `GET /auth/nonce` → `signMessage("Sign in to VIZNAGO FURY\nNonce: {nonce}")` → `POST /auth/verify` → JWT stored in `localStorage['vf_jwt']`
- **Collapsible drawer** on every active position card; open/closed state persists across re-renders
- **Mode toggle**: Defensor Bajista / Avaro radio buttons (Avaro disabled for BTC pairs — golden rule enforced in UI and API)
- **Config form**: trigger %, hedge size %, HL API Key (64-hex private key, password field, red label), HL wallet address (yellow label)
- **Key validation**: 64-hex length check client-side before submit (prevents "20 bytes" bot crash)
- **Create or update**: `POST /bots` (new) or `PUT /bots/{id}` (existing inactive bot) → `POST /bots/{id}/start`
- **Active state**: replaces form with live status row + stop button; last event shown inline
- **Stop button**: styled red for clear destructive intent
- **Amber highlight**: unprotected positions show amber toggle to draw user attention
- **WebSocket**: `wss://{host}/trading/lp-hedge/api/ws/{config_id}?token={jwt}` auto-connects on activate, auto-reconnects after 10 s on drop, updates status row in real time
- **Live log terminal**: real-time stdout lines from bot subprocess shown in monospace terminal per bot
- **Live bots panel**: dynamic `#live-bots-section` replaces hardcoded static hedge panel; shows all active bots with range, trigger, last event, log terminal
- **Pre-fetch on load**: `GET /bots/{id}/status` called on page load for active bots to avoid "Verificando…" after refresh
- **Sign-in gate**: if no JWT, drawer shows "Sign In with Wallet" button
- **Watch mode**: drawer shows disabled message (no protection without wallet)
- **Bilingual**: all new strings added to `i18n.js` (ES + EN, ~30 keys each)
- **Nginx proxy**: already configured at `/trading/lp-hedge/api/` → port 8001 with WebSocket upgrade headers

### ✅ Phase 5: Admin & UX Hardening (complete — 2026-03-20)

- **Nuclear Stop button** (`☢ Stop All`): pulsing red button in navbar, visible only to admin wallets
  - `ADMIN_WALLETS` env var (comma-separated) → `is_admin: true` claim injected into JWT at sign-in
  - `POST /admin/stop-all`: server re-validates `is_admin` claim; terminates all bot subprocesses and marks all `active=False` (no auto-restart)
  - Confirmation modal with bot count before firing
  - Client decodes JWT (base64) for UI gating; server enforces independently (two-layer security)
- **Bot persistence across API restarts**: `_shutting_down` flag prevents `active=False` on graceful shutdown; `_auto_restart_bots()` in lifespan re-launches all `active=True` configs on startup
- **Auto-refresh off by default**: saves droplet resources; user-selectable intervals (Off / 1m / 3m / 5m / 10m) in navbar pill control; preference persisted in `localStorage['vf_refresh_interval']`
- **Unicorn favicon** 🦄: SVG emoji favicon (`data:image/svg+xml`) — Uniswap symbol, no image file needed
- **Waitlist CTA**: landing page "Inicia Tu Backtest" section replaced with email waitlist form; submissions stored in `localStorage` (Step 8 will wire to backend)
- **Standalone bot retired**: `live_hedge_bot.py` no longer runs as a standalone systemd service; all bot lifecycle now managed exclusively by BotManager via the SaaS API

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
| Root process risk | FastAPI service currently runs as root — creating dedicated `viznago` system user is an open item (Step 10 pre-req) |

---

## 12. Implementation Phases

| Step | Scope | Status |
|---|---|---|
| **0** | Dashboard Phase 1–3: wallet connect, positions, i18n, watch mode, tabs | ✅ Complete |
| **1** | MariaDB: create databases + user + schema | ✅ Complete |
| **2** | `live_hedge_bot.py` refactor: all config from env vars | ✅ Complete |
| **3** | FastAPI skeleton + auth (nonce + JWT + `/auth/*`) | ✅ Complete |
| **4** | Bot config CRUD endpoints + DB models | ✅ Complete |
| **5** | Bot Manager (spawn/stop/tail subprocesses) | ✅ Complete |
| **6** | WebSocket live event stream | ✅ Complete |
| **7** | Dashboard Phase 4 (protection drawer + WS client + live bots panel) | ✅ Complete |
| **7.5** | Admin hardening: nuclear stop, bot persistence, auto-refresh control, waitlist CTA | ✅ Complete |
| **8** | Subscription + USDC on-chain payment verification | 🔲 Pending |
| **9** | Email alerts per user (reuse existing email setup) | 🔲 Pending |
| **10** | Alpha test with 3–5 real users | 🔲 Pending |

**Estimated remaining to MVP: 1–2 weeks.**

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
