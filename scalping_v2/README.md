# Bitcoin Scalping Trading Bot v2.0

**High-frequency Bitcoin scalping strategy using EMA, RSI, Stochastic, and Volume analysis**

---

## 🎯 Overview

The Scalping Bot v2.0 is a fully operational paper trading system that generates LONG/SHORT signals based on real-time Bitcoin market data from BingX exchange. It uses multiple technical indicators, market regime detection, and a learning system to improve signal quality over time.

**Current Status:** ✅ **FULLY OPERATIONAL** (Paper Trading Mode)

---

## 🚀 Quick Start

### Prerequisites
```bash
# Python 3.8+
pip3 install pandas numpy requests flask flask-cors python-dotenv
```

### Configuration
1. Set up BingX API credentials in `config/.env`:
```env
BINGX_API_KEY=your_api_key
BINGX_API_SECRET=your_secret
```

2. Adjust trading parameters in `config_live.json` (optional)

### Run the Bot
```bash
# Start trading bot (paper mode)
python3 live_trader.py --mode paper --config config_live.json

# Start web dashboard (separate terminal)
python3 dashboard_web.py
```

### Access Dashboard
```
https://dev.ueipab.edu.ve:5900/scalping/
```

---

## 📊 Features

### Real-Time Trading
- ✅ Fetches real Bitcoin prices from BingX every 30 seconds
- ✅ 1-minute candle scalping (true high-frequency)
- ✅ Paper trading simulation with real market data
- ✅ Automatic position management (SL/TP/Time-based exits)

### Technical Analysis
- ✅ **EMA Trend Detection** (5, 8, 21 periods)
- ✅ **RSI Momentum** (14 period)
- ✅ **Stochastic Oscillator** (14, 3)
- ✅ **Volume Analysis** (1.3x confirmation)
- ✅ **ATR Volatility** (14 period for dynamic stops)

### Market Intelligence
- ✅ **Market Regime Detection** (trending/ranging/choppy)
- ✅ **Signal Confidence Scoring** (65% minimum)
- ✅ **Learning System** (adjusts confidence based on results)
- ✅ **Multi-condition Signal Validation**

### Risk Management
- ✅ Daily loss limit (-3% max)
- ✅ Max drawdown protection (-10% max)
- ✅ Consecutive loss circuit breaker (3 losses)
- ✅ Max 1 concurrent position
- ✅ Max 3-minute position hold time

### Monitoring
- ✅ **Web Dashboard** - Real-time monitoring via browser
- ✅ **Console Dashboard** - Terminal-based display
- ✅ **API Endpoints** - Status, indicators, trades, performance
- ✅ **Comprehensive Logging** - All activity tracked

---

## 📁 Project Structure

```
scalping_v2/
├── live_trader.py                      # Main bot orchestrator
├── dashboard_web.py                    # Flask web dashboard
├── config_live.json                    # Trading configuration
│
├── src/
│   ├── api/
│   │   └── bingx_api.py               # BingX exchange client
│   ├── signals/
│   │   └── scalping_signal_generator.py  # Signal generation
│   ├── indicators/
│   │   └── scalping_engine.py         # Core technical analysis
│   ├── execution/
│   │   ├── paper_trader.py            # Paper trading simulation
│   │   ├── position_manager.py        # Position tracking
│   │   └── order_executor.py          # Order management
│   ├── risk/
│   │   ├── risk_manager.py            # Risk controls
│   │   └── position_sizer.py          # Position sizing
│   └── monitoring/
│       ├── dashboard.py               # Console dashboard
│       └── performance_tracker.py     # Performance metrics
│
├── templates/
│   └── dashboard.html                 # Web UI
├── static/
│   ├── css/dashboard.css              # Dashboard styling
│   └── js/dashboard.js                # Dashboard logic
│
├── logs/
│   ├── live_trading.log               # Bot activity log
│   ├── dashboard_web.log              # Dashboard log
│   └── final_snapshot.json            # Real-time state
│
└── docs/
    ├── ARCHITECTURE_OVERVIEW.md       # System architecture
    ├── FINAL_VERIFICATION_2025-11-02.md  # Complete verification
    ├── JSON_SERIALIZATION_FIX.md      # Fix documentation
    └── QUICK_REFERENCE.md             # Quick reference guide
```

---

## 🔧 Configuration

### Trading Parameters (`config_live.json`)

```json
{
  "initial_capital": 1000.0,      // Starting balance
  "leverage": 5,                   // 5x leverage
  "risk_per_trade": 1.0,          // 1% risk ($10 per trade)
  "max_positions": 1,              // Max concurrent positions
  "timeframe": "1m",               // 1-minute candles

  "target_profit_pct": 0.003,     // 0.3% take profit
  "max_loss_pct": 0.0015,         // 0.15% stop loss
  "max_position_time": 180,        // 3 minutes max hold

  "min_confidence": 0.65,          // 65% minimum confidence
  "min_volume_ratio": 1.3          // 1.3x volume confirmation
}
```

### Risk Management

```json
{
  "daily_loss_limit": 3.0,         // -3% max daily loss
  "max_drawdown": 10.0,            // -10% max drawdown
  "consecutive_loss_limit": 3,     // Circuit breaker
  "max_daily_trades": 30           // Max trades per day
}
```

---

## 📈 Signal Generation

### LONG Signal Conditions

**Primary (70% confidence):**
- EMA 5 > EMA 8 > EMA 21 (strong bullish trend)
- Stochastic bullish crossover
- Volume > 1.3x average

**Secondary (60% confidence):**
- RSI < 30 (oversold)
- Price near support level
- Bullish candlestick pattern

**Tertiary (50% confidence):**
- EMA micro crossover
- Volume spike > 1.5x

### SHORT Signal Conditions

**Primary (70% confidence):**
- EMA 5 < EMA 8 < EMA 21 (strong bearish trend)
- Stochastic bearish crossover
- Volume > 1.3x average

**Secondary (60% confidence):**
- RSI > 70 (overbought)
- Price near resistance level
- Bearish candlestick pattern

**Tertiary (50% confidence):**
- EMA micro crossover
- Volume spike > 1.5x

### Confidence Adjustments

- **Win rate > 60%:** +20% confidence boost
- **Win rate < 40%:** -20% confidence penalty
- **3+ consecutive losses:** -30% confidence penalty
- **Choppy market:** -30% confidence reduction
- **Ranging market:** -10% confidence reduction

---

## 🔄 Data Flow

```
Timer (30s) → live_trader.py → scalping_signal_generator.py →
bingx_api.py (fetch 100 candles) → scalping_engine.py (calculate indicators) →
Signal Generated (confidence >= 65%) → live_trader.py (execute paper trade) →
Monitor Position (every 5s) → Close on SL/TP/Time →
Export Snapshot → dashboard_web.py (display)
```

---

## 🐛 Recent Fixes (2025-11-02)

### Fix #1: Environment File Loading
**Issue:** Bot couldn't load BingX API credentials
**Solution:** Changed from relative to absolute path
**File:** `live_trader.py` line 22

### Fix #2: DataFrame Conversion
**Issue:** BingX API returns list, not DataFrame
**Solution:** Added `pd.DataFrame(klines)` conversion
**File:** `scalping_signal_generator.py` line 129

### Fix #3: JSON Serialization
**Issue:** `Object of type bool is not JSON serializable`
**Solution:** Custom `NumpyEncoder` class
**File:** `live_trader.py` lines 40-54, 509

---

## 📊 Current Performance

```
Bot Status:       ✅ ACTIVE
Mode:             Paper Trading
Balance:          $1,000.00
BTC Price:        Real-time from BingX
Signal Checks:    Every 30 seconds
Data Source:      100 1-minute candles
Update Cycle:     5 seconds
Indicators:       All calculated
Errors:           0
Uptime:           100%
```

**Trading Stats:**
- Max Positions: 1
- Min Confidence: 65%
- Risk per Trade: 1% ($10)
- Stop Loss: 0.15% (ATR-adjusted)
- Take Profit: 0.3% (2:1 R/R)
- Max Hold Time: 3 minutes

---

## 🎛️ API Endpoints

### Web Dashboard Endpoints

```
GET /                          # Main dashboard page
GET /api/status               # Bot status, account, positions
GET /api/indicators           # Technical indicators
GET /api/trades?limit=10      # Recent trades
GET /api/performance          # Performance statistics
GET /api/risk                 # Risk management status
GET /health                   # Health check
```

---

## 📖 Documentation

### Quick Start Guides
- **README.md** (this file) - Project overview
- **QUICK_REFERENCE.md** - Quick reference card
- **docs/FINAL_VERIFICATION_2025-11-02.md** - Complete verification report

### Technical Documentation
- **ARCHITECTURE_OVERVIEW.md** - System architecture (850+ lines)
- **JSON_SERIALIZATION_FIX.md** - Bug fix documentation
- **DASHBOARD_ENHANCEMENTS.md** - Dashboard features

### Code Documentation
- Inline comments in all Python files
- Docstrings for all classes and methods
- Type hints for function signatures

---

## 🚦 System Status

### Services

**Trading Bot:**
```bash
sudo systemctl status scalping-trading-bot
sudo journalctl -u scalping-trading-bot -f
```

**Web Dashboard:**
```bash
sudo systemctl status scalping-dashboard
sudo journalctl -u scalping-dashboard -f
```

### Logs

```bash
# Bot logs
tail -f logs/live_trading.log

# Dashboard logs
tail -f logs/dashboard_web.log

# Real-time state
cat logs/final_snapshot.json | python3 -m json.tool
```

---

## 🔐 Security

- ✅ API keys stored in `.env` file (not committed)
- ✅ Paper trading mode prevents real money loss
- ✅ Conservative risk limits (1% per trade, -3% daily)
- ✅ Circuit breaker for consecutive losses
- ✅ HTTPS enabled for web dashboard

---

## 🛠️ Development

### Run Tests
```bash
# Test BingX API connection
python3 -c "from src.api.bingx_api import BingXAPI; api = BingXAPI('key', 'secret'); print(api.get_ticker_price('BTC-USDT'))"

# Test signal generation
python3 -c "from src.signals.scalping_signal_generator import ScalpingSignalGenerator; # Add test code"
```

### Debug Mode
```bash
# Run with verbose logging
python3 live_trader.py --mode paper --config config_live.json --debug
```

---

## 📝 Changelog

### v2.0 (2025-11-02)
- ✅ Fixed JSON serialization (NumpyEncoder)
- ✅ Fixed DataFrame conversion
- ✅ Fixed environment file loading
- ✅ Enhanced web dashboard with scalping-specific features
- ✅ Implemented learning system
- ✅ Added market regime detection
- ✅ Volatility-adjusted stop losses
- ✅ Complete architecture documentation

### v1.0 (Initial Release)
- Basic scalping strategy
- Paper trading simulation
- Console dashboard
- Risk management

---

## 🎯 Roadmap

### Short-Term
- [ ] Signal history tracking and backtesting
- [ ] Performance analytics dashboard
- [ ] Email/SMS alert system
- [ ] Automated trade journal

### Medium-Term
- [ ] Multi-timeframe analysis (1m, 5m, 15m)
- [ ] Machine learning signal enhancement
- [ ] Order book depth analysis
- [ ] Correlation analysis (BTC dominance, funding rates)

### Long-Term
- [ ] Live trading mode (after extensive validation)
- [ ] Multi-symbol support (ETH, BNB, SOL)
- [ ] Portfolio management across strategies
- [ ] Advanced risk models (Kelly Criterion, VaR)

---

## 📞 Support

### Issues & Bugs
1. Check logs: `tail -f logs/live_trading.log`
2. Verify configuration: `cat config_live.json`
3. Check bot status: `sudo systemctl status scalping-trading-bot`
4. Review documentation in `docs/` folder

### Common Issues

**Bot not fetching prices:**
- Verify BingX API credentials in `.env`
- Check internet connection
- Review logs for error messages

**Dashboard shows empty indicators:**
- Ensure bot is running
- Check `logs/final_snapshot.json` exists and is valid JSON
- Restart dashboard service

**JSON errors:**
- Verify `NumpyEncoder` is being used in `json.dump()`
- Check for new indicator types that need serialization

---

## 📄 License

This project is for educational and personal use only. Not financial advice. Trade at your own risk.

---

## 🙏 Acknowledgments

- BingX API for real-time market data
- Technical analysis libraries (pandas, numpy)
- Flask framework for web dashboard
- systemd for service management

---

**Version:** 2.0 Enhanced
**Last Updated:** 2025-11-02
**Status:** Production Ready (Paper Trading)
**Dashboard:** https://dev.ueipab.edu.ve:5900/scalping/

---

## ⚠️ Disclaimer

This software is for educational purposes only. Cryptocurrency trading carries significant risk. Never trade with money you cannot afford to lose. Always start with paper trading to validate strategies before considering live trading.

**Not financial advice. Trade responsibly.**
