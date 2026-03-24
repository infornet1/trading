# DeFi Hedge Bot — Subscription & Membership Plans

## Product Vision

A managed LP hedging service where users connect their Hyperliquid API key and the platform automatically protects their Uniswap v3 liquidity pools from impermanent loss.

**Value Proposition:** "Your pools only win — we handle the hedge."

---

## Membership Tiers

### Free Tier — "Explorer"
| Feature | Details |
|---------|---------|
| Price | $0/month |
| Pools | 1 pool max |
| Bot Mode | Bot Defensor Bajista only (hedge) |
| Pairs | ETH/USDC only |
| Notifications | Email only |
| Dashboard | Basic (PnL, pool status) |
| AI Assistant | 5 messages/day |
| Support | Community forum |
| Capital Limit | Up to $500 pool value |

**Purpose:** Let users test the system with minimal risk. Prove the concept works.

---

### Starter Tier — "Defensor Bajista"
| Feature | Details |
|---------|---------|
| Price | $19/month or $190/year (save 17%) |
| Pools | Up to 3 pools |
| Bot Mode | Bot Defensor Bajista (hedge) |
| Pairs | ETH/USDC, BTC/USDC |
| Notifications | Email + Telegram |
| Dashboard | Full (PnL, APR, IL, hedge history, ADX chart) |
| AI Assistant | 50 messages/day |
| Support | Email support (48h response) |
| Capital Limit | Up to $5,000 pool value |
| Extras | Weekly market analysis email |

---

### Pro Tier — "Defensor Alcista"
| Feature | Details |
|---------|---------|
| Price | $49/month or $490/year (save 17%) |
| Pools | Up to 10 pools |
| Bot Mode | Bot Defensor Bajista + Bot Defensor Alcista (hedge + long trading) |
| Pairs | ETH/USDC, BTC/USDC, + selected altcoin pools |
| Networks | Arbitrum + Base |
| Notifications | Email + Telegram + WhatsApp |
| Dashboard | Advanced (real-time, ADX regime alerts, rebalance history) |
| AI Assistant | 200 messages/day |
| Support | Priority email (24h response) |
| Capital Limit | Up to $50,000 pool value |
| Extras | Custom range suggestions based on AT, trailing stop tuning |
| Auto-Rebalance | Automatic range rebalancing when pool exits range |

---

### Enterprise Tier — "Institutional"
| Feature | Details |
|---------|---------|
| Price | $199/month or $1,990/year (save 17%) |
| Pools | Unlimited |
| Bot Mode | All modes + custom strategies |
| Pairs | All supported pairs |
| Networks | Arbitrum, Base, Ethereum L1 |
| Notifications | All channels + API webhooks |
| Dashboard | White-label option |
| AI Assistant | Unlimited |
| Support | Dedicated account manager, 1h response |
| Capital Limit | Unlimited |
| Extras | Custom bot parameters, API access, multi-wallet |
| SLA | 99.9% uptime guarantee |
| Reporting | Monthly PDF report, tax-ready export |

---

## Revenue Model

### Subscription Revenue (Primary)
| Tier | Monthly | Annual | Target Users (Y1) | Monthly Revenue |
|------|---------|--------|-------------------|-----------------|
| Free | $0 | $0 | 500 | $0 |
| Starter | $19 | $190 | 100 | $1,900 |
| Pro | $49 | $490 | 40 | $1,960 |
| Enterprise | $199 | $1,990 | 5 | $995 |
| **Total** | | | **645** | **$4,855** |

### Performance Fee (Optional Add-on)
- 5% of hedge profits (only charged when hedge makes money)
- Aligns incentives: we only earn when we save you money
- Applied monthly, transparent in dashboard
- Free/Starter: not available
- Pro/Enterprise: opt-in

### Referral Program
- Refer a friend → both get 1 month free (Starter or Pro)
- Bootcamp alumni: 20% lifetime discount on any tier
- Volume discount: 3+ Enterprise accounts → custom pricing

---

## Cost Structure (Estimated Monthly)

| Cost Item | Monthly | Notes |
|-----------|---------|-------|
| Server (VPS) | $50-100 | Trading engine + API servers |
| Odoo CE Hosting | $0 | Self-hosted, community edition |
| Hyperliquid API | $0 | Free to use |
| Uniswap v3 RPC | $50-100 | Alchemy/Infura for Arbitrum |
| Email Service | $20 | Transactional emails (SendGrid) |
| Telegram Bot | $0 | Free API |
| WhatsApp API | $50 | Meta Business API |
| Domain + SSL | $15 | Annual, amortized |
| **Total** | **$185-285** | |

**Break-even:** ~10 Starter subscribers or ~6 Pro subscribers.

---

## Onboarding Flow

```
1. User registers on portal (Odoo website)
         |
2. Selects membership tier
         |
3. Payment (Stripe/crypto via USDC)
         |
4. Tutorial: "How to set up your first pool"
   - Open Uniswap v3 pool on Arbitrum
   - Fund Hyperliquid with 10-20% of pool value
   - Generate Hyperliquid API key (More → API)
         |
5. Paste API key in portal (encrypted with SHA-256)
         |
6. Configure pool parameters:
   - Select pair (ETH/USDC or BTC/USDC)
   - Set range (or use AI-suggested range)
   - Choose bot mode (Defensor Bajista or Defensor Alcista)
         |
7. Bot activates → monitoring begins
         |
8. Dashboard shows real-time status
```

---

## Security Model

### API Key Management
- Users provide Hyperliquid **API key** (NOT private key)
- API key can ONLY trade (long/short) — cannot withdraw funds
- Key encrypted with SHA-256 before storage
- Key expires max 180 days — system alerts for renewal
- User can revoke key anytime from Hyperliquid

### Platform Security
- No custody of user funds at any point
- All trading happens on user's own Hyperliquid account
- LP pools remain under user's wallet control
- Platform only monitors and executes hedge trades via API
- 2FA required for portal login
- All API communications over HTTPS/WSS

### Trust Architecture
```
USER'S WALLET (MetaMask/etc)
  └── Controls: Uniswap v3 LP position
  └── Controls: Hyperliquid account funds

PLATFORM (our bot)
  └── Has: Hyperliquid API key (trade-only)
  └── Can: Open/close short/long positions
  └── Cannot: Withdraw funds, transfer USDC, change settings

RESULT: User maintains full custody at all times
```

---

## Feature Roadmap

### Phase 1 — MVP (Month 1-2)
- [ ] Single-user bot (own capital)
- [ ] Hyperliquid API integration
- [ ] Uniswap v3 pool monitoring (via RPC)
- [ ] Bot Defensor Bajista mode (hedge on exit below range)
- [ ] Basic web dashboard (FastAPI + Jinja2)
- [ ] Email notifications

### Phase 2 — Multi-User Portal (Month 3-4)
- [ ] Odoo CE 19 integration (membership, billing, CRM)
- [ ] User registration + onboarding flow
- [ ] API key management (encrypted storage)
- [ ] Free + Starter tiers launch
- [ ] Telegram notifications
- [ ] ADX regime alerts

### Phase 3 — Pro Features (Month 5-6)
- [ ] Bot Defensor Alcista mode (long trading on breakout)
- [ ] Auto-rebalancing
- [ ] AI-suggested ranges (based on AT)
- [ ] Pro tier launch
- [ ] WhatsApp notifications
- [ ] Performance analytics

### Phase 4 — Scale (Month 7-12)
- [ ] Enterprise tier
- [ ] Multi-network support (Base, Ethereum L1)
- [ ] Altcoin pool support
- [ ] White-label dashboard
- [ ] API access for enterprise
- [ ] Tax reporting export
- [ ] Mobile app (PWA)

---

## Competitive Positioning

### vs DeFi Suite (Raúl/Talenlan)
- DeFi Suite requires trust in their platform
- We offer: self-hosted option (Option B from Clase 3)
- Open-source bot core, paid managed service
- Can coexist — target different user segments

### vs Manual Management
- Manual requires constant monitoring
- Bot reacts in seconds, not hours
- Consistent execution, no emotional decisions
- Cost of subscription << cost of missed hedge

### vs Other LP Management Tools
- revert.finance: monitoring only, no hedging
- Arrakis/Gamma: auto-rebalance but no perps hedge
- Our edge: **hedge coverage** that eliminates IL risk

---

## Pricing Psychology

- **Free tier exists** to build trust and user base
- **$19 Starter** is "cup of coffee" pricing — easy impulse decision
- **$49 Pro** is "serious tool" pricing — pays for itself with one saved rebalance
- **$199 Enterprise** is "peace of mind" pricing for larger portfolios
- Annual discount (17%) encourages commitment
- Performance fee aligns interests — we only win when user wins

---

## Marketing Channels

| Channel | Strategy |
|---------|----------|
| Bootcamp Alumni | Direct outreach, 20% discount |
| Crypto Twitter/X | Educational threads about IL protection |
| YouTube | Tutorial videos: "How to earn 8-15% monthly with LP" |
| Discord/Telegram | Community group with free AT analysis |
| Reddit (r/defi) | Case studies and backtest results |
| Referral Program | Word of mouth from satisfied users |
| SEO | "Uniswap v3 impermanent loss protection" keywords |

---

## Key Metrics to Track

| Metric | Target (Y1) |
|--------|-------------|
| Total Registered Users | 500+ |
| Paid Subscribers | 145+ |
| Monthly Recurring Revenue | $4,855+ |
| Churn Rate | < 5%/month |
| Average Revenue Per User | $33.50 |
| Pool Value Under Management | $500K+ |
| Hedge Success Rate | > 85% |
| Platform Uptime | 99.5%+ |
| NPS Score | > 50 |

---

## Legal Considerations

- **Not investment advice** — platform is a tool, not a fund
- **No custody** — users maintain full control of their funds
- **Terms of Service** — clear risk disclaimers
- **Privacy Policy** — GDPR compliant, API keys encrypted
- **Jurisdiction** — consider crypto-friendly jurisdictions
- **Disclaimer:** "Past backtest performance does not guarantee future results"

---

*This is a preliminary plan. Pricing and features subject to adjustment based on market feedback and user testing.*
