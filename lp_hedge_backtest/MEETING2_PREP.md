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
| M2-1 | Fee projections on position card (daily/weekly/monthly/annual) | Low | Most compelling investor metric — shows yield potential at a glance | 🔲 |
| M2-2 | APR + Fee APR in position card header | Low | They see value immediately, no scrolling needed | 🔲 |
| M2-3 | Distance to trigger % + show BOTH upper and lower triggers in active bot card | Low | "How close is the bot to firing?" — both directions; they show upper+lower | 🔲 |
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

### TIER 3 — Architecture resilience (deferred — post investor meeting)

| ID | Item | Effort | Why | Status |
|---|---|---|---|---|
| M2-9 | SL/TP as native HL trigger orders | High | Survive bot process crash — their biggest architecture upgrade. Requires: place SL+TP on HL after open, track order IDs, update native SL on every trailing stop move (cancel+replace), restart recovery from HL state. Fee cost same as today. **Deferred — needs stable open+close cycle first.** | 🔲 Post-meeting |
| M2-10 | Auto-reactivation after insufficient balance | Medium | VIZNIAGO has AUTO_REARM but may not handle balance case | 🔲 Post-meeting |
| M2-11 | Pre-trigger as % before range edge (replace buffer) | Medium | Cleaner UX than current TRIGGER_OFFSET_PCT | 🔲 Post-meeting |
| M2-13 | Mode enforcement in bot code (Bajista vs Alcista) | Low-Medium | Silent bug: `live_hedge_bot.py` never reads the `mode` field from DB — both modes behave identically today (both triggers always active). Fix: read `BOT_MODE` env var injected by bot_manager at launch; if `aragan`, skip `from_above` trigger entirely. Bajista = `below_range` only. Alcista = both triggers. Low effort code change, requires bot restart per config. | 🔲 Post-meeting |
| M2-16 | Implement LONG on upside breakout for Defensor Alcista | High | **Critical false promise:** UI says "SHORT en caídas + LONG en rupturas al alza" but bot code has ZERO LONG logic — never implemented. When price breaks above the range ceiling, LP stops earning fees and bot does nothing. Full implementation requires: (1) arm `price_was_below` flag when price is inside range, (2) fire LONG when price breaks above `upper_bound * (1 + UPPER_BUFFER)`, (3) manage LONG with same trailing SL logic, (4) close LONG on TP/SL/re-entry. **Action 1 (UI fix — no restart, zero bot impact): update i18n.js Alcista desc to remove LONG claim until implemented. Action 2 (this item): build the actual LONG logic.** Requires careful testing before deploy to any live config. | 🔲 Post-meeting |
| M2-17 | Native HL SL order placed immediately when SHORT opens | Medium | **Investor-driven:** current SL is code-evaluated only — if bot process crashes, open SHORT has zero stop protection until restart. Fix: place a native HL trigger order as SL the moment `open_hedge()` succeeds. Two options: **Option A (simpler):** place native SL at open, fixed — never moves even if trailing stop activates. Protects crash scenario, ships faster. **Option B (full):** native SL at open + cancel+replace on every trailing stop move — full protection, requires tracking HL order IDs and handling cancel/replace loop. Recommended path: ship Option A first, upgrade to Option B as follow-on. Triggered by 2026-04-15 live session where investor SHORT opened with 0.3% SL ($7 room) and no native HL protection. | 🔲 Post-meeting |
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

*Last updated: 2026-04-16 (M2-19 done — DeFi menu reorder investor-requested)*
