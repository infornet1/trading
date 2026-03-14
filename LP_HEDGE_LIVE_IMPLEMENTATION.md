# LP + Perps Hedge: Live Implementation Summary
**Last Updated:** March 14, 2026
**Project:** Bootcamp Cripto 2026 Pilot Run
**Status:** 🟢 LIVE & PROTECTED

---

## 📋 Position History

### Position v1 — NFT #5364087 (March 13, 2026)
- **Range:** $1,800.87 — $2,250.75 (~25% wide)
- **Closed/Replaced:** March 14, 2026
- **Reason:** Range too wide vs bootcamp methodology (optimal = 10-15%). Rebalanced to a tighter range based on confirmed support/resistance.

### Position v2 — NFT #5364575 (March 14, 2026) ← ACTIVE
- **Network:** Arbitrum
- **Pair:** ETH / USDC (0.05% Fee Tier)
- **Range:** $1,919.89 — $2,232.81
- **Width:** ~16.3% (bootcamp target: 10-15%)
- **Floor basis:** $1,924 support level (4 confirmed touches on 4h chart)
- **Ceiling basis:** $2,199 resistance level
- **Market context at open:** ADX = 13.7 (falling) → lateral market, ideal for LP

---

## 🤖 Bot Aragan v1.2 — Active Configuration

Custom Python execution engine monitoring the position 24/7 as a systemd service.

- **Service:** `live_hedge_bot.service`
- **NFT Monitored:** `#5364575`
- **Monitoring:** Checks Hyperliquid ETH price every 30 seconds.
- **Trigger:** Price hits **$1,910.29** (0.5% below floor $1,919.89)
- **Hedge Action:** Opens a **10x SHORT** on Hyperliquid (Size: 0.05 ETH)
- **Risk Management:**
    - **Stop Loss:** 0.5% above entry
    - **Breakeven:** Moves SL to entry once 1.0% profit is reached
    - **Take Profit:** Closes short when price returns to floor ($1,919.89)

---

## 🏗️ Infrastructure & Security

- **Service Mode:** systemd (`live_hedge_bot.service`) — auto-restarts on failure
- **API Setup:** Main Wallet + Agent (API Wallet) — trade-only permissions, cannot withdraw
- **Config:** `.env` file (never commit to git)

---

## 📧 Alert System

- **Sender:** `finanzas@ueipab.edu.ve`
- **Recipients:** `perdomo.gustavo@gmail.com`, `carlosam81@gmail.com`
- **Events:** Bot Startup, Hedge Opened, Breakeven Protected, Hedge Closed

---

## 🛠️ Operational Commands

```bash
# Check status
sudo systemctl status live_hedge_bot.service

# View live logs
sudo journalctl -u live_hedge_bot.service -f

# Restart after config changes
sudo systemctl restart live_hedge_bot.service
```

---

## 📊 Account Details

- **Hedge Wallet:** `0xeF0DDF18382538F31dcfa0AF40B47eE8c5A2cf2f` (Hyperliquid)
- **Collateral Type:** Cross-Margin (Spot USDC as Perp collateral)
- **Liquidation Risk:** Minimal — 0.5% SL + dynamic breakeven protection

---

## 💡 Bootcamp Methodology Notes (Raúl & Jaime)

- **Timeframe for range:** 4h chart (ETH daily range = 10-15% width)
- **Range = Soporte + Resistencia** (confirmed 2-3+ touches)
- **ADX < 20** = lateral = open pool; **ADX > 25** = trend = caution
- **Short trigger:** 0.5-1% below floor (avoids false breakouts)
- **BTC: NEVER short** — long only. ETH: long + short OK.
- **Hedge size:** 10% of pool value on Hyperliquid
- **Pool APR tracking:** use `revert.finance`

---

## 💰 Capital Management Notes (March 14, 2026)

### Available Capital: $1,269.84 USDC — NOT deployed in LP

**Context:** $1,269.84 USDC available but with hard return deadlines:
- 50% ($634.92) → due back **March 25, 2026** (11 days)
- 50% ($634.92) → due back **March 28, 2026** (14 days)

**Decision: Do NOT open LP pool with this capital.**

Reasons:
- LP strategy requires weeks/months to accumulate fees offsetting IL + gas
- 11-14 day horizon is too short — break-even needs 5-10 days with no buffer
- If price exits range even 3-4 days, fees = $0 during that period
- Principal belongs to a third party — reputational risk outweighs potential gain (~$5-26)

**Recommended action:** Deposit in **Morpho or Aave v3 on Arbitrum** (via Rabby Wallet lending tab)
- ~6-12% APY, instant withdrawal, zero IL risk
- Estimated yield: ~$3-6 over 11-14 days
- Withdraw $634.92 on Mar 25, remaining $634.92 on Mar 28

### Revert.finance Clarification
`revert.finance` is **not** a USDC yield platform. Its actual use cases:
1. **Analytics** — track APR, fees earned, IL on active LP positions (use this for pool #5364575)
2. **Auto-Compoundor** — reinvests LP fees back into the position automatically
3. **Revert Lend** — borrow USDC using Uniswap v3 NFT as collateral (not relevant here)

### Future Capital Allocation (when capital has no deadline)
Suggested setup based on market analysis (Mar 14, 2026):
- **BTC/USDC pool** on Arbitrum, range **$65,568 — $74,022** (12.9% wide)
- BTC ADX = 12.8 (falling) → lateral market, ideal for LP
- $65,568 support: 3 confirmed touches
- Split: 85% to pool, 15% to Hyperliquid hedge reserve (LONG only — never short BTC)
