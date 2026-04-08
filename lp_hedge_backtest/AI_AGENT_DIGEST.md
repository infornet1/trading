# VIZNIAGO — AI Agent Digest (Future Roadmap)

> **Status: Deferred — post-alpha**
> Documented Apr 2 2026. Do not build during alpha phase. Revisit when active user base
> justifies the operational cost and complexity.

---

## What this is

An out-of-band AI layer that reads VIZNIAGO's event stream and generates human-readable
summaries, incident explanations, and anomaly flags. It never touches the trading hot path.

---

## Architecture (3-tier principle)

```
Tier 1 — Real-time (every 30s bot loop)          DETERMINISTIC ONLY
  live_hedge_bot.py — SL, trailing stop,
  position sync, error guards
  → Zero AI. Must be fast and predictable.

Tier 2 — Near-real-time (every 5–15 min)         RULE-BASED DAEMON
  Supervisor / cron watches bot_events:
  error bursts, ghost hedges, stalled bots,
  zero-balance HL wallets
  → Telegram / email alerts on threshold breach.
  → No AI needed. Simple rules are enough here.

Tier 3 — Daily / on-incident (async)             AI AGENT LIVES HERE
  Reads last 24h of bot_events across all users.
  Generates digest, incident reports, anomaly flags.
  Out-of-band — never blocks live positions.
```

---

## Planned AI Agent responsibilities (Tier 3 only)

### 1. Daily digest
- Summarize all bot activity across all users in plain language
- Flag anything unusual: bots that stopped unexpectedly, large PnL swings,
  error counts above baseline
- Post to admin Telegram or admin dashboard

### 2. Incident auto-report
- Triggered when Tier 2 fires an alert
- AI reads the event sequence and generates a plain-language explanation:
  what happened, why, what the bot did, what needs attention
- Posted to user Telegram + admin dashboard
- Replaces the manual forensic analysis currently done by the dev

### 3. User-facing explainer
- When a user's bot stops unexpectedly, auto-send a plain-language summary:
  "Your protection bot closed the hedge at $X because ETH recovered above
  the trailing stop. Your LP is currently unprotected. Re-arm here: [link]"
- Reduces support burden and builds user trust

### 4. Anomaly detection
- Flags event sequences that don't match known patterns
- Example: hedge_opened → no breakeven after 24h → flag for review
- Example: 3+ rapid start/stop cycles in 1 hour → likely user confusion, trigger
  onboarding nudge

---

## Why NOT during alpha

| Concern | Detail |
|---|---|
| Cost | Every AI call costs money. At 5 users / 50 events/day = manageable. At 500 users it becomes a real line item that needs pricing into plans |
| Complexity | Another component that can go down or misbehave |
| Premature | The deterministic bugs (ghost hedge, None subscript) needed code fixes, not AI judgment. Fix the code first |
| Hallucination risk | False positives in financial context have real consequences |
| Not the bottleneck | At alpha, user trust is built by the core bot working reliably, not by AI summaries |

---

## Prerequisites before building

- [ ] Core bot reliability established (alpha complete, known bugs fixed)
- [ ] Telegram alert system live (Option A — wallet-based)
- [ ] Admin dashboard event timeline visible
- [ ] At least 10 active users generating meaningful event volume
- [ ] Claude API key with dedicated cost budget allocated

---

## Incident that motivated this (Apr 2 2026)

Bot config 12 / NFT #5400850 entered a 15-minute error loop after the user manually
closed the HL SHORT position outside the bot. Root cause was a code bug (missing None
check in `close_hedge`), not a monitoring gap. Both bugs were fixed immediately:

- `close_hedge` now handles `market_close` returning None (external close detected, bot
  self-resets to IDLE)
- Periodic HL position sync added (every 5 min while hedge active — detects external
  closes within one sync cycle)

The AI Digest would have added value here at the **reporting layer** (auto-generating
the incident explanation for the user) but would NOT have prevented or fixed the
underlying bug faster than the code fix did.

**Lesson: rule-based fixes first. AI for communication and pattern recognition second.**
