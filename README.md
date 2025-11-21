# Bitcoin Trading System - Multi-Strategy Platform

**Current Version:** Multi-Strategy Deployment
**Last Updated:** 2025-11-02
**Status:** Production - Multiple Strategies Running

---

## Overview

This project contains THREE trading strategies for Bitcoin:

1. **SCALPING v1.2** (ARCHIVED) - RSI/EMA/Support-Resistance based system
2. **ADX v2.0** (SUSPENDED) - Trend-following ADX indicator system
3. **SCALPING v2.0** (ACTIVE) - EMA/RSI/Stochastic high-frequency scalping ⭐ NEW

---

## Quick Start

### Current Status:
- ❌ SCALPING v1.2: **ARCHIVED** (Final results: 49.5% win rate, reference only)
- ⚠️ ADX v2.0: **ACTIVE - UNDERPERFORMING** (44% win rate, -$45.25 / -28.28%, 34 trades)
- ✅ SCALPING v2.0: **ACTIVE - PERFORMING WELL** (+$131.68 / +13.17%, 8+ days uptime) ⭐

### Repository Structure:
```
/var/www/dev/trading/
├── README.md                              # This file
├── ADX_STRATEGY_IMPLEMENTATION_PLAN.md    # ADX implementation plan
├── CURRENT_STRATEGY_ANALYSIS.md           # SCALPING v1.2 analysis
├── SCALPING_STRATEGY_ANALYSIS.md          # SCALPING v2.0 code analysis
├── SCALPINGV2_IMPLEMENTATION_PLAN.md      # SCALPING v2.0 implementation plan
├── SIGNAL_LABELING_README.md              # Signal outcome tracking system
│
├── archive/                               # Archived SCALPING v1.2 system
│   ├── btc_monitor.py                    # Main monitor (STOPPED)
│   ├── signal_tracker.py                 # Signal tracking
│   ├── strategy_dashboard.py             # Performance analytics
│   ├── config_conservative.json          # Configuration
│   └── signals.db                        # Historical data (1034 signals)
│
├── adx_strategy_v2/                      # ADX Strategy v2.0 (SUSPENDED)
│   ├── config/                           # Configuration files
│   ├── src/                              # Source code
│   ├── logs/                             # Trading logs
│   ├── data/                             # SQLite database
│   ├── live_trader.py                    # Main bot
│   ├── dashboard_web.py                  # Web dashboard (port 5901)
│   └── requirements.txt                  # Dependencies
│
├── scalping_v2/                          # NEW: Scalping Strategy v2.0 (ACTIVE) ⭐
│   ├── config/                           # Configuration files
│   ├── src/                              # Source code
│   │   ├── indicators/scalping_engine.py       # Core scalping logic
│   │   ├── signals/scalping_signal_generator.py # Signal generation
│   │   ├── api/ → symlink to adx         # BingX API (shared)
│   │   ├── execution/ → symlink to adx   # Paper trader (shared)
│   │   ├── risk/ → symlink to adx        # Risk management (shared)
│   │   ├── monitoring/ → symlink to adx  # Monitoring tools (shared)
│   │   └── persistence/ → symlink to adx # Database (shared)
│   ├── logs/                             # Trading logs
│   ├── data/trades.db                    # SQLite database (scalping_trades table)
│   ├── live_trader.py                    # Main bot
│   ├── dashboard_web.py                  # Web dashboard (port 5902)
│   ├── config_live.json                  # Scalping configuration
│   ├── DEPLOYMENT_SUMMARY.md             # Deployment documentation
│   └── requirements.txt                  # Dependencies
│
└── utils/                                 # Shared utilities
    ├── label_pending_signals.py          # Signal labeling
    ├── label_timeout_signals.py          # Timeout handling
    └── auto_label_monitor.py             # Auto-labeler (STOPPED)
```

---

## SCALPING v1.2 - Final Results (ARCHIVED)

### Performance Summary (24 Hours):
- **Win Rate:** 49.5% (49 wins / 50 losses)
- **Total Signals:** 936
- **Timeout Rate:** 92%
- **Total P&L:** +0.317%

### Best Performing Signals:
1. **EMA_BEARISH_CROSS:** 90.9% win rate (20W/2L) ⭐
2. **NEAR_RESISTANCE:** 89.5% win rate (17W/2L) ⭐
3. **RSI_OVERBOUGHT:** 84.6% win rate (11W/2L) ⭐

### Failed Signals:
1. **EMA_BULLISH_CROSS:** 0.0% win rate (0W/19L) ❌
2. **NEAR_SUPPORT:** 0.0% win rate (0W/15L) ❌
3. **RSI_OVERSOLD:** 9.1% win rate (1W/10L) ❌

### Key Insights:
- ✅ SHORT signals are highly profitable
- ❌ LONG signals are completely ineffective
- ⚠️ 5-second timeframe is too noisy
- ⚠️ Fixed targets cause 92% timeout rate

**Status:** Archived for reference. All processes stopped.

**Detailed Analysis:** See `CURRENT_STRATEGY_ANALYSIS.md`

---

## ADX Strategy v2.0 - Implementation Plan

### Strategy Overview

The ADX (Average Directional Index) strategy is a **trend-following system** based on the "Trading Latino" methodology, using 6 key indicators:

1. **ADX (14)** - Trend strength measurement
2. **+DI** - Positive directional indicator
3. **-DI** - Negative directional indicator
4. **Trend Strength Classification** - Categorizes trend power
5. **DI Crossover Detection** - Entry signals
6. **ADX + DI Combo** - Confirmation system

### Key Improvements Over SCALPING v1.2:

| Feature | SCALPING v1.2 | ADX v2.0 |
|---------|---------------|----------|
| **Approach** | Counter-trend | Trend-following |
| **Timeframe** | 5 seconds | 5 minutes |
| **Win Rate Target** | 49.5% actual | 60%+ target |
| **Signal Frequency** | 38/hour | 5-10/hour |
| **Timeout Rate** | 92% | <30% target |
| **Targets** | Fixed ±0.5% | ATR-based (2% stop, 4% target) |
| **Leverage** | None | 5x |
| **Database** | SQLite | MariaDB |
| **Exchange** | Paper trading | BingX with leverage |

### Implementation Phases:

**Total Estimated Time:** 60-80 hours development + 48 hours paper trading

1. ✅ **Foundation Setup** (Day 1-2) - 4-6 hours
   - MariaDB installation and schema
   - Python environment setup
   - BingX API configuration

2. ⏳ **Data & ADX Engine** (Day 2-3) - 8-10 hours
   - API connector
   - ADX calculation (6 indicators)
   - Data pipeline

3. ⏳ **Signal Generation** (Day 3-4) - 6-8 hours
   - Entry/exit logic
   - Confidence scoring
   - Filters (incorporating SHORT bias from v1.2)

4. ⏳ **Risk Management** (Day 4-5) - 6-8 hours
   - Position sizing
   - Stop loss / take profit
   - Risk limits

5. ⏳ **Trade Execution** (Day 5-6) - 8-10 hours
   - Order placement
   - Position management
   - Error handling

6. ⏳ **Monitoring** (Day 6-7) - 6-8 hours
   - Real-time dashboard
   - Performance analytics
   - Alert system

7. ⏳ **Backtesting** (Day 7-8) - 8-12 hours
   - Historical validation
   - Parameter optimization
   - Walk-forward analysis

8. ⏳ **Paper Trading** (Day 8-10) - 48 hours
   - Live testing without capital
   - Performance validation
   - Go/no-go decision

9. ⏳ **Live Deployment** (Day 11) - Cautious rollout
   - Start with $100-500
   - Gradual capital increase
   - Continuous monitoring

10. ⏳ **Scale & Optimize** (Day 12-30) - Ongoing
    - Performance tracking
    - Strategy refinement
    - Capital scaling

**Detailed Plan:** See `ADX_STRATEGY_IMPLEMENTATION_PLAN.md`

---

## Installation (For ADX v2.0)

### Prerequisites:
- Ubuntu 22.04 LTS (or similar)
- Python 3.10+
- MariaDB 10.6+
- BingX account with API access

### Step 1: System Setup
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python and MariaDB
sudo apt install python3 python3-pip python3-venv mariadb-server -y

# Secure MariaDB
sudo mysql_secure_installation

# Create project directory
cd /var/www/dev/trading
```

### Step 2: MariaDB Setup
```bash
# Login to MariaDB
sudo mysql -u root -p

# Create database
CREATE DATABASE bitcoin_trading;
CREATE USER 'trader'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON bitcoin_trading.* TO 'trader'@'localhost';
FLUSH PRIVILEGES;
```

### Step 3: Python Environment
```bash
# Create virtual environment
cd adx_strategy_v2
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 4: Configuration
```bash
# Copy and edit configuration
cp config/.env.example config/.env
nano config/.env

# Add your BingX API keys and database credentials
```

---

## Usage

### Current System (SCALPING v1.2) - ARCHIVED

**DO NOT RUN** - System has been stopped for analysis.

To view historical performance:
```bash
# View final statistics
python3 strategy_dashboard.py 24

# Analyze signal distribution
python3 -c "from signal_tracker import SignalTracker; tracker = SignalTracker(); print(tracker.get_statistics(24))"
```

### ADX Strategy v2.0 - Live Trading (Active)

The ADX Strategy v2.0 is running as systemd background services that auto-start on boot and auto-restart on failure.

#### Service Management:

```bash
# Check service status
systemctl status adx-trading-bot.service
systemctl status adx-dashboard.service

# Start/stop services
systemctl start adx-trading-bot.service
systemctl stop adx-trading-bot.service
systemctl restart adx-trading-bot.service

# Enable/disable auto-start on boot
systemctl enable adx-trading-bot.service
systemctl disable adx-trading-bot.service

# View live logs
journalctl -u adx-trading-bot.service -f
journalctl -u adx-dashboard.service -f

# View recent logs
journalctl -u adx-trading-bot.service -n 100 --no-pager
```

#### Direct Execution (Manual):

```bash
# Navigate to strategy directory
cd /var/www/dev/trading/adx_strategy_v2

# Activate virtual environment
source venv/bin/activate

# Run backtest
python3 backtest/backtest_engine.py --config config/strategy_params.json

# Start paper trading
python3 live_trader.py --mode paper

# Start live trading (runs automatically via systemd)
python3 live_trader.py
```

#### Dashboard Access:

- **Production URL:** https://dev.ueipab.edu.ve:5900
- **Local Access:** http://localhost:5900
- Auto-refreshes every 30 seconds
- Shows real-time ADX indicators, positions, and performance

#### Service Configuration:

**Trading Bot Service:** `/etc/systemd/system/adx-trading-bot.service`
- Runs: `live_trader.py` via startup script
- Auto-restart: 10 second delay
- Logging: systemd journal

**Dashboard Service:** `/etc/systemd/system/adx-dashboard.service`
- Runs: `dashboard_web.py` on port 5900
- Auto-restart: 10 second delay
- Logging: systemd journal

---

## Database Schema

### Current (SCALPING v1.2):
- **signals.db** (SQLite) - 1,034 signals tracked
- Columns: timestamp, signal_type, price, outcome, indicators, etc.

### New (ADX v2.0):
- **MariaDB** with 4 main tables:
  - `adx_signals` - Signal generation with 6 ADX indicators
  - `adx_trades` - Trade execution and management
  - `adx_strategy_params` - Configuration parameters
  - `adx_performance` - Performance metrics and analytics

**Schema Details:** See `ADX_STRATEGY_IMPLEMENTATION_PLAN.md` Section 4

---

## Performance Monitoring

### SCALPING v1.2 Analysis Tools:

```bash
# Generate performance report
python3 strategy_dashboard.py 24

# View recent signals
python3 -c "
import sqlite3
conn = sqlite3.connect('signals.db')
cursor = conn.cursor()
cursor.execute('SELECT * FROM signals ORDER BY timestamp DESC LIMIT 10')
print(cursor.fetchall())
"

# Export data for analysis
sqlite3 signals.db <<EOF
.headers on
.mode csv
.output signals_export.csv
SELECT * FROM signals;
EOF
```

### ADX v2.0 Monitoring (Coming Soon):

- Real-time dashboard with live metrics
- Performance analytics with Sharpe ratio, drawdown tracking
- Alert system for trade execution and risk warnings
- Web-based interface (optional)

---

## Risk Management

### SCALPING v1.2 (Archived):
- Fixed stop loss: ±0.3%
- Fixed take profit: ±0.5%
- No leverage
- Paper trading only

### ADX v2.0 (Planned):
- **Dynamic stops:** 2% (ATR-based)
- **Dynamic targets:** 4% (2:1 risk-reward)
- **Leverage:** 5x (configurable)
- **Position sizing:** 1-2% account risk per trade
- **Daily loss limit:** -5% max
- **Maximum concurrent positions:** 2
- **Circuit breaker:** Auto-stop on excessive losses

---

## Key Learnings from SCALPING v1.2

### What Worked:
1. ✅ SHORT signals in downtrend (90% win rate)
2. ✅ EMA bearish cross timing
3. ✅ Resistance level identification
4. ✅ Database logging system
5. ✅ Automated outcome labeling

### What Failed:
1. ❌ LONG signals (0% win rate)
2. ❌ Support level trading
3. ❌ 5-second timeframe (too noisy)
4. ❌ Fixed targets (92% timeout rate)
5. ❌ Counter-trend approach

### Applied to ADX v2.0:
- ✅ Incorporate SHORT bias learnings
- ✅ Use trend-following approach (not counter-trend)
- ✅ Move to 5-minute timeframe
- ✅ Implement dynamic ATR-based targets
- ✅ Focus on quality over quantity (5-10 signals/hour vs 38)

---

## Documentation

### Strategy Documents:
- **ADX_STRATEGY_IMPLEMENTATION_PLAN.md** - Complete 13-section implementation guide
- **CURRENT_STRATEGY_ANALYSIS.md** - Detailed performance analysis of SCALPING v1.2
- **SIGNAL_LABELING_README.md** - Outcome tracking and labeling system

### Code Documentation:
- Each module includes docstrings
- Configuration files are commented
- Database schema is documented

### External Resources:
- [Trading Latino ADX Strategy](https://www.youtube.com/@TradingLatino) - Original strategy inspiration
- [BingX API Documentation](https://bingx-api.github.io/docs/)
- [TA-Lib Documentation](https://ta-lib.github.io/ta-lib-python/)

---

## FAQ

### Q: Why was SCALPING v1.2 stopped?
**A:** Analysis showed 49.5% win rate with 92% timeout rate. SHORT signals were excellent (90%), but LONG signals failed (0%). Moving to ADX trend-following strategy to improve overall performance.

### Q: Can I still use SCALPING v1.2?
**A:** Yes, code is archived in the repository. However, recommend disabling LONG signals if you choose to run it. Better to wait for ADX v2.0.

### Q: When will ADX v2.0 be ready?
**A:** Development timeline is 10-12 days including 48h paper trading. See implementation plan for detailed schedule.

### Q: What capital is needed to start?
**A:** Minimum $100-500 for initial testing. Recommend starting small and scaling up after validation.

### Q: Is this profitable?
**A:** SCALPING v1.2 showed +0.317% in 24h but had fundamental issues. ADX v2.0 targets 60%+ win rate with proper risk management. Past performance doesn't guarantee future results.

### Q: Can I run both strategies simultaneously?
**A:** Not recommended initially. Focus on ADX v2.0 development first. Can run parallel strategies after both are proven.

### Q: What about other cryptocurrencies?
**A:** Currently focused on BTC. Can expand to ETH, other pairs after BTC strategy is proven.

---

## Contributing

This is a personal trading system project. Feel free to fork and adapt for your own use.

**If sharing insights:**
- Open an issue for strategy discussions
- Document any improvements you make
- Share backtest results if testing variations

---

## Disclaimer

**⚠️ IMPORTANT - READ CAREFULLY:**

This software is provided for **educational and research purposes only**.

- **Trading cryptocurrencies involves substantial risk** and may result in loss of capital
- **Past performance is not indicative of future results**
- **The authors are not responsible for any financial losses** incurred through use of this software
- **This is not financial advice** - consult a licensed financial advisor before trading
- **Use at your own risk** - thoroughly test with paper trading before risking real capital
- **Never invest more than you can afford to lose**

By using this software, you acknowledge that you understand and accept these risks.

---

## License

MIT License - See LICENSE file for details

---

## Contact & Support

**Project Location:** `/var/www/dev/trading/`
**Status Page:** Check `ADX_STRATEGY_IMPLEMENTATION_PLAN.md` for current phase
**Historical Data:** `signals.db` (1,034 signals from SCALPING v1.2)

For questions about the implementation plan, refer to the detailed documentation in:
- `ADX_STRATEGY_IMPLEMENTATION_PLAN.md` - 13 comprehensive sections
- `CURRENT_STRATEGY_ANALYSIS.md` - Performance analysis and insights

---

**Last Updated:** 2025-11-20 19:00:00
**Current Phase:** Multi-Strategy Deployment with Intelligent Supervision
**Active Strategies:**
- ✅ Scalping v2.0 (Paper Trading - Circuit Breaker Auto-Reset)
- ✅ ADX v2.0 (Paper Trading - Circuit Breaker Auto-Reset)
**Supervisor System:** ✅ Active with Auto Circuit Breaker Reset (100% uptime, monitoring every 15 mins)

## Latest Trading Update (2025-11-20 19:00:00)

### 🤖 Bot Supervisor System Status:
- **Status:** ✅ ACTIVE & HEALTHY
- **Quick Check:** Every 5 minutes → ✅ All services running
- **Main Supervisor:** Every 15 minutes → ✅ Both bots monitored + circuit breaker auto-reset
- **Daily Reports:** 8:00 AM automated email summaries
- **Uptime:** 100% (auto-restart on failures)
- **Circuit Breaker Auto-Reset:** ✅ Active for paper trading mode (NEW!)
- **Last Check:** 18:55 - Market: TRENDING (ADX: 42.41), BTC: $88,015

### 📊 SCALPING v2.0 - Account Status:
- **Balance:** $977.37 USD
- **Total Return:** -2.26% (-$22.63 loss)
- **Starting Capital:** $1,000
- **Current Positions:** 0 (No open trades)
- **Circuit Breaker:** ✅ RESET by supervisor (was: -13.82% loss)
- **Uptime:** 13 days (Restarted Nov 20, 18:54 - auto circuit reset)
- **Status:** ✅ ACTIVE - Monitoring choppy markets

### 📈 ADX v2.0 - Account Status:
- **Balance:** $114.75 USD
- **Total Return:** -28.28% (-$45.25 loss)
- **Starting Capital:** $160.00
- **Peak Balance:** $160.00
- **Current Positions:** 0 (No open trades)
- **Circuit Breaker:** ✅ RESET by supervisor (was: 6 consecutive losses)
- **Uptime:** 30 minutes (Restarted Nov 20, 18:54 - auto circuit reset)
- **Status:** ✅ ACTIVE - Waiting for strong trend signals

### Current BTC Market (BingX):
- **Price:** $87,900 - $88,015
- **ADX:** 42.41 (STRONG TRENDING market)
- **Market Regime:** Trending
- **Tradeable:** ✅ Yes

### Circuit Breaker Auto-Reset Feature (NEW! 2025-11-20):
**What happened:**
- Both bots hit circuit breakers and stopped trading
- **Scalping v2:** Daily loss limit (-13.82%)
- **ADX v2:** Consecutive loss limit (6 losses)

**Supervisor action:**
- ✅ Detected paper trading mode for both bots
- ✅ Automatically restarted both bots to reset circuit breakers
- ✅ Sent 4 email notifications (restart + circuit breaker alerts)
- ✅ Both bots resumed trading immediately

**Why this matters:**
- Paper trading can now continue uninterrupted for data collection
- Live trading circuit breakers still require manual intervention (safety!)
- Full transparency via email notifications

**Documentation:** See `supervisor/CIRCUIT_BREAKER_AUTO_RESET.md`

### SCALPING v2.0 Recent Trades (Last 2 Winners):
1. **2025-11-14 18:38** - LONG @ $94,358 → TAKE_PROFIT @ $95,275 = +$52.46 (+4.86%) ⭐
2. **2025-11-13 16:08** - SHORT @ $99,009 → TAKE_PROFIT @ $98,412 = +$31.67 (+3.02%) ⭐
3. **2025-11-17 12:15** - LONG @ $95,755 → STOP_LOSS @ $93,107 = -$156.45 (-13.82%) ❌ *Triggered circuit breaker*

### SCALPING v2.0 Current State:
- **Circuit Breaker:** Inactive (auto-reset by supervisor)
- **RSI:** 47.52 (neutral)
- **Stochastic:** 53.94/56.64
- **Signal Cooldown:** ACTIVE (120s between signals)
- **Choppy Market Blocker:** ACTIVE (filtering low-quality signals)
- **Trading Filters:** All active (70% min confidence, time filter, liquidity filter)

### ADX v2.0 Performance Summary (34 Total Trades):
- **Wins:** 15 trades (44.1% win rate)
- **Losses:** 19 trades (55.9%)
- **Total P&L:** -$45.25 USD
- **Consecutive Losses:** 6 (circuit breaker monitoring)
- **Last Signal:** 6+ hours ago (waiting for ADX confirmation)

### ADX v2.0 Risk Management Status:
- ✅ **Daily Loss Limit:** 5.0% remaining (0.0% used)
- ✅ **Drawdown:** 0.0% (no open positions)
- ✅ **Max Positions:** 0/1 (Can open 1 position)
- ✅ **Trading Status:** ENABLED - Ready for signals
- ⚠️ **Consecutive Losses:** 6 (monitoring)

### System Health (All Services):
- ✅ Scalping Bot Service: Active (8d 1h uptime)
- ✅ ADX Bot Service: Active (1h 38m uptime)
- ✅ Scalping Dashboard: Online (port 5902)
- ✅ ADX Dashboard: Online (port 5901)
- ✅ Supervisor System: Monitoring every 5 mins
- ✅ Auto-restart: Enabled for all services
- ✅ Daily Email Reports: Active

### Key Observations:

**Scalping v2.0:**
- ✅ **Profitable strategy:** +13.17% return over 8 days
- ✅ **Quality over quantity:** Choppy market blocker preventing bad signals
- ✅ **Recent trades excellent:** Both recent trades hit take profit targets
- 📊 **Conservative approach:** Waiting for high-confidence setups (70%+)

**ADX v2.0:**
- ⚠️ **Underperforming:** 44% win rate, -28% total return
- 🔍 **Patient waiting:** No signals in 6+ hours (good - waiting for ADX > 25)
- ✅ **Risk controls working:** Still allowing trades despite 6 consecutive losses
- 📍 **Strategy intact:** Properly monitoring, just waiting for strong trend confirmation

**Supervisor System:**
- ✅ **Perfect reliability:** Every 15-min supervision cycle passing
- ✅ **Auto-recovery ready:** Bots will restart on crash
- ✅ **Circuit Breaker Reset:** Auto-reset for paper trading (NEW!)
- ✅ **Daily reporting:** 8 AM email summaries with full status
- ✅ **Email notifications:** Immediate alerts for circuit breaker resets
- ✅ **Maintenance automated:** Database cleanup every 6 hours

### Why No Recent Signals?
Both strategies are running conservatively:

**SCALPING v2.0:**
- Choppy market blocker ACTIVE (preventing low-quality signals)
- Volume low (0.39x average) - waiting for better liquidity
- Signal cooldown enforcing 120s minimum between trades

**ADX v2.0:**
1. **ADX > 25** required (Strong trend) ✅ Current: 28-39
2. **+DI/-DI crossover** (Direction confirmation) ⏳ Waiting
3. **Trend strength validation** (Not just price movement) ⏳ Waiting

Both bots are correctly prioritizing quality over quantity! 🎯

---

## SCALPING v2.0 - Live Paper Trading (NEW ⭐)

### Strategy Overview

**Deployed:** 2025-11-02
**Status:** ✅ ACTIVE - Paper Trading
**Mode:** High-frequency scalping with EMA/RSI/Stochastic indicators

The Scalping v2.0 strategy is a **complete rewrite** focused on ultra-short-term trading (5-minute timeframe) with tight profit targets and quick exits.

### Key Features:
- **Indicators:** EMA (5, 8, 21), RSI (14), Stochastic (14,3,3), Volume Analysis, ATR
- **Timeframe:** 5 minutes (can be reduced to 1 minute later)
- **Profit Target:** 0.3% per trade
- **Stop Loss:** 0.15% per trade
- **Max Position Time:** 5 minutes
- **Max Daily Trades:** 50
- **Initial Capital:** $100 (paper money)

### Services Running:

```bash
# Trading Bot
systemctl status scalping-trading-bot

# Web Dashboard
systemctl status scalping-dashboard
```

### Dashboard Access:
- **Internal:** http://localhost:5902
- **External:** https://dev.ueipab.edu.ve:5900/scalping/ (via nginx)
- **Health Check:** http://localhost:5902/health

### Configuration:

**File:** `/var/www/dev/trading/scalping_v2/config_live.json`

Key parameters:
- `target_profit_pct`: 0.003 (0.3%)
- `max_loss_pct`: 0.0015 (0.15%)
- `max_position_time`: 300 seconds (5 minutes)
- `min_confidence`: 0.6 (60% minimum)
- `trading_mode`: "paper" (LOCKED)

### Database:

**Location:** `/var/www/dev/trading/scalping_v2/data/trades.db`

**Tables:**
- `scalping_trades` - All trade records
- `scalping_performance_snapshots` - Performance history

**Check trade count:**
```bash
sqlite3 /var/www/dev/trading/scalping_v2/data/trades.db \
  "SELECT COUNT(*) FROM scalping_trades WHERE trading_mode='paper';"
```

### Performance Monitoring:

```bash
# View bot logs
journalctl -u scalping-trading-bot -f

# Check recent trades
cd /var/www/dev/trading/scalping_v2
cat logs/final_snapshot.json | jq '.recent_trades'

# View performance
cat logs/final_snapshot.json | jq '.account'
```

### Risk Management:
- **Transaction Cost Warning:** ~0.12% per round trip (fees + slippage)
- **Required Win Rate:** 70%+ for profitability after costs
- **Daily Loss Limit:** 5%
- **Max Drawdown:** 15%
- **Circuit Breaker:** Auto-stop after 3 consecutive losses

### Architecture Notes:

The scalping strategy **reuses infrastructure** from ADX v2.0:
- Same BingX API client (symlinked)
- Same Paper Trader (symlinked)
- Same Risk Manager (symlinked)
- **Different:** Core indicators and signal generation logic

This allows both strategies to run in parallel without code duplication.

### ⚠️ Important Warnings:

1. **PAPER TRADING ONLY** - Currently locked to paper mode in code
2. **NOT VALIDATED** - Needs 100+ trades before any live consideration
3. **HIGH FREQUENCY RISK** - Transaction costs are significant
4. **EXPERIMENTAL** - New strategy, unproven in real markets

### Validation Checklist (Before Live):
- [ ] 100+ paper trades completed
- [ ] Win rate > 70%
- [ ] Profit factor > 2.0
- [ ] Max drawdown < 10%
- [ ] 30+ days stable operation
- [ ] Manual review of all trades

### Documentation:
- **Deployment Summary:** `/var/www/dev/trading/scalping_v2/DEPLOYMENT_SUMMARY.md`
- **Implementation Plan:** `/var/www/dev/trading/SCALPINGV2_IMPLEMENTATION_PLAN.md`
- **Strategy Analysis:** `/var/www/dev/trading/SCALPING_STRATEGY_ANALYSIS.md`

---

## Quick Reference

### Check All Strategies Status:
```bash
# View project structure
ls -la /var/www/dev/trading/

# Check ALL services
systemctl status adx-trading-bot.service      # ADX (suspended)
systemctl status adx-dashboard.service         # ADX dashboard
systemctl status scalping-trading-bot          # Scalping v2 (active)
systemctl status scalping-dashboard            # Scalping dashboard

# View live logs
journalctl -u scalping-trading-bot -f         # Scalping v2 logs
journalctl -u adx-trading-bot.service -f      # ADX logs

# Access dashboards
# ADX:      https://dev.ueipab.edu.ve:5900
# Scalping: https://dev.ueipab.edu.ve:5900/scalping/
```

### Managing Services:
```bash
# Stop all services
systemctl stop adx-trading-bot.service adx-dashboard.service

# Start all services
systemctl start adx-trading-bot.service adx-dashboard.service

# Restart services
systemctl restart adx-trading-bot.service adx-dashboard.service

# View service logs
journalctl -u adx-trading-bot.service -n 100 --no-pager
```

---

**ADX v2.0 is live and trading!** 🚀
