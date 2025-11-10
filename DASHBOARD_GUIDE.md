# Signal Tracking Dashboard Guide

## 🎯 What This Does

The signal tracking system automatically:
1. **Logs every trading signal** the monitor detects
2. **Tracks the outcome** - did it hit target or stop loss?
3. **Calculates win rate** - what percentage of signals are profitable?
4. **Shows performance stats** - which signal types work best?
5. **Provides a web dashboard** - visualize everything in real-time

## 📊 How It Works

### Automatic Signal Logging

When the monitor runs, it:
```
1. Detects signal (e.g., RSI oversold)
   ↓
2. Logs to database:
   - Entry price
   - Suggested stop loss
   - Suggested target
   - All indicators (RSI, EMA, support/resistance)
   ↓
3. Continuously tracks price:
   - Records highest price reached
   - Records lowest price reached
   ↓
4. Determines outcome:
   - WIN: Target hit before stop
   - LOSS: Stop hit before target
   - TIMEOUT: Neither hit after 1 hour
   - PENDING: Still watching
```

### What Gets Tracked

For each signal:
- **Timestamp**: When it was detected
- **Signal Type**: RSI_OVERSOLD, NEAR_SUPPORT, etc.
- **Direction**: LONG or SHORT
- **Entry Price**: BTC price when signal appeared
- **Suggested Stops/Targets**: What the system recommended
- **Indicators**: RSI, EMA, support/resistance values
- **Conflict Status**: Was it a conflicting signal?
- **Outcome**: WIN, LOSS, TIMEOUT, or PENDING
- **Actual Performance**: Max gain/loss reached

## 🚀 Quick Start

### Step 1: Start the Monitor (with tracking)

```bash
cd /var/www/dev/trading
source venv/bin/activate
python btc_monitor.py
```

The monitor will automatically:
- Detect signals
- Log them to `signals.db`
- Track outcomes in real-time
- Show win/loss results in console

### Step 2: View the Dashboard

**In a SECOND terminal:**
```bash
cd /var/www/dev/trading
source venv/bin/activate
python dashboard.py
```

Then open your browser to:
```
http://localhost:5800
```

Or from another computer on same network:
```
http://YOUR_SERVER_IP:5800
```

### Step 3: Let It Run!

Leave both running:
- **Terminal 1**: Monitor detecting and logging signals
- **Terminal 2**: Dashboard serving web interface
- **Browser**: Auto-refreshes every 30 seconds with latest stats

## 📈 Dashboard Features

### Main Stats (Top Cards)

**Total Signals**
- How many signals detected in time period
- Shows completed vs pending

**Win Rate**
- Percentage of profitable signals
- Color coded:
  - Green: >60% (excellent)
  - Yellow: 40-60% (good)
  - Red: <40% (needs improvement)

**Avg Win / Avg Loss**
- Average profit per winning trade
- Average loss per losing trade
- Helps calculate risk/reward

**Profit Factor**
- Avg Win ÷ Avg Loss
- >1.5 = excellent strategy
- >1.0 = profitable
- <1.0 = losing money

**Best/Worst Signal Types**
- Which signals have highest win rate
- Which to avoid

**Conflicting Signals**
- How many bad setups avoided
- Saved you from losing trades!

### Signals Table (Bottom)

Shows recent signals with:
- **Time**: When detected
- **Type**: RSI_OVERSOLD, NEAR_RESISTANCE, etc.
- **Direction**: LONG (buy) or SHORT (sell)
- **Price**: BTC price at signal
- **RSI**: RSI value
- **Target/Stop**: Where to take profit/cut loss
- **Outcome**: WIN, LOSS, PENDING, TIMEOUT
- **P&L %**: Actual profit/loss percentage

### Time Period Selector

Switch between:
- **Last Hour**: See recent performance
- **Last 6 Hours**: Current session view
- **Last 24 Hours**: Full day stats (default)
- **Last Week**: Longer-term performance

## 📊 Understanding the Stats

### What's a Good Win Rate?

```
70%+ = Exceptional (professional level)
60-70% = Excellent (very profitable)
50-60% = Good (profitable with discipline)
40-50% = Acceptable (break-even to small profit)
<40% = Needs improvement (review strategy)
```

**Important**: Even 55% win rate is profitable if:
- Avg Win > Avg Loss
- You follow risk management
- You avoid conflicting signals

### Profit Factor Explained

```
Profit Factor = (Total Win $) / (Total Loss $)

Example:
10 wins of $5 each = $50
5 losses of $3 each = $15
Profit Factor = $50 / $15 = 3.33 (excellent!)

2.0+ = Outstanding
1.5-2.0 = Excellent
1.0-1.5 = Good
<1.0 = Losing money
```

### Signal Type Performance

The dashboard shows which signals work best:

**Example Output:**
```
Best: RSI_OVERSOLD (72% win rate)
Worst: NEAR_RESISTANCE (38% win rate)
```

**What this means:**
- Focus on RSI_OVERSOLD signals
- Be cautious with NEAR_RESISTANCE
- Maybe increase confidence threshold for weak types

## 💡 How to Use This Data

### Week 1-2: Data Collection

**Goal**: Gather enough signals to see patterns

**Actions**:
- Let monitor run as much as possible
- Don't trade yet (paper trade only)
- Wait for at least 50 completed signals
- Watch the dashboard daily

**What to look for**:
- Is win rate >50%?
- Which signal types perform best?
- Are conflicting signals really bad? (should be)

### Week 3-4: Analysis

**Goal**: Understand what works

**Questions to answer**:
1. **Which time of day** has best signals?
2. **Which signal types** are most reliable?
3. **What RSI levels** work best? (e.g., <25 vs <30)
4. **Do EMA crossovers** add value?
5. **How often are stops hit** vs targets?

**Dashboard helps with**:
- Filter by time period to see patterns
- Compare signal type performance
- Calculate if strategy is profitable

### Month 2+: Optimization

**Goal**: Improve the strategy

**Based on data, you might**:
1. **Tighten RSI threshold**
   - If RSI <30 only shows 45% win rate
   - But RSI <25 shows 65% win rate
   - → Update config to only alert on <25

2. **Skip certain signal types**
   - If NEAR_RESISTANCE only wins 35%
   - → Disable in email_config.json

3. **Adjust targets**
   - If 80% hit 0.3% but only 40% hit 0.5%
   - → Lower target to 0.3% for higher win rate

4. **Wait for multiple confirmations**
   - Signals with 2+ confirmations: 70% win
   - Signals with 1 confirmation: 40% win
   - → Only trade with 2+ confirmations

## 📋 Sample Dashboard Interpretation

### Example Scenario

**Dashboard shows:**
```
Period: Last 24 Hours
Total Signals: 45
Win Rate: 58%
Wins: 20, Losses: 14, Pending: 11
Avg Win: +0.52%
Avg Loss: -0.31%
Profit Factor: 1.68
Best Type: RSI_OVERSOLD (70% win rate)
Conflicts: 8 (avoided)
```

**What this tells you:**

✅ **Good signs:**
- Win rate >50% (profitable)
- Profit factor >1.5 (good risk/reward)
- Avg win > avg loss (proper asymmetry)
- Conflicts being avoided (system working)
- RSI_OVERSOLD reliable (focus here)

⚠️ **Things to note:**
- 11 pending signals (need more time)
- 45 signals in 24h might be too many (quality vs quantity)

**Recommended actions:**
1. **Focus on RSI_OVERSOLD** - highest win rate
2. **Consider raising thresholds** to get fewer, better quality signals
3. **Let pending signals complete** before making strategy changes
4. **Continue collecting data** for more confidence

### Another Example (Warning Signs)

**Dashboard shows:**
```
Period: Last Week
Total Signals: 180
Win Rate: 38%
Wins: 45, Losses: 75, Pending: 60
Avg Win: +0.48%
Avg Loss: -0.35%
Profit Factor: 0.92
Best Type: EMA_BULLISH_CROSS (48%)
Conflicts: 25
```

**What this tells you:**

🚨 **Red flags:**
- Win rate <40% (losing strategy)
- Profit factor <1.0 (losing money overall)
- Even "best" type only 48%
- Too many signals (180 in week = overtrading)

**DO NOT TRADE** with these stats!

**What to do:**
1. **STOP** any live trading immediately
2. **Review SIGNAL_GUIDE.md** - might be misreading signals
3. **Tighten thresholds** - use config_conservative.json
4. **Wait for data to improve** before risking money
5. **Consider if market conditions** are unusual (crash, pump, etc.)

## 🛠️ Advanced Usage

### Export Data for Analysis

The database is SQLite format at `signals.db`

**To export to CSV:**
```bash
source venv/bin/activate
python3 << EOF
import sqlite3
import csv

conn = sqlite3.connect('signals.db')
cursor = conn.cursor()

cursor.execute('SELECT * FROM signals ORDER BY timestamp DESC LIMIT 1000')
rows = cursor.fetchall()
columns = [description[0] for description in cursor.description]

with open('signals_export.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(columns)
    writer.writerows(rows)

print("Exported to signals_export.csv")
conn.close()
EOF
```

### Query Specific Data

**Example: Get all winning RSI_OVERSOLD signals**
```bash
sqlite3 signals.db "SELECT timestamp, price, rsi, max_gain_pct FROM signals WHERE signal_type='RSI_OVERSOLD' AND final_result='WIN' ORDER BY max_gain_pct DESC LIMIT 10;"
```

**Example: Calculate performance by hour of day**
```bash
sqlite3 signals.db "SELECT strftime('%H', timestamp) as hour, COUNT(*) as total, SUM(CASE WHEN final_result='WIN' THEN 1 ELSE 0 END) as wins FROM signals GROUP BY hour ORDER BY hour;"
```

### Reset Database (Start Fresh)

If you want to clear all data and start over:
```bash
rm signals.db
python signal_tracker.py  # Recreates empty database
```

**Warning**: This deletes all historical data!

## 📱 Mobile Access

The dashboard is mobile-friendly!

**To access from phone:**
1. Make sure phone is on same WiFi as server
2. Find your server's IP address:
   ```bash
   hostname -I
   ```
3. On phone browser, go to:
   ```
   http://SERVER_IP:5000
   ```

Example: `http://192.168.1.100:5000`

## ⚙️ Configuration

### Disable Tracking

If you want to run monitor without tracking:
```python
# In btc_monitor.py, change:
monitor = BTCMonitor(enable_tracking=False)
```

### Custom Database Location

```python
# In btc_monitor.py:
tracker = SignalTracker(db_path='/path/to/custom_signals.db')
```

### Adjust Outcome Timeframe

Default: 1 hour to hit target/stop, then marks as TIMEOUT

**To change:**
```python
# In signal_tracker.py, find check_signal_outcome():
if datetime.now() - signal_time > timedelta(hours=2):  # Change to 2 hours
    final_result = 'TIMEOUT'
```

## 🎓 Learning from the Data

### Pattern Recognition

After collecting data for 1-2 weeks, look for patterns:

**Question 1: Time of Day**
- Do morning signals (7-11 AM) perform better?
- Are evening signals (7-11 PM) more volatile?
- Should I avoid trading during certain hours?

**Question 2: Market Conditions**
- Do signals work better in trending markets?
- Are range-bound days harder to trade?
- Should I sit out after big news events?

**Question 3: Indicator Reliability**
- Is RSI alone enough?
- Do I need EMA confirmation?
- Are support/resistance levels accurate?

**Question 4: Position Management**
- Should I use trailing stops after 0.3% profit?
- Is 0.5% target too ambitious in choppy markets?
- Should I scale out (take partial profits)?

### Continuous Improvement

**Monthly Review Process:**

1. **Export last month's data**
2. **Calculate**:
   - Overall win rate
   - Win rate by signal type
   - Win rate by time of day
   - Average time to target
   - Average time to stop
3. **Identify**:
   - Best performing setups
   - Worst performing setups
   - Patterns in losses
4. **Adjust**:
   - Config thresholds
   - Email alert preferences
   - Trading rules
5. **Test** changes for 1-2 weeks
6. **Measure** if improvement occurred

## ❓ Troubleshooting

### Dashboard won't load

**Error**: "Connection refused"
- Check `python dashboard.py` is running
- Try `http://127.0.0.1:5000` instead of localhost
- Check firewall isn't blocking port 5000

**Error**: "No module named 'flask'"
```bash
source venv/bin/activate
pip install flask
```

### No signals showing

**Problem**: Dashboard empty
- Check monitor is running (`python btc_monitor.py`)
- Wait for actual signals to be detected
- Database needs time to populate

### Win rate seems wrong

**Issue**: Win rate 100% or 0%
- Not enough completed signals yet
- Most are still "PENDING"
- Wait for 20+ completed signals

### Signals stuck in PENDING

**Cause**: Market not moving enough to hit target or stop

**Normal if**:
- Low volatility period
- Tight stop/target ranges
- Will resolve as TIMEOUT after 1 hour

## 🎯 Success Metrics

### Minimum Data Requirements

Before making decisions:
- At least **50 completed signals** (not pending)
- At least **1 week of tracking**
- Multiple market conditions sampled

### Good Performance Indicators

You're ready to consider live trading if:
- ✅ Win rate >55% over 100+ signals
- ✅ Profit factor >1.3
- ✅ Best signal type >65% win rate
- ✅ Conflicting signals avoided (tracked separately)
- ✅ Consistent across different time periods
- ✅ Understand WHY signals win/lose

### Warning Signs

**DO NOT trade if**:
- ❌ Win rate <45%
- ❌ Profit factor <1.0
- ❌ All signal types <50%
- ❌ Wild variance day to day
- ❌ You can't explain the edge

## 📚 Next Steps

1. **Start Collecting**: Run monitor 24/7 if possible
2. **Review Daily**: Check dashboard each day
3. **Analyze Weekly**: Deep dive into patterns
4. **Optimize Monthly**: Adjust based on data
5. **Paper Trade**: Practice with data-backed confidence
6. **Go Live**: Only after consistent profitability in tracking

Remember: The dashboard is your **truth detector**. It shows if the strategy actually works, not just if it sounds good. Trust the data, not your hopes.

---

**Dashboard URL**: http://localhost:5800
**Database**: signals.db
**Monitor**: python btc_monitor.py
**Dashboard**: python dashboard.py
