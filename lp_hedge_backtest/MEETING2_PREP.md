# VIZNIAGO — 2nd Investor Meeting Preparation
*Prepared: 2026-04-03 | Based on: DeFi Suite (Jaime & Raul) platform comparison*

---

## Reference Material Reviewed

- 5 screenshots of DeFi Suite (Talent Academy Bootcamp Cripto 2026)
- Release notes: DeFi Suite latest deployment (9.txt)
- Context: investor user shared these as reference after 1st meeting

---

## What DeFi Suite Currently Shows (Screenshots)

### LP Position Card (Image 1)
- Compact header bar: Valor LP · Entry · PNL · APR · Fee APR · Fees
- Full P&L breakdown separating **capital IL** from **fees earned**
- **Fee projections**: Diario / Semanal / Mensual / Anual ($ and %)
- APR Total + APR Fees displayed prominently

### Protection Config Modal (Image 2)
- HL balance shown **immediately** inside the modal
- **Buffer de Capital** as pill buttons: Sin / +10% / +20% / +30% / +40% / +50%
- Capital formula shown explicitly: `pool $754 + 50%`
- Margin calculator: Margen requerido / Balance wallet / Disponible después
- "No proteger cuando reentra al rango desde arriba" checkbox

### Active Bot View (Image 3)
- **TRIGGERS**: both lower and upper range bounds shown
- **DISTANCIA**: % distance to nearest trigger (-1.65% from $2,139.91)
- CAPITAL amount + source formula
- LEVERAGE displayed
- Bot wallet address shown (truncated)

### Platform Structure (Image 5 — Talent Academy DeFi Suite)
- Tabs: Wallets / Hedge (Haragán) / Trading (Avaro) / Insider (Catador) / **Backtesting 2024-2026**
- Backtesting **integrated in platform** (not separate page)
- ETH/USD 180% APR / BTC/USD 800% APR shown as tabs
- Results by year: 2024 / 2025 / 2026

### Insider (Catador) Bot Config (Image 7)
- Mean-reversion bot trading **inside** the range
- **Take Profit Escalonado**: 25% / 50% / 75% / 100% of range (each closes 25%)
- Buffer Interior slider
- Breakeven % slider (1–5%)
- Auto-rearm checkbox

---

## Their Latest Release (9.txt) — Key Upgrades

### Architecture shift: Real HL orders vs code-evaluated
Their TPs and SLs are now placed as **native Hyperliquid trigger orders**, not evaluated
by bot code. This means they execute even if the bot process is down.

> VIZNIAGO risk: if `live_hedge_bot.py` crashes, open positions have no SL protection
> until the process restarts. This is a resilience gap worth addressing.

### New features shipped:
| Feature | Bot | Notes |
|---|---|---|
| Pre-trigger configurable | Ávaro + Catador | Distance before range edge to fire (0% = exact edge) |
| 3 staged TPs as real HL orders | Ávaro | TP1/TP2/TP3 — % gain + % close each |
| Breakeven SL → range edge | Ávaro | Not entry price — more logical |
| Ladder TPs as real HL orders | Catador | 25/50/75% of range |
| TP at breakeven + auto SL move | Catador | Places real TP, moves SL when executed |
| Default leverage 20x (was 10x) | Both | Max 20x BTC/ETH, 15x others |
| Auto-reactivation after balance SL | Both | < 5 min, no manual restart |
| Smarter margin calc | Both | Request vs execution distinction |
| Orphan order cleanup | Both | Cancels TPs on SL, cancels SL on last TP |
| Duplicate SL fix | Both | Verifies + cleans duplicates |

---

## Audio Transcript Findings (4.1 / 6.1 / 8.1)

### 4.1 — Buffer Capital bidirectional logic (Jaime)
- +50% buffer is their **tested and audited default** — not just a setting, it's the recommended config
- Key insight: **deactivate "no proteger desde arriba"** so the bot opens a SHORT when price breaks ABOVE the range too
- With +50% extra capital, that SHORT protection is extra strong — covers commissions of failed opens and gains

### 6.1 — Backtesting as acquisition tool (Raul)
- Historical data loaded: **Q1 2026 + all 2025 + 2024** in daily candles
- Backtester variables include: leverage, capital per bot, Stop Plus, and **monthly reinvestment %**
- Raul personally uses **50% reinvest / 50% withdraws** — offered as educational reference
- **Available to ALL users including free tier** — explicit acquisition/lead strategy

### 8.1 — Catador (Insider) bot TP ladder (Raul)
- **Breakeven trigger configurable**: default 1% gain → SL moves to breakeven. User can raise the threshold.
- **Escalonado TPs**: range divided into 4 equal quarters, default 25% close at each quarter
- Fully configurable: e.g. 25% close at 50% range, rest at 75%, 100% — user manages risk
- Closes at 75% of range (not 100%) as a valid aggressive-conservative middle ground

### New gaps identified from audio
| Gap | DeFi Suite | VIZNIAGO | Priority |
|---|---|---|---|
| Upper + lower trigger both visible in bot card | ✅ Both shown | ❌ Lower only | 🔴 High |
| Monthly reinvestment % in backtester | ✅ | ❌ | 🟡 Medium |
| +50% buffer as default (not user-set) | ✅ Audited default | Manual input | 🟡 Medium |
| Backtester open to free users | ✅ | Check current | 🟡 Medium |
| Catador breakeven % (configurable threshold) | ✅ 1% default | Check | 🟡 Medium |

---

## Gap Analysis: VIZNIAGO vs DeFi Suite

| Feature | DeFi Suite | VIZNIAGO | Priority |
|---|---|---|---|
| Fee projections (daily/weekly/monthly/annual) | ✅ | ❌ | 🔴 High |
| APR + Fee APR in position header | ✅ | ❌ | 🔴 High |
| Distance to trigger % | ✅ | ❌ | 🔴 High |
| Both triggers (upper + lower) in bot card | ✅ | ❌ Lower only | 🔴 High |
| HL balance in protection modal | ✅ | Wallet dropdown only | 🔴 High |
| IL vs Fees P&L split | ✅ | ❌ | 🟡 Medium |
| Buffer Capital pill selector | ✅ | Slider only | 🟡 Medium |
| +50% buffer as tested default | ✅ Audited | Manual | 🟡 Medium |
| Integrated backtesting | ✅ in platform | Separate page | 🟡 Medium |
| Monthly reinvestment % in backtester | ✅ | ❌ | 🟡 Medium |
| Backtester open to free tier | ✅ | Check | 🟡 Medium |
| Catador escalonado TP ladder | ✅ | ❌ | 🟡 Medium |
| Configurable breakeven % threshold | ✅ 1% default | Check | 🟡 Medium |
| TPs/SLs as real HL orders | ✅ | ❌ Code-evaluated | 🔴 Resilience risk |
| Auto-reactivation after balance SL | ✅ < 5 min | Partial (AUTO_REARM) | 🟡 Medium |
| Orphan order cleanup | ✅ | Needs verification | 🟡 Medium |
| **Whale Tracker** | ❌ | ✅ | VIZNIAGO differentiator |
| **Whitepaper** | ❌ | ✅ | VIZNIAGO differentiator |
| **Forensic event history** | ❌ | ✅ | VIZNIAGO differentiator |
| **NFT ID search / Explorar** | ❌ | ✅ | VIZNIAGO differentiator |
| **Roadmap** | ❌ | ✅ | VIZNIAGO differentiator |
| **Non-custodial emphasis** | Not stated | ✅ | VIZNIAGO differentiator |

---

## 2nd Meeting Tier List

### TIER 1 — High visual impact, close gap fast (frontend only)

| ID | Item | Effort | Why | Status |
|---|---|---|---|---|
| M2-1 | Fee projections on position card (daily/weekly/monthly/annual) | Low | Most compelling investor metric — shows yield potential at a glance | ✅ Done (prior session) |
| M2-2 | APR + Fee APR in position card header | Low | They see value immediately, no scrolling needed | ✅ Done (prior session) |
| M2-3 | Distance to trigger % + show BOTH upper and lower triggers in active bot card | Low | "How close is the bot to firing?" — both directions; they show upper+lower | ✅ Done (prior session) |
| M2-4 | HL balance shown inside protection config modal | Low | Direct investor meeting 1 feedback, they already have it | ✅ Done |

### TIER 2 — UX parity + important improvements

| ID | Item | Effort | Why | Status |
|---|---|---|---|---|
| M2-5 | IL vs Fees P&L split on position card | Medium | Honest breakdown — fees are good news, IL is the cost | 🔲 |
| M2-6 | Buffer Capital pill buttons (Sin/+10/+20/+30/+50%) | Low | Cleaner than slider, shows options at a glance | ✅ Done 2026-04-25 — pills above hedge slider (Sin/+10%/+20%/+30%/+50%/+100%), click syncs slider + highlights active pill via `setHedgePill()` |
| M2-7 | Backtesting link/embed inside LP Defensor | Low | Bring it closer to the product, not a separate page | ✅ Done 2026-04-25 — `📊 Ver Backtester →` link added to position card footer, links to landing page backtester |
| M2-8 | Orphan order cleanup audit | Medium | Resilience — verify TPs cancel on SL and vice versa | 🔲 |
| T1-3 | Forensic PnL label fix in bot events | Low | Dashboard showed PnL as `$3.25` (dollar amount) but `pnl` field stores a percentage — misleading for investors. Fix: changed label from `$X.XX` to `X.XX%` in dashboard event rows and active bot status line (`dashboard.js`). Also a VIZNIAGO differentiator: price at every bot event (D3). | ✅ Done 2026-04-25 |
| T2-6 | HL API connection status indicator in LP section | Low | Investor ask — confirm HL connection is live without navigating away. Added `● API Online` / `● Sin conexión` chip next to HL Balance bar on active bot view, derived from `_hlBalanceCache` result. Pure frontend, no restart. | ✅ Done 2026-04-25 |
| M2-12 | Frontend restart/maintenance guard | Low | UX resilience — auto-detect API unavailability, show non-dismissible "Reconnecting…" overlay + disable all interactive elements (buttons/forms) during maintenance flag or outage. Reuses existing `/status/maintenance` poll. Two layers: (1) maintenance flag disables UI, (2) 2x consecutive health check fails triggers overlay. Frontend only, zero backend change, zero restart needed. | ✅ Done 2026-04-22 |
| M2-14 | Bot event session grouping in EVENTOS DEL BOT | Low | Events accumulate across test + live sessions — investors see confusing mixed history. Group by "Bot Iniciado" boundary: latest session expanded, older sessions collapsed (▶ Sesión 02 abr · 12:43 PM · 3 eventos). Full history preserved, never deleted. Pure frontend, zero API/backend change. Three options considered: A) filter pill, B) session grouping (recommended), C) separator label. | ✅ Done |
| M2-15 | Delete internal test events for NFT 5403096 (investor bot) | Low | Test events from pre-meeting session (12:43, 1:10, 1:14 PM) appear in investor's bot card. These were created during internal testing, not by the investor. "SHORT Cerrado" orphaned in current session is misleading — no real HL trade happened. Decision: delete rows from bot_events where config_id = (NFT 5403096 config) AND ts < 2026-04-04 14:43:00. **Requires careful DB access review before executing — do NOT run without explicit coordination.** | 🔲 Pending review |
| M2-19 | DeFi menu reorder across all pages — Wallet → LP Defensor → Explorar → Whale | Low | Investor-requested (2026-04-16 meeting). Reordered all 6 pages: index, dashboard, wallet, explore, whale, whitepaper. Landing page also gained missing Explorar entry. Zero API restart needed. | ✅ Done 2026-04-16 |
| M2-20 | Fix `reentry_guard_cleared` logged as ❌ Error in bot events | Low | Bot emits `reentry_guard_cleared` event type but it wasn't in the DB enum — MariaDB rejected it and exception handler stored it as `error`. UI showed ❌ for a normal housekeeping event. Two-part fix: (1) ALTER TABLE added `reentry_guard_cleared` to MariaDB enum, existing misclassified row corrected in DB; (2) SQLAlchemy Python enum in `api/models.py` was also missing the value — caused 500 on `/admin/overview` (LookupError). Added to models.py + API restart. Dashboard `typeMap` already had `🔓 Re-entrada Lista` mapping. Admin overview confirmed 200 after restart. | ✅ Done 2026-04-16 |

### Live Session Improvements (2026-04-04 — during investor meeting)

| Item | Description | Status |
|---|---|---|
| HL Wallet + API Key reordered to top of form | Moved credentials to position 2 (right after header, before HL Balance bar) — investor feedback "nice" | ✅ Done |
| Wallet hint for new users | Shows "Ingresa tu wallet para ver el balance" below API key when no wallet pre-filled | ✅ Done |
| Defensor Bajista desc precision | "SHORT solo en caídas" → "SHORT solo cuando el precio rompe por debajo del rango" | ✅ Done |
| Defensor Bajista disabled — Próximamente badge | Silent bug discovered: both modes identical in bot code (from_above trigger always active). Bajista disabled with amber pill until M2-13 ships. Alcista auto-selected as only active mode. | ✅ Done |
| Fix: "Activando..." button stuck on new NFT activation | Two early-return validation paths disabled the button but never re-enabled it on failure. Investor hit this activating NFT 5426040 — reused saved HL wallet but no API key entered (required on first create). Fixed + clear Spanish error message. No restart needed. | ✅ Done 2026-04-14 |
| Fix: SL too tight — bots whipsawed (NFT 5413901 + 5426040) | Bot SL floor is 0.3% (~$7 room at ETH ~$2,313) — too tight for ETH noise. Bot 17 fired SHORT twice today, both SL hit immediately within minutes. Updated sl_pct = 1.500% via DB for both configs (17 + 18). Droplet rebooted 2026-04-14, both bots restarted confirmed with sl_pct: 1.5 in started events. | ✅ Done 2026-04-14 |
| Both bots ARMED — ETH above ceilings (2026-04-15 ~17:21) | ETH reached $2,349, crossing above both range ceilings. Bot 17 (NFT 5413901) armed at $2,347.28 ceiling — fires SHORT ≤ $2,335.55. Bot 18 (NFT 5426040) armed at $2,349.63 ceiling — fires SHORT ≤ $2,337.89. First live test of 1.5% SL in action. | 🔄 Live |

### TIER 3 — Architecture resilience

#### Active development (2026-04-16)

| ID | Item | Effort | Why | Status |
|---|---|---|---|---|
| M2-21 | V2 engine — native HL SL orders + cancel/replace trail + crash recovery | High | **Live on Config 17 (NFT 5413901) as of 2026-04-16. Graduated to Config 20 (NFT 5435626, investor new LP) on 2026-04-17 14:10.** Three-part upgrade: (1) native HL trigger SL placed immediately on SHORT open — if bot crashes, HL fires SL automatically; (2) cancel+replace native SL on every trailing-stop move — SL on HL always reflects latest trail level; (3) startup reconciliation — detects orphan SHORTs from prior crashes, recovers state, places SL if missing. Graceful degradation: if native SL fails, code-evaluated SL remains active + warning logged. **Native SL fix root cause resolved 2026-04-17:** Three failed attempts logged — tpsl:"" → HTTP 422; grouping=normalTpsl → "Main order cannot be trigger order"; grouping=positionTpsl → waitingForTrigger with no usable OID. **Working solution: `grouping="na"` + `tpsl="sl"` + whole-dollar price rounding** (ETH trigger prices must be $1-increment on HL at this price range). First live confirmation: OID 386076318720 placed on orphan recovery. Also confirmed crash recovery correctly handles external position close (manual trade closed by admin 2026-04-17 → `stopped/external_close` event, bot reset to idle cleanly). **Breakeven + trailing stop live-validated 2026-04-22/23:** Config 20 trade #4 opened 14:27 at $2,412.25 — ran ~10h, hit breakeven at 16:43 UTC when price reached $2,386.75 (1.057% gain); native SL replaced with new order at entry price $2,412.25 (OID 393120049456). Trade closed at 00:38 UTC Apr 23 at ~$2,376.05 via trailing stop. Orphan recovery confirmed same session: API restart at 02:29 UTC, bot re-adopted open SHORT, placed fresh native SL+TP (OIDs 393977634190/393977653299). | ✅ Native SL working — Config 17 + Config 20 |
| M2-23 | Reentry guard — re-arm when price continues below SL hit level | Low | **Confirmed real gap (observed 2026-04-17 on Config 17).** Current logic: after SL hit, reentry guard set (e.g. $2,383.80); bot stays disarmed until price goes ABOVE guard. Failure mode: if price never reaches guard but stays below trigger (danger zone), bot is unprotected indefinitely — observed as ~1hr exposure gap (09:28 SL hit → 10:31 re-arm). **Fix:** two-condition guard clear — (1) existing: price > guard_price; (2) new: price drops below SL-hit price (price continued falling past where SL fired → whipsaw risk gone → safe to re-arm). Added `sl_close_price` state var; set in `close_hedge()` / `_reset_short_state()`; checked in main loop guard section. Whipsaw protection preserved for bounces at trigger level; gap protection fixed for continued downside moves. Applied to both V1 (`live_hedge_bot.py`) and V2 (`live_hedge_bot_v2.py`). **Deployed 2026-04-17 13:16 — both bots restarted idle, ETH $2,407.** Suggested by investor 2026-04-17. | ✅ Done 2026-04-17 |
| M2-22 | API background LP→DB reconciliation + LP event handling | Medium | **Shipped as `api/lp_reconciler.py`.** Hourly background job scans all active aragan/avaro configs, verifies each Uniswap v3 NFT on-chain. If liquidity=0 or NFT burned: sets `active=FALSE`, logs `lp_removed`/`lp_burned` bot_event, stops running bot process, emails admin. Catches LP removals that happen while the bot is stopped (bot's own `_sync_lp_position` only runs while `hedge_active`). Also fixed: bot_manager now handles `lp_removed`/`lp_burned` events with `_mark_inactive` + admin email. Fixed `reentry_guard_cleared` missing from `_EVENT_MAP` (was stored as `error`). New event types added to SQLAlchemy + MariaDB enum: `lp_removed`, `lp_burned`, `orphan_recovered`. | ✅ Done 2026-04-16 |

#### Admin Dashboard improvements (assessed 2026-04-17)

Full assessment performed against current `admin/admin.js` (1263 lines). Four priority tiers identified.

**Tier A — High impact, zero restart (pure frontend ~30 min total):**

| ID | Item | Effort | Why | Status |
|---|---|---|---|---|
| M2-24 | Engine badge (V1/V2) on bot cards | Low | `engine_v2` field not in API response but `"engine":"v2"` is logged in started event details — derived client-side from `recent_events`. V2=green badge, V1=muted badge, tooltip explains each. No API change needed. | ✅ Done 2026-04-17 |
| M2-25 | Missing event labels for new event types | Low | `evtLabel()` / `evtColor()` had no entries for `lp_removed`, `lp_burned`, `orphan_recovered`, `fury_*`, `whale_*` — showed raw type string. Added 14 new entries to both maps. | ✅ Done 2026-04-17 |
| M2-26 | Fix stale "SIN SL NATIVO" copy in detail drawer | Low | Message said *"Implementar Opción A"* — V2 exists now. Updated to accurately describe current state: software-only SL, crash risk if bot goes down. | ✅ Done 2026-04-17 |
| M2-27 | Reentry guard pill on idle card | Low | Guard state is in-memory only (not in DB). Derived client-side from `recent_events`: guard is active if latest close event (sl_hit/trailing_stop) precedes latest reset event (reentry_guard_cleared/started). Shows `🔒 $X` amber pill in card footer when active. | ✅ Done 2026-04-17 |

**Tier B — High impact, needs backend endpoint:**

| ID | Item | Effort | Why | Status |
|---|---|---|---|---|
| M2-28 | Per-bot restart from admin UI | Medium | Nuclear stops all; no targeted restart. Crashed bot (`active=True`, `running=False`) requires direct DB+systemctl. New `POST /admin/restart/{config_id}` + button on card. | 🔲 Post-meeting |
| M2-29 | Engine V2 toggle from admin UI | Low | ~~Switching V1↔V2 currently requires direct DB access.~~ **Deferred indefinitely (2026-04-22):** all active bots already on V2. 9 inactive configs last ran V1 but are out-of-range. Planned path: one-time SQL migration to mark all inactive LP configs V2, then archive `live_hedge_bot.py`. Toggle UI not needed. | ⏸ Deferred — V1 archive planned |
| M2-30 | Force LP reconciler scan button | Low | Must wait up to 1 hour for reconciler to catch LP removals. Admin toolbar button: `POST /admin/reconcile-now` → triggers `_reconcile_all()` immediately. | 🔲 Post-meeting |

**Tier B.5 — Admin card layout:**

| ID | Item | Effort | Why | Status |
|---|---|---|---|---|
| M2-36 | Separate LP Hedge and Whale Tracker into distinct sections | Low | LP and Whale cards mixed in same grid — crashed LP bot can be buried under 3 Whale cards. Split into `🛡️ LP Hedge` (aragan/avaro/fury) and `🐋 Whale Tracker` sections, each with own Running/Stopped subsections. LP always first (priority). Each section independently collapsible. Zero restart. | ✅ Done 2026-04-17 |
| M2-37 | Whale bots on/off toggle from admin | Medium | 3 whale bots consume ~6.6% CPU + ~261 MB RAM polling every 30s. Added `POST /admin/stop-whale-bots` + `POST /admin/start-whale-bots` endpoints (admin-only). `🐋 Whale Tracker` section header shows contextual button: **⏸ Pausar Whales** (when all running) or **▶ Activar Whales** (when stopped). Live-tested 2026-04-17. | ✅ Done 2026-04-17 |
| M2-38 | VIZBOT AI assistant knowledge base expansion | Medium | Assistant only knew V1 bot via static .md docs — completely blind to V2 engine, reentry guard, LP reconciler, new event types, FURY/Whale bot params, and admin dashboard features added in M2-21 through M2-37. Created `VIZBOT_KNOWLEDGE.md` (comprehensive feature doc: V1 vs V2, all modes, all event types, all bot parameter tables, reentry guard logic, LP reconciler, admin features, platform principles). Added to `_DOCS` list as first-loaded doc. Extended env-var auto-extraction to cover all 4 bot scripts (V1, V2, FURY, Whale). No API restart needed — KB reloads on next assistant call. | ✅ Done 2026-04-17 |
| M2-39 | Circuit breaker: pause after N consecutive SL hits | Medium | **Identified 2026-04-21 via trade audit on NFT 5435626.** On Apr 19 ETH choppy session ($2,332–$2,341), bot opened 7 consecutive SHORTs in 85 min — all stopped out by the native SL (0.1% = ~$2.34 room vs ~$8 ETH oscillation). Cost: -$2.27 USDC in losses + commissions before the big winner (#8) recovered. **Implemented 2026-04-22:** `_CB_STOP_THRESHOLD=3`, `_CB_PAUSE_SECS=1200` (20 min). Counter increments on `sl_hit`/`trailing_stop`, resets on `tp_hit`. Fires `circuit_breaker` DB event + email when triggered. Status line shows `🔴 CIRCUIT BREAKER (Xs)`. Requires bot restart. **Bug fixed 2026-04-23:** Original implementation only incremented counter on `sl_hit`/`trailing_stop` close paths — but in practice ALL SL hits arrive via `external_close` (native HL trigger fires before the 30s software poll). 6 consecutive SL hits overnight, counter stuck at 0, CB never fired. Fix: added CB increment + threshold check to both `external_close` paths in `close_hedge()` and `_sync_hl_position()`. Also added `consecutive_stops` field to `stopped` event details for observability. **Live-validated 2026-04-23 20:02 UTC:** Config 20 hit 3 consecutive `external_close` hits (choppy ETH session ~$2,318–$2,335). CB fired: `_consecutive_stops` reached threshold, 20-min pause enforced. Next entry at 20:22 UTC (exactly 20 min later). **Additional DB fix 2026-04-23:** `circuit_breaker` was missing from MySQL `bot_events.event_type` enum — CB fired correctly but event fell back to `error` type with CB details in `details` field. Fixed with `ALTER TABLE` adding `circuit_breaker` to enum (no restart needed). **Python SQLAlchemy enum fix 2026-04-25:** `circuit_breaker` was also missing from the SQLAlchemy `Enum()` in `api/models.py` — Python ORM rejected inserts before they reached MySQL, still logging CB events as `error`. Added `"circuit_breaker"` to `BotEvent.event_type` enum definition in `models.py`, API restarted. Next CB firing will log with correct event type. | ✅ Done + Live-validated 2026-04-23 · SQLAlchemy fix 2026-04-25 |
| M2-40 | Cooldown period after external_close re-arm | Low | **Identified 2026-04-21 via trade audit on NFT 5435626.** After a native SL fires and bot detects `external_close`, reentry guard clears in 31–61 seconds in choppy markets — bot re-enters almost immediately into the same adverse conditions. **Implemented 2026-04-22:** `_EXT_COOLDOWN_SECS=300` (5 min). Set in both `close_hedge()` (market_close returns None) and `_sync_hl_position()` (periodic sync detects missing position). Status line shows `⏸️ EXT COOLDOWN (Xs)`. Requires bot restart. **Live-validated 2026-04-22 13:57 UTC:** Native SL fired on Config 20. `stopped` event logged with `cooldown: 300` in details. Guard cleared 31s later at 13:58:17 (price $2,413.65 < SL $2,413.76) but cooldown held — no re-entry until 14:02:46 UTC. | ✅ Done + Live-validated 2026-04-22 |

**Tier C — Medium impact, pure frontend:**

| ID | Item | Effort | Why | Status |
|---|---|---|---|---|
| M2-31 | V2 bot count in stats bar | Low | Stats show total active bots but no V1/V2 split. Filterable client-side from pools data already loaded. | ✅ Done 2026-04-22 |
| M2-32 | CAÍDO bots banner at page top | Low | When `active=True` but `running=False` (crashed), card turns red but no prominent admin alert. Add banner: *"⚠️ X bots crashed — attention required"* auto-shown when any crashed bot detected. | ✅ Done 2026-04-22 |

**Tier D — Low priority / Step 8:**

| ID | Item | Effort | Why | Status |
|---|---|---|---|---|
| M2-33 | Override Plan / Suspend / Refund / Note actions | High | Already stubbed with `alert('Disponible en Step 8')`. Full billing management — deferred to subscription system. | 🔲 Step 8 |
| M2-34 | Reconciler last-run timestamp in admin | Low | No visibility into when LP reconciler last scanned. Nice-to-have status indicator. | 🔲 Post-meeting |
| M2-35 | Platform-wide cumulative P&L stat | Medium | Aggregate all bot close events — investor-facing health metric for admin overview. | 🔲 Post-meeting |

---

#### Deferred (post investor meeting)

| ID | Item | Effort | Why | Status |
|---|---|---|---|---|
| M2-9 | SL/TP as native HL trigger orders | High | **Fully implemented 2026-04-22.** V2 engine ships native trigger SL (M2-21) + native trigger TP (`_place_native_tp` / `_cancel_native_tp`). TP placed at open when `TP_PCT` configured; cancelled on all close paths; recovered/re-placed on orphan recovery at startup. `tpsl="tp"`, `grouping="na"`, whole-dollar rounding, `limit_px = trigger * 0.97`. **Live-validated 2026-04-22 13:48 UTC:** `tp_oid: 392796553319` confirmed in Config 20 `hedge_opened` event (entry $2,411.35, TP target ~$2,267.47, SL OID 392796496914). | ✅ Done + Live-validated 2026-04-22 |
| M2-10 | Auto-reactivation after insufficient balance | Medium | VIZNIAGO has AUTO_REARM but may not handle balance case | 🔲 Post-meeting |
| M2-11 | Pre-trigger as % before range edge (replace buffer) | Medium | Cleaner UX than current TRIGGER_OFFSET_PCT | 🔲 Post-meeting |
| M2-13 | Mode enforcement in bot code (Bajista vs Alcista) | Low-Medium | Silent bug: `live_hedge_bot.py` never reads the `mode` field from DB — both modes behave identically today (both triggers always active). Fix: read `BOT_MODE` env var injected by bot_manager at launch; if `aragan`, skip `from_above` trigger entirely. Bajista = `below_range` only. Alcista = both triggers. **Implemented 2026-04-22 in V2:** `FROM_ABOVE_ENABLED = BOT_MODE != "aragan"` gates direction tracking + entry. Startup log prints active mode + trigger description. `mode`/`from_above_enabled` added to `started` event details. **Live-validated 2026-04-22 13:48 UTC:** Config 20 `hedge_opened` shows `trigger: from_above` — mode enforcement working in live conditions. | ✅ Done + Live-validated 2026-04-22 |
| M2-16 | Implement LONG on upside breakout for Defensor Alcista | High | **Critical false promise fixed 2026-04-25 (UI only):** `bot.desc` and `prot.mode.avaro.desc` in i18n.js (ES + EN) updated — LONG claim removed. New desc: "SHORT cuando el precio entra al rango desde arriba. SL ajustado + trailing stop automático." Bot LONG logic still not implemented — UI now accurately describes what the bot does. Full LONG implementation deferred. | 🔲 Bot logic post-meeting · ✅ UI false promise fixed 2026-04-25 |
| M2-17 | Native HL SL order placed immediately when SHORT opens | Medium | **Superseded by M2-21.** V2 ships Option B (full — native SL at open + cancel+replace on every trail move). Originally considered Option A only (fixed SL, simpler). V2 went straight to Option B. | ✅ Covered by M2-21 |
| M2-18 | Remove silent SL floor — replace with inline UI warning (Option C) | Low | **Investor-validated (2026-04-16):** bot silently overrides user SL from 0.1% → 0.3% (`_SL_FLOOR_PCT`) without any UI feedback — trust issue. Investor set 0.1%, bot ran 0.3%, he had no idea. Fix: remove silent floor in `live_hedge_bot.py`, add inline warning in protection config form when SL < 0.5%: *"Un SL de X% (~$Y) puede cerrarse por el ruido normal del mercado. Mínimo recomendado: 0.5%"*. User can still proceed — their choice, their responsibility. Zero silent overrides. Frontend + bot change, requires restart. **Platform principle confirmed (2026-04-16):** VIZNIAGO must never adjust any user parameter behind the frontend — not SL, not leverage, not any config field. UI warns, user decides. No DB patches to "fix" user settings outside the UI. This applies to all future features. | ✅ Done 2026-04-16 |

### TIER D — VIZNIAGO Differentiators to present at meeting

| ID | Item | Notes |
|---|---|---|
| D1 | Whale Tracker | They have nothing equivalent — unique intelligence layer |
| D2 | Whitepaper | Shows seriousness — they have no public documentation |
| D3 | Forensic event history in position cards | Price at every bot event — they don't show this. PnL label fixed 2026-04-25 (T1-3): now shows `X.XX%` correctly. |
| D4 | NFT Token ID search + Explorar tab | More flexible position discovery |
| D5 | Non-custodial architecture | Keys never leave user wallet — trust differentiator |
| D6 | Public roadmap | Shows where the platform is going |

---

## Meeting 2 Narrative Strategy

**Opening:** Lead with what was fixed since meeting 1 (show the list of tier 1 completions).

**Middle:** Show the fee projections and APR on the position card — this is the metric that makes an investor think "this generates real yield."

**On DeFi Suite comparison:** Don't mention it directly. If asked "have you seen other platforms?" say:
> *"Yes, we've studied the market. They're more mature on analytics. We're ahead on intelligence — the Whale Tracker is something nobody else is doing for LP managers."*

**On infrastructure cost:** Come prepared with Oracle Cloud Free Tier proposal — $0 to start, pay-as-you-grow.

**On token/DAO:** If asked, stick to the whitepaper language:
> *"It's in research. We're not making promises until we know exactly what value it adds."*

---

## What NOT to show at Meeting 2
- BTC strategy negative backtest results (unless directly asked)
- Incomplete features
- The FURY bot complexity (too technical, off-topic for LP focus)
- Any infrastructure cost numbers without the Oracle alternative ready

---

*Last updated: 2026-04-25 — Frontend pass: M2-6 ✅ M2-7 ✅ M2-16 (UI) ✅ T1-3 ✅ T2-6 ✅ all shipped, no restart. M2-39 SQLAlchemy enum fix ✅ (api/models.py, API restarted). Previously: M2-9 ✅ M2-13 ✅ M2-21 ✅ M2-39 ✅ M2-40 ✅ all live-validated. M2-29 deferred.*
