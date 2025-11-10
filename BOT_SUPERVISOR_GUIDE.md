# Bot Supervisor System - Complete Guide

**Created:** 2025-11-10
**Purpose:** Automated monitoring and recovery for trading bots
**Status:** ✅ Production Ready

---

## 📋 Overview

The **Bot Supervisor** is a macro-level monitoring system that runs via cron jobs to:

1. ✅ **Detect crashes** - Catch when bots stop unexpectedly
2. ✅ **Auto-restart** - Automatically restart crashed bots
3. ✅ **Check health** - Monitor beyond just "is process alive"
4. ✅ **Analyze market** - Determine if conditions warrant trading
5. ✅ **Clean state** - Remove old logs, optimize databases
6. ✅ **Generate reports** - Daily comprehensive status reports

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│              CRON SCHEDULER (Root Level)                 │
└─────────────────────────────────────────────────────────┘
                           │
           ┌───────────────┼───────────────┬──────────────┐
           │               │               │              │
           ▼               ▼               ▼              ▼
    ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
    │  Quick   │   │   Main   │   │  State   │   │  Daily   │
    │  Health  │   │Supervisor│   │ Manager  │   │  Report  │
    │  (5min)  │   │ (15min)  │   │  (6hr)   │   │  (daily) │
    └──────────┘   └──────────┘   └──────────┘   └──────────┘
         │               │               │              │
         └───────────────┴───────────────┴──────────────┘
                           │
                     ┌─────┴─────┐
                     │           │
                     ▼           ▼
              ┌──────────┐ ┌──────────┐
              │Scalping  │ │  ADX v2  │
              │   v2     │ │   Bot    │
              └──────────┘ └──────────┘
```

---

## 📁 Files Structure

```
/var/www/dev/trading/supervisor/
├── bot_supervisor.py              # Main orchestrator
├── market_condition_checker.py    # Market analysis
├── bot_health_monitor.py          # Health checking
├── state_manager.py               # State cleanup
├── quick_health_check.py          # Fast crash detection
├── install_cron.sh                # Cron installation script
├── logs/
│   ├── supervisor.log             # Main supervisor log
│   ├── cron.log                   # Cron execution log
│   ├── quick_check.log            # Quick checks log
│   ├── cleanup.log                # Cleanup operations
│   └── reports.log                # Daily reports
└── reports/
    └── report_YYYYMMDD.json       # Daily JSON reports
```

---

## 🚀 Installation

### Step 1: Verify Files

All supervisor scripts should already be created in `/var/www/dev/trading/supervisor/`

```bash
ls -l /var/www/dev/trading/supervisor/
```

### Step 2: Install Cron Jobs

```bash
cd /var/www/dev/trading/supervisor
./install_cron.sh
```

This will prompt you to install the following cron jobs:

- **Every 5 minutes:** Quick health check (crash detection)
- **Every 15 minutes:** Full supervision cycle
- **Every 6 hours:** State cleanup for both bots
- **Every day at 8 AM:** Daily report generation
- **Every hour:** Disk space check

### Step 3: Verify Installation

```bash
# View installed cron jobs
crontab -l

# Should show 5 trading bot supervisor entries
```

---

## 🔧 Cron Schedule

| Frequency | Task | Script | Purpose |
|-----------|------|--------|---------|
| **Every 5 min** | Quick Health Check | `quick_health_check.py` | Detect and restart crashed bots immediately |
| **Every 15 min** | Main Supervisor | `bot_supervisor.py` | Full health check, market analysis, smart decisions |
| **Every 6 hours** | State Cleanup | `state_manager.py` | Archive old logs, optimize DB, clear temp files |
| **Daily 8 AM** | Daily Report | `bot_supervisor.py --report` | Comprehensive status report |
| **Every hour** | Disk Space | Built-in check | Alert if disk usage > 80% |

---

## 🎯 What Each Component Does

### 1. **Quick Health Check** (Every 5 minutes)

**Purpose:** Fast crash detection and immediate restart

**What it checks:**
- Is the systemd service active?

**Actions:**
- If service is DOWN → Restart immediately
- Log all actions

**Use case:** Bot crashes due to error, memory issue, etc.

---

### 2. **Main Supervisor** (Every 15 minutes)

**Purpose:** Intelligent monitoring and decision-making

**What it checks:**
1. **Market Conditions:**
   - Current ADX value
   - Market regime (trending/ranging/choppy)
   - Volatility levels
   - BTC price

2. **Bot Health:**
   - Service running?
   - Database being updated?
   - Recent errors in logs?
   - Process consuming CPU?

3. **Smart Decisions:**
   - Should bot be running given market conditions?
   - Is bot healthy or just alive?
   - Should we restart or just monitor?

**Actions:**
- Restart if bot crashed AND market conditions are good
- Monitor if bot unhealthy but not critical
- Report if bot idle but market unsuitable (expected behavior)

---

### 3. **State Manager** (Every 6 hours)

**Purpose:** Keep system clean and optimized

**What it does:**
- Archive logs older than 7 days
- Optimize database (VACUUM)
- Remove temporary files (*.tmp, *.lock)
- Clear old performance snapshots

**Why:** Prevents disk space issues, maintains performance

---

### 4. **Daily Report** (8 AM daily)

**Purpose:** Comprehensive status overview

**Generates:**
- Market conditions summary
- Both bots' health status
- Recent issues/restarts
- Performance metrics
- JSON report saved for analysis

**File:** `/var/www/dev/trading/supervisor/reports/report_YYYYMMDD.json`

---

## 📊 Monitoring & Logs

### View Real-Time Supervisor Activity

```bash
# Main supervisor log
tail -f /var/www/dev/trading/supervisor/logs/supervisor.log

# Quick health checks
tail -f /var/www/dev/trading/supervisor/logs/quick_check.log

# Cron execution
tail -f /var/www/dev/trading/supervisor/logs/cron.log

# Cleanup operations
tail -f /var/www/dev/trading/supervisor/logs/cleanup.log
```

### View Recent Supervisor Runs

```bash
# Last 50 lines of main supervisor
tail -50 /var/www/dev/trading/supervisor/logs/supervisor.log

# Check if any restarts happened today
grep "Restarting" /var/www/dev/trading/supervisor/logs/*.log
```

### View Daily Reports

```bash
# Today's report
cat /var/www/dev/trading/supervisor/reports/report_$(date +%Y%m%d).json | jq

# List all reports
ls -lh /var/www/dev/trading/supervisor/reports/
```

---

## 🎮 Manual Commands

### Check Market Conditions

```bash
python3 /var/www/dev/trading/supervisor/bot_supervisor.py --check-market
```

**Output:**
```json
{
  "tradeable": false,
  "regime": "ranging",
  "adx": 18.22,
  "volatility": 0.15,
  "btc_price": 105948.70
}
```

### Check Bot Health

```bash
# Scalping v2
python3 /var/www/dev/trading/supervisor/bot_health_monitor.py scalping_v2

# ADX v2
python3 /var/www/dev/trading/supervisor/bot_health_monitor.py adx_v2
```

### Manual Restart

```bash
# Via supervisor (with cleanup)
python3 /var/www/dev/trading/supervisor/bot_supervisor.py --restart scalping_v2
python3 /var/www/dev/trading/supervisor/bot_supervisor.py --restart adx_v2

# Direct systemctl (no cleanup)
systemctl restart scalping-trading-bot
systemctl restart adx-trading-bot.service
```

### Generate Report Now

```bash
python3 /var/www/dev/trading/supervisor/bot_supervisor.py --report
```

### Manual State Cleanup

```bash
python3 /var/www/dev/trading/supervisor/state_manager.py scalping_v2 --cleanup
python3 /var/www/dev/trading/supervisor/state_manager.py adx_v2 --cleanup
```

---

## 🔍 Troubleshooting

### Cron Not Running?

```bash
# Check if cron service is active
systemctl status cron

# View cron logs
journalctl -u cron -f

# Test cron job manually
/usr/bin/python3 /var/www/dev/trading/supervisor/bot_supervisor.py
```

### Supervisor Not Finding Bots?

Check paths in `bot_supervisor.py`:
```python
self.bots = {
    'scalping_v2': {
        'service': 'scalping-trading-bot',
        'path': '/var/www/dev/trading/scalping_v2',
        ...
    }
}
```

### Logs Not Created?

```bash
# Create log directories
mkdir -p /var/www/dev/trading/supervisor/logs
mkdir -p /var/www/dev/trading/supervisor/reports

# Set permissions
chmod 755 /var/www/dev/trading/supervisor/logs
```

### Market Checker Failing?

```bash
# Test market checker directly
python3 /var/www/dev/trading/supervisor/market_condition_checker.py

# Check for API issues
curl "https://open-api.bingx.com/openApi/swap/v2/quote/klines?symbol=BTC-USDT&interval=5m&limit=10"
```

---

## 🎯 Decision Logic

### When Does Supervisor Restart a Bot?

**Restart Conditions (ALL must be true):**
1. ✅ Service is DOWN/crashed
2. ✅ Market conditions are favorable
3. ✅ Bot is enabled in config

**OR**

1. ✅ Service is UP
2. ✅ Bot is unhealthy with "stuck" or "frozen" issues
3. ✅ Bot hasn't updated database in >10 minutes

### What "Unhealthy" Means

A bot is considered unhealthy if:
- ❌ No database updates in 10+ minutes
- ❌ Multiple errors in recent logs (>5)
- ❌ Process PID not found
- ❌ Service shows as "degraded"

### Market Conditions Logic

**Tradeable Markets:**
- ADX > 25 (trending) - ADX bot can trade
- Volatility 0.5-2.0% (choppy) - Scalping bot can trade

**Non-Tradeable:**
- ADX < 25 AND volatility < 0.5% (ranging/dead market)

---

## 📈 Best Practices

### 1. Monitor Supervisor Regularly

```bash
# Add to your daily routine
tail -50 /var/www/dev/trading/supervisor/logs/supervisor.log
```

### 2. Check Daily Reports

```bash
# Every morning, review
cat /var/www/dev/trading/supervisor/reports/report_$(date +%Y%m%d).json | jq
```

### 3. Set Up Email Alerts (Optional)

Add to supervisor scripts to email on critical issues:
```python
# In bot_supervisor.py
if critical_issue:
    send_email("Bot crashed and couldn't restart")
```

### 4. Disk Space Management

Supervisor checks disk space hourly. If >80%:
- Clean up old logs manually
- Archive old databases
- Check for large files: `du -sh /var/www/dev/trading/* | sort -h`

---

## ⚙️ Configuration

### Enable/Disable Bots

Edit `/var/www/dev/trading/supervisor/bot_supervisor.py`:

```python
self.bots = {
    'scalping_v2': {
        ...
        'enabled': True,  # Set to False to disable
    },
    'adx_v2': {
        ...
        'enabled': True,  # Set to False to disable
    }
}
```

### Change Check Frequency

Edit crontab:
```bash
crontab -e

# Change from every 15 minutes
*/15 * * * * /usr/bin/python3 /var/www/dev/trading/supervisor/bot_supervisor.py

# To every 10 minutes
*/10 * * * * /usr/bin/python3 /var/www/dev/trading/supervisor/bot_supervisor.py
```

---

## 🚨 Emergency Procedures

### Stop All Supervision

```bash
# Comment out all trading bot cron jobs
crontab -e

# Or remove them
crontab -l | grep -v "bot_supervisor" | crontab -
```

### Manual Recovery

```bash
# Stop everything
systemctl stop scalping-trading-bot adx-trading-bot.service

# Clean states
python3 /var/www/dev/trading/supervisor/state_manager.py scalping_v2 --cleanup
python3 /var/www/dev/trading/supervisor/state_manager.py adx_v2 --cleanup

# Start fresh
systemctl start scalping-trading-bot adx-trading-bot.service
```

---

## 📊 Success Metrics

**Supervisor is working well if:**

✅ Bots restart automatically after crashes
✅ No restarts during normal operation (low false positives)
✅ Logs show regular health checks every 5/15 minutes
✅ Daily reports generated successfully
✅ Disk space stays under 80%
✅ State cleanup runs without errors

---

## 🆘 Support

### Check System Status

```bash
# Quick status of everything
/var/www/dev/trading/supervisor/bot_supervisor.py --check-market
systemctl status scalping-trading-bot adx-trading-bot.service
df -h /
```

### Common Issues

| Issue | Solution |
|-------|----------|
| Bot keeps restarting | Check bot logs for errors, not supervisor issue |
| Supervisor not running | Check cron: `systemctl status cron` |
| Logs filling disk | Increase cleanup frequency or reduce retention |
| False restarts | Adjust health check thresholds in code |

---

## 📝 Change Log

**2025-11-10** - Initial release
- Created complete supervisor system
- 5 cron jobs configured
- Market condition analyzer
- Bot health monitor
- State manager
- Daily reporting

---

## 🔗 Related Documentation

- **Main README:** `/var/www/dev/trading/README.md`
- **ADX Strategy:** `/var/www/dev/trading/QUICK_START_ADX_V2.md`
- **Scalping v2:** `/var/www/dev/trading/scalping_v2/DEPLOYMENT_SUMMARY.md`

---

**Supervisor Status:** ✅ Active and Monitoring
**Last Updated:** 2025-11-10
**Maintained By:** Trading System Team
