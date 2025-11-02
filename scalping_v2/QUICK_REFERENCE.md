# Scalping Strategy v2.0 - Quick Reference

## Service Management

### Start/Stop/Restart
```bash
# Start the bot
sudo systemctl start scalping-trading-bot

# Stop the bot
sudo systemctl stop scalping-trading-bot

# Restart the bot
sudo systemctl restart scalping-trading-bot

# Check status
systemctl status scalping-trading-bot
```

### View Logs
```bash
# Real-time logs
journalctl -u scalping-trading-bot -f

# Last 50 lines
journalctl -u scalping-trading-bot -n 50

# Since 10 minutes ago
journalctl -u scalping-trading-bot --since "10 minutes ago"
```

## API Endpoints

### Base URL
```
http://localhost:5902
```

### Available Endpoints
```bash
# System status and account
curl http://localhost:5902/api/status | jq

# Technical indicators
curl http://localhost:5902/api/indicators | jq

# Performance metrics
curl http://localhost:5902/api/performance | jq

# Risk status
curl http://localhost:5902/api/risk | jq

# Recent trades
curl http://localhost:5902/api/trades | jq
```

## Web Dashboard

### URL
```
https://dev.ueipab.edu.ve:5900/scalping/
```

### Features
- Real-time account balance
- Current BTC price
- Technical indicators
- Open positions
- Recent trades
- Risk metrics
- Performance charts

## Configuration

### Main Config File
```
/var/www/dev/trading/scalping_v2/config_live.json
```

### Key Parameters
```json
{
  "initial_capital": 1000.0,
  "timeframe": "1m",
  "signal_check_interval": 30,
  "max_position_time": 180,
  "risk_per_trade": 1.0,
  "daily_loss_limit": 3.0,
  "max_positions": 1,
  "min_confidence": 0.65
}
```

### To Apply Config Changes
```bash
sudo systemctl restart scalping-trading-bot
```

## Database

### Location
```
/var/www/dev/trading/scalping_v2/data/trades.db
```

### Reset Database
```bash
cd /var/www/dev/trading/scalping_v2
rm -f data/trades.db
python3 init_database.py
sudo systemctl restart scalping-trading-bot
```

## BingX API Setup

### Environment File
```
/var/www/dev/trading/scalping_v2/config/.env
```

### Add Credentials
```bash
# Edit .env file
nano /var/www/dev/trading/scalping_v2/config/.env

# Add these lines:
BINGX_API_KEY=your_api_key_here
BINGX_API_SECRET=your_api_secret_here

# Restart bot
sudo systemctl restart scalping-trading-bot
```

## Troubleshooting

### Bot Won't Start
```bash
# Check logs for errors
journalctl -u scalping-trading-bot -n 100

# Check if port 5902 is in use
netstat -tlnp | grep 5902

# Verify config file is valid JSON
python3 -c "import json; print(json.load(open('config_live.json')))"
```

### Dashboard Shows Wrong Data
```bash
# Clear browser cache (Ctrl+Shift+R)
# Verify nginx is routing correctly
sudo nginx -t
sudo systemctl reload nginx

# Check which service is on port 5902
curl http://localhost:5902/api/status | jq '.bot_status'
```

### Balance Not Updating
```bash
# Disable session restoration (already done)
# Check if final_snapshot.json exists
ls -la /var/www/dev/trading/scalping_v2/logs/final_snapshot.json

# If it exists and has wrong balance, remove it
rm -f /var/www/dev/trading/scalping_v2/logs/final_snapshot.json

# Restart bot
sudo systemctl restart scalping-trading-bot
```

### No Signals Generating
```bash
# Check if API credentials are set
journalctl -u scalping-trading-bot -n 50 | grep -i "api"

# Should see: "✅ BingX API initialized"
# If you see: "⚠️  BingX API credentials not found"
# Then add credentials to config/.env (see BingX API Setup above)
```

## Performance Monitoring

### Check Current Balance
```bash
curl -s http://localhost:5902/api/status | jq '.account.balance'
```

### Check Total PNL
```bash
curl -s http://localhost:5902/api/status | jq '.account.total_pnl'
```

### Check Open Positions
```bash
curl -s http://localhost:5902/api/status | jq '.positions'
```

### Check Recent Trades
```bash
curl -s http://localhost:5902/api/trades | jq '.trades[:5]'
```

## Important Files

| File | Purpose |
|------|---------|
| `live_trader.py` | Main bot orchestration |
| `config_live.json` | Configuration parameters |
| `src/indicators/scalping_engine.py` | Signal generation logic |
| `src/signals/scalping_signal_generator.py` | Market data integration |
| `dashboard_web.py` | Web dashboard backend |
| `static/js/dashboard.js` | Web dashboard frontend |
| `data/trades.db` | SQLite database |
| `logs/live_trading.log` | Bot activity log |

## Current Status

- **Version:** Scalping Strategy v2.0 Enhanced
- **Mode:** Paper Trading
- **Balance:** $1000.00
- **Timeframe:** 1-minute candles
- **Signal Checks:** Every 30 seconds
- **Max Position Time:** 3 minutes
- **Service Status:** ✅ Active (running)

## Documentation

- **Enhancements:** `ENHANCEMENTS_APPLIED.md`
- **Bug Fixes:** `BUGFIXES_AND_OPTIMIZATIONS.md`
- **Final Status:** `FINAL_STATUS_2025-11-02.md`
- **This Reference:** `QUICK_REFERENCE.md`

---

**Last Updated:** 2025-11-02 01:40 AM
