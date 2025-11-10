# 📊 Pending Signals Monitor - Quick Guide

## What It Does

Real-time monitoring tool that tracks all PENDING signals and shows:
- How close they are to hitting TARGET (WIN)
- How close they are to hitting STOP LOSS (LOSS)
- Current profit/loss percentage
- Signal age
- Status indicators

## Quick Start

### Basic Usage (10 second refresh)

```bash
cd /var/www/dev/trading
source venv/bin/activate
python3 monitor_pending_signals.py
```

### Fast Refresh (5 seconds)

```bash
python3 monitor_pending_signals.py 5
```

### Slow Refresh (30 seconds)

```bash
python3 monitor_pending_signals.py 30
```

## What You'll See

```
================================================================================
📊 PENDING SIGNALS MONITOR
================================================================================
🕐 Time: 2025-10-11 11:23:44
💰 Current BTC Price: $112,310.50
📝 Monitoring 50 pending signal(s)
================================================================================

📈 SUMMARY:
   🎯 Near Target (80%+):  3 signals
   ⚠️  Near Stop (80%+):    7 signals
   📈 In Profit:           16 signals
   📉 In Loss:             13 signals
   ⏸️  Neutral:             13 signals

🔥 SIGNALS NEAR TARGET (80%+)
------------------------------------------------------------
  ID  Type          Dir   Entry     Target    Progress  P&L    Age
1493  RSI_OVERSOLD  LONG  $112,086  $112,366  80.2%    +0.20%  20m
1490  EMA_CROSS     LONG  $112,042  $112,322  95.8%    +0.24%  24m
1488  NEAR_SUPPORT  LONG  $112,037  $112,317  97.8%    +0.24%  26m

⚠️  SIGNALS NEAR STOP LOSS (80%+)
------------------------------------------------------------
  ID  Type          Dir   Entry     Stop      Progress  P&L    Age
1509  NEAR_SUPPORT  LONG  $112,450  $112,281  82.7%    -0.12%  1m
1484  RSI_OVERBOUGHT SHORT $112,160  $112,328  89.5%    -0.13%  33m
```

## Status Indicators

| Indicator | Meaning | Action |
|-----------|---------|--------|
| 🎯 TARGET HIT! | Signal hit target | Should be marked as WIN soon |
| ❌ STOP HIT! | Signal hit stop loss | Should be marked as LOSS soon |
| 🔥 Very Close to Target | 80%+ to target | Likely to WIN |
| ⚠️ Close to Stop | 80%+ to stop | Likely to LOSS |
| 📈 In Profit | Currently profitable | Waiting for target |
| 📉 In Loss | Currently losing | Waiting for stop or recovery |
| ⏸️ Flat | Near entry price | Neutral |

## Understanding the Data

### Progress Percentages

**To Target:**
- 100% = Hit target (WIN)
- 80-99% = Very close
- 50-79% = Halfway there
- <50% = Still far

**To Stop:**
- 100% = Hit stop (LOSS)
- 80-99% = Very close to stop loss
- <50% = Safe distance

### P&L (Profit/Loss)

- `+0.25%` = In profit, 0.25% above entry
- `-0.15%` = In loss, 0.15% below entry
- `±0.00%` = Flat, at entry price

### Age

- `5m` = Signal is 5 minutes old
- `60m` = Signal is 1 hour old
- Signals >60 min = May timeout soon

## Use Cases

### 1. Monitor Active Trades

```bash
# Watch every 5 seconds for active trading
python3 monitor_pending_signals.py 5
```

**Look for:**
- Signals near target (about to WIN)
- Signals near stop (about to LOSS)

### 2. End of Day Review

```bash
# Quick snapshot
python3 monitor_pending_signals.py
# Press Ctrl+C after viewing
```

**Check:**
- How many signals are profitable
- Average P&L
- Signals stuck (old age, no movement)

### 3. Performance Analysis

Run monitor and observe:
- Which signal types get closest to target
- Which signal types hit stop more often
- Average time to WIN/LOSS

## Tips

### Finding Winners

Look for patterns in signals that reach 80%+ to target:
- What type? (RSI_OVERSOLD, NEAR_SUPPORT, etc.)
- What direction? (LONG vs SHORT)
- What market conditions? (check trend on main monitor)

### Avoiding Losers

Watch signals near stop loss:
- Do certain types hit stop more?
- Are they fighting the trend?
- Consider tighter stops for those types

### Stuck Signals

Signals with:
- Age >60 minutes
- Progress <50% to both target and stop
- Near 0% P&L

→ These will likely TIMEOUT (neither WIN nor LOSS)

## Stopping the Monitor

**Press `Ctrl+C`**

You'll see final statistics:
```
✅ Monitor stopped by user
Final statistics:
   Average P&L: +0.08%
   Signals monitored: 50
```

## Advanced: Integration with Main Monitor

**Terminal Setup:**

**Terminal 1:** Run main monitor
```bash
python3 btc_monitor.py config_atr_test.json
```

**Terminal 2:** Run pending signals monitor
```bash
python3 monitor_pending_signals.py 10
```

**Terminal 3:** Run dashboard
```bash
python3 dashboard.py
```

Now you have:
- Terminal 1: Signal generation + logging
- Terminal 2: Real-time pending signal tracking
- Terminal 3: Web dashboard (http://localhost:5800)

## Troubleshooting

### No Pending Signals

```
✅ No pending signals - all have been resolved!
```

**Means:**
- All signals have hit target, stop, or timed out
- Wait for new signals to be generated
- Check main monitor is running

### Can't Fetch Price

```
⚠️  Could not fetch BTC price, retrying...
```

**Solution:**
- Check internet connection
- Wait a moment, it will retry automatically

### Database Locked

```
database is locked
```

**Solution:**
- Main monitor is writing to database
- Wait a moment and try again
- Don't run multiple instances

## Files

- `monitor_pending_signals.py` - Main monitoring script
- `signals.db` - SQLite database with all signals
- `PENDING_SIGNALS_MONITOR_GUIDE.md` - This guide

## Example Session

```bash
cd /var/www/dev/trading
source venv/bin/activate

# Start monitoring with 10 second refresh
python3 monitor_pending_signals.py 10

# Watch for a few minutes
# Press Ctrl+C when done

# Output:
✅ Monitor stopped by user
Final statistics:
   Average P&L: +0.12%
   Signals monitored: 45
```

---

**Created:** 2025-10-11
**Purpose:** Track pending signals in real-time
**Status:** ✅ Ready to use
