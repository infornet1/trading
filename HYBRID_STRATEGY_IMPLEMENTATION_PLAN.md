# 🔄 Hybrid Strategy Implementation Plan - WITH LABELING SYSTEM

## Executive Summary

**Approach:** Run BOTH strategies simultaneously with comprehensive labeling for tracking and comparison

**Strategy A:** Your Current Scalping Strategy (Proven 61.5% win rate)
**Strategy B:** Trading Latino Strategy (Swing trading, needs testing)

**Key Innovation:** Advanced labeling system to track, compare, and optimize both strategies independently

---

## 🏷️ Signal/Trade Labeling System

### Database Schema Enhancement

**New columns to add to `signals` table:**

```sql
ALTER TABLE signals ADD COLUMN strategy_name TEXT DEFAULT 'SCALPING';
ALTER TABLE signals ADD COLUMN strategy_version TEXT DEFAULT 'v1.0';
ALTER TABLE signals ADD COLUMN timeframe TEXT DEFAULT '5s';
ALTER TABLE signals ADD COLUMN signal_quality TEXT;
ALTER TABLE signals ADD COLUMN trade_group_id TEXT;
ALTER TABLE signals ADD COLUMN entry_reason TEXT;
ALTER TABLE signals ADD COLUMN exit_reason TEXT;
ALTER TABLE signals ADD COLUMN strategy_profit REAL;
ALTER TABLE signals ADD COLUMN tags TEXT;
ALTER TABLE signals ADD COLUMN market_condition TEXT;
ALTER TABLE signals ADD COLUMN session_id TEXT;
```

### Labeling Schema Details

#### 1. **strategy_name** (TEXT)
Identifies which strategy generated the signal

**Values:**
- `'SCALPING'` - Your current RSI/EMA/Support/Resistance strategy
- `'TRADING_LATINO'` - Squeeze Momentum + ADX strategy
- `'HYBRID'` - Signals that meet both strategies' criteria
- `'MANUAL'` - Manually placed trades

**Usage:**
```python
signal_tracker.log_signal(
    alert,
    data,
    indicators,
    strategy_name='SCALPING'
)
```

#### 2. **strategy_version** (TEXT)
Track strategy iterations and improvements

**Format:** `v{major}.{minor}.{patch}`

**Examples:**
- `'v1.0'` - Initial implementation
- `'v1.1'` - Added ATR dynamic targets
- `'v1.2'` - Added trend filter
- `'v2.0'` - Major strategy overhaul
- `'latino-v1.0'` - Trading Latino first version

**Usage:**
```python
# In config file
"strategy_version": "v1.2"

# Automatically added to every signal
```

#### 3. **timeframe** (TEXT)
Record the timeframe used for signal generation

**Values:**
- `'5s'` - 5 seconds (your current scalping)
- `'1m'`, `'5m'`, `'15m'` - Minute timeframes
- `'1h'`, `'4h'`, `'1d'` - Hour/day timeframes
- `'mixed'` - Multiple timeframe analysis

**Usage:**
```python
# Scalping
timeframe='5s'

# Trading Latino
timeframe='4h'
```

#### 4. **signal_quality** (TEXT)
Rate signal quality based on confluence of indicators

**Values:**
- `'HIGH'` - All conditions met perfectly
- `'MEDIUM'` - Most conditions met
- `'LOW'` - Minimal conditions met
- `'PERFECT'` - Rare, all indicators align

**Criteria for Scalping Strategy:**
```python
def calculate_signal_quality_scalping(indicators, alert):
    score = 0

    # Check RSI strength
    if alert['type'] == 'RSI_OVERSOLD' and indicators['rsi'] < 25:
        score += 2  # Very oversold
    elif alert['type'] == 'RSI_OVERSOLD' and indicators['rsi'] < 30:
        score += 1  # Oversold

    # Check trend alignment
    if indicators['trend'] in ['BULLISH', 'BEARISH']:  # Not NEUTRAL
        score += 2

    # Check EMA confluence
    if alert['type'] in ['EMA_BULLISH_CROSS', 'EMA_BEARISH_CROSS']:
        score += 2

    # Check support/resistance proximity
    if alert['type'] in ['NEAR_SUPPORT', 'NEAR_RESISTANCE']:
        score += 1

    # Check ATR (volatility appropriate)
    if 0.08 < indicators['atr_pct'] < 0.20:  # Sweet spot
        score += 1

    # No conflicts
    if not indicators['has_conflict']:
        score += 1

    # Classify
    if score >= 7:
        return 'PERFECT'
    elif score >= 5:
        return 'HIGH'
    elif score >= 3:
        return 'MEDIUM'
    else:
        return 'LOW'
```

**Criteria for Trading Latino:**
```python
def calculate_signal_quality_latino(squeeze, adx, momentum):
    score = 0

    # Squeeze just released (not ongoing)
    if squeeze['just_released']:
        score += 3

    # ADX very strong
    if adx['value'] > 40:
        score += 3
    elif adx['value'] > 30:
        score += 2
    elif adx['value'] > 23:
        score += 1

    # Momentum very strong
    if abs(momentum['value']) > 2.0:
        score += 2
    elif abs(momentum['value']) > 1.0:
        score += 1

    # ADX rising (strengthening trend)
    if adx['rising']:
        score += 2

    # Clear directional movement
    if adx['di_spread'] > 10:  # +DI and -DI spread
        score += 1

    if score >= 9:
        return 'PERFECT'
    elif score >= 6:
        return 'HIGH'
    elif score >= 4:
        return 'MEDIUM'
    else:
        return 'LOW'
```

#### 5. **trade_group_id** (TEXT)
Group related signals together

**Format:** `{strategy}_{date}_{sequence}`

**Examples:**
- `'SCALP_20251011_001'` - First scalping session of the day
- `'LATINO_20251011_001'` - First Trading Latino setup
- `'HEDGE_20251011_001'` - Hedged position group

**Usage:**
```python
# When opening multiple positions for same setup
trade_group_id = f"SCALP_{datetime.now().strftime('%Y%m%d')}_{seq:03d}"

# All signals in same setup get same group_id
```

**Benefits:**
- Track related positions together
- Calculate group P&L
- Analyze hedging effectiveness
- Identify which setups perform best

#### 6. **entry_reason** (TEXT)
Detailed explanation of why signal was taken

**Format:** Human-readable description with key metrics

**Examples for Scalping:**
```
"RSI_OVERSOLD(24.5) + BULLISH_TREND + NEAR_SUPPORT($111,850) + ATR(0.12%)"
"EMA_BULLISH_CROSS + STRONG_BULLISH_TREND + NO_CONFLICT"
"NEAR_SUPPORT($111,900) + RSI_OVERSOLD(28) + BEARISH_TO_NEUTRAL_REVERSAL"
```

**Examples for Trading Latino:**
```
"SQUEEZE_RELEASED(4bars) + ADX(32.5) + MOMENTUM_BULLISH(+1.8) + +DI>-DI"
"PERFECT_SETUP: SQUEEZE_JUST_FIRED + ADX_RISING(28->34) + STRONG_MOMENTUM(+2.3)"
"ADX_VERY_STRONG(45.2) + SQUEEZE_RELEASED + MOMENTUM_INCREASING"
```

**Template:**
```python
def generate_entry_reason_scalping(alert, indicators):
    parts = []

    # Main signal
    parts.append(f"{alert['type']}")

    # Add key metrics
    if 'rsi' in indicators:
        parts.append(f"RSI({indicators['rsi']:.1f})")

    if indicators.get('trend'):
        parts.append(f"{indicators['trend']}_TREND")

    if alert['type'] in ['NEAR_SUPPORT', 'NEAR_RESISTANCE']:
        level = indicators.get('support') or indicators.get('resistance')
        parts.append(f"LEVEL(${level:,.2f})")

    if indicators.get('atr_pct'):
        parts.append(f"ATR({indicators['atr_pct']:.2f}%)")

    return " + ".join(parts)
```

#### 7. **exit_reason** (TEXT)
Why position was closed

**Values:**
- `'TARGET_HIT'` - Take profit reached
- `'STOP_HIT'` - Stop loss triggered
- `'TIMEOUT'` - Signal expired
- `'MOMENTUM_REVERSAL'` - Momentum turned against us
- `'SQUEEZE_RETURNED'` - Market entering consolidation
- `'ADX_FALLING'` - Trend weakening
- `'TREND_REVERSAL'` - Major trend change detected
- `'MANUAL_CLOSE'` - User intervention
- `'RISK_MANAGEMENT'` - Max loss limit reached
- `'CONFLICTING_SIGNAL'` - Opposite signal appeared

**Examples:**
```
"TARGET_HIT: +0.52% profit @ $112,350"
"STOP_HIT: -0.15% loss @ $111,890"
"MOMENTUM_REVERSAL: Histogram turned red after +0.35% gain"
"TREND_REVERSAL: EMA_DEATH_CROSS detected, closed SHORT positions"
"ADX_FALLING: ADX dropped from 35 to 22, closed LONG @ +0.8%"
```

#### 8. **strategy_profit** (REAL)
Actual profit/loss attributed to this strategy

**Calculation:**
```python
# For scalping (small positions, fast trades)
strategy_profit = (exit_price - entry_price) / entry_price * position_size * leverage

# For Trading Latino (larger moves)
strategy_profit = (exit_price - entry_price) / entry_price * position_size * leverage

# Store in USDT
```

**Usage:**
```python
# When signal closes
final_pnl = calculate_pnl(entry_price, exit_price, position_size, direction)

update_signal(
    signal_id,
    strategy_profit=final_pnl,
    exit_reason="TARGET_HIT: +2.5% profit"
)
```

#### 9. **tags** (TEXT - JSON array)
Flexible tagging for advanced filtering

**Format:** JSON array of strings
```json
["squeeze_setup", "adr_high", "asia_session", "btc_dominance_rising"]
```

**Categories of Tags:**

**Market Condition:**
- `"volatile"`, `"calm"`, `"ranging"`, `"trending"`
- `"high_volume"`, `"low_volume"`
- `"breakout"`, `"breakdown"`, `"consolidation"`

**Session/Time:**
- `"asia_session"`, `"europe_session"`, `"us_session"`
- `"weekend"`, `"weekday"`
- `"high_liquidity"`, `"low_liquidity"`

**Technical:**
- `"golden_cross"`, `"death_cross"`
- `"support_bounce"`, `"resistance_reject"`
- `"fibonacci_level"`, `"round_number"`
- `"divergence"`

**Strategy Specific:**
- `"squeeze_setup"`, `"squeeze_fired"`
- `"adx_very_strong"`, `"perfect_confluence"`
- `"counter_trend"`, `"trend_following"`

**Risk:**
- `"low_risk"`, `"high_risk"`, `"hedged"`
- `"reduced_size"`, `"full_size"`

**Usage:**
```python
tags = [
    "squeeze_fired",
    "adx_very_strong",
    "us_session",
    "high_volume",
    "perfect_confluence"
]

log_signal(..., tags=json.dumps(tags))
```

#### 10. **market_condition** (TEXT)
Snapshot of overall market state

**Values:**
- `"STRONG_BULLISH"` - Clear uptrend, ADX > 30, price >> EMAs
- `"WEAK_BULLISH"` - Uptrend, ADX 20-30
- `"STRONG_BEARISH"` - Clear downtrend, ADX > 30, price << EMAs
- `"WEAK_BEARISH"` - Downtrend, ADX 20-30
- `"RANGING"` - Sideways, ADX < 20
- `"VOLATILE"` - High ATR, choppy
- `"CONSOLIDATING"` - Squeeze active, low volatility

**Auto-detected:**
```python
def detect_market_condition(indicators):
    adx = indicators['adx_value']
    trend = indicators['trend']
    atr_pct = indicators['atr_pct']

    if trend == 'BULLISH' and adx > 30:
        return 'STRONG_BULLISH'
    elif trend == 'BULLISH' and adx > 20:
        return 'WEAK_BULLISH'
    elif trend == 'BEARISH' and adx > 30:
        return 'STRONG_BEARISH'
    elif trend == 'BEARISH' and adx > 20:
        return 'WEAK_BEARISH'
    elif adx < 20 and atr_pct < 0.10:
        return 'CONSOLIDATING'
    elif adx < 20:
        return 'RANGING'
    elif atr_pct > 0.15:
        return 'VOLATILE'
    else:
        return 'NEUTRAL'
```

#### 11. **session_id** (TEXT)
Track trading sessions

**Format:** `{date}_{strategy}_{session_number}`

**Examples:**
- `"20251011_SCALPING_01"` - First scalping session of the day
- `"20251011_LATINO_01"` - First Latino session
- `"20251011_HYBRID_NIGHT"` - Night trading session

**Benefits:**
- Compare morning vs evening performance
- Track different trading times
- Analyze session-based strategies

---

## 📊 Strategy Comparison Queries

### Performance by Strategy

```sql
-- Win rate by strategy
SELECT
    strategy_name,
    strategy_version,
    COUNT(*) as total_trades,
    SUM(CASE WHEN final_result = 'WIN' THEN 1 ELSE 0 END) as wins,
    SUM(CASE WHEN final_result = 'LOSS' THEN 1 ELSE 0 END) as losses,
    ROUND(SUM(CASE WHEN final_result = 'WIN' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as win_rate,
    ROUND(AVG(strategy_profit), 2) as avg_profit,
    ROUND(SUM(strategy_profit), 2) as total_profit
FROM signals
WHERE final_result IN ('WIN', 'LOSS')
GROUP BY strategy_name, strategy_version
ORDER BY total_profit DESC;
```

### Performance by Signal Quality

```sql
-- Which quality signals perform best?
SELECT
    strategy_name,
    signal_quality,
    COUNT(*) as trades,
    ROUND(AVG(CASE WHEN final_result = 'WIN' THEN 100 ELSE 0 END), 1) as win_rate,
    ROUND(AVG(strategy_profit), 2) as avg_profit
FROM signals
WHERE final_result IN ('WIN', 'LOSS')
GROUP BY strategy_name, signal_quality
ORDER BY strategy_name, win_rate DESC;
```

### Performance by Market Condition

```sql
-- Which strategy works better in which conditions?
SELECT
    market_condition,
    strategy_name,
    COUNT(*) as trades,
    ROUND(AVG(CASE WHEN final_result = 'WIN' THEN 100 ELSE 0 END), 1) as win_rate,
    ROUND(AVG(strategy_profit), 2) as avg_profit
FROM signals
WHERE final_result IN ('WIN', 'LOSS')
GROUP BY market_condition, strategy_name
ORDER BY market_condition, avg_profit DESC;
```

### Performance by Timeframe

```sql
-- Compare timeframes
SELECT
    timeframe,
    strategy_name,
    COUNT(*) as trades,
    ROUND(AVG(CASE WHEN final_result = 'WIN' THEN 100 ELSE 0 END), 1) as win_rate,
    ROUND(SUM(strategy_profit), 2) as total_profit
FROM signals
WHERE final_result IN ('WIN', 'LOSS')
GROUP BY timeframe, strategy_name
ORDER BY total_profit DESC;
```

### Best Entry Reasons

```sql
-- Which entry reasons have highest win rate?
SELECT
    strategy_name,
    entry_reason,
    COUNT(*) as occurrences,
    ROUND(AVG(CASE WHEN final_result = 'WIN' THEN 100 ELSE 0 END), 1) as win_rate,
    ROUND(AVG(strategy_profit), 2) as avg_profit
FROM signals
WHERE final_result IN ('WIN', 'LOSS')
GROUP BY strategy_name, entry_reason
HAVING occurrences >= 5
ORDER BY win_rate DESC, avg_profit DESC
LIMIT 20;
```

### Tags Analysis

```sql
-- Find profitable tag combinations
SELECT
    tags,
    COUNT(*) as trades,
    ROUND(AVG(CASE WHEN final_result = 'WIN' THEN 100 ELSE 0 END), 1) as win_rate,
    ROUND(SUM(strategy_profit), 2) as total_profit
FROM signals
WHERE final_result IN ('WIN', 'LOSS')
AND tags IS NOT NULL
GROUP BY tags
HAVING trades >= 3
ORDER BY total_profit DESC
LIMIT 15;
```

---

## 🔧 Implementation Steps

### Step 1: Update Database Schema

```bash
cd /var/www/dev/trading
source venv/bin/activate
python3 << 'EOF'
import sqlite3

conn = sqlite3.connect('signals.db')
cursor = conn.cursor()

# Add new columns
cursor.execute("ALTER TABLE signals ADD COLUMN strategy_name TEXT DEFAULT 'SCALPING'")
cursor.execute("ALTER TABLE signals ADD COLUMN strategy_version TEXT DEFAULT 'v1.2'")
cursor.execute("ALTER TABLE signals ADD COLUMN timeframe TEXT DEFAULT '5s'")
cursor.execute("ALTER TABLE signals ADD COLUMN signal_quality TEXT")
cursor.execute("ALTER TABLE signals ADD COLUMN trade_group_id TEXT")
cursor.execute("ALTER TABLE signals ADD COLUMN entry_reason TEXT")
cursor.execute("ALTER TABLE signals ADD COLUMN exit_reason TEXT")
cursor.execute("ALTER TABLE signals ADD COLUMN strategy_profit REAL")
cursor.execute("ALTER TABLE signals ADD COLUMN tags TEXT")
cursor.execute("ALTER TABLE signals ADD COLUMN market_condition TEXT")
cursor.execute("ALTER TABLE signals ADD COLUMN session_id TEXT")

conn.commit()
conn.close()

print("✅ Database schema updated with labeling columns")
EOF
```

### Step 2: Update signal_tracker.py

```python
# Add to log_signal() method parameters:
def log_signal(
    self,
    alert: dict,
    price_data: dict,
    indicators: dict,
    has_conflict: bool = False,
    suggested_stop: float = None,
    suggested_target: float = None,
    # NEW PARAMETERS:
    strategy_name: str = 'SCALPING',
    strategy_version: str = 'v1.2',
    timeframe: str = '5s',
    signal_quality: str = None,
    trade_group_id: str = None,
    entry_reason: str = None,
    tags: list = None,
    market_condition: str = None,
    session_id: str = None
) -> int:

    # Auto-calculate signal quality if not provided
    if signal_quality is None:
        signal_quality = self.calculate_signal_quality(
            alert, indicators, strategy_name
        )

    # Auto-generate entry reason if not provided
    if entry_reason is None:
        entry_reason = self.generate_entry_reason(
            alert, indicators, strategy_name
        )

    # Auto-detect market condition if not provided
    if market_condition is None:
        market_condition = self.detect_market_condition(indicators)

    # Convert tags list to JSON string
    tags_json = json.dumps(tags) if tags else None

    # Insert into database with new fields
    cursor.execute('''
        INSERT INTO signals (
            timestamp, signal_type, direction, ...
            strategy_name, strategy_version, timeframe,
            signal_quality, trade_group_id, entry_reason,
            tags, market_condition, session_id
        ) VALUES (?, ?, ?, ..., ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (..., strategy_name, strategy_version, timeframe,
          signal_quality, trade_group_id, entry_reason,
          tags_json, market_condition, session_id))
```

### Step 3: Update btc_monitor.py for Scalping

```python
# In run() loop when logging signals:

signal_id = self.signal_tracker.log_signal(
    alert,
    data,
    indicators,
    has_conflict,
    suggested_stop=stop,
    suggested_target=target,
    # NEW: Add labeling
    strategy_name='SCALPING',
    strategy_version='v1.2',  # From config
    timeframe='5s',
    trade_group_id=f"SCALP_{datetime.now().strftime('%Y%m%d')}_{self.signal_count:03d}",
    tags=['scalping', 'high_frequency', session_tag, condition_tag]
)
```

### Step 4: Create Trading Latino Monitor with Labeling

```python
# In trading_latino_monitor.py:

signal_id = self.signal_tracker.log_signal(
    alert,
    data,
    indicators,
    has_conflict=False,
    suggested_stop=stop,
    suggested_target=target,
    # Trading Latino specific labeling
    strategy_name='TRADING_LATINO',
    strategy_version='v1.0',
    timeframe='4h',
    trade_group_id=f"LATINO_{datetime.now().strftime('%Y%m%d')}_{setup_count:03d}",
    tags=['swing_trade', 'squeeze_momentum', 'adx_strong', session_tag]
)
```

### Step 5: Create Strategy Comparison Dashboard

Create `strategy_dashboard.py`:

```python
#!/usr/bin/env python3
from flask import Flask, render_template, jsonify
import sqlite3
import json

app = Flask(__name__)

@app.route('/')
def dashboard():
    return render_template('strategy_comparison.html')

@app.route('/api/strategy/performance')
def strategy_performance():
    conn = sqlite3.connect('signals.db')
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            strategy_name,
            COUNT(*) as total,
            SUM(CASE WHEN final_result = 'WIN' THEN 1 ELSE 0 END) as wins,
            AVG(strategy_profit) as avg_profit,
            SUM(strategy_profit) as total_profit
        FROM signals
        WHERE final_result IN ('WIN', 'LOSS')
        GROUP BY strategy_name
    """)

    results = []
    for row in cursor.fetchall():
        results.append({
            'strategy': row[0],
            'total': row[1],
            'wins': row[2],
            'win_rate': (row[2] / row[1]) * 100,
            'avg_profit': row[3],
            'total_profit': row[4]
        })

    conn.close()
    return jsonify(results)

@app.route('/api/strategy/by_quality')
def by_quality():
    # Return performance by signal quality
    ...

@app.route('/api/strategy/by_condition')
def by_condition():
    # Return performance by market condition
    ...

if __name__ == '__main__':
    app.run(port=5801, debug=False)
```

---

## 📈 Hybrid Execution Plan

### Capital Allocation

**Total Capital: $500**

**Scalping Strategy: $200 (40%)**
- Position size: $10-20 per trade
- Max concurrent: 10 positions
- Timeframe: 5 seconds
- Labels: `strategy_name='SCALPING'`, `timeframe='5s'`

**Trading Latino: $300 (60%)**
- Position size: $150 per trade
- Max concurrent: 2 positions
- Timeframe: 4 hours
- Labels: `strategy_name='TRADING_LATINO'`, `timeframe='4h'`

### Daily Execution

**Scalping (Continuous):**
```bash
# Terminal 1
python3 btc_monitor.py config_scalping.json
```

**Trading Latino (Every 4 hours):**
```bash
# Terminal 2
python3 trading_latino_monitor.py config_trading_latino.json
```

**Dashboard (Comparison):**
```bash
# Terminal 3
python3 strategy_dashboard.py
# Visit: http://localhost:5801
```

### Monitoring & Tracking

**Real-time queries:**
```bash
# Which strategy is performing better TODAY?
python3 << 'EOF'
import sqlite3
from datetime import datetime

conn = sqlite3.connect('signals.db')
cursor = conn.cursor()

cursor.execute("""
    SELECT
        strategy_name,
        COUNT(*) as trades,
        ROUND(SUM(strategy_profit), 2) as profit
    FROM signals
    WHERE DATE(timestamp) = DATE('now')
    AND final_result IN ('WIN', 'LOSS')
    GROUP BY strategy_name
""")

print("📊 TODAY'S PERFORMANCE:")
for strategy, trades, profit in cursor.fetchall():
    print(f"  {strategy}: {trades} trades, ${profit} profit")

conn.close()
EOF
```

---

## 📊 Analysis & Optimization

### Weekly Review Queries

**1. Strategy Comparison:**
```sql
SELECT
    strategy_name,
    timeframe,
    COUNT(*) as trades,
    ROUND(AVG(CASE WHEN final_result = 'WIN' THEN 100 ELSE 0 END), 1) as win_rate,
    ROUND(SUM(strategy_profit), 2) as total_profit,
    ROUND(AVG(strategy_profit), 2) as avg_profit_per_trade
FROM signals
WHERE timestamp >= datetime('now', '-7 days')
AND final_result IN ('WIN', 'LOSS')
GROUP BY strategy_name, timeframe;
```

**2. Best Signal Qualities:**
```sql
SELECT
    strategy_name,
    signal_quality,
    COUNT(*) as trades,
    ROUND(AVG(CASE WHEN final_result = 'WIN' THEN 100 ELSE 0 END), 1) as win_rate
FROM signals
WHERE timestamp >= datetime('now', '-7 days')
GROUP BY strategy_name, signal_quality
ORDER BY win_rate DESC;
```

**3. Market Condition Performance:**
```sql
SELECT
    strategy_name,
    market_condition,
    COUNT(*) as trades,
    ROUND(SUM(strategy_profit), 2) as profit
FROM signals
WHERE timestamp >= datetime('now', '-7 days')
GROUP BY strategy_name, market_condition
ORDER BY profit DESC;
```

### Optimization Decisions

**Based on data, adjust allocation:**

If Scalping outperforms:
- Increase scalping allocation to 70%
- Reduce Latino to 30%
- Or disable Latino temporarily

If Latino outperforms:
- Increase Latino allocation to 70%
- Reduce scalping to 30%
- Consider larger position sizes for Latino

If both perform well:
- Keep 60/40 split
- Possibly increase total capital

---

## 🎯 Success Metrics

### Track These KPIs:

**Per Strategy:**
- Win rate
- Average profit per trade
- Total profit
- Maximum drawdown
- Sharpe ratio
- Number of trades per day

**Comparative:**
- Which strategy has higher win rate?
- Which strategy has larger average profit?
- Which strategy has more consistent returns?
- Which works better in trending markets?
- Which works better in ranging markets?

### Decision Framework:

**After 7 days, evaluate:**

**Scenario A: Scalping >> Latino**
→ Increase scalping allocation, reduce Latino

**Scenario B: Latino >> Scalping**
→ Increase Latino allocation, reduce scalping

**Scenario C: Both profitable**
→ Keep hybrid approach, optimize capital split

**Scenario D: One consistently loses**
→ Disable losing strategy, double down on winner

---

## 📝 Configuration Files

### config_scalping.json
```json
{
  "strategy_name": "SCALPING",
  "strategy_version": "v1.2",
  "timeframe": "5s",
  "exchange": "bingx",
  "symbol": "BTC-USDT",
  "interval": 5,
  "use_atr_targets": true,
  "use_trend_filter": true,
  "position_management": {
    "position_size_pct": 5.0,
    "max_concurrent": 10,
    "capital_allocation": 200
  },
  "labeling": {
    "auto_quality": true,
    "auto_entry_reason": true,
    "auto_market_condition": true,
    "default_tags": ["scalping", "high_frequency"]
  }
}
```

### config_trading_latino.json
```json
{
  "strategy_name": "TRADING_LATINO",
  "strategy_version": "v1.0",
  "timeframe": "4h",
  "exchange": "bingx",
  "symbol": "BTC-USDT",
  "squeeze_momentum": {
    "enabled": true,
    "length": 20
  },
  "adx": {
    "enabled": true,
    "threshold": 23
  },
  "position_management": {
    "position_size": 150,
    "max_concurrent": 2,
    "capital_allocation": 300
  },
  "labeling": {
    "auto_quality": true,
    "auto_entry_reason": true,
    "auto_market_condition": true,
    "default_tags": ["swing_trade", "squeeze_momentum"]
  }
}
```

---

## 🚀 Implementation Timeline

**Week 1: Setup & Labeling**
- Day 1-2: Update database schema ✓
- Day 3-4: Update signal_tracker.py with labeling
- Day 5-6: Update btc_monitor.py (scalping)
- Day 7: Test labeling system

**Week 2: Trading Latino Development**
- Day 8-10: Develop squeeze_momentum.py & adx_indicator.py
- Day 11-12: Create trading_latino_strategy.py
- Day 13-14: Integrate with signal_tracker (labeling)

**Week 3: Dashboard & Testing**
- Day 15-16: Create strategy_dashboard.py
- Day 17-18: Backtest both strategies with labeling
- Day 19-21: Paper trade both strategies simultaneously

**Week 4: Evaluation & Optimization**
- Day 22-28: Run both strategies, analyze labeled data
- Day 29: Review performance by strategy/quality/condition
- Day 30: Decide on capital allocation adjustments

---

## ✅ Next Steps

1. **Confirm approach** ✓ (You chose Option C: Hybrid)
2. **Update database schema** (Add labeling columns)
3. **Update signal_tracker.py** (Add labeling parameters)
4. **Update btc_monitor.py** (Add labels to scalping signals)
5. **Develop Trading Latino** (With built-in labeling)
6. **Create comparison dashboard** (Visualize strategy performance)
7. **Paper trade both** (Collect labeled data)
8. **Analyze & optimize** (Use labels to improve)

---

**Updated:** 2025-10-11
**Status:** 📋 Ready for Implementation
**Next Action:** Update database schema with labeling columns
