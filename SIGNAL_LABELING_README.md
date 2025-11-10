# Signal Labeling System

## Overview
The signal labeling system automatically updates signal outcomes (WIN/LOSS/TIMEOUT) to track trading performance.

## Problem Fixed
Previously, 773+ signals were stuck with `outcome = "PENDING"` and never getting updated. These signals were older than 1 hour but weren't being labeled.

## Solution Implemented

### 1. Manual Labeling Script (`label_timeout_signals.py`)
Marks all PENDING signals older than 1 hour as TIMEOUT.

**Usage:**
```bash
# Dry run (preview changes)
python3 label_timeout_signals.py --dry-run

# Run with default 1 hour timeout
python3 label_timeout_signals.py

# Run with custom timeout (e.g., 2 hours)
python3 label_timeout_signals.py 2
```

### 2. Automatic Labeling Monitor (`auto_label_monitor.py`)
Background service that automatically labels timeout signals every minute.

**Usage:**
```bash
# Start with 60 second check interval
python3 auto_label_monitor.py 60 &

# Start with 5 minute check interval (default 300 seconds)
python3 auto_label_monitor.py &

# Check if running
ps aux | grep auto_label_monitor

# View logs
tail -f auto_labeler.log

# Stop the service
pkill -f auto_label_monitor.py
```

**Current Status:**
- ✅ Auto-labeler is running (PID: 1581333)
- Check interval: 60 seconds
- Labeled 43 signals on startup

### 3. Historical Price Labeling (`label_pending_signals.py`)
Advanced script that fetches historical price data from Binance to accurately label signals.

**Note:** Currently not functional due to Binance API geo-restrictions (HTTP 451). Use the timeout-based labeling instead.

## Current Statistics

### Overall Distribution (965 total signals):
- **TIMEOUT**: 787 signals (81.6%)
- **WIN**: 81 signals (8.4%)
- **LOSS**: 50 signals (5.2%)
- **PENDING**: 46 signals (4.8%) - Recent signals < 1 hour old

### Last 24 Hours (874 signals):
- **Win Rate**: 49.5% (49 wins / 50 losses)
- **Timeouts**: 728 signals
- **Pending**: 46 signals (recent, < 1 hour old)

### Best Performing Signal Types:
1. **EMA_BEARISH_CROSS**: 90.9% win rate (20W/2L)
2. **NEAR_RESISTANCE**: 89.5% win rate (17W/2L)
3. **RSI_OVERBOUGHT**: 84.6% win rate (11W/2L)

### Worst Performing Signal Types:
1. **EMA_BULLISH_CROSS**: 0.0% win rate (0W/19L)
2. **NEAR_SUPPORT**: 0.0% win rate (0W/15L)
3. **RSI_OVERSOLD**: 9.1% win rate (1W/10L)

## Monitoring

### Check Current Status:
```bash
# Overall statistics
python3 -c "from signal_tracker import SignalTracker; tracker = SignalTracker(); print(tracker.get_statistics(24))"

# Strategy dashboard
python3 strategy_dashboard.py 24

# Count by outcome
python3 -c "import sqlite3; conn = sqlite3.connect('signals.db'); cursor = conn.cursor(); cursor.execute('SELECT outcome, COUNT(*) FROM signals GROUP BY outcome'); print(cursor.fetchall())"
```

### Manual Labeling:
If signals get stuck again, run:
```bash
python3 label_timeout_signals.py
```

## How It Works

### Signal Lifecycle:
1. **Signal Generated** → `outcome = "PENDING"`
2. **Monitor Tracks** → Updates `highest_price` and `lowest_price`
3. **Target/Stop Hit** → `outcome = "WIN"` or `"LOSS"`
4. **1 Hour Timeout** → `outcome = "TIMEOUT"` (via auto_label_monitor.py)

### Why Timeouts?
Signals that don't hit target or stop within 1 hour are marked as TIMEOUT because:
- The market conditions have changed
- The signal is no longer valid
- It prevents signals from staying PENDING forever

## Files Created/Modified

### New Files:
- `label_timeout_signals.py` - Manual timeout labeling
- `auto_label_monitor.py` - Automatic background labeling
- `label_pending_signals.py` - Historical price-based labeling (not working due to API restrictions)
- `auto_labeler.log` - Log file for auto-labeler
- `SIGNAL_LABELING_README.md` - This file

### Existing System:
- `btc_monitor.py` - Main monitor (calls `check_signal_outcome()` for active signals)
- `signal_tracker.py` - Database and signal tracking logic
- `signals.db` - SQLite database with all signals

## Recommendations

1. **Keep auto_label_monitor.py running** - It will automatically label timeout signals
2. **Monitor the win rates** - Adjust strategy based on signal type performance
3. **Consider disabling weak signals** - EMA_BULLISH_CROSS and NEAR_SUPPORT have 0% win rate
4. **Focus on strong signals** - EMA_BEARISH_CROSS and NEAR_RESISTANCE have 90%+ win rate

## Troubleshooting

### Auto-labeler not running:
```bash
# Check if running
ps aux | grep auto_label_monitor

# Restart if needed
python3 auto_label_monitor.py 60 > auto_labeler_output.log 2>&1 &
```

### Too many PENDING signals:
```bash
# Check count
python3 -c "import sqlite3; conn = sqlite3.connect('signals.db'); cursor = conn.cursor(); cursor.execute('SELECT COUNT(*) FROM signals WHERE outcome=\"PENDING\"'); print(f'PENDING: {cursor.fetchone()[0]}')"

# Run manual labeling
python3 label_timeout_signals.py
```

### Check for old PENDING signals:
```bash
python3 -c "import sqlite3; from datetime import datetime, timedelta; conn = sqlite3.connect('signals.db'); cursor = conn.cursor(); threshold = (datetime.now() - timedelta(hours=1)).isoformat(); cursor.execute('SELECT COUNT(*) FROM signals WHERE outcome=\"PENDING\" AND timestamp < ?', (threshold,)); print(f'Old PENDING (>1h): {cursor.fetchone()[0]}')"
```
