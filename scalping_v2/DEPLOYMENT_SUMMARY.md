# ScalpingV2 Strategy - Deployment Summary
**Date:** 2025-11-02
**Status:** ✅ DEPLOYED AND RUNNING
**Mode:** Paper Trading Only

---

## 🎯 DEPLOYMENT STATUS

### ✅ Services Running

```
● scalping-trading-bot.service - ACTIVE
  Port: N/A (background service)
  PID: Running
  Mode: Paper Trading
  Auto-start: ENABLED

● scalping-dashboard.service - ACTIVE
  Port: 5902 (internal)
  External: https://dev.ueipab.edu.ve:5900/scalping/ (via nginx)
  Auto-start: ENABLED
```

### 📊 Key Information

- **Strategy Type:** Bitcoin Scalping v2.0
- **Indicators:** EMA (5, 8, 21), RSI (14), Stochastic (14, 3), Volume, ATR
- **Timeframe:** 5 minutes
- **Signal Check Interval:** 300 seconds (5 minutes)
- **Initial Capital:** $100.00
- **Trading Mode:** PAPER ONLY (simulated)
- **Database:** SQLite (`data/trades.db`)

---

## 📁 PROJECT STRUCTURE

```
/var/www/dev/trading/scalping_v2/
├── src/
│   ├── api/                    → symlink to ADX (BingX API)
│   ├── execution/              → symlink to ADX (Paper Trader, Order Executor)
│   ├── risk/                   → symlink to ADX (Risk Manager, Position Sizer)
│   ├── monitoring/             → symlink to ADX (Dashboard, Performance Tracker)
│   ├── persistence/            → symlink to ADX (Trade Database)
│   ├── indicators/
│   │   └── scalping_engine.py     ← NEW: Core scalping logic
│   └── signals/
│       └── scalping_signal_generator.py  ← NEW: Signal generation
│
├── logs/
│   ├── live_trading.log           # Bot logs
│   ├── dashboard_web.log          # Dashboard logs
│   └── final_snapshot.json        # Current state (for dashboard)
│
├── data/
│   └── trades.db                  # SQLite database
│       ├── scalping_trades
│       └── scalping_performance_snapshots
│
├── systemd/
│   ├── scalping-trading-bot.service
│   └── scalping-dashboard.service
│
├── config/
│   └── .env                       → symlink to ADX (API credentials)
│
├── templates/
│   └── dashboard.html             # Modified for scalping
│
├── static/                        → symlink to ADX (CSS, JS)
│
├── live_trader.py                 # Main bot script
├── dashboard_web.py               # Web dashboard (port 5902)
├── config_live.json               # Scalping configuration
├── start_bot.sh                   # Startup script
├── init_database.py               # Database initialization
├── requirements.txt               # Python dependencies
└── venv/                          # Python virtual environment
```

---

## ⚙️ CONFIGURATION

### config_live.json

```json
{
  "strategy_name": "Bitcoin Scalping v2.0",
  "initial_capital": 100.0,
  "leverage": 5,
  "symbol": "BTC-USDT",
  "timeframe": "5m",

  "target_profit_pct": 0.003,      // 0.3% profit target
  "max_loss_pct": 0.0015,           // 0.15% stop loss
  "max_position_time": 300,         // 5 minutes max hold

  "max_daily_trades": 50,
  "max_positions": 2,
  "risk_per_trade": 2.0,
  "daily_loss_limit": 5.0,

  "ema_fast": 8,
  "ema_slow": 21,
  "ema_micro": 5,
  "rsi_period": 14,
  "min_confidence": 0.6,

  "trading_mode": "paper"
}
```

---

## 🔧 OPERATIONS

### Service Management

```bash
# Start services
sudo systemctl start scalping-trading-bot scalping-dashboard

# Stop services
sudo systemctl stop scalping-trading-bot scalping-dashboard

# Restart services
sudo systemctl restart scalping-trading-bot scalping-dashboard

# Check status
systemctl status scalping-trading-bot
systemctl status scalping-dashboard

# View logs
journalctl -u scalping-trading-bot -f
journalctl -u scalping-dashboard -f
```

### File Locations

```bash
# Main directory
cd /var/www/dev/trading/scalping_v2

# View bot logs
tail -f logs/live_trading.log

# View dashboard logs
tail -f logs/dashboard_web.log

# Check database
python3 -c "import sqlite3; conn = sqlite3.connect('data/trades.db'); cursor = conn.cursor(); cursor.execute('SELECT COUNT(*) FROM scalping_trades'); print(f'Total trades: {cursor.fetchone()[0]}')"

# Monitor snapshot
watch -n 5 cat logs/final_snapshot.json
```

### Dashboard Access

- **Internal:** http://localhost:5902
- **External:** https://dev.ueipab.edu.ve:5900/scalping/
- **Health Check:** http://localhost:5902/health

### API Endpoints

- `GET /` - Main dashboard UI
- `GET /api/status` - Bot status + account + positions
- `GET /api/indicators` - Current scalping indicators
- `GET /api/trades?limit=10&mode=paper` - Recent trades
- `GET /api/performance` - Performance statistics
- `GET /api/risk` - Risk management status
- `GET /health` - Health check

---

## 📊 DATABASE SCHEMA

### scalping_trades

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT | Primary key (scalp_timestamp_side) |
| timestamp | TEXT | Trade timestamp (ISO 8601) |
| side | TEXT | LONG or SHORT |
| entry_price | REAL | Entry price in USDT |
| exit_price | REAL | Exit price in USDT |
| quantity | REAL | BTC quantity |
| pnl | REAL | Realized P&L in USDT |
| pnl_percent | REAL | P&L percentage |
| fees | REAL | Trading fees |
| exit_reason | TEXT | Exit reason |
| hold_duration | REAL | Duration in seconds |
| stop_loss | REAL | Stop loss price |
| take_profit | REAL | Take profit price |
| trading_mode | TEXT | 'paper' or 'live' |
| signal_data | TEXT | JSON with indicators & conditions |
| position_data | TEXT | JSON with position details |
| created_at | TEXT | Creation timestamp |

### scalping_performance_snapshots

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Auto-increment primary key |
| timestamp | TEXT | Snapshot timestamp |
| balance | REAL | Current balance |
| equity | REAL | Current equity |
| total_pnl | REAL | Total P&L |
| total_return_percent | REAL | Return percentage |
| peak_balance | REAL | Peak balance |
| max_drawdown | REAL | Max drawdown percentage |
| total_trades | INTEGER | Total trade count |
| win_rate | REAL | Win rate (0-1) |
| created_at | TEXT | Creation timestamp |

---

## 📈 PERFORMANCE MONITORING

### Check Trade Count

```bash
sqlite3 /var/www/dev/trading/scalping_v2/data/trades.db \
  "SELECT COUNT(*) as trades,
          SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
          SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
          SUM(pnl) as total_pnl
   FROM scalping_trades WHERE trading_mode='paper';"
```

### Today's Performance

```bash
sqlite3 /var/www/dev/trading/scalping_v2/data/trades.db \
  "SELECT COUNT(*) as today_trades,
          AVG(pnl) as avg_pnl,
          SUM(pnl) as total_pnl
   FROM scalping_trades
   WHERE DATE(timestamp) = DATE('now')
   AND trading_mode='paper';"
```

### Recent Trades

```bash
sqlite3 /var/www/dev/trading/scalping_v2/data/trades.db \
  "SELECT timestamp, side, entry_price, exit_price, pnl, exit_reason
   FROM scalping_trades
   ORDER BY timestamp DESC
   LIMIT 10;"
```

---

## ⚠️ IMPORTANT NOTES

### 1. Paper Trading Only
- Currently configured for PAPER TRADING ONLY
- No real funds at risk
- Uses live BingX market data but simulates execution
- Tracks performance as if real trading

### 2. Live Trading Disabled
- Live trading mode is BLOCKED in code
- To enable live trading (NOT RECOMMENDED YET):
  1. Remove the sys.exit(1) block in live_trader.py
  2. Extensive testing required first (100+ paper trades)
  3. Win rate must be >70% before considering live

### 3. Transaction Costs
- Paper trader simulates fees: 0.05% taker, 0.02% maker
- With target profit of 0.3% and fees of ~0.12% per round trip
- Net profit potential: ~0.18% per winning trade
- Requires high win rate (70%+) to be profitable

### 4. Slippage Risk
- Tight stop loss (0.15%) is vulnerable to slippage
- During volatility, actual stop loss could be 2-3x wider
- Monitor closely during first week

### 5. Daily Limits
- Max daily trades: 50
- Daily loss limit: 5%
- Max drawdown: 15%
- Consecutive loss limit: 3

---

## 🔍 VALIDATION CHECKLIST

### ✅ Completed
- [x] Directory structure created
- [x] Virtual environment setup
- [x] Dependencies installed
- [x] Database initialized (scalping_trades table)
- [x] Configuration file created
- [x] Scalping engine implemented
- [x] Signal generator implemented
- [x] Main bot modified for scalping
- [x] Dashboard created (port 5902)
- [x] Systemd services created
- [x] Services enabled and started
- [x] Bot running in background
- [x] Dashboard accessible

### 📋 TODO (Monitoring Phase)
- [ ] Monitor for 24 hours - verify no crashes
- [ ] Check first 10 signals generated
- [ ] Validate indicator calculations
- [ ] Review first 5 trades (if any executed)
- [ ] Confirm database is recording properly
- [ ] Test dashboard displays data correctly
- [ ] Verify risk limits are enforced

### 📋 TODO (Before Live Trading)
- [ ] Complete 100+ paper trades
- [ ] Achieve 70%+ win rate
- [ ] Profit factor > 2.0
- [ ] Max drawdown < 10%
- [ ] Run for 30+ days continuously
- [ ] Review all trades manually
- [ ] Backtest on historical data
- [ ] Start with $50-100 max (if approved)

---

## 🚨 TROUBLESHOOTING

### Bot Won't Start

```bash
# Check logs
journalctl -u scalping-trading-bot -n 50 --no-pager

# Check if port conflicts
netstat -tlnp | grep 5902

# Test manual start
cd /var/www/dev/trading/scalping_v2
source venv/bin/activate
python3 live_trader.py --mode paper
```

### Dashboard Not Loading

```bash
# Check dashboard service
systemctl status scalping-dashboard

# Check if running
curl http://localhost:5902/health

# Test manual start
cd /var/www/dev/trading/scalping_v2
source venv/bin/activate
python3 dashboard_web.py
```

### No Signals Generating

```bash
# Check BingX API connectivity
cd /var/www/dev/trading/scalping_v2
source venv/bin/activate
python3 -c "from src.api.bingx_api import BingXAPI; import os; from dotenv import load_dotenv; load_dotenv('config/.env'); api = BingXAPI(os.getenv('BINGX_API_KEY'), os.getenv('BINGX_API_SECRET')); print(api.get_ticker_price('BTC-USDT'))"

# Lower confidence threshold (in config_live.json)
"min_confidence": 0.5  # was 0.6

# Restart bot
sudo systemctl restart scalping-trading-bot
```

### Database Issues

```bash
# Check database exists
ls -lh /var/www/dev/trading/scalping_v2/data/trades.db

# Verify tables
sqlite3 data/trades.db ".tables"

# Reinitialize if needed
python3 init_database.py
```

---

## 📞 SUPPORT & RESOURCES

### Log Files
- Bot: `/var/www/dev/trading/scalping_v2/logs/live_trading.log`
- Dashboard: `/var/www/dev/trading/scalping_v2/logs/dashboard_web.log`
- Systemd Bot: `journalctl -u scalping-trading-bot`
- Systemd Dashboard: `journalctl -u scalping-dashboard`

### Configuration Files
- Main Config: `/var/www/dev/trading/scalping_v2/config_live.json`
- Environment: `/var/www/dev/trading/adx_strategy_v2/config/.env` (symlinked)
- Bot Service: `/etc/systemd/system/scalping-trading-bot.service`
- Dashboard Service: `/etc/systemd/system/scalping-dashboard.service`

### Documentation
- Implementation Plan: `/var/www/dev/trading/SCALPINGV2_IMPLEMENTATION_PLAN.md`
- Strategy Analysis: `/var/www/dev/trading/SCALPING_STRATEGY_ANALYSIS.md`
- This Document: `/var/www/dev/trading/scalping_v2/DEPLOYMENT_SUMMARY.md`

---

## 🎉 DEPLOYMENT COMPLETE

**Scalping Strategy v2.0 is now LIVE in paper trading mode!**

**Next Steps:**
1. Monitor the bot for 24-48 hours
2. Check logs daily for errors
3. Review dashboard regularly
4. Analyze first signals and trades
5. Adjust parameters if needed
6. Continue paper trading for at least 30 days before any live consideration

**⚠️ REMEMBER:**
- This is PAPER TRADING ONLY
- NO REAL FUNDS AT RISK
- Monitor closely for first week
- High win rate (70%+) required for profitability
- Do NOT enable live trading without extensive validation

---

**Deployment Date:** 2025-11-02 00:35 UTC-4
**Deployed By:** Claude Code Assistant
**Version:** 2.0
**Status:** ✅ ACTIVE & MONITORING
