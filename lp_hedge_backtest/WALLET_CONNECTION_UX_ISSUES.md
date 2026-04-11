# Wallet Connection & Session State — UX Issues Tracker
**Created:** 2026-04-11  
**Priority:** 🔴 Critical UX  
**Context:** First surfaced during live LP test with wallet `0xB901326…Bf7D` after Rabby extension auto-update triggered a full session wipe.

---

## Background

VIZNIAGO uses a JWT-based auth flow: wallet signs a nonce → JWT stored in `localStorage` (`vf_jwt`). Every protected API call (`GET /bots`, WebSocket, HL balance) requires this JWT. If it is lost, the user sees an empty dashboard — **no bot cards, no protection status, no live log** — with no clear explanation of why.

The risk is highest for Web3 wallet extensions (Rabby, MetaMask) because they fire browser events (`accountsChanged`, `chainChanged`) outside the page's control, and those events can trigger session teardown.

---

## Incident Log

### INC-001 — 2026-04-11 — Rabby Extension Update Wipes Session
**Reporter:** Owner wallet `0xB901326…`  
**Symptom:** Woke up → VIZNAGO DeFi page showed no bot card. Hard refresh → Rabby prompted re-sign. Extension update popup was visible in the browser.  
**Root cause:** Rabby auto-updated overnight. Extension reload fired `accountsChanged([])` → `handleAccountsChanged` called `disconnectWallet()` → `localStorage.removeItem('vf_jwt')`. JWT gone. Dashboard in anonymous/guest mode.  
**Impact:** User could not see running bot (bot 17 was healthy on the server). Required manual re-authentication.  
**Fix applied:** `dashboard.js` — 300 ms debounce on `accountsChanged([])`. If a real account arrives within 300 ms, the disconnect is suppressed (transient switch, not a true disconnect). Genuine disconnects (wallet locked, extension removed) still fire.  
**Status:** ✅ Fixed in commit `0a8021b`

---

### INC-002 — 2026-04-11 — Wrong Account Selected in Rabby During Re-Auth
**Reporter:** Owner  
**Symptom:** After INC-001, user re-authenticated. Rabby had `0xB901326…` as active. That wallet had zero `bot_configs` → dashboard showed empty state → perceived as "orphan bot."  
**Root cause:** `0xB901326…` is the designated LP wallet (new, no bots configured yet). `0xeF0DDF…` is the admin wallet. Rabby switched to the new wallet; user expected admin wallet.  
**Impact:** Confusion + 2-hour troubleshooting session. No actual data loss or bot disruption.  
**Fix applied:** None needed in code — correct wallet was identified. Bot 17 was created for `0xB901326…`. Improved understanding of two-wallet architecture.  
**Status:** ✅ Resolved (operational, not a code bug)

---

### INC-003 — 2026-04-11 — Live Log Empty on Bot Start (Race Condition)
**Reporter:** Owner  
**Symptom:** Bot 17 just started. Dashboard protection drawer showed live log as completely empty.  
**Root cause:** `saasLoadBots()` calls `GET /bots/17/events?hours=72` immediately after `POST /bots/17/start`. The `started` event is emitted by the bot subprocess ~2–3 seconds later. All three events queries (08:17:14, 08:17:16 × 2) returned 0 results. WebSocket for bot 17 connected 2 minutes later (08:19:22) due to dashboard re-render cycle. Log appeared empty during that gap.  
**Impact:** User thought bot was broken. Bot was healthy — logs arrived after WS connected.  
**Fix applied:** None yet (see open items below).  
**Status:** 🟡 Partially mitigated (localStorage cache helps on reload). Startup race still exists.

---

### INC-004 — 2026-04-11 — Duplicate Bot Conflict (Bot 16 + Bot 17, Same NFT + HL Wallet)
**Reporter:** Owner  
**Symptom:** After bot 17 was created for `0xB901326…`, bot 16 (admin wallet `0xeF0DDF…`) was still running. Both watched NFT #5413901 and used `0xeF0DDF…` as the HL wallet. Two independent bots could have opened conflicting positions.  
**Root cause:** Bot 16 was previously the admin test bot for the same NFT. It was not deactivated when the proper LP wallet (`0xB901326…`) came online.  
**Impact:** Double-hedge risk. Resolved before any trigger fired (ETH was IDLE in range).  
**Fix applied:** Bot 16 stopped via API (`POST /bots/16/stop`), `active=0` in DB. Bot 17 is now the sole bot for NFT #5413901.  
**Status:** ✅ Fixed manually. See open item below for prevention.

---

## Open UX Issues (Not Yet Fixed)

### UX-001 — No "Session Lost" Visual When JWT Is Cleared
**Priority:** 🔴 High  
**Description:** When the JWT is wiped (extension update, account switch, expiry), the dashboard silently reverts to guest mode. The user sees no bot cards and no explanation. They may think the platform is down or the bot crashed.  
**Expected behavior:** Show a persistent amber banner: *"Your session ended. Sign in again to see your bots."* with a sign-in button. Do NOT just show the empty state silently.  
**Affected files:** `dashboard.js` — `disconnectWallet()`, `showSessionExpiredBanner()` (already exists for 401 expiry, extend to cover `disconnectWallet()` path)  
**Effort:** Small (1–2h)  
**Fix applied:**
- `dashboard.js` — `disconnectWallet()` now accepts `{ showBanner: false }` option. Before clearing state, checks if a session was active (`saas.jwt` or `localStorage vf_jwt`). If `showBanner: true` and `hadSession`, calls `showSessionExpiredBanner()`.
- `dashboard.js` — `handleAccountsChanged` debounce now calls `disconnectWallet({ showBanner: true })` so Rabby/MetaMask involuntary disconnects show the banner.
- Voluntary "Disconnect" button calls `disconnectWallet()` with no argument — no banner shown (user knows they disconnected).
- `index.html` — Updated banner text to English: *"Your session ended — your bots are still running. Sign in again to see your dashboard."*  
**Status:** ✅ Fixed

---

### UX-002 — Live Log Empty for ~2 Min After Bot Starts (Race Condition)
**Priority:** 🟡 Medium  
**Description:** `saasLoadBots()` fetches events immediately after `POST /bots/{id}/start`. The `started` event is written ~2–3 s later by the subprocess. The log panel shows empty until the WebSocket connects (~1–2 min) or the page is refreshed.  
**Expected behavior:** After starting a bot, auto-reload events after a short delay (e.g. 3 s) to catch the `started` event. Or poll once at T+5s as a safety net.  
**Fix applied:** `dashboard.js` — in `activateProtection`, after `connectBotWS(configId)` a `setTimeout(..., 3000)` fires one `GET /bots/{id}/events?limit=10` call. Results are de-duped (`.includes(line)` check) and appended to `saas.logs[configId]`, then `renderLiveBots()` is called to repaint the log panel with the `started` entry.  
**Affected files:** `dashboard.js` — `activateProtection` function  
**Effort:** Small (30 min)  
**Status:** ✅ Fixed

---

### UX-003 — No Duplicate Bot Guard When Creating a New Bot Config for an Already-Watched NFT
**Priority:** 🔴 High  
**Description:** A user (or admin) can create a second `bot_config` for an NFT that is already being watched by another config. Two bots then independently hedge on the same HL wallet. This is a financial risk.  
**Expected behavior:**
- Backend (`POST /bots`): check if any `bot_config` with `nft_token_id = X` and `active = true` already exists (regardless of `user_address`). If so, reject with `409 Conflict: NFT #X is already being actively hedged by another bot.`
- Frontend: surface the 409 as an inline error in the protection drawer.  
**Affected files:** `api/routers/bots.py` — `create_bot` endpoint  
**Effort:** Small (1h backend + 30 min frontend)  
**Fix applied:**
- `api/routers/bots.py` — `create_bot`: queries for any active `BotConfig` with same `nft_token_id` before inserting; returns HTTP 409 with detail message.
- `landing/dashboard/dashboard.js` — `apiCall`: attaches `e.status = res.status` to thrown errors so callers can branch on HTTP status code.
- `landing/dashboard/dashboard.js` — `activateProtection` catch block: on `err.status === 409`, injects a red inline error banner inside the protection drawer (`prot-inline-error`) instead of the generic toast. Button re-enables so user can act.
- Tested: `POST /bots` with NFT 5413901 (bot 17 active) → `HTTP 409 {"detail":"NFT #5413901 is already being actively hedged by another bot."}` ✅  
**Status:** ✅ Fixed

---

### UX-004 — Rabby Extension Update Still Disconnects If User Has No JWT (Edge Case)
**Priority:** 🟡 Medium  
**Description:** The 300 ms debounce (INC-001 fix) works when `accountsChanged([account])` arrives within 300 ms of the empty-array event. Rabby extension restarts can take longer than 300 ms to fully reload, meaning the debounce may not always suppress the disconnect.  
**Expected behavior:** On page load, if `vf_jwt` exists in `localStorage` but `saas.jwt` is null (page just refreshed), do not call `disconnectWallet()` from `accountsChanged` until at least one `eth_accounts` check has been performed by `init()`.  
**Fix applied:**
- `dashboard.js` — `window._initComplete = false` set at module scope before `init()`.
- `init()` — sets `window._initComplete = true` in all exit paths of the `eth_accounts` promise (success, no-accounts, error, no-ethereum).
- `handleAccountsChanged` — the 300 ms debounce now also checks `window._initComplete`; `disconnectWallet` is not called if init hasn't finished its own accounts check yet.  
**Affected files:** `dashboard.js` — `init()`, `handleAccountsChanged()`  
**Effort:** Small (1h)  
**Status:** ✅ Fixed

---

### UX-005 — No Warning When User Connects Wrong Wallet (LP vs HL Mix-Up)
**Priority:** 🟡 Medium  
**Description:** Users with multiple wallets in Rabby may sign in with the wrong address. If that wallet has no bots, they see an empty state with no hint that they might be on the wrong account.  
**Expected behavior:** If `GET /bots` returns an empty array AND the wallet has LP positions detected on-chain (via `fetchPositions()`), show a hint: *"Your LP positions don't have any bots yet. Create one in the protection drawer, or check if you're connected with the right wallet."*  
**Fix applied:**
- `saas.botsLoaded` flag added to `saas` state object (default `false`). Set to `true` in `saasLoadBots` after the first successful `GET /bots` response. Reset to `false` in `disconnectWallet`.
- `renderLiveBots()` — empty-state branch now checks: `saas.botsLoaded && saas.jwt && state.positions.length > 0`. If true, renders a green-tinted info box: *"No bots configured yet. Your LP positions don't have any protection bots. Create one using the protection drawer on each position, or check that you're connected with the correct wallet."*
- No extra API calls needed — positions are already in `state.positions` from `fetchPositions()`.  
**Affected files:** `dashboard.js` — `saas` init, `saasLoadBots()`, `disconnectWallet()`, `renderLiveBots()`  
**Effort:** Medium (2–3h, requires correlating on-chain positions with DB bots)  
**Status:** ✅ Fixed

---

### UX-006 — WebSocket Auto-Reconnect Not Firing After API Service Restart
**Priority:** 🟡 Medium  
**Description:** When `viznago_api.service` restarts, all WebSocket connections drop. The dashboard's reconnect logic (10 s retry if `bot.active && saas.jwt`) should re-establish connections, but during the restart window the JWT may be valid while the API is not yet accepting connections — the reconnect silently fails and is not retried again.  
**Expected behavior:** Implement exponential backoff (1s, 2s, 4s, 8s… up to 60s) for WebSocket reconnects. Show a small "reconnecting…" pill in the live log panel during the gap.  
**Fix applied:**
- `saas._wsRetry = {}` added (per-bot retry counter, reset on disconnect and on successful `onopen`).
- `connectBotWS()` — `ws.onopen` resets `saas._wsRetry[configId] = 0`.
- `ws.onclose` — if bot is still active and JWT valid: computes `delay = min(1000 * 2^attempt, 60000)`, appends `"⟳ Connection lost — reconnecting in Xs…"` to the live log, then `setTimeout(connectBotWS, delay)`. Sequence: 1s → 2s → 4s → 8s → 16s → 32s → 60s (capped).
- Non-retried exits (bot stopped or logged out) return immediately without scheduling a retry.
- `saas._wsRetry` reset in `disconnectWallet` so counters don't carry across sessions.  
**Affected files:** `dashboard.js` — `connectBotWS()`, `disconnectWallet()`  
**Effort:** Medium (2–3h)  
**Status:** ✅ Fixed

---

## Architecture Note — Two-Wallet Pattern

VIZNIAGO supports a clean separation of LP and HL wallets:

```
LP Wallet  (0xB901326…)   ← Signs into dashboard, owns Uniswap NFT
       ⬇ protected by
HL Wallet  (0xeF0DDF…)    ← Holds hedge capital, executes shorts on Hyperliquid
```

- The LP wallet is the **signing identity** for the VIZNIAGO dashboard (JWT subject).
- The HL wallet is stored in `bot_configs.hl_wallet_addr` and `hl_api_key` (encrypted).
- They can be the same address (single-wallet mode, as in early admin testing) or different (recommended production pattern).
- Wallet Manager v2 (`landing/wallet/index.html`) is the dedicated page for managing the LP ↔ HL relationship.

**Risk:** If a bot is set up with the LP wallet also acting as HL wallet (`hl_wallet_addr = user_address`), and the user later creates a second bot for the same NFT from a different LP wallet (two-wallet pattern), both configs share the same HL wallet and WILL conflict. UX-003 prevents this at the API level.

---

## Fix Priority Queue

| ID | Issue | Effort | Priority |
|----|-------|--------|----------|
| UX-003 | ~~Duplicate bot guard on same NFT~~ | 1.5h | ✅ Fixed |
| UX-001 | ~~"Session lost" banner instead of silent empty state~~ | 1.5h | ✅ Fixed |
| UX-002 | ~~Live log empty 2 min after bot start~~ | 30 min | ✅ Fixed |
| UX-004 | ~~Debounce may not cover slow extension restarts~~ | 1h | ✅ Fixed |
| UX-005 | ~~Wrong wallet hint when LP positions exist but no bots~~ | 2–3h | ✅ Fixed |
| UX-006 | ~~WS exponential backoff + reconnecting pill~~ | 2–3h | ✅ Fixed |
