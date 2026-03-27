# LP + Perps Hedge Strategy — Complete Guide

## Overview

Automated strategy combining **Uniswap v3 concentrated liquidity provision** with **perpetual futures hedging** on Hyperliquid to protect against impermanent loss (IL).

Based on **Bootcamp Cripto 2026** by Jaime Merino (Trading Latino) and Raúl Martín (Talenlan).

---

## How It Works

```
Pool ETH/USDC active inside range → generates fees
         |
Price drops to lower bound
         |
BOT detects exit from range
         |
Opens SHORT on Hyperliquid (via API key)
         |
Pool out of range → no fees BUT
Short is profiting → compensates IL
         |
Price returns → SHORT closes automatically (TP)
Price keeps falling → SHORT keeps covering
```

**Key insight:** The goal is NOT to profit from the hedge — it's to **break even on IL** so you can close the pool without loss, take hedge profits, and reopen a new range with capital intact.

---

## Three Bot Modes

### VIZNAGO Defensor Bajista (Hedge Only — Recommended for LP holders)
- SHORT when price drops below lower bound OR crosses upper bound downward
- Bear hedge with bullish bias — on upside, SL exits quickly and LP keeps all gains
- For passive investors who want capital protection
- **Best performer in backtests** (+361% vs +340% LP Only)
- Requires a Uniswap v3 LP position (NFT)

### VIZNAGO Defensor Alcista (Hedge + Trading)
- SHORT when price drops below lower bound
- LONG when price breaks above upper bound (with trailing stop)
- For active traders who want to maximize returns
- Requires parameter tuning per market conditions
- Requires a Uniswap v3 LP position (NFT)

### VIZNAGO FURY (Standalone RSI Perps — No LP Required)
- Pure perpetuals trading on Hyperliquid — **does NOT require a Uniswap LP position**
- 6-gate signal stack on 15-minute candles with 1-hour MTF confirmation:
  - Gate 1: EMA-8 vs EMA-21 trend direction
  - Gate 2: RSI(9/OHLC4) < 35 LONG | > 65 SHORT on 15m
  - Gate 3: 1h RSI confirms (< 50 LONG, > 50 SHORT)
  - Gate 4: Volume spike > 20-bar average
  - Gate 5: OBV 5-bar slope (longs only)
  - Gate 6: Funding rate bias (> +0.05% → SHORT only)
- Dynamic leverage: 3 gates=3x, 4=5x, 5=8x, 6=12x
- ATR-12 hybrid stop with 3R target
- BTC golden rule strictly enforced: LONG only, never SHORT BTC
- Circuit breaker: pauses on 5% daily drawdown OR 3 consecutive losses
- **Status as of March 2026:** Paper trading phase (not live) — ETH approved for paper trade, BTC not yet approved

---

## Strategy Parameters

### LP Position
| Parameter | Value | Notes |
|-----------|-------|-------|
| Fee Tier | 0.05% | The "secret" — high rotation, best for ETH/BTC |
| Network | Arbitrum or Base | Gas < $0.10 per tx |
| Pairs | ETH/USDC, BTC/USDC only | Other assets risk permanent IL |
| Range Width | ~10-15% | Based on support/resistance via AT |

### Hedge (Short)
| Parameter | Value | Notes |
|-----------|-------|-------|
| Trigger | lower_bound - 0.5% | STOP LIMIT, not market order |
| Size | 50% of volatile capital | ETH/BTC side of LP position |
| Take Profit | lower_bound price | Close when price returns to range |
| Leverage | 2x | Conservative, avoid liquidation |

### Long (Defensor Alcista Only)
| Parameter | Value | Notes |
|-----------|-------|-------|
| Trigger | upper_bound + 0.5% | Breakout confirmation |
| Initial Stop | -0.5% from entry | Tight initial protection |
| Trailing Stop | -2% from max price | Locks in profits on the way up |

### Golden Rules
- **BTC: NEVER SHORT** — No ceiling, asymmetric liquidation risk
- **BTC: LONG ONLY** — Bot de trading solo long para BTC
- **ETH: Long + Short OK** — Bidirectional hedge allowed

---

## Technical Analysis Framework

### 3 Layers (Raúl Martín)
1. **Technical (90%):** ADX, EMAs, support/resistance, chart patterns
2. **Fundamental:** ETF news, regulation, institutional adoption
3. **Geopolitical:** Interest rates, wars, inflation — can override everything

### ADX Regime Detection
| ADX Value | Regime | Action |
|-----------|--------|--------|
| < 20 | Lateral/Ranging | **OPEN POOL** — ideal conditions |
| 20-25 | Developing trend | Caution, monitor closely |
| > 25-30 | Strong trend | **HIGH RISK** for pools, hedge mandatory |

### Breakout Detection Signals
1. ADX with negative slope → losing directional force
2. Price touches same S/R level 3+ times → range confirmed
3. Volume decreases on each touch → less conviction
4. Divergence: price makes new low but ADX doesn't → weakness

### EMA Crossover
- **EMA(10) > MA(25):** Bullish — price trending up
- **EMA(10) < MA(25):** Bearish — price trending down
- Used to confirm trend direction, not for entry/exit

### Recommended Timeframes
| Timeframe | Use Case |
|-----------|----------|
| Daily | BTC range (weekly duration) |
| 4 Hours | ETH range (daily duration) — **optimal balance** |
| 1 Hour | Active management, higher APR, more rebalances |
| 15 Minutes | NOT recommended — too much gas, pool lasts minutes |

---

## Range Configuration with AT

The range is configured between **support** (lower bound) and **resistance** (upper bound) identified on the chart:

- **Wider range** = fewer rebalances, less gas, but lower fee concentration
- **Tighter range** = more fees per dollar, but exits range faster
- **Recommendation:** Start with daily range for ETH, weekly for BTC. Tighten with experience.
- Short trigger goes 0.5-1% **below** the lower bound to avoid false activations

---

## Capital Allocation (Jaime's Framework)

| Allocation | Percentage | Purpose |
|------------|-----------|---------|
| HODL | 40% | Long-term Bitcoin hold, never sell |
| Liquidity Pools | 30% | Fee generation via Uniswap v3 |
| Spot Trading | 20% | Active trading (EMA crossovers, breakouts) |
| Futures (Hedge) | 10% | ONLY for hedging pool IL, not speculation |

---

## Backtest Results (ETH/USDT 2025)

Tested on full 2025 data (8,733 hourly candles, $1,418 - $4,934 price range):

| Strategy | Return | Max DD | Sharpe | Sortino |
|----------|--------|--------|--------|---------|
| HODL 50/50 | -5.6% | 32.5% | -0.01 | -0.01 |
| LP Only | +340% | 39.4% | 2.55 | 3.64 |
| **Bot Defensor Bajista** | **+361%** | **29.4%** | **2.88** | **4.69** |
| Bot Defensor Alcista | +357% | 34.9% | 2.82 | 4.89 |

### Key Findings
- Hedge adds **+$2,083** vs LP Only and reduces max drawdown by **10 points**
- Dynamic rebalancing (42 rebalances) keeps position in range **75%** of the time
- Defensor Alcista long trading has 24% win rate — needs parameter tuning
- Static ranges fail (23% time in range without rebalancing)

---

## Current Market Analysis (March 13, 2026)

### BTC/USDT — $90,575
- ADX: 31.7 (rising) — **STRONG TREND, NOT IDEAL FOR POOLS**
- Direction: Bearish (-DI > +DI)
- EMA(10) $92,293 < MA(25) $94,524 — bearish crossover
- Support: $87,266 - $88,520
- Resistance: $90,585 - $95,491

### ETH/USDT — $3,114
- ADX: 30.6 (FALLING from 36.7) — **Trend losing force**
- Direction: Bearish (-DI > +DI)
- EMA(10) $3,158 < MA(25) $3,256 — bearish crossover
- Support: $2,899 - $2,981
- Resistance: $3,234 - $3,383

### Recommended Pool Configurations

#### ETH/USDC — Deploy when ADX < 20
```
Lower Bound:  $2,900  (support cluster)
Upper Bound:  $3,380  (resistance cluster)
Width:        ~15.5%
Fee Tier:     0.05%
Network:      Arbitrum
Hedge:        SHORT at $2,885 (-0.5% below lower)
TP:           $2,900
```

#### BTC/USDC — Weekly Range
```
Lower Bound:  $87,500  (support cluster)
Upper Bound:  $95,500  (resistance)
Width:        ~8.8%
Fee Tier:     0.05%
Network:      Arbitrum
Mode:         LONG only (never short BTC)
Long trigger: $95,978 (+0.5% above upper)
```

#### If deploying NOW (higher risk, wider defensive ranges):
- **ETH:** $2,800 - $3,400 (~19.5% width, hedge mandatory)
- **BTC:** $85,000 - $96,000 (~12.2% width, long only)

---

## Infrastructure

### Current Stack
- **Backtester:** `/var/www/dev/trading/lp_hedge_backtest/`
- **Price Data:** BingX API (Binance/Bybit geo-blocked)
- **Python venv:** `/var/www/dev/trading/venv/`
- **Course PDFs:** `/home/ftpuser/pool/`

### Hyperliquid Connection
- **Wallet:** `0x5Bb02931E8840D8185a66d318BF8AFa2b78f909e`
- **Balance:** 5.42 USDC (need min $10 for API)
- **API Key:** Use API key (NOT private key) — can only trade, cannot withdraw
- **Key expiry:** Max 180 days, renew before expiration

### Next Steps — Build Live Bot
1. Monitor ADX daily (4h chart) — wait for lateral signal
2. Fund Hyperliquid with 10-20% of pool value
3. Build live trading engine (FastAPI + Hyperliquid API + Uniswap v3 RPC)
4. Deploy first pool with $50-100 (minimum viable test)
5. Monitor with revert.finance for real APR tracking

### Future — Trading Portal
- Odoo Community 19 for business layer (membership, billing, CRM)
- FastAPI microservice for trading engine
- Separate concerns: Odoo handles business, bot handles trading
- Phase 1: Own bot working → Phase 2: Multi-user portal → Phase 3: Scale

---

## Glossary

| Term | Definition |
|------|-----------|
| **VIZNAGO Defensor Bajista** | LP hedge bot — short-only when price drops below range or re-enters from above |
| **VIZNAGO Defensor Alcista** | LP hedge + long trading mode (short below, long above range) |
| **VIZNAGO FURY** | Standalone RSI perps bot — no LP required, 6-gate signal stack on 15m candles |
| **IL** | Impermanent Loss — value lost vs holding when price moves |
| **Concentrated LP** | Uniswap v3 — provide liquidity in a specific price range |
| **Trailing Stop** | Stop loss that moves up with price, closes on X% drop from max |
| **SL Floor** | Hard minimum stop-loss of 0.3% — prevents whipsaw from tiny SL gaps |
| **ADX** | Average Directional Index — measures trend strength (not direction) |
| **Regime** | Market state: lateral (ADX<20), trending (ADX>30) |
| **Rebalance** | Close pool and reopen at new range when price exits |
| **Circuit Breaker** | FURY safety — pauses trading after 5% daily loss or 3 consecutive losses |
| **OHLC4** | (Open+High+Low+Close)/4 — RSI source used in FURY for smoother signals |
| **MTF** | Multi-timeframe — FURY uses 15m signals confirmed by 1h trend |
| **DeFi Suite** | Raúl's platform that automates pool hedging |
| **Talentoso** | AI assistant from bootcamp (Claude Opus 4.6 based) |

---

*Strategy based on Bootcamp Cripto 2026 — Talent Academy. Educational material, not investment advice.*
