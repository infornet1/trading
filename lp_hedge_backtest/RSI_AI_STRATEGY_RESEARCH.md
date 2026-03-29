# RSI + AI Strategy Research — VIZNAGO FURY
**Date:** March 24, 2026 — Updated March 27, 2026
**Status:** Implementation Complete — Pending Backtest Validation

---

## Overview

This document captures research on AI-enhanced RSI trading strategies for BTC/USDC and ETH/USDC pairs, an audit of the existing `adx_strategy_v2` bot, practitioner best practices sourced from X (March 2025–2026), the VIZNAGO FURY standalone perps spec, and the roadmap for integrating a new RSI/AI module into VIZNAGO FURY.

---

## 1. Why Pure RSI Is No Longer Enough

Static RSI (fixed 30/70 thresholds) is a **declining edge**:

- Win rates dropped from ~62% (2017) → ~39% (2022) for RSI/Bollinger strategies
- Crypto market microstructure has changed significantly since 2020
- Fixed thresholds do not adapt to volatility regimes
- Any new RSI bot needs an AI or adaptive layer to be relevant in 2025-2026

**Crypto-specific parameter correction (X practitioner consensus):**
- Standard 70/30 thresholds were calibrated for equities — too tight for crypto's baseline volatility
- 1h crypto charts: use **period 7-9 with 75/25 thresholds** (not 70/30)
- 15m crypto charts: use **35/65 thresholds** to match faster mean-reversion dynamics
- Short-period RSI (2-6) with 85/15 thresholds outperforms RSI-14 for pure mean-reversion plays

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

**Production implementation detail (BOSWaves, from X research):**
1. Compute base RSI (period 14)
2. Apply **HMA-4 (Hull Moving Average, period 4)** smoothing to RSI before comparison — reduces noise without lag penalty
3. Maintain rolling array of last 100-200 confirmed RSI values
4. Upper threshold = 80th percentile of array | Lower threshold = 20th percentile
5. **Regime persistence:** signal stays active until opposite threshold is crossed — no whipsaw on minor oscillations
6. During low-volatility consolidation, thresholds tighten automatically (e.g., 60/40). During trends, they widen (80+/20-)

**AI-driven alternative (Tickeron pattern):** After 200+ trades, ML fits per-asset thresholds. BTC effective oversold on Hyperliquid ≈ 28, not 30. ETH ≈ 32.

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

## 4. Signal Quality Enhancements (X Research — March 2026)

These are additive improvements not found in academic papers — sourced from practitioner discussions on X and algo-trading communities.

### 4.1 RSI Source: Switch from Close to OHLC4

Use `(Open + High + Low + Close) / 4` as the RSI input instead of just Close price.

- One-line change in implementation
- Smooths the oscillator — fewer whipsaws
- Makes divergence signals easier to detect
- No new parameters introduced

### 4.2 RSI Failure Swings (Algorithmically Clean — High Priority)

Failure swings track **only RSI structure** — no price/RSI comparison needed. Easier to implement than divergence.

**Bearish failure swing (short signal):**
1. RSI rises into overbought (above threshold)
2. RSI retreats below threshold
3. RSI bounces but **fails to reach the prior peak** (second peak < first peak, stays below OB zone)
4. RSI breaks below the trough between the two peaks
5. Entry: short on candle after trough breakdown
6. Stop loss: above the second-peak price level

**Bullish failure swing (long signal):**
1. RSI drops into oversold (below threshold)
2. RSI bounces above threshold
3. RSI pulls back but **fails to reach the prior trough** (second trough > first trough, stays above OS zone)
4. RSI breaks above the peak between the two troughs
5. Entry: long on candle after peak breakout
6. Stop loss: below the second-trough price level

**Filter requirement:** Add ADX < 25 gate before allowing failure swing entries — prevents false signals in strong trending markets.

### 4.3 Hidden Divergence (Trend Continuation — Missing from Prior Research)

Hidden divergence gives **trend-continuation entries at pullback prices** — high value for perps bots.

**Hidden bullish (long the pullback in an uptrend):**
- Price makes a **higher low** (normal uptrend pullback)
- RSI makes a **lower low** simultaneously
- Signal: uptrend continues — buy the dip

**Hidden bearish (short the bounce in a downtrend):**
- Price makes a **lower high** (dead-cat bounce)
- RSI makes a **higher high** simultaneously
- Signal: downtrend continues — short the bounce

**Algorithmic detection parameters (Cleo Finance implementation):**
- Lookback range: 60 bars
- Pivot lookback left: 1 bar | Pivot lookback right: 3 bars
- Both swing points must be local extrema within a 5-bar window
- **Confirmation required:** candlestick pattern (hammer/engulfing) OR RSI crossing back through threshold before entry
- Higher timeframe divergences carry more weight: daily > 4h > 1h > 15m

**References:**
- [Hidden Divergence Strategy — QuantStrategy.io](https://quantstrategy.io/blog/what-is-a-hidden-divergence-how-to-use-it-in-trading/)
- [RSI Divergence Crypto Bot — Cleo Finance / Medium](https://medium.com/cleo-finance/how-to-create-a-crypto-bot-trading-rsi-divergence-c99505ef6074)

### 4.4 Volume Confirmation Gates

**OBV slope gate (blocks distribution traps):**
- Before entering any RSI long, check: `OBV_5bar_slope > 0`
- If OBV is falling while RSI is oversold, smart money is distributing — the bounce is a trap
- Only adds 1 indicator, no new parameters

**Volume spike gate:**
- Entry candle volume must exceed the 20-bar average volume
- RSI signals on low-volume candles have significantly lower follow-through in crypto
- Implementation: `candle_volume > volume_sma_20`

**RSI-VWAP variant (optional):**
- Calculate RSI on VWAP data instead of close price
- Anchors momentum calculation to volume-weighted fair value
- Filters out thin-volume spikes with no institutional backing
- Available as indicator on WunderTrading / TradingView

**References:**
- [RSI-VWAP Free Strategy for Bots — WunderTrading](https://help.wundertrading.com/en/articles/5176436-rsi-vwap-free-tradingview-strategy-for-bots)
- [OBV Smart Money Tracking — CryptoHopper](https://www.cryptohopper.com/news/chart-decoder-series-volume-obv-the-smart-money-tracking-system-12165)

### 4.5 Multi-Timeframe RSI Stacking

**Minimum viable 3-layer gate for a perps bot:**
- Primary signal: 15m RSI
- Gate 1: 1h RSI must confirm direction (if 15m oversold, 1h RSI must also be below 50)
- Gate 2: Daily RSI must not be at extreme opposite (don't take longs if daily RSI is overbought)
- Result: eliminates counter-trend entries without ML infrastructure

**RSI Superstack scoring (7-timeframe):**
Monitor RSI across 5m / 15m / 30m / 1h / 4h / 1d / 1w — produce confluence score 0-7:
- Score 5-7 bullish → high-confidence long, full position size
- Score 3-4 → reduce size by 50%
- Score 0-2 → skip signal

**Stochastic RSI as trigger complement:**
- Use RSI-14 on 1h as the **trend filter** (is this an uptrend or downtrend context?)
- Use StochRSI on 15m as the **entry trigger** (faster, more sensitive)
- Avoids circular logic of using RSI for both filtering and triggering

**References:**
- [Multi-Timeframe RSI and Stochastics — FMZQuant / Medium](https://medium.com/@FMZQuant/multi-timeframe-rsi-and-stochastics-strategy-d56106d09171)

---

## 5. ATR Stop Loss — Production Numbers

### Stop Placement Formula
```
Long:  stop = entry_price - (multiplier × ATR_12)
Short: stop = entry_price + (multiplier × ATR_12)
```

Use **ATR-12** (not ATR-14) — ATR-14 lags by 1-2 candles in fast-moving crypto markets.

**Multiplier by trade type:**
- Mean-reversion RSI trades (15m, high frequency): **1.0–1.5× ATR**
- Trend-continuation RSI trades (swing): **2.0–3.0× ATR**
- ⚠️ 3× ATR on a mean-reversion trade creates a stop wider than the expected profit

### Hybrid ATR Stop (Prevents Volatility Spike Widening)

```python
atr_raw = 1.5 * ATR_12
stop_distance = max(atr_raw, FLOOR)
stop_distance = min(stop_distance, CEILING)
```

| Asset | Floor | Ceiling |
|-------|-------|---------|
| BTC   | $150  | $800    |
| ETH   | $50   | $300    |

Prevents ATR from producing absurdly wide stops during flash crashes.

### Position Sizing with ATR

```
position_size = (account_balance × risk_pct) / stop_distance
```

Risk 1-2% of account per trade. Normalizes position size across volatility regimes.

**References:**
- [Dollar Stop vs ATR Stop Loss — KJ Trading Systems](https://kjtradingsystems.com/algo-trading-tip-dollar-vs-atr-stop-losses.html)
- [ATR Stop Loss Strategy for Crypto — Flipster](https://flipster.io/blog/atr-stop-loss-strategy)

---

## 6. Signal Priority Stack (Combined Architecture)

Ordered by implementation effort vs signal quality impact:

| Priority | Enhancement | Effort | Value |
|----------|------------|--------|-------|
| 1 | Switch RSI source to OHLC4 | 1 line | Low noise |
| 2 | Volume spike gate (>20-bar avg) | 1 line | Cuts thin-volume false signals |
| 3 | OBV 5-bar slope gate on longs | 5 lines | Blocks distribution traps |
| 4 | ATR-12 hybrid stop (capped/floored) | 10 lines | Survives volatility spikes |
| 5 | Failure swing detection | 30 lines | Early reversal entries, RSI-only logic |
| 6 | 3-layer MTF gate (15m/1h/daily) | 20 lines | Eliminates counter-trend entries |
| 7 | Hidden divergence detection | 60 lines | Trend-continuation pullback entries |
| 8 | Adaptive percentile thresholds + HMA | 40 lines | Regime-adaptive OB/OS levels |
| 9 | XGBoost on RSI+ATR+MACD+ADX features | 1-2 days | +15-30% signal accuracy |
| 10 | Genetic Algo dual RSI reoptimization | 3-5 days | Strongest edge for ETH |

---

## 7. ADX Strategy v2 Audit — Why It Has Poor ROI

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

## 8. Common Bot-Builder Mistakes (Practitioner Level — X Research)

**RSI ignores trend direction entirely:** RSI < 30 in a downtrend ≠ RSI < 30 in an uptrend. Without a trend direction filter (price above/below 200 EMA, or ADX > 25), RSI oversold in a bear market will keep triggering losing longs. Single most cited mistake across all sources.

**The too-perfect backtest trap:** Signs of overfitting — near-straight equity curve, >75% WR with tiny drawdown, performance collapses if threshold moves 2 points, strategy only works on one specific 6-month window. Rule: if you cannot explain the edge in one sentence without referencing specific parameters, you are curve-fitting.

**Indicator overload without hierarchy:** Adding RSI + MACD + Bollinger + EMA + ATR + Volume simultaneously without defined roles. Each indicator must have a defined role: RSI = oversold/overbought detector, ATR = volatility filter, OBV = volume confirmation. More indicators without this structure increases overfitting risk.

**Candle-close timing (critical for live bots):** RSI calculated on an in-progress (unclosed) candle will repaint. On 15m, a signal appearing at minute 12 may vanish by minute 15. Only compute signals on confirmed closed candles via WebSocket stream — never via polling.

**Partial fill handling:** Live bot without a partial-fill handler will have undefined position state after the first partial execution. This is not mentioned in most tutorials but causes real production failures.

**Fee minimum for viability:** Average gain per trade must exceed ~0.4% round-trip (0.1% maker/taker each side + slippage) for the strategy to be live-profitable. RSI strategies averaging 0.2-0.3% per trade that look profitable in backtests are often underwater live.

**References:**
- [8 Tips to Avoid Curve-Fitting — AlgomaticTrading](https://www.algomatictrading.com/post/8-tips-to-avoid-curve-fitting)
- [12 Automated Trading Mistakes — TradingView Hub](https://www.tv-hub.org/guide/automated-trading-mistakes)
- [Common Pitfalls Crypto Trading Bots — CoinBureau](https://coinbureau.com/guides/crypto-trading-bot-mistakes-to-avoid/)

---

## 9. Open Source Frameworks for Reference

| Framework | Best For |
|-----------|---------|
| [Freqtrade + FreqAI](https://github.com/freqtrade/freqtrade) | Full pipeline: feature engineering, ML training, live retraining, execution. Best documented. |
| [OctoBot](https://github.com/Drakkar-Software/OctoBot) | Supports Hyperliquid + 15 exchanges. Strategy marketplace. |
| [Hummingbot](https://github.com/hummingbot/hummingbot) | Market-making / HFT. Extensible. |

---

## 10. Integration Plan for VIZNAGO FURY

### Bot Architecture Overview

```
VIZNAGO bot modes:
├── Defensor Bajista  (aragan) — LP hedge only            [LIVE]
├── Defensor Alcista  (avaro)  — LP hedge + long breakout [LIVE]
└── RSI Trader        (fury)   — Standalone Hyperliquid   [BUILT — pending backtest gate]
    ├── No LP position required — pure Hyperliquid perps
    ├── BTC: long-only signals (golden rule enforced)
    ├── ETH: bidirectional (long + short)
    └── Timeframe: 15m candles, 1h + daily confirmation
```

### Signal Stack (Ordered Gate System)

```
Entry allowed only if ALL gates pass:

Gate 1 (Trend):      EMA 8 > EMA 21 (long) or EMA 8 < EMA 21 (short)
Gate 2 (Momentum):   RSI on OHLC4 < 35 (long) or > 65 (short) on 15m
Gate 3 (MTF):        1h RSI confirms direction, daily RSI not at opposite extreme
Gate 4 (Volume):     Entry candle volume > 20-bar average
Gate 5 (OBV):        OBV 5-bar slope > 0 (longs only)
Gate 6 (ADX):        ADX 20-25 regime check for failure swing / divergence signals
Gate 7 (Funding):    If funding rate > +0.05%, bias short (carry overlay)

Position sizing:     (account × 0.01-0.02) / ATR-12 hybrid stop distance
Leverage:            Dynamic 3-12x based on confluence score (gates passed)
Stop loss:           min(max(1.5 × ATR_12, floor), ceiling)
Take profit:         3R (3× stop distance)
Circuit breaker:     Auto-pause if daily drawdown > 5% or 3 consecutive losses
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

#### Path B — New RSI/AI Module in VIZNAGO (RSI Trader mode)

**Selected path — implementation complete as of March 27, 2026.**

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Indicators: RSI(OHLC4), EMA-8/21, OBV slope, ATR-12 (`src/indicators/technical.py`) | ✅ Done |
| 2 | `StandalonePerpsSimulator` with circuit breaker, ATR stop, dynamic leverage (`src/hedge/standalone_perps_simulator.py`) | ✅ Done |
| 3 | `FuryBacktestEngine` — full 15m+1h loop with gate scoring (`src/engine/backtest_engine.py`) | ✅ Done |
| 4 | `FuryComparator` for FURY vs HODL side-by-side (`src/engine/strategy_comparator.py`) | ✅ Done |
| 5 | `live_fury_bot.py` — production subprocess bot, confirmed-candle rule, `[EVENT]` emission | ✅ Done |
| 6 | API integration: DB columns, migrations, mode enum, spawn logic, validation (`api/`) | ✅ Done |
| 7 | Run 90-day backtest — gate: WR ≥ 52% before paper trade | ⏳ Pending |
| 8 | Paper trade 3-4 weeks minimum | ⏳ Pending |
| 9 | Gate behind Pro+ membership tier | ⏳ Pending |

**XGBoost / Genetic Algorithm variants** (Variant A & B from research) deferred — base 6-gate stack must clear the backtest gate first before adding ML complexity.

### ADX Regime Integration (Natural Fit)

The ADX framework already in VIZNAGO becomes a **pre-filter** for RSI signals:

| ADX Regime | RSI Strategy Behavior |
|------------|----------------------|
| ADX < 20 (lateral) | RSI mean-reversion signals + failure swings |
| ADX 20-25 (developing) | Reduced position size, higher RSI confluence required |
| ADX > 25 (trending) | Hidden divergence signals only (trend-continuation pullback entries) |

---

## 11. Key Rules Before Any Live Deployment

1. **Never deploy without 90+ day out-of-sample backtest** — the adx_strategy_v2 went live without this
2. **Always include fees (0.10% round trip) and slippage (0.1-0.2%) in backtest**
3. **Paper trade minimum 3-4 weeks** before real capital
4. **BTC: long-only RSI signals** — golden rule always enforced
5. **Win rate threshold: 52% minimum** at 2:1 R:R before going live
6. **Circuit breaker: max 3 consecutive losses OR 5% daily drawdown** — auto-pause bot
7. **Position sizing: max 2% of account per trade** — survive 10 consecutive losses
8. **Only compute signals on confirmed closed candles** — never on in-progress candles
9. **Implement partial fill handler** before first live trade
10. **Average gain per trade must exceed 0.4%** — otherwise fees eat the edge

---

## 12. Recommended Action Order

```
Step 1  → [DONE] Chose Path B — standalone FURY bot on Hyperliquid (not fixing adx_strategy_v2)
Step 2  → [DONE] Built indicators: RSI(OHLC4), EMA-8/21, OBV slope, ATR-12
Step 3  → [DONE] Built StandalonePerpsSimulator with circuit breaker + dynamic leverage
Step 4  → [DONE] Built FuryBacktestEngine (15m + 1h MTF loop, 6-gate scoring)
Step 5  → [DONE] Built FuryComparator for FURY vs HODL comparison
Step 6  → [DONE] Built live_fury_bot.py — production subprocess, confirmed-candle rule
Step 7  → [DONE] API integration: fury mode enum, DB columns, migrations, spawn logic, validation
Step 8  → [NEXT] Run 90-day backtest on real BTC/ETH data — gate: WR ≥ 52%
Step 9  → If WR ≥ 52%: paper trade 3-4 weeks via VIZNAGO dashboard
           If WR < 52%: tune gates or add XGBoost Variant A (CPU-only)
Step 10 → Live deploy — gate behind Pro+ membership tier
```

---

## 13. Backtest Results & Tuning Notes (March 27, 2026)

### 13.1 ETH/USDT Baseline (RSI 25/75)
- **Result:** +3.97% (90 days) vs HODL -29.30%
- **Win Rate:** 29.4% (Profitable due to ~3:1 R:R)
- **Total Trades:** 68
- **Sharpe Ratio:** 0.53
- **Observation:** ETH is structurally profitable with the current RSI setup. The 3:1 R:R breakeven is 25%, and ETH is consistently holding at 29-32%, even in downtrends.

### 13.2 BTC/USDT — The "Golden Rule" & Bidirectional Test
- **Long-Only (Golden Rule):** -58.75% return, 30.2% WR, 129 trades.
- **Bidirectional (Shorts Allowed):** -85.54% return, 28.6% WR, 241 trades.
- **Critical Finding — Fee Drag:**
  - BTC executed **241 trades** in 90 days, losing **$4,467 in fees** (45% of capital).
  - The ATR stop floor ($150) is too tight for BTC at $60k-$70k prices (~0.2% stop). 
  - Friction (0.1% fees + 0.15% slippage round-trip) consumes the entire stop distance, making the strategy a "fee farm" for the exchange.
- **Action:** BTC requires **wider stops** (increase ATR floor to $300-$500) or **higher gate confluence** (min-gates 5) to reduce overtrading in noise.

### 13.3 Summary Decision
- **ETH:** Proceed to paper trade.
- **BTC:** DO NOT deploy. Current RSI thresholds and stops are too sensitive for BTC price action, leading to terminal fee decay.

---

## 14. BTC Tuning Study — ATR Floor + Gate Confluence (March 28, 2026)

**Goal:** Reproduce baseline with golden rule enforced, then systematically test two fixes from Section 13.2.

**Bug fixed:** BTC golden rule (long-only) was documented but not implemented in `standalone_perps_simulator.py`. Shorts were being taken freely. Fixed in this session — `long_only=True` now enforced by default for BTC.

### 14.1 Corrected Baseline (min-gates 4, floor $150, long-only)

| Metric | Value |
|--------|-------|
| Return | **-52.91%** |
| HODL | -21.25% (BTC bear period Dec25-Mar26) |
| Alpha | -31.66% |
| Win Rate | 31.5% |
| Total Trades | 130 (all longs) |
| Fees | **$3,902** |
| Sharpe | -2.44 |
| Max Drawdown | 57.8% |

Root cause confirmed: fee drag. 130 trades × ~$30 avg fee = structural loss at this frequency.

### 14.2 Full Tuning Matrix (Dec 2025 – Mar 2026)

| Config | Return | WR | Trades | Fees | Alpha vs HODL | Sharpe | MaxDD |
|--------|--------|----|--------|------|---------------|--------|-------|
| Baseline (min4, $150) | -52.91% | 31.5% | 130 | $3,902 | -31.66% | -2.44 | 57.8% |
| A: min5, floor $150 | -9.00% | 30.8% | 13 | $544 | +12.25% | -2.80 | 16.1% |
| B: min4, floor $300 | -55.23% | 29.3% | 123 | $3,489 | -33.97% | -2.67 | 58.5% |
| C: min5, floor $300 | -7.49% | 30.8% | 13 | $491 | +13.77% | -2.21 | 15.5% |
| **D: min5, floor $500** | **+3.27%** | **38.5%** | **13** | **$404** | **+24.52%** | **1.31** | **11.0%** |

**Key insight — ATR floor alone does nothing:** Test B shows that raising the floor to $300 with min-gates 4 barely changes trade count (130→123). The wider stop reduces position size but the signal fires just as often. Fee drag persists.

**Key insight — min-gates 5 is the essential lever:** Drops 130 trades → 13, fees from $3,902 → $544. The circuit breaker now fires far less, and the small number of ultra-high-conviction signals shows positive expectancy.

**Key insight — floor $500 flips BTC to profitable:** Test D is the first positive BTC config: +3.27%, Sharpe 1.31, MaxDD 11%. The $500 floor gives the position enough room to reach 3R TP without being stopped by micro-volatility.

### 14.3 OOS Validation — Test D on Summer 2025 (Jun–Sep 2025)

| Metric | Value |
|--------|-------|
| Return | +7.51% |
| HODL | +2.62% |
| Alpha | +4.89% |
| Win Rate | 46.2% |
| Total Trades | 13 |
| Sharpe | 2.54 |
| Max Drawdown | 8.9% |

### 14.4 Full 10-Month Validation (BingX) — Test D on May 2025 → Mar 2026

**Data fetched:** 30,089 × 15m candles via BingX (also fixed a BingX pagination bug in `price_fetcher.py` — see Section 14.5).

| Metric | Value |
|--------|-------|
| Return | **-33.32%** |
| HODL | **-33.26%** |
| **Alpha vs HODL** | **-0.06%** (zero alpha) |
| Win Rate | 28.6% |
| Total Trades | 56 |
| Fees | $1,708 |
| Sharpe | -2.89 |
| Max Drawdown | 37.5% |
| Circuit breaker fires | **10× in 10 months** (~once per month) |

### 14.4b Definitive 2-Year Validation (OKX) — Jan 2024 → Mar 2026

**Data source:** OKX history-candles API (added as primary source — see Section 14.6). 78,337 × 15m candles.

| Metric | Value |
|--------|-------|
| Return | **-83.46%** |
| HODL | **+61.25%** (2024 bull run) |
| **Alpha vs HODL** | **-144.70%** |
| Win Rate | 22.9% |
| Total Trades | 175 |
| Fees | $2,296 |
| Sharpe | -4.59 |
| Max Drawdown | 84.6% |
| Circuit breaker fires | **30× in 2 years** (~every 2.4 weeks) |

### 14.5 Honest Assessment & Final BTC Decision

**Full cross-period picture (all validated with OKX data):**
- Jun-Sep 2025 (bear → sideways): +7.51% vs HODL +2.62% → alpha +4.89% ← cherry-picked best
- Dec 2025-Mar 2026 (bearish): +3.27% vs HODL -21.25% → alpha +24.52% ← cherry-picked best
- May 2025-Mar 2026 (10 months): -33.32% vs HODL -33.26% → **alpha -0.06%**
- **Jan 2024-Mar 2026 (2 years): -83.46% vs HODL +61.25% → alpha -144.70%** ← definitive

**Root cause — fundamental incompatibility:**
- Circuit breaker fires every 2.4 weeks over 2 years = recurrent, systematic, not recoverable by tuning
- In a 2024-2025 bull market, long-only "buy the oversold dip" on 15m BTC is a losing proposition — BTC trends hard, pullbacks on 15m are noise, not reversion opportunities
- WR 22.9% over 175 trades — no amount of ATR/gate tuning fixes a structural 22% WR

**Final BTC Decision: DO NOT DEPLOY — Strategy incompatible with BTC microstructure ❌**

This is not a tuning problem. It is a fundamental incompatibility: **15m RSI mean-reversion long-only does not match BTC's behavior across any 2024-2026 market regime** (bull, bear, or sideways).

**What would actually work for BTC (future research):**
1. **Longer timeframe** — 4h or daily RSI signals, not 15m. BTC trends on short timeframes.
2. **Bidirectional** — allow shorts in downtrends (violates golden rule, but that rule may be too restrictive for a dedicated perps strategy)
3. **XGBoost regime filter** — classify bull vs bear market first; only take longs during confirmed bull phases
4. **Focus on ETH instead** — ETH has demonstrably stronger mean-reversion on 15m due to its higher beta and more predictable oscillations

### 14.6 Data Infrastructure Notes & Source Comparison

**Data source research conducted 2026-03-28.** All sources tested for connectivity from the server.

| Source | 15m History | Max/Request | Auth | Geo-Block | Verdict |
|--------|------------|-------------|------|-----------|---------|
| **OKX** | **2021+** | **300** | ❌ None | ❌ None | **✅ Primary (added)** |
| BingX | May 2025+ | 1,440 | ❌ None | ❌ None | ✅ Fallback |
| Hyperliquid | ~52 days | 5,000 | ❌ None | ❌ None | Live signals only |
| Gate.io | ~104 days | 2,000 | ❌ None | ❌ None | Recent only |
| Kraken REST | ~7 days | 720 | ❌ None | ❌ None | Useless for backtest |
| Bybit | Unknown | 1,000 | ❌ None | ✅ Blocked | Unavailable |
| Binance | Unknown | 1,000 | ❌ None | ✅ Blocked | Unavailable |

**OKX pagination:** `after=<ts_ms>` walks backwards; 300 candles/request; 2 years = ~234 calls (~47s).

**Hyperliquid API** (tested 2026-03-28): Max 5,000 candles per request, ~52 days of 15m. Correct for **live trading signals only** — not for backtesting.

**Available cached data (data_cache/):**
- `BTCUSDT_15m_2024-01-01_2026-03-27.csv` — 78,337 candles (OKX, 2 years) ← definitive
- `BTCUSDT_1h_2024-01-01_2026-03-27.csv` — 19,585 candles (OKX, 2 years)
- `BTCUSDT/ETHUSDT` 15m/1h May 2025 → Mar 2026 (BingX)
- Older 90-day windows

### 14.7 Code Changes Made (March 28, 2026)

- `src/data/price_fetcher.py`: **Added OKX as primary source** (2021+ history, 300/req, backward pagination); fixed BingX pagination bug (`empty_skip_count` replaces premature `< 1440` break); source order: OKX → BingX → Bybit → Binance
- `src/hedge/standalone_perps_simulator.py`: Added `long_only`, `atr_floor`, `atr_ceiling` params; implemented BTC golden rule (was documented but not enforced)
- `src/engine/backtest_engine.py`: `FuryBacktestEngine` passes `atr_floor`, `atr_ceiling`, `long_only` from config to simulator
- `run_fury_backtest.py`: Added `--atr-floor-btc`, `--atr-floor-eth`, `--atr-ceil-btc`, `--bidirectional` CLI flags

---

*Research based on papers published 2024-2026 and X practitioner discussions March 2025-2026. Strategy parameters require validation against current market conditions before deployment. Not investment advice.*
