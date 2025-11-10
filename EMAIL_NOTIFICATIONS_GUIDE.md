# Bot Supervisor - Email Notifications Guide

**Created:** 2025-11-10
**Status:** ✅ Fully Functional
**Recipient:** perdomo.gustavo@gmail.com

---

## 📧 Overview

The Bot Supervisor now sends **automated email notifications** to keep you informed about:

1. **Daily Reports** - Every day at 8 AM
2. **Crash Alerts** - Immediate notification when bots crash/restart
3. **Test Emails** - Verify configuration is working

---

## 📨 Email Types

### 1. Daily Report (8 AM)

**Subject:** `✅ Daily Bot Supervisor Report - YYYY-MM-DD`

**Contains:**
- 📊 Market conditions (BTC price, ADX, regime, tradeable status)
- 🤖 Bot health status (all bots)
- 📋 Issues summary
- 🎯 Supervisor activity overview
- 🔗 Dashboard links

**Frequency:** Once per day at 8:00 AM

**Example:**
```
✅ Daily Bot Supervisor Report - 2025-11-10

MARKET CONDITIONS
-----------------
BTC Price: $105,337.20
ADX: 38.26 ✅ (Strong trend)
Regime: Trending
Tradeable: ✅ Yes

BOT HEALTH
----------
Scalping v2: ✅ Running - Healthy
ADX v2: ✅ Running - Healthy

SUMMARY
-------
All bots running: ✅
All bots healthy: ✅
Total issues: 0
```

---

### 2. Crash Alert (Immediate)

**Subject:** `🚨 Bot Supervisor Alert: [Bot Name] RESTARTED` or `RESTART FAILED`

**Contains:**
- ⚠️ Which bot crashed
- ✅/❌ Restart status (successful or failed)
- 🕐 Timestamp
- 📝 Error details
- 🔧 Next steps (automatic or manual)

**Frequency:** Immediate (within 5-15 minutes of crash)

**Example (Successful Restart):**
```
🚨 Bot Supervisor Alert: Scalping v2 RESTARTED

Bot: Scalping v2
Status: RESTARTED ✅
Time: 2025-11-10 14:30:00

What Happened?
The supervisor detected that Scalping v2 stopped running.
✅ The bot was automatically restarted successfully.

Next Steps:
✅ No action required. Bot is back online and monitoring market conditions.
```

**Example (Failed Restart):**
```
🚨 Bot Supervisor Alert: ADX v2 RESTART FAILED

Bot: ADX v2
Status: RESTART FAILED ❌
Time: 2025-11-10 14:30:00

What Happened?
The supervisor detected that ADX v2 stopped running.
❌ Attempted to restart but failed. Manual intervention required!

Next Steps:
1. SSH into the server
2. Check bot logs
3. Check system resources
4. Manual restart
```

---

### 3. Test Email

**Subject:** `✅ Bot Supervisor Email Test`

**Contains:**
- Confirmation message
- Timestamp

**Use:** Verify email configuration is working

---

## ⚙️ Configuration

### Current Settings

**Email Config File:** `/var/www/dev/trading/supervisor/email_config.json`

```json
{
  "smtp_server": "smtp.gmail.com",
  "smtp_port": 587,
  "sender_email": "finanzas@ueipab.edu.ve",
  "smtp_password": "****",
  "recipient_email": "perdomo.gustavo@gmail.com"
}
```

### Change Recipient Email

```bash
nano /var/www/dev/trading/supervisor/email_config.json

# Change this line:
"recipient_email": "your.new.email@example.com"
```

### Disable Email Notifications

**Option 1 - Keep system but skip emails:**

Edit `/var/www/dev/trading/supervisor/bot_supervisor.py`:
```python
# In __init__ method, add:
self.email_notifier = None  # Disable emails
```

**Option 2 - Comment out in cron:**
```bash
crontab -e

# Comment out the daily report line:
# 0 8 * * * /usr/bin/python3 /var/www/dev/trading/supervisor/bot_supervisor.py --report
```

---

## 🧪 Testing

### Test Email Configuration

```bash
cd /var/www/dev/trading/supervisor
python3 supervisor_email_notifier.py --test
```

**Expected output:**
```
Sending test email...
✅ Email sent: ✅ Bot Supervisor Email Test
```

**Check your inbox** - you should receive a test email within 1-2 minutes.

### Test Daily Report (Manual)

```bash
cd /var/www/dev/trading
python3 supervisor/bot_supervisor.py --report
```

**Expected output:**
```
📊 Generating supervisor report...
🔍 Checking market conditions...
   Market Regime: trending
   ADX: 38.26
   ...
📧 Sending daily email report...
✅ Email report sent successfully
```

### Test Crash Alert (Simulate)

```bash
# Simulate crash alert
cd /var/www/dev/trading/supervisor
python3 supervisor_email_notifier.py --crash "Test Bot" true
```

---

## 📅 Email Schedule

| Time | Email Type | Trigger | Content |
|------|-----------|---------|---------|
| **8:00 AM Daily** | Daily Report | Scheduled (cron) | Full system status, market conditions, bot health |
| **Immediate** | Crash Alert | Bot stops unexpectedly | Restart status, error details, action needed |
| **On Demand** | Test Email | Manual command | Configuration verification |

---

## 📊 What Each Email Contains

### Daily Report Email Sections:

1. **Header**
   - Report date
   - Visual banner

2. **Market Conditions**
   - Current BTC price
   - ADX value (trend strength)
   - Market regime (trending/choppy/ranging)
   - Tradeable status

3. **Bot Health Status**
   - Table of all bots
   - Running status (🟢 Running / 🔴 Stopped)
   - Health status (✅ Healthy / ⚠️ Issues)
   - Issue count

4. **Summary**
   - All bots running? Yes/No
   - All bots healthy? Yes/No
   - Total issues detected
   - Market conditions summary

5. **Issues (if any)**
   - Detailed list of any problems
   - Per-bot breakdown

6. **Supervisor Activity**
   - Health check frequency
   - Market monitoring
   - State cleanup status
   - Crash/restart summary

7. **Footer**
   - Timestamp
   - Dashboard links
   - Server information

---

## 🎨 Email Formatting

Emails are sent in **HTML format** with:
- ✅ Professional styling
- 📊 Color-coded metrics
- 📱 Mobile-responsive
- 🔗 Clickable dashboard links
- ✉️ Plain text fallback

**Colors:**
- 🟢 Green = Good/Healthy/Running
- 🟡 Yellow = Warning/Degraded
- 🔴 Red = Error/Stopped/Failed
- 🔵 Blue = Info/Neutral

---

## 🔍 Troubleshooting

### Not Receiving Emails?

**1. Check email configuration:**
```bash
cat /var/www/dev/trading/supervisor/email_config.json
```

**2. Test email manually:**
```bash
python3 /var/www/dev/trading/supervisor/supervisor_email_notifier.py --test
```

**3. Check supervisor logs:**
```bash
tail -50 /var/www/dev/trading/supervisor/logs/supervisor.log | grep -i email
```

**4. Check spam folder**
- Emails from `finanzas@ueipab.edu.ve` might be marked as spam
- Add to contacts/whitelist

**5. Verify cron is running:**
```bash
systemctl status cron
crontab -l | grep supervisor
```

### Email Sending Fails?

**Check error in logs:**
```bash
grep -i "email" /var/www/dev/trading/supervisor/logs/*.log | tail -20
```

**Common issues:**
- SMTP credentials expired
- Network connectivity issues
- Gmail security settings (if using Gmail)
- Recipient email invalid

**Fix SMTP credentials:**
```bash
nano /var/www/dev/trading/supervisor/email_config.json
# Update smtp_password
```

### Emails Delayed?

- Cron schedule is every 8 AM for daily reports
- Crash alerts are immediate (5-15 min after crash)
- SMTP can take 1-2 minutes to deliver

---

## 📝 Email Examples

### Example 1: All Healthy (Daily Report)

```
Subject: ✅ Daily Bot Supervisor Report - 2025-11-10

Market: BTC $105,337 | ADX 38.26 (Trending) | Tradeable ✅

Bots:
  Scalping v2: ✅ Running - Healthy
  ADX v2: ✅ Running - Healthy

Summary:
  ✅ All bots running
  ✅ All bots healthy
  📊 0 issues detected
  🎯 No crashes in past 24h

[View ADX Dashboard] [View Scalping Dashboard]
```

### Example 2: Bot Crashed & Restarted

```
Subject: 🚨 Bot Supervisor Alert: Scalping v2 RESTARTED

⚠️  ALERT: Bot crashed but automatically recovered

Bot: Scalping v2
Status: ✅ RESTARTED
Time: 2025-11-10 14:30:00

The supervisor detected the bot stopped and restarted it successfully.

✅ No action required - bot is back online
```

### Example 3: Issues Detected

```
Subject: ⚠️  Daily Bot Supervisor Report - 2025-11-10

Market: BTC $105,337 | ADX 12.27 (Weak) | Not Tradeable ⚠️

Bots:
  Scalping v2: ⚠️  Issues - Database not updating
  ADX v2: ✅ Running - Healthy

Issues Detected:
  • Scalping v2: No database updates in 10+ minutes

Recommended Actions:
  1. Check Scalping v2 logs
  2. Verify API connectivity
  3. Consider manual restart if persists
```

---

## 🔒 Security & Privacy

### Email Content

Emails contain:
- ✅ System status information
- ✅ Market data (public information)
- ✅ Bot names and health status
- ❌ **NO API keys or passwords**
- ❌ **NO trading account balances**
- ❌ **NO sensitive credentials**

### SMTP Credentials

- Stored in `email_config.json`
- File permissions: `-rw-r--r--` (644)
- Only root can modify
- Password is app-specific (not account password)

---

## 📈 Future Enhancements (Optional)

Potential additions you could request:

1. **Weekly Digest**
   - Performance summary
   - Trade statistics
   - Uptime metrics
   - Trend analysis

2. **Performance Alerts**
   - Low win rate warnings
   - Excessive drawdown alerts
   - High P&L notifications

3. **Custom Thresholds**
   - Email only if issues detected
   - Skip emails on weekends
   - Hourly updates during trading

4. **Multiple Recipients**
   - CC additional emails
   - Different alerts for different people

5. **SMS Alerts** (via Twilio)
   - Critical crashes
   - Major P&L changes

---

## 💡 Tips

1. **Check your spam folder first** after enabling emails
2. **Whitelist finanzas@ueipab.edu.ve** in your email client
3. **Set up email filters** to organize bot emails
4. **Review daily reports** regularly (even if all healthy)
5. **Don't panic on crash alerts** - supervisor auto-restarts in most cases

---

## 🆘 Support Commands

```bash
# Test email
python3 /var/www/dev/trading/supervisor/supervisor_email_notifier.py --test

# Generate manual report
python3 /var/www/dev/trading/supervisor/bot_supervisor.py --report

# Check email config
cat /var/www/dev/trading/supervisor/email_config.json

# View recent email logs
grep -i email /var/www/dev/trading/supervisor/logs/*.log | tail -20

# Verify cron schedule
crontab -l | grep -E "(report|supervisor)"
```

---

## ✅ Verification Checklist

After installation, verify emails are working:

- [ ] Test email received: `python3 supervisor_email_notifier.py --test`
- [ ] Daily report received (wait until 8 AM or run manually)
- [ ] Email not in spam folder
- [ ] Sender address whitelisted
- [ ] Dashboard links work in email
- [ ] HTML formatting displays correctly
- [ ] Mobile display works (if checking on phone)

---

## 📊 Current Status

**Email System:** ✅ Installed and Tested
**Sender:** finanzas@ueipab.edu.ve
**Recipient:** perdomo.gustavo@gmail.com
**Daily Schedule:** 8:00 AM
**Crash Alerts:** Enabled (immediate)
**Test Status:** ✅ Passed (2025-11-10 17:48)

---

**Next Email:** Tomorrow at 8:00 AM (Daily Report)

**Documentation:** Complete
**Tested:** ✅ Yes
**Production Ready:** ✅ Yes

---

*For questions or to modify email settings, edit `/var/www/dev/trading/supervisor/email_config.json`*
