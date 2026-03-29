# VIZNAGO FURY — SaaS Option B: Hosted LP Hedge Bot Service
> Architecture & Implementation Plan — v1.5 (2026-03-21)
> Status: **Steps 0–8.5 Complete · Step 8 (Unlock Protocol) + Step 9 (Telegram) Pending**

---

## 1. Goal

Allow any user to connect their wallet to the VIZNAGO FURY dashboard, select a
Uniswap v3 LP position, configure hedge parameters, and activate a managed Bot
Defensor Bajista/Defensor Alcista instance — without running anything locally.

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

### 8.1 Plan Tiers

| Plan | Price | Active Bots | Check Interval | Alerts |
|---|---|---|---|---|
| Free | $0 | 0 (monitor only) | — | — |
| Starter | $29 USDC/mo | 1 | 30s | Telegram (high-priority) |
| Pro | $79 USDC/mo | 5 | 10s | Telegram (all events + commands) |

**No email required at any tier. Wallet + NFT Key = full identity.**

---

### 8.2 Payment — Unlock Protocol NFT Key on Arbitrum One

**Network: Arbitrum One** — confirmed. Same network as users' LP pools and Uniswap v3
positions. No bridging required — users pay subscriptions with the same wallet and USDC
they already have on Arbitrum.

Instead of a database subscription row, the user's plan is an **NFT sitting in their wallet**.
Access is gated by on-chain NFT ownership — no payment database, no trust-the-server.

**How it works:**

```
1. Deploy two "Lock" smart contracts on Arbitrum One (one-time, ~$0.10 total)
   → Starter Lock: 29 USDC / 30 days  (contract address → STARTER_LOCK_ADDRESS in .env)
   → Pro Lock:     79 USDC / 30 days  (contract address → PRO_LOCK_ADDRESS in .env)
   Deploy via: app.unlock-protocol.com → Create Lock → select Arbitrum One

2. User clicks "Subscribe" in dashboard
   → Wallet prompts: approve 29 USDC on Arbitrum → confirm (~$0.01–$0.05 gas)
   → One transaction → NFT "Key" lands in their wallet
   → NFT shows: "VIZNAGO FURY — Starter — expires April 21 2026"
   → NFT has a Key ID (e.g. Key #42) — this IS their subscription identity

3. API checks access on every sign-in (one on-chain call):
   lock.getHasValidKey(walletAddress) → true | false
   → true  → issue JWT with plan: starter
   → false → issue JWT with plan: free

4. Auto-renewal (optional):
   → User pre-approves contract to pull 29 USDC on expiry
   → Renews silently — no clicks, no support tickets
   → Cancel = revoke the ERC-20 approval. Done.
```

**What Unlock Protocol handles vs what you build:**

| Task | Owner |
|---|---|
| Collecting USDC on Arbitrum | Unlock smart contract |
| Minting NFT Key to user | Unlock smart contract |
| Expiry logic | Unlock smart contract |
| Auto-renewal pulls | Unlock smart contract |
| Withdrawing revenue to your wallet | You (via Unlock UI or direct contract call) |
| Checking if user has valid key | Your API — one `getHasValidKey()` call |

---

### 8.2.1 Cost Breakdown — Arbitrum One

**One-time deployment (you pay once, ever):**

| Action | Cost |
|---|---|
| Deploy Starter Lock contract | ~$0.03–$0.10 |
| Deploy Pro Lock contract | ~$0.03–$0.10 |
| **Total one-time** | **~$0.20** |

**Per subscription payment (ongoing):**

| Fee | Who pays | Starter | Pro |
|---|---|---|---|
| Unlock Protocol fee (1%) | Deducted from revenue | $0.29 | $0.79 |
| Key purchase gas | User | ~$0.01–$0.05 | ~$0.01–$0.05 |
| Revenue withdrawal gas | You | ~$0.01–$0.05 | ~$0.01–$0.05 |
| Unlock Labs monthly platform fee | Nobody | **$0** | **$0** |

**Net revenue per payment:**
```
Starter: $29.00 USDC collected → $28.71 to you (1% = $0.29 to Unlock DAO)
Pro:     $79.00 USDC collected → $78.21 to you (1% = $0.79 to Unlock DAO)
```

The 1% protocol fee goes to the Unlock DAO treasury — partially burned as UP tokens.
Not a SaaS fee. No company profits from it.

**Compared to alternatives:**

| Option | Fee | KYC | Privacy |
|---|---|---|---|
| **Unlock Protocol (Arbitrum)** | **1%** | **None** | **Full** |
| Stripe | 2.9% + $0.30 | Business KYC | None |
| Coinbase Commerce | 1% | Business KYC | None |
| Manual tx_hash (original plan) | 0% | None | Full — but no auto-renewal |

**Why Arbitrum is the right choice** (not Base, Polygon, or mainnet):
- Users already have USDC on Arbitrum — zero bridging friction
- Same wallet, same network as their Uniswap v3 LP positions
- Low gas: key purchase costs users ~$0.01–$0.05
- Native USDC (not bridged) — no wrapped token confusion
- Ethereum L2 security guarantees (vs Polygon PoS)

**Privacy:** No email, no KYC, no name. Wallet address + NFT Key ID = full identity.

---

### 8.3 Subscription Expiry with Open HL Position — Grace Period

**Critical edge case:** bot has an active short in profit when the Key NFT expires.
Killing the bot immediately could force-close a winning trade. This must never happen.

**Rule: never force-close an open position on expiry.**

```
Key expires
    ↓
Is there an active SHORT open?
    ├── NO  → stop bot immediately (clean)
    └── YES → enter GRACE PERIOD
                  │
                  ├── Position closes naturally via trailing SL
                  │       └──→ bot stops · user notified
                  │
                  ├── User renews within 72h
                  │       └──→ back to ACTIVE seamlessly
                  │
                  └── 72h pass, position still open
                          → urgent Telegram alert to user
                          └── 48h more, no renewal
                                  → close at market → bot stops
```

**Grace period rules:**
- Bot runs in `grace_period` mode: manages existing position only, opens NO new shorts
- Hard cap: 72h grace + 48h urgent warning = 120h maximum before force-close
- Renewal during grace → seamless return to normal, no restart needed
- All state transitions logged to `bot_events` table

**Bot mode env var injected by BotManager:**
```
BOT_MODE=active        → normal operation
BOT_MODE=grace_period  → manage existing position only, no new entries
BOT_MODE=closing       → close position at market immediately, then exit
```

**Subscription watchdog:** background task in API checks every hour for expired keys
with open positions and transitions bot mode accordingly.

---

### 8.4 Backend pieces to build

- `GET /subscription` — current plan, Key NFT token ID, expiry date, days remaining
- `GET /admin/overview` — already includes plan per pool (complete ✅)
- On-chain Key check in `api/auth.py`: `getHasValidKey()` called on JWT issuance
- Subscription watchdog async task (expiry + grace period state machine)
- Plan enforcement in BotManager: check plan tier before `start()`, enforce bot count limits
- Deploy Starter + Pro Lock contracts on Arbitrum via `app.unlock-protocol.com`

**Open decisions before building:**
- [ ] Confirm Starter price: $29 USDC/mo
- [ ] Confirm Pro price: $79 USDC/mo
- [ ] Confirm Free plan: monitor-only OR 7-day trial with 1 active bot?
- [ ] Deploy Lock contracts → get contract addresses for `.env`

---

## 9. Alerts — Telegram Bot (Anonymous, Real-Time)

### 9.1 Why Telegram + NFT Key is the right alert channel

DeFi users are pseudonymous by default. Requiring an email address to receive alerts
creates a wallet → real-world identity linkage that breaks user trust and may deter
serious LP holders. Telegram + NFT Key solves this cleanly:

```
Unlock Protocol NFT Key  →  subscription identity (on-chain)
Telegram Bot             →  alert delivery (off-chain, pseudonymous)

Neither requires a name, email address, or any real-world identity.
The NFT Key ID IS the identity bridge.
```

| Property | Email | Telegram + NFT Key |
|---|---|---|
| Identity revealed | Yes — email = real person | No — just a number |
| Delivery speed | Minutes (spam filters) | Instant push |
| DeFi users already use it | Maybe | Almost universally |
| Two-way commands | No | Yes |
| Infrastructure cost | SMTP + domain setup | One bot token (free) |
| Personal data stored | Email address | Nothing identifiable |

**Email remains optional** — available for users who explicitly opt in (e.g. subscription
receipts, grace period warnings). Never mandatory.

---

### 9.2 Setup flow (one-time per user)

```
1. User mints NFT Key #42 → Starter plan activated
2. Dashboard shows: "Enable Telegram Alerts"
   → "Message @ViznagoFuryBot and send: /start 42"
3. User opens Telegram → sends /start 42
4. Bot verifies Key #42 owner matches their connected wallet (on-chain)
5. Stores: { nft_key_id: 42, telegram_chat_id: 7291834 }
6. Replies: "✅ Alertas activadas para Key #42"

No email. No name. Nothing identifiable stored on Viznago's side.
```

---

### 9.3 Alert events per plan

| Event | Starter | Pro |
|---|---|---|
| `hedge_opened` — short opened | ✅ | ✅ |
| `sl_hit` — stop loss fired | ✅ | ✅ |
| `tp_hit` — take profit hit | ✅ | ✅ |
| `error` — bot crashed | ✅ | ✅ |
| `breakeven` — SL moved to entry | ❌ | ✅ |
| `started` — bot confirmed running | ❌ | ✅ |
| `stopped` — bot stopped | ❌ | ✅ |
| Subscription expiry warning | ✅ | ✅ |
| Grace period alert (open position) | ✅ | ✅ |

---

### 9.4 Alert message format

```
🚨 SHORT ABIERTO — ETH/USDC NFT #5364575
Par: ETH-PERP · Trigger: entrada desde arriba
Precio: $2,180.00 · Tamaño: 0.045 ETH
Leverage: 5x · SL inicial: $2,191.00

🛡️ BREAKEVEN ACTIVADO
SL movido a precio de entrada $2,180 · PnL actual: +1.0%

🛑 TRAILING STOP ACTIVADO
Precio cierre: $2,095 · PnL: +2.3% · Duración: 4h 23min

❌ BOT CAÍDO — acción requerida
NFT #5364575 · Error: HL API timeout
Ingresa al dashboard para reiniciarlo.

⚠️ SUSCRIPCIÓN EXPIRADA — short activo en curso
Grace period activo. 72h para renovar tu Key NFT.
Posición actual: PnL +1.8% · SL trailing activo
```

---

### 9.5 Two-way commands (Pro plan)

```
/status   → current bot state, PnL, SL price, time running
/stop     → request bot stop (asks /confirm before acting)
/confirm  → confirms a pending /stop command
/help     → list available commands
```

This lets Pro users manage their bot from Telegram without opening the dashboard —
critical for traders on the move.

---

### 9.6 Privacy architecture

```
What Viznago stores:
  nft_key_id:        42          ← on-chain number, not a person
  telegram_chat_id:  7291834     ← Telegram's internal ID number

What Viznago does NOT store:
  ✗ Name
  ✗ Email address
  ✗ Phone number
  ✗ Telegram username
  ✗ IP address
  ✗ Any real-world identity
```

---

### 9.7 Backend pieces to build

- **Telegram Bot**: create via `@BotFather` → get `TELEGRAM_BOT_TOKEN` → store in `.env`
- **Webhook endpoint** `POST /telegram/webhook`: parse `/start <key_id>`, verify NFT
  ownership on-chain, store `{ nft_key_id, telegram_chat_id }` in new `telegram_links` table
- **Alert dispatcher** `api/telegram_alerts.py`: async `send_alert(config_id, event, details)`
  — looks up `telegram_chat_id` by config → sends via Bot API
- **Hook into BotManager** `_handle_event()`: fire `send_alert()` as background task after
  DB write + WS broadcast (non-blocking)
- **Command handler**: `/status` queries live bot state + last event; `/stop` triggers
  `manager.stop(config_id)` after `/confirm`
- **New DB table**: `telegram_links (nft_key_id, telegram_chat_id, linked_at)`

---

## 10. Golden Rules (Enforced in Bot Code)

These rules from Bootcamp Cripto 2026 are enforced server-side regardless
of user config — not just UI hints:

- **BTC: NEVER short** — bot refuses to open SHORT on BTC pairs
- **ETH:** long + short OK (Defensor Bajista + Defensor Alcista modes)
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
- **Mode toggle**: Defensor Bajista / Defensor Alcista radio buttons (Defensor Alcista disabled for BTC pairs — golden rule enforced in UI and API)
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
| **8.5** | Admin monitoring dashboard: pool health, HL live positions, event history, fills, wallet acquisition funnel | ✅ Complete |
| **8** | Subscriptions via Unlock Protocol NFT Keys + grace period state machine | 🔲 Pending |
| **9** | Telegram Bot alerts (anonymous, NFT Key linked, two-way commands) | 🔲 Pending |
| **10** | Alpha test with 3–5 real users | 🔲 Pending |
| **W1** | VIZNAGO WHALE — leaderboard tracker, position diffing, copy-trade signals, dashboard panel | ✅ Complete |
| **W2** | Whale signal enrichment — leverage, liq price, margin, ROE%, funding delta in every signal row | ✅ Complete |
| **W3** | Whale Intelligence Agent Phase 1 — HistoryStore, PatternEngine, SignalEnricher, convergence panel | 🔲 Planned |
| **W4** | Whale Intelligence Agent Phase 2 — backtest framework, Telegram CRITICAL alerts, pinned watchlist | 🔲 Planned |

**Estimated remaining to MVP: 1–2 weeks.**

---

## 13. Feature Modules

In addition to the core SaaS steps above, VIZNAGO ships three intelligence modules:

| Module | Doc | Status |
|--------|-----|--------|
| VIZNAGO WHALE — Tracker | [WHALE_TRACKER.md](WHALE_TRACKER.md) | ✅ Live |
| VIZNAGO WHALE — Intelligence Agent | [WHALE_INTELLIGENCE_AGENT.md](WHALE_INTELLIGENCE_AGENT.md) | 🔲 Planned |
| FURY RSI Bot + Backtest | [RSI_AI_STRATEGY_RESEARCH.md](RSI_AI_STRATEGY_RESEARCH.md) | ✅ Live (ETH) |

---

## 14. Post-Alpha Upgrade Path

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

## 15. Open Decisions (For Review)

**Blocking Step 8 (Subscriptions):**
- [x] Network confirmed: **Arbitrum One** (same network as users' LP pools)
- [ ] Deploy Starter Lock on Arbitrum via app.unlock-protocol.com → add `STARTER_LOCK_ADDRESS` to `.env`
- [ ] Deploy Pro Lock on Arbitrum via app.unlock-protocol.com → add `PRO_LOCK_ADDRESS` to `.env`
- [ ] Confirm Starter plan price: $29 USDC/mo
- [ ] Confirm Pro plan price: $79 USDC/mo
- [ ] Free plan: monitor-only dashboard OR 7-day trial with 1 active bot?

**Blocking Step 9 (Telegram):**
- [ ] Create `@ViznagoFuryBot` via Telegram `@BotFather` → store `TELEGRAM_BOT_TOKEN` in `.env`
- [ ] Confirm two-way commands scope for Pro plan (`/status`, `/stop` — see Section 9.5)

**Infrastructure (pre-alpha):**
- [ ] Create dedicated `viznago` Linux system user (API currently runs as root — security risk)
- [ ] Configure Telegram webhook URL in production (`POST /telegram/webhook`)

---

*VIZNAGO FURY — Bootcamp Cripto 2026 · LP + Perps Hedge Strategy*
