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
| M2-6 | Buffer Capital pill buttons (Sin/+10/+20/+30/+50%) | Low | Cleaner than slider, shows options at a glance | 🔲 |
| M2-7 | Backtesting link/embed inside LP Defensor | Low | Bring it closer to the product, not a separate page | 🔲 |
| M2-8 | Orphan order cleanup audit | Medium | Resilience — verify TPs cancel on SL and vice versa | 🔲 |
| M2-12 | Frontend restart/maintenance guard | Low | UX resilience — auto-detect API unavailability, show non-dismissible "Reconnecting…" overlay + disable all interactive elements (buttons/forms) during maintenance flag or outage. Reuses existing `/status/maintenance` poll. Two layers: (1) maintenance flag disables UI, (2) 2x consecutive health check fails triggers overlay. Frontend only, zero backend change, zero restart needed. | 🔲 |
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
| M2-21 | V2 engine — native HL SL orders + cancel/replace trail + crash recovery | High | **Live on Config 17 (NFT 5413901) as of 2026-04-16. Graduated to Config 20 (NFT 5435626, investor new LP) on 2026-04-17 14:10.** Three-part upgrade: (1) native HL trigger SL placed immediately on SHORT open — if bot crashes, HL fires SL automatically; (2) cancel+replace native SL on every trailing-stop move — SL on HL always reflects latest trail level; (3) startup reconciliation — detects orphan SHORTs from prior crashes, recovers state, places SL if missing. Graceful degradation: if native SL fails, code-evaluated SL remains active + warning logged. **Native SL fix (2026-04-17):** tpsl:"sl" → tpsl:"" (standalone trigger) + 1s settle delay. Both V2 bots running clean as of 14:10. Supersedes M2-9 and M2-17. | 🔄 Live — Config 17 + Config 20 |
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
| M2-29 | Engine V2 toggle from admin UI | Low | Switching V1↔V2 currently requires direct DB access. Toggle on card or wallet panel — `PATCH /admin/pool/{id}` with `engine_v2`. | 🔲 Post-meeting |
| M2-30 | Force LP reconciler scan button | Low | Must wait up to 1 hour for reconciler to catch LP removals. Admin toolbar button: `POST /admin/reconcile-now` → triggers `_reconcile_all()` immediately. | 🔲 Post-meeting |

**Tier B.5 — Admin card layout:**

| ID | Item | Effort | Why | Status |
|---|---|---|---|---|
| M2-36 | Separate LP Hedge and Whale Tracker into distinct sections | Low | LP and Whale cards mixed in same grid — crashed LP bot can be buried under 3 Whale cards. Split into `🛡️ LP Hedge` (aragan/avaro/fury) and `🐋 Whale Tracker` sections, each with own Running/Stopped subsections. LP always first (priority). Each section independently collapsible. Zero restart. | ✅ Done 2026-04-17 |
| M2-37 | Whale bots on/off toggle from admin | Medium | 3 whale bots consume ~6.6% CPU + ~261 MB RAM polling every 30s. Added `POST /admin/stop-whale-bots` + `POST /admin/start-whale-bots` endpoints (admin-only). `🐋 Whale Tracker` section header shows contextual button: **⏸ Pausar Whales** (when all running) or **▶ Activar Whales** (when stopped). Requires API restart. | ✅ Done 2026-04-17 |

**Tier C — Medium impact, pure frontend:**

| ID | Item | Effort | Why | Status |
|---|---|---|---|---|
| M2-31 | V2 bot count in stats bar | Low | Stats show total active bots but no V1/V2 split. Filterable client-side from pools data already loaded. | 🔲 Post-meeting |
| M2-32 | CAÍDO bots banner at page top | Low | When `active=True` but `running=False` (crashed), card turns red but no prominent admin alert. Add banner: *"⚠️ X bots crashed — attention required"* auto-shown when any crashed bot detected. | 🔲 Post-meeting |

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
| M2-9 | SL/TP as native HL trigger orders | High | **Superseded by M2-21.** V2 engine ships exactly this: native trigger SL at open, cancel+replace on trail, crash recovery. TP as native order not yet implemented (optional follow-on). | ✅ Covered by M2-21 |
| M2-10 | Auto-reactivation after insufficient balance | Medium | VIZNIAGO has AUTO_REARM but may not handle balance case | 🔲 Post-meeting |
| M2-11 | Pre-trigger as % before range edge (replace buffer) | Medium | Cleaner UX than current TRIGGER_OFFSET_PCT | 🔲 Post-meeting |
| M2-13 | Mode enforcement in bot code (Bajista vs Alcista) | Low-Medium | Silent bug: `live_hedge_bot.py` never reads the `mode` field from DB — both modes behave identically today (both triggers always active). Fix: read `BOT_MODE` env var injected by bot_manager at launch; if `aragan`, skip `from_above` trigger entirely. Bajista = `below_range` only. Alcista = both triggers. Low effort code change, requires bot restart per config. | 🔲 Post-meeting |
| M2-16 | Implement LONG on upside breakout for Defensor Alcista | High | **Critical false promise:** UI says "SHORT en caídas + LONG en rupturas al alza" but bot code has ZERO LONG logic — never implemented. When price breaks above the range ceiling, LP stops earning fees and bot does nothing. Full implementation requires: (1) arm `price_was_below` flag when price is inside range, (2) fire LONG when price breaks above `upper_bound * (1 + UPPER_BUFFER)`, (3) manage LONG with same trailing SL logic, (4) close LONG on TP/SL/re-entry. **Action 1 (UI fix — no restart, zero bot impact): update i18n.js Alcista desc to remove LONG claim until implemented. Action 2 (this item): build the actual LONG logic.** Requires careful testing before deploy to any live config. | 🔲 Post-meeting |
| M2-17 | Native HL SL order placed immediately when SHORT opens | Medium | **Superseded by M2-21.** V2 ships Option B (full — native SL at open + cancel+replace on every trail move). Originally considered Option A only (fixed SL, simpler). V2 went straight to Option B. | ✅ Covered by M2-21 |
| M2-18 | Remove silent SL floor — replace with inline UI warning (Option C) | Low | **Investor-validated (2026-04-16):** bot silently overrides user SL from 0.1% → 0.3% (`_SL_FLOOR_PCT`) without any UI feedback — trust issue. Investor set 0.1%, bot ran 0.3%, he had no idea. Fix: remove silent floor in `live_hedge_bot.py`, add inline warning in protection config form when SL < 0.5%: *"Un SL de X% (~$Y) puede cerrarse por el ruido normal del mercado. Mínimo recomendado: 0.5%"*. User can still proceed — their choice, their responsibility. Zero silent overrides. Frontend + bot change, requires restart. **Platform principle confirmed (2026-04-16):** VIZNIAGO must never adjust any user parameter behind the frontend — not SL, not leverage, not any config field. UI warns, user decides. No DB patches to "fix" user settings outside the UI. This applies to all future features. | ✅ Done 2026-04-16 |

### TIER D — VIZNIAGO Differentiators to present at meeting

| ID | Item | Notes |
|---|---|---|
| D1 | Whale Tracker | They have nothing equivalent — unique intelligence layer |
| D2 | Whitepaper | Shows seriousness — they have no public documentation |
| D3 | Forensic event history in position cards | Price at every bot event — they don't show this |
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

*Last updated: 2026-04-17 — M2-37 done (Whale toggle: stop/start-whale-bots endpoints + section header button, API restarted)*
