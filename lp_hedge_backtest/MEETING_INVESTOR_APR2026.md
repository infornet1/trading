# Investor Meeting Notes — April 2, 2026
**Context:** Live demo session with potential capital supporter. User mounted a real LP position during meeting. Bot was paused for discussion. Meeting goal: build trust and unlock support capital.

---

## Q&A Log

### Q1 — Why was the SHORT opened ~2% below the LP top range ($2,130.3)?

**Answer:** Intentional by design. The bot has a built-in **2% confirmation buffer** (UPPER_BUFFER_PCT) below the upper range bound before firing the FROM ABOVE trigger. This prevents false entries on small wicks or bounces off the top. The bot waits for price to confirm it's genuinely falling before opening the hedge.

- LP top: $2,130.30 → 2% below = ~$2,087 → bot fired at **$2,086.30** ✅
- This actually gave a **better entry** than firing at $2,130
- Result: +$7.16 net / +29% return on margin (see CASE_STUDY_BOT_TRIGGER_APR2026.md)

**Follow-up clarification:** The 2% is NOT a UI slider — it's an internal default value (UPPER_BUFFER_PCT=2.0 in bot env). It's separate from the "Buffer de Breakout" slider in the UI which controls the BELOW RANGE trigger (TRIGGER_OFFSET_PCT).

---

### Q2 — Was the hedge size (Tamaño de cobertura) set at 100% by the user?

**Answer:** Yes, confirmed from DB. Config ID 4 for wallet `0xe84f181541072c14a6a28224a33b078a44cc343c` had `hedge_ratio = 100.00%`. This was manually set — system default is 50%. At 100% the bot is fully delta-neutral: shorts exactly what the LP holds in ETH.

---

### Q3 — Can hedge size be more than 100%? (Directional Bet discussion)

**Answer:** The DB supports it (Numeric field, no cap at DB level). However, **the UI slider is currently hard-capped at 100%** (dashboard.js line 1995: `min="10" max="100"`).

**Conceptual framework proposed:**
| Mode | Hedge Ratio | Behavior |
|---|---|---|
| Defensive (current) | 10–100% | Pure IL protection |
| Offensive (future) | 101–200% | Directional bet — profits more than LP loses on downside |

**Important clarification from user:** The idea is NOT to run 2 bots on the same LP simultaneously. It's to **choose one mode when setting up the LP** — either defensive or directional. One bot, one LP, pick your strategy upfront.

---

### Q4 — Hyperliquid minimum order size ($10 notional)

**Investor raised:** HL requires a minimum ~$10 notional per order. Does VIZNIAGO enforce this?

**Current state (gap identified):** Bot has `MIN_HEDGE_ETH = 0.001` (~$2 at current ETH price) — technically below HL's floor. The bot works correctly for any reasonably sized LP (yesterday's trade was 0.1233 ETH / ~$250 notional, well above the floor). However, a very small LP could trigger a failed order.

**Practical safe zone:**
- At 50% hedge ratio → LP needs at least ~$20 ETH exposure
- At 100% hedge ratio → LP needs at least ~$10 ETH exposure
- Anything below that risks a rejected order from HL

**Fix needed:** Raise `MIN_HEDGE_ETH` to ~0.005 ETH (enforces ~$10 floor at current prices) and add a dashboard warning if LP is too small to hedge.

---

### Q5 — "Buffer de Breakout" slider only controls the lower trigger, not the upper

**Investor discovered:** He set the buffer slider to 1% expecting it to apply to both triggers. In reality:
- Slider "Buffer de Breakout" → `TRIGGER_OFFSET_PCT` → **only controls the below-range (lower) trigger**
- `UPPER_BUFFER_PCT = 2.0` → hardcoded internally, **never exposed in UI**

**Confirmed from DB for his LP (NFT #5402203):**
- Upper trigger: $2,013.88 = 2.0% below upper bound $2,054.98 (hardcoded)
- Lower trigger: $1,876.15 = 1.0% below lower bound $1,895.10 (his slider setting ✅)

**Gap:** Slider label is misleading — users reasonably expect it to control both triggers consistently.

**Agreed fix (not yet implemented):**
- Option A: Single slider controls both triggers (simpler UX — "how much confirmation before bot fires?")
- Option B: Two separate sliders with clear labels — "Buffer superior" and "Buffer inferior"
- Recommendation: Option A — one slider, both triggers, consistent behavior

**Code change needed:**
- `live_hedge_bot.py`: replace hardcoded `UPPER_BUFFER_PCT = 2.0` with `UPPER_BUFFER = TRIGGER_OFFSET` (same env var)
- Dashboard label: clarify slider applies to both triggers

---

## Pending Action Items

| Item | Priority | Notes |
|---|---|---|
| Fix buffer slider — apply to both triggers | High | `live_hedge_bot.py`: use `TRIGGER_OFFSET` for upper buffer too. Update dashboard label. No DB change needed. |
| Fix MIN_HEDGE_ETH floor | High | ✅ Deployed — `MIN_NOTIONAL_USD=10` check + email alert + dashboard red warning. |
| Min pool calculator in dashboard | High | ✅ Deployed — "Pool mínimo para cubrir" row in margin box, live, turns green/red. |
| Extend hedge slider to 200% | Medium | Frontend fix (dashboard.js line 1995). Add warning label above 100%: "Modo Ofensivo — directional bet, not pure protection". |
| "Modo Ofensivo" UX design | Low | Consider toggle or separate mode label rather than just extending slider silently. |
| BTC pool support | Medium | Investor opened a WBTC/USDC LP — not displayed, not supported. Two parts: (1) dashboard reads WBTC positions (display only, no bot); (2) optional BTC short hedge — user opt-in with explicit warning "against default strategy recommendation". Some users may want directional short on BTC. Golden rule from Jaime is no BTC shorts — but platform should let advanced users override with informed consent. |
| Follow-up with investor | High | Outcome of today's meeting TBD — did he approve support capital? |

---

## Investor Feedback — UI/UX Notes (raw from meeting)

### Wallets
- LP protection section should show API connection status to Hyperliquid (is the HL API key connected and working?)

### Explorer
- NFT search + wallet (0x...) search — finding by NFT token ID is faster, should be supported
- Left sidebar shows the connected wallet address even in "explore mode" — it shouldn't, explorer should feel wallet-agnostic

### LP
- When bot is stopped, the event log disappears from the UI — **in alpha it should persist** so users can review performance history even after stopping
- Private key / wallet input is confusing when a user has multiple wallets — **suggest dropdown list** to select which wallet the key belongs to, instead of a plain text field
- Show HL wallet balance directly in the LP section (currently only visible in Trading Panel)

### Bot
- **Forensic analysis feature**: show what the price was at each bot event — users want to reconstruct "what happened and at what price" directly from the dashboard (currently requires manual DB lookup)

### Telegram
- Bot sends too much detail / unnecessary info — needs a cleaner, more concise notification format. Less is more.

---

## Context for Next Session

- **Outcome: POSITIVE — investor likely to support the project ✅**
- Investor saw a **live LP mount + real bot trigger event** (APR2026 case study)
- He asked technically sharp questions — he understands DeFi mechanics
- The bot performed correctly in every detail he questioned
- Main trust signals delivered: live proof, transparent config, non-custodial, real on-chain verifiable trades
- He also opened a BTC LP during the meeting — exposed the BTC support gap
- Left with a list of UX improvements (see Investor Feedback section above) — shows genuine engagement
