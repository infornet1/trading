# RSI + AI Strategy Research — VIZNAGO FURY
**Date:** March 24, 2026
**Status:** Research & Planning Phase

---

## Overview

This document captures research on AI-enhanced RSI trading strategies for BTC/USDC and ETH/USDC pairs, an audit of the existing `adx_strategy_v2` bot, and the roadmap for integrating a new RSI/AI module into VIZNAGO FURY.

---

## 1. Why Pure RSI Is No Longer Enough

Static RSI (fixed 30/70 thresholds) is a **declining edge**:

- Win rates dropped from ~62% (2017) → ~39% (2022) for RSI/Bollinger strategies
- Crypto market microstructure has changed significantly since 2020
- Fixed thresholds do not adapt to volatility regimes
- Any new RSI bot needs an AI or adaptive layer to be relevant in 2025-2026

---

## 2. AI-Enhanced RSI Methods — 2024-2025 Research

### Method 1: XGBoost + RSI Features
**Best for:** First implementation — highest ROI on development effort

- RSI-14 and RSI-30 fed as numeric features into XGBoost alongside MACD, ATR, Bollinger Band width
- Model learns nonlinear relationships (e.g. RSI-30 is only meaningful as a sell signal in specific volatility regimes)
- CPU-only — no GPU infrastructure required
- **2025 paper (arXiv 2410.06935):** 92.4% directional accuracy on BTC 15-min candles
  - Precision: 89.17%, Recall: 94.90%, ROC AUC: 0.9817
  - Dataset: BTC 15-min candles, Feb 2021 – Feb 2022
- ⚠️ 92% classification accuracy ≠ 92% profitable trades — fees and slippage reduce real returns significantly

**References:**
- [XGBoost + RSI Bitcoin Trend Prediction (arXiv 2410.06935)](https://arxiv.org/html/2410.06935v1)
- [LSTM+XGBoost hybrid (arXiv 2506.22055)](https://arxiv.org/html/2506.22055v1)

---

### Method 2: Genetic Algorithm RSI (CGA-Agent) — Strongest ETH Results
**Best for:** ETH/USDC — documented strongest improvement

- Uses **dual RSI crossover** as base signal: RSI-fast crosses RSI-slow
- Genetic algorithm reoptimizes RSI periods + MA filters + slope filters every 30 days
- Rolling window reoptimization prevents parameter decay over time
- **2025 paper (arXiv 2510.07943):** Results on Dec 2024 – Sep 2025 data:

| Asset | Return Improvement | Sharpe Improvement |
|-------|-------------------|-------------------|
| BTC   | +29.17%           | —                 |
| ETH   | +550%             | +354.35%          |
| BNB   | +169.48%          | —                 |

- ETH benefits most due to stronger mean-reversion properties vs BTC
- ⚠️ Results compare optimized vs unoptimized dual-RSI, not vs buy-and-hold

**References:**
- [CGA-Agent Genetic Algorithm + RSI (arXiv 2510.07943)](https://arxiv.org/html/2510.07943v1)

---

### Method 3: Adaptive / Dynamic RSI Thresholds
**Best for:** Low-overhead improvement over static thresholds

- Instead of fixed 30/70: compute thresholds dynamically using a **rolling percentile window** (e.g. 252-bar lookback)
- Overbought = RSI exceeds its own 90th percentile historically
- Oversold = RSI falls below its own 10th percentile historically
- No ML infrastructure — just smarter math
- Naturally adapts to volatility regime changes

---

### Method 4: Reinforcement Learning (DQN / SAC) + RSI
**Best for:** Research — NOT recommended for near-term deployment

- DQN agent selects among RSI and other strategies per market condition
- **2025 paper (Tandfonline):** Starting from $1M, DQN achieved 120× NAV growth on BTC (2022–2025 backtest)
- **SAC (Soft Actor-Critic):** 94% annualized returns in high-volatility periods

**Critical caveat — community reality check:**
> A Freqtrade strategy with +50% backtest return / 75% win rate went live to -10% / 40% win rate.
> This overfitting gap is the norm, not the exception for DRL.

- GPU required, 6-12 months of tuning minimum
- ❌ **Not recommended for VIZNAGO until simpler methods are validated first**

**References:**
- [DQN Selects RSI Strategies for BTC (Tandfonline 2025)](https://www.tandfonline.com/doi/full/10.1080/23322039.2025.2594873)
- [Multi-level DQN Bitcoin — Sharpe 2.74 (Nature 2024)](https://www.nature.com/articles/s41598-024-51408-w)
- [SAC/DDQN Crypto Portfolio (arXiv 2511.20678)](https://arxiv.org/html/2511.20678v1)

---

### Method 5: LSTM / Transformer + RSI
**Best for:** Price prediction research — NOT direct trading signals

- **Helformer (SpringerNature 2025):** LSTM-Transformer hybrid on BTC 2017-2024. MAPE 0.0148%, R² ~1.0 on test data
- **LSTM standalone (arXiv 2511.00665):** ~65% return on BTC post-ETF approval (Jan 2024)
- **TFT Multi-Crypto (MDPI 2025):** Temporal Fusion Transformer with RSI, MACD, on-chain data
- ⚠️ Most LSTM bots fail live due to lag: "makes a little money initially but slowly loses through late trades"

**References:**
- [Helformer LSTM-Transformer (SpringerNature 2025)](https://journalofbigdata.springeropen.com/articles/10.1186/s40537-025-01135-4)
- [Technical Analysis Meets ML: BTC (arXiv 2511.00665)](https://arxiv.org/abs/2511.00665)
- [TFT Multi-Crypto (MDPI 2025)](https://www.mdpi.com/2079-8954/13/6/474)

---

## 3. Method Comparison Table

| Method | Dev Complexity | Infrastructure | Live Risk | Performance Edge |
|--------|---------------|----------------|-----------|-----------------|
| Static RSI (baseline) | Very Low | None | Low | Declining (~39% WR) |
| Adaptive RSI thresholds | Low | CPU | Low | Solid, low overhead |
| XGBoost + RSI features | Low-Medium | CPU only | Medium | +15-30% signal accuracy |
| Genetic Algo dual RSI | Medium | CPU | Medium | High for ETH (+550% vs baseline) |
| LSTM + RSI | Medium | GPU helpful | Medium-High | Moderate, lag issues |
| DRL (DQN/SAC) + RSI | High | GPU required | Very High | High backtest, poor live |
| LSTM+Transformer ensemble | Very High | GPU required | Very High | Best accuracy, most overfit |

---

## 4. ADX Strategy v2 Audit — Why It Has Poor ROI

The existing `adx_strategy_v2` bot was audited on March 24, 2026.

### Live Trading Results (Oct 18 – Dec 9, 2025)
| Metric | Value |
|--------|-------|
| Starting balance | $160.00 |
| Current balance | $114.75 |
| Total P&L | **-$45.25 (-28.28%)** |
| Total trades | 34 |
| Win rate | 41.2% |
| Profit factor | 0.43 |
| Expectancy | -$0.81 per trade |

**Break-even requirement:** 52%+ win rate at 2:1 R:R. Current 41% is structurally unprofitable.

---

### Critical Flaws Found

#### 🔴 CRITICAL — RSI Filter Was Never Running
- RSI value was always `None` in live trading
- Filter silently bypassed — every entry accepted regardless of RSI
- Should have been filtering overbought longs and oversold shorts
- **Impact:** Entry quality severely degraded for entire live trading period

#### 🔴 CRITICAL — Multi-Timeframe Confirmation Disabled
- `check_multi_timeframe_confirmation()` requires an API client parameter
- API client was never passed → function always returned `True`
- Should have filtered 30-40% of false signals
- **Impact:** MTF confirmation provided zero protection

#### 🔴 CRITICAL — Backtest Never Executed
- `backtest_adx.py` framework exists but was never run
- Strategy went live without any historical validation
- 100+ trades needed for statistical validity — only 34 trades taken

#### 🟠 HIGH — Slippage Destroyed One Trade (Kill Shot)
- Oct 22 trade: intended risk 2% ($3.20), actual loss 18.63% ($29.78)
- Market gapped 4.7% past stop, amplified by 5× leverage
- Single trade caused most of the -28% all-time loss
- **Fixed Nov 7:** 50% slippage buffer added, position hard cap 10%

#### 🟠 HIGH — Backtest P&L Calculations Wrong
- Hardcoded `$100 capital` instead of real balance tracking
- No fees deducted (0.05-0.10% per side = 0.10% round trip)
- No slippage modeled in backtest
- Results from backtest are not meaningful

#### 🟠 HIGH — Look-Ahead Bias in Candle Checking
- Backtest checks future candles for SL/TP hits
- Introduces survivorship bias in performance metrics

#### 🟡 MEDIUM — Config Issues (Fixed Nov 7)
- Circuit breaker was 10 losses (allowed 70% drawdown) → fixed to 3
- Leverage was 5× → reduced to 3×
- Trailing stop had early return bug → fixed

---

### Root Cause Summary

> The ADX strategy concept (ADX + RSI + Multi-Timeframe) is not inherently bad.
> The -28% loss is entirely explainable by execution/infrastructure failures:
> two critical filters silently broken, no real backtest, and dangerous position
> sizing with 5× leverage and no slippage buffer.

---

## 5. Open Source Frameworks for Reference

| Framework | Best For |
|-----------|---------|
| [Freqtrade + FreqAI](https://github.com/freqtrade/freqtrade) | Full pipeline: feature engineering, ML training, live retraining, execution. Best documented. |
| [OctoBot](https://github.com/Drakkar-Software/OctoBot) | Supports Hyperliquid + 15 exchanges. Strategy marketplace. |
| [Hummingbot](https://github.com/hummingbot/hummingbot) | Market-making / HFT. Extensible. |

---

## 6. Integration Plan for VIZNAGO FURY

### Proposed New Bot Mode

```
VIZNAGO bot modes:
├── Defensor Bajista  (aragan) — LP hedge only            [LIVE]
├── Defensor Alcista  (avaro)  — LP hedge + long breakout [LIVE]
└── RSI Trader        (rsi)    — AI-optimized RSI perps   [PLANNED]
    ├── No LP position required — pure Hyperliquid perps
    ├── BTC: long-only signals (golden rule enforced)
    └── ETH: bidirectional (long + short)
```

### Two Build Paths

#### Path A — Fix adx_strategy_v2 First (Recommended First Step)

1. Fix backtest engine: real balance tracking, fees, slippage model
2. Fix RSI filter: wire RSI calculation into live signal pipeline
3. Fix MTF: pass API client to multi-timeframe confirmation
4. Run backtest on 90-120 days historical data
5. Validate win rate ≥ 52% on out-of-sample data
6. Paper trade 3-4 weeks before any live consideration

**If win rate ≥ 52% → existing strategy is viable with no extra build**
**If win rate < 52% → proceed to Path B with clean knowledge of what doesn't work**

#### Path B — New RSI/AI Module in VIZNAGO

1. Add `RSI Trader` as 4th strategy in `src/engine/strategy_comparator.py`
2. Implement two variants:
   - **Variant A:** XGBoost + RSI (RSI-14, RSI-30, ATR, MACD, ADX as features)
   - **Variant B:** Genetic Algorithm dual RSI with 30-day rolling reoptimization
3. Backtest both on same BTC/ETH 2025 dataset already used for LP hedge
4. Compare results directly vs Defensor Bajista / Defensor Alcista / LP Only / HODL
5. Integrate best performer as `mode = 'rsi'` in API + dashboard
6. Gate behind Pro+ membership tier

### ADX Regime Integration (Natural Fit)

The ADX framework already in VIZNAGO becomes a **pre-filter** for RSI signals:

| ADX Regime | RSI Strategy Behavior |
|------------|----------------------|
| ADX < 20 (lateral) | RSI mean-reversion signals (oversold/overbought) |
| ADX 20-25 (developing) | Reduced position size, higher RSI confidence required |
| ADX > 25 (trending) | RSI trend-continuation signals (pullback to 40-50 in uptrend) |

This eliminates the most common RSI failure mode: taking mean-reversion signals during strong trends.

---

## 7. Key Rules Before Any Live Deployment

1. **Never deploy without 90+ day out-of-sample backtest** — the adx_strategy_v2 went live without this
2. **Always include fees (0.10% round trip) and slippage (0.1-0.2%) in backtest**
3. **Paper trade minimum 3-4 weeks** before real capital
4. **BTC: long-only RSI signals** — golden rule always enforced
5. **Win rate threshold: 52% minimum** at 2:1 R:R before going live
6. **Circuit breaker: max 3 consecutive losses** — proven critical from adx_strategy_v2 lesson
7. **Position sizing: max 10% of account per trade** with 50% slippage buffer

---

## 8. Recommended Action Order

```
Step 1 → Fix adx_strategy_v2 backtest (fees, slippage, real balance)
Step 2 → Fix RSI + MTF filters in adx_strategy_v2
Step 3 → Run 90-day backtest, measure real win rate
Step 4 → If WR ≥ 52%: paper trade adx_strategy_v2
         If WR < 52%: build VIZNAGO RSI module (Path B)
Step 5 → Add RSI Trader mode to VIZNAGO (XGBoost variant first)
Step 6 → Backtest RSI Trader on same dataset as LP hedge strategies
Step 7 → If results competitive: add to dashboard as new bot mode
Step 8 → Gate behind Pro+ tier in membership plans
```

---

*Research based on papers published 2024-2026. Strategy parameters require validation against current market conditions before deployment. Not investment advice.*
