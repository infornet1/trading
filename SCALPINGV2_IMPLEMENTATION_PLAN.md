# ScalpingV2 Strategy - Implementation Plan
**Version:** 2.0
**Created:** 2025-11-02
**Status:** READY FOR REVIEW
**Deployment Mode:** Paper Trading Only (Background Service)

---

## EXECUTIVE SUMMARY

This plan outlines the implementation of a Bitcoin scalping strategy running parallel to the existing ADX strategy v2.0. The new ScalpingV2 will:

- ✅ Run as separate background systemd service (like ADX)
- ✅ Use same BingX API for market data (paper trading simulation)
- ✅ Have its own database tables (separate from ADX)
- ✅ Run on separate port: 5902/5903 (ADX uses 5901/5900)
- ✅ Use existing infrastructure (BingX API, paper trader, monitoring)
- ✅ Deploy in 100% paper trading mode initially

**Timeline:** 6-8 hours total implementation
**Risk Level:** Low (paper trading only, no real funds)
**Dependencies:** Existing ADX v2 infrastructure

---

## PART 1: ARCHITECTURE DESIGN

### 1.1 System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    TRADING SYSTEM OVERVIEW                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────┐         ┌──────────────────────┐     │
│  │   ADX Strategy v2    │         │  Scalping Strategy   │     │
│  │    (SUSPENDED)       │         │        v2            │     │
│  ├──────────────────────┤         ├──────────────────────┤     │
│  │ Port: 5901 (5900)    │         │ Port: 5902 (5903)    │     │
│  │ Timeframe: 5min      │         │ Timeframe: 5min      │     │
│  │ Signals: ADX         │         │ Signals: EMA/RSI     │     │
│  │ DB: adx_trades       │         │ DB: scalping_trades  │     │
│  │ Status: Stopped      │         │ Status: NEW          │     │
│  └──────────────────────┘         └──────────────────────┘     │
│            │                                  │                  │
│            └──────────────┬──────────────────┘                  │
│                           │                                      │
│                  ┌────────▼────────┐                            │
│                  │  BingX API      │                            │
│                  │  (Market Data)  │                            │
│                  └────────┬────────┘                            │
│                           │                                      │
│              ┌────────────┴────────────┐                        │
│              │                         │                        │
│      ┌───────▼────────┐       ┌───────▼────────┐              │
│      │  Paper Trader  │       │  SQLite DB     │              │
│      │  (Simulated)   │       │  trades.db     │              │
│      └────────────────┘       └────────────────┘              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Component Mapping

| Component | ADX v2 | ScalpingV2 | Shared? |
|-----------|--------|------------|---------|
| **BingX API Client** | ✅ | ✅ | ✅ SHARED (reuse code) |
| **Paper Trader** | ✅ | ✅ | ✅ SHARED (reuse code) |
| **Order Executor** | ✅ | ✅ | ✅ SHARED (reuse code) |
| **Position Manager** | ✅ | ✅ | ✅ SHARED (reuse code) |
| **Risk Manager** | ✅ | ✅ | ✅ SHARED (reuse params) |
| **Database (SQLite)** | adx tables | scalping tables | ⚠️ SEPARATE TABLES |
| **Indicator Engine** | adx_engine.py | scalping_engine.py | ❌ SEPARATE |
| **Signal Generator** | signal_generator.py | scalping_signal_generator.py | ❌ SEPARATE |
| **Main Bot** | live_trader.py | live_trader.py | ⚠️ COPIED & MODIFIED |
| **Dashboard** | dashboard_web.py | dashboard_web.py | ⚠️ COPIED & MODIFIED |
| **Systemd Service** | adx-trading-bot | scalping-trading-bot | ❌ SEPARATE |
| **Port** | 5901/5900 | 5902/5903 | ❌ SEPARATE |
| **Config File** | config_live.json | config_live.json | ⚠️ SEPARATE |

**Legend:**
- ✅ SHARED: Copy and reuse as-is
- ⚠️ SEPARATE: Copy and modify
- ❌ SEPARATE: Create new

---

## PART 2: FILE STRUCTURE

### 2.1 Directory Structure

```
/var/www/dev/trading/
│
├── adx_strategy_v2/                    # EXISTING (keep as-is)
│   ├── src/
│   │   ├── api/
│   │   │   └── bingx_api.py           # ← REUSE THIS
│   │   ├── execution/
│   │   │   ├── paper_trader.py         # ← REUSE THIS
│   │   │   ├── order_executor.py       # ← REUSE THIS
│   │   │   └── position_manager.py     # ← REUSE THIS
│   │   ├── risk/
│   │   │   ├── risk_manager.py         # ← REUSE THIS
│   │   │   └── position_sizer.py       # ← REUSE THIS
│   │   ├── monitoring/
│   │   │   ├── dashboard.py            # ← REUSE THIS
│   │   │   ├── performance_tracker.py  # ← REUSE THIS
│   │   │   └── alerts.py               # ← REUSE THIS
│   │   └── persistence/
│   │       └── trade_database.py       # ← REUSE THIS (different tables)
│   ├── live_trader.py
│   ├── dashboard_web.py
│   └── config_live.json
│
└── scalping_v2/                        # NEW DIRECTORY
    ├── src/
    │   ├── api/
    │   │   └── bingx_api.py           # → SYMLINK to ../adx_strategy_v2/src/api/
    │   ├── execution/
    │   │   ├── paper_trader.py         # → SYMLINK
    │   │   ├── order_executor.py       # → SYMLINK
    │   │   └── position_manager.py     # → SYMLINK
    │   ├── indicators/
    │   │   └── scalping_engine.py      # ← NEW (adapted from bitcoin_scalping.py)
    │   ├── signals/
    │   │   └── scalping_signal_generator.py  # ← NEW
    │   ├── risk/
    │   │   ├── risk_manager.py         # → SYMLINK
    │   │   └── position_sizer.py       # → SYMLINK
    │   ├── monitoring/
    │   │   ├── dashboard.py            # → SYMLINK
    │   │   ├── performance_tracker.py  # → SYMLINK
    │   │   └── alerts.py               # → SYMLINK
    │   └── persistence/
    │       └── trade_database.py       # → SYMLINK (will use scalping_trades table)
    │
    ├── logs/                           # ← NEW
    │   ├── live_trading.log
    │   ├── alerts.log
    │   └── final_snapshot.json
    │
    ├── data/                           # ← NEW
    │   └── trades.db                   # SQLite database (scalping tables)
    │
    ├── templates/                      # ← COPY from ADX
    │   └── dashboard.html              # (modify for scalping indicators)
    │
    ├── static/                         # → SYMLINK to ADX static/
    │
    ├── systemd/                        # ← NEW
    │   ├── scalping-trading-bot.service
    │   └── scalping-dashboard.service
    │
    ├── venv/                           # ← NEW (Python virtual environment)
    │
    ├── config/                         # ← NEW
    │   └── .env                        # → SYMLINK to ADX .env (same API keys)
    │
    ├── live_trader.py                  # ← COPY from ADX (modify for scalping)
    ├── dashboard_web.py                # ← COPY from ADX (change port to 5902)
    ├── config_live.json                # ← NEW (scalping parameters)
    ├── start_bot.sh                    # ← NEW
    ├── requirements.txt                # ← COPY from ADX
    └── README.md                       # ← NEW (documentation)
```

### 2.2 What to Copy vs Symlink

**SYMLINK (shared code):**
- `src/api/` - BingX API client
- `src/execution/` - Paper trader, order executor, position manager
- `src/risk/` - Risk manager, position sizer
- `src/monitoring/` - Dashboard, performance tracker, alerts
- `src/persistence/` - Trade database (uses different table names via config)
- `static/` - CSS, JS files
- `config/.env` - API credentials

**COPY & MODIFY:**
- `live_trader.py` - Import scalping engine instead of ADX
- `dashboard_web.py` - Change port to 5902, display scalping indicators
- `templates/dashboard.html` - Update UI for scalping metrics

**CREATE NEW:**
- `src/indicators/scalping_engine.py` - Core scalping logic
- `src/signals/scalping_signal_generator.py` - Signal generation
- `config_live.json` - Scalping parameters
- `start_bot.sh` - Startup script
- `systemd/*.service` - Systemd service files
- `logs/`, `data/`, `venv/` - Empty directories

---

## PART 3: DATABASE DESIGN

### 3.1 Database Schema

Since we're using the same SQLite database structure, we'll add separate tables with `scalping_` prefix:

**File:** `/var/www/dev/trading/scalping_v2/data/trades.db`

```sql
-- Main trades table (identical to ADX structure)
CREATE TABLE IF NOT EXISTS scalping_trades (
    id TEXT PRIMARY KEY,                    -- Format: scalp_1730512345_long
    timestamp TEXT NOT NULL,                -- ISO 8601 format
    side TEXT NOT NULL,                     -- 'LONG' or 'SHORT'
    entry_price REAL NOT NULL,
    exit_price REAL,
    quantity REAL NOT NULL,                 -- BTC quantity
    pnl REAL,                               -- Realized P&L in USDT
    pnl_percent REAL,                       -- P&L percentage
    fees REAL,                              -- Trading fees
    exit_reason TEXT,                       -- 'profit_target', 'stop_loss', 'time_exit', etc.
    hold_duration REAL,                     -- Duration in seconds
    closed_at TEXT,                         -- Exit timestamp
    stop_loss REAL,                         -- Stop loss price
    take_profit REAL,                       -- Take profit price
    trading_mode TEXT DEFAULT 'paper',      -- 'paper' or 'live'

    -- Scalping-specific data (stored as JSON)
    signal_data TEXT,                       -- JSON: {confidence, conditions, indicators, ...}
    position_data TEXT,                     -- JSON: {size_info, volume_ratio, ...}

    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Performance snapshots (same structure as ADX)
CREATE TABLE IF NOT EXISTS scalping_performance_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    balance REAL NOT NULL,
    equity REAL NOT NULL,
    total_pnl REAL NOT NULL,
    total_return_percent REAL NOT NULL,
    peak_balance REAL NOT NULL,
    max_drawdown REAL NOT NULL,
    total_trades INTEGER NOT NULL,
    win_rate REAL NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_scalping_trades_timestamp ON scalping_trades(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_scalping_trades_mode ON scalping_trades(trading_mode);
CREATE INDEX IF NOT EXISTS idx_scalping_trades_side ON scalping_trades(side);
CREATE INDEX IF NOT EXISTS idx_scalping_performance_timestamp ON scalping_performance_snapshots(timestamp DESC);
```

### 3.2 Signal Data JSON Structure

The `signal_data` field will store scalping-specific metrics:

```json
{
  "strategy": "scalping_v2",
  "confidence": 0.75,
  "conditions": ["trend_momentum", "oversold_bounce"],
  "risk_reward": 2.5,
  "indicators": {
    "ema_5": 49850.25,
    "ema_8": 49845.12,
    "ema_21": 49820.50,
    "rsi": 35.5,
    "stoch_k": 25.3,
    "stoch_d": 22.1,
    "volume_ratio": 1.5,
    "atr": 125.50,
    "atr_pct": 0.0025
  },
  "market_conditions": {
    "near_support": true,
    "near_resistance": false,
    "bullish_pattern": true,
    "bearish_pattern": false,
    "price_change_pct": 0.15
  }
}
```

### 3.3 Database Initialization Script

**File:** `/var/www/dev/trading/scalping_v2/init_database.py`

```python
#!/usr/bin/env python3
"""Initialize ScalpingV2 database with required tables."""

import sqlite3
import os
from pathlib import Path

DB_PATH = Path(__file__).parent / 'data' / 'trades.db'

def init_database():
    """Create database and tables if they don't exist."""

    # Ensure data directory exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create trades table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scalping_trades (
            id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            side TEXT NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL,
            quantity REAL NOT NULL,
            pnl REAL,
            pnl_percent REAL,
            fees REAL,
            exit_reason TEXT,
            hold_duration REAL,
            closed_at TEXT,
            stop_loss REAL,
            take_profit REAL,
            trading_mode TEXT DEFAULT 'paper',
            signal_data TEXT,
            position_data TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create performance snapshots table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scalping_performance_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            balance REAL NOT NULL,
            equity REAL NOT NULL,
            total_pnl REAL NOT NULL,
            total_return_percent REAL NOT NULL,
            peak_balance REAL NOT NULL,
            max_drawdown REAL NOT NULL,
            total_trades INTEGER NOT NULL,
            win_rate REAL NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_scalping_trades_timestamp
        ON scalping_trades(timestamp DESC)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_scalping_trades_mode
        ON scalping_trades(trading_mode)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_scalping_trades_side
        ON scalping_trades(side)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_scalping_performance_timestamp
        ON scalping_performance_snapshots(timestamp DESC)
    """)

    conn.commit()
    conn.close()

    print(f"✅ Database initialized: {DB_PATH}")
    print(f"   - scalping_trades table created")
    print(f"   - scalping_performance_snapshots table created")
    print(f"   - Indexes created")

if __name__ == "__main__":
    init_database()
```

---

## PART 4: CONFIGURATION

### 4.1 ScalpingV2 Configuration File

**File:** `/var/www/dev/trading/scalping_v2/config_live.json`

```json
{
  "strategy_name": "Bitcoin Scalping v2.0",
  "strategy_type": "scalping",

  "initial_capital": 100.0,
  "leverage": 5,

  "risk_per_trade": 2.0,
  "daily_loss_limit": 5.0,
  "max_drawdown": 15.0,
  "max_positions": 2,
  "max_concurrent_trades": 1,
  "consecutive_loss_limit": 3,
  "max_daily_trades": 50,

  "symbol": "BTC-USDT",
  "timeframe": "5m",
  "signal_check_interval": 300,

  "ema_fast": 8,
  "ema_slow": 21,
  "ema_micro": 5,
  "rsi_period": 14,
  "rsi_oversold": 35,
  "rsi_overbought": 65,
  "stoch_period": 14,
  "stoch_smooth": 3,
  "volume_ma_period": 20,
  "atr_period": 14,

  "target_profit_pct": 0.003,
  "max_loss_pct": 0.0015,
  "max_position_time": 300,

  "min_volume_ratio": 1.2,
  "min_confidence": 0.6,
  "order_book_imbalance": 0.6,

  "enable_short_bias": true,
  "short_bias_multiplier": 1.5,

  "sl_atr_multiplier": 2.0,
  "tp_atr_multiplier": 4.0,

  "trading_mode": "paper",
  "enable_email_alerts": false,
  "enable_console_dashboard": true,

  "database": {
    "type": "sqlite",
    "path": "data/trades.db",
    "trades_table": "scalping_trades",
    "performance_table": "scalping_performance_snapshots"
  },

  "logging": {
    "level": "INFO",
    "file": "logs/live_trading.log",
    "max_size_mb": 10,
    "backup_count": 5
  }
}
```

### 4.2 Key Configuration Differences from ADX

| Parameter | ADX v2 | ScalpingV2 | Reason |
|-----------|--------|------------|--------|
| **strategy_type** | "adx" | "scalping" | Identifies strategy |
| **initial_capital** | $160 | $100 | Fresh start |
| **max_positions** | 2 | 2 | Same |
| **max_daily_trades** | ~10 | 50 | Scalping needs more |
| **timeframe** | 5m | 5m | Same for now |
| **signal_check_interval** | 300s | 300s | Same (can reduce later to 60s) |
| **target_profit_pct** | 4% (TP/entry) | 0.3% | Much tighter |
| **max_loss_pct** | 2% (SL/entry) | 0.15% | Much tighter |
| **max_position_time** | N/A | 300s (5min) | Time-based exit |
| **database.trades_table** | "trades" | "scalping_trades" | Separate tables |

---

## PART 5: COMPONENT IMPLEMENTATION

### 5.1 Scalping Indicator Engine

**File:** `/var/www/dev/trading/scalping_v2/src/indicators/scalping_engine.py`

This will be adapted from the provided `bitcoin_scalping.py` code with key modifications:

**Key Features:**
1. EMA analysis (5, 8, 21 periods)
2. RSI momentum (14 period)
3. Stochastic oscillator (14, 3, 3)
4. Volume analysis (20-period SMA)
5. ATR for volatility
6. Candlestick pattern detection

**Modifications needed:**
- Integrate with BingX API data format
- Return signals compatible with paper trader
- Add proper error handling
- Use configuration from config_live.json

**Method signature:**
```python
def analyze_microstructure(df: pd.DataFrame, config: Dict) -> Dict:
    """
    Analyze market for scalping opportunities.

    Args:
        df: DataFrame with OHLCV data from BingX
        config: Configuration dictionary

    Returns:
        {
            'timestamp': str,
            'price': float,
            'indicators': {...},
            'signals': {
                'long': {...},  # or None
                'short': {...}  # or None
            }
        }
    """
```

### 5.2 Signal Generator

**File:** `/var/www/dev/trading/scalping_v2/src/signals/scalping_signal_generator.py`

Wrapper around scalping engine that:
1. Fetches market data from BingX API
2. Calls scalping engine analysis
3. Filters signals based on risk rules
4. Formats signals for execution layer

**Key methods:**
```python
class ScalpingSignalGenerator:
    def __init__(self, api, config):
        self.api = api
        self.config = config
        self.engine = BitcoinScalpingEngine(config)

    def generate_signals(self) -> Dict:
        """Check for trading opportunities."""
        # Fetch data
        df = self.api.get_kline_data(...)

        # Analyze
        analysis = self.engine.analyze_microstructure(df)

        # Filter and return
        return self._filter_signals(analysis)
```

### 5.3 Modified Main Bot

**File:** `/var/www/dev/trading/scalping_v2/live_trader.py`

Copy from ADX version and modify:

**Key changes:**
```python
# OLD (ADX):
from src.indicators.adx_engine import ADXEngine
from src.signals.signal_generator import ADXSignalGenerator

# NEW (Scalping):
from src.indicators.scalping_engine import BitcoinScalpingEngine
from src.signals.scalping_signal_generator import ScalpingSignalGenerator

# Initialize with scalping components
self.signal_generator = ScalpingSignalGenerator(
    api=self.api,
    config=self.config
)
```

**Main loop remains same:**
1. Fetch current price
2. Update positions
3. Check for signals (every 5 minutes)
4. Execute signals via paper trader
5. Monitor and log

### 5.4 Modified Dashboard

**File:** `/var/www/dev/trading/scalping_v2/dashboard_web.py`

Copy from ADX version and modify:

**Key changes:**
```python
# Change port
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5902, debug=False)  # Was 5901

# Update API endpoints to read from scalping tables
@app.route('/api/trades')
def get_trades():
    mode = request.args.get('mode', 'paper')
    limit = int(request.args.get('limit', 10))

    # Read from scalping_trades table
    db = TradeDatabase(table_prefix='scalping_')
    trades = db.get_recent_trades(limit, mode)
    return jsonify(trades)

# Update indicator display
@app.route('/api/indicators')
def get_indicators():
    # Read from final_snapshot.json
    snapshot = load_snapshot()

    # Return scalping indicators (EMA, RSI, Stochastic)
    return jsonify({
        'ema_5': snapshot.get('ema_5'),
        'ema_8': snapshot.get('ema_8'),
        'ema_21': snapshot.get('ema_21'),
        'rsi': snapshot.get('rsi'),
        'stoch_k': snapshot.get('stoch_k'),
        'volume_ratio': snapshot.get('volume_ratio')
    })
```

**Template changes:** (`templates/dashboard.html`)
- Replace "ADX Strategy v2.0" → "Scalping Strategy v2.0"
- Replace ADX indicators → Scalping indicators (EMA, RSI, Stochastic)
- Update charts and visualizations

---

## PART 6: SYSTEMD SERVICES

### 6.1 Trading Bot Service

**File:** `/etc/systemd/system/scalping-trading-bot.service`

```ini
[Unit]
Description=Scalping Strategy v2.0 Trading Bot
After=network.target mysql.service
Wants=network-online.target

[Service]
Type=simple
User=root
Group=webdev
WorkingDirectory=/var/www/dev/trading/scalping_v2
ExecStart=/bin/bash /var/www/dev/trading/scalping_v2/start_bot.sh

# Restart policy
Restart=always
RestartSec=10
StartLimitInterval=5min
StartLimitBurst=5

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=scalping-trading-bot

# Security
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

### 6.2 Dashboard Service

**File:** `/etc/systemd/system/scalping-dashboard.service`

```ini
[Unit]
Description=Scalping Strategy v2.0 - Web Dashboard
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/var/www/dev/trading/scalping_v2
ExecStart=/var/www/dev/trading/scalping_v2/venv/bin/python3 /var/www/dev/trading/scalping_v2/dashboard_web.py

# Restart policy
Restart=always
RestartSec=10

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=scalping-dashboard

# Environment
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
```

### 6.3 Startup Script

**File:** `/var/www/dev/trading/scalping_v2/start_bot.sh`

```bash
#!/bin/bash
# ScalpingV2 Trading Bot Startup Script

set -e

# Navigate to project directory
cd /var/www/dev/trading/scalping_v2

# Activate virtual environment
source venv/bin/activate

# Export environment variables
export PYTHONUNBUFFERED=1

# Start the bot in paper mode
exec python3 live_trader.py \
    --mode paper \
    --config config_live.json \
    --skip-confirmation
```

Make executable:
```bash
chmod +x /var/www/dev/trading/scalping_v2/start_bot.sh
```

---

## PART 7: IMPLEMENTATION TIMELINE

### Phase 1: Directory Setup (30 minutes)

```bash
# 1. Create directory structure
mkdir -p /var/www/dev/trading/scalping_v2/{src/{api,execution,indicators,signals,risk,monitoring,persistence},logs,data,config,systemd,templates,static}

# 2. Create symlinks to shared code
cd /var/www/dev/trading/scalping_v2/src
ln -s ../../adx_strategy_v2/src/api api
ln -s ../../adx_strategy_v2/src/execution execution
ln -s ../../adx_strategy_v2/src/risk risk
ln -s ../../adx_strategy_v2/src/monitoring monitoring
ln -s ../../adx_strategy_v2/src/persistence persistence

cd /var/www/dev/trading/scalping_v2
ln -s ../adx_strategy_v2/static static
ln -s ../adx_strategy_v2/config/.env config/.env

# 3. Setup virtual environment
python3 -m venv venv
source venv/bin/activate
cp ../adx_strategy_v2/requirements.txt .
pip install -r requirements.txt

# 4. Copy template files
cp ../adx_strategy_v2/templates/dashboard.html templates/
cp ../adx_strategy_v2/requirements.txt .
```

### Phase 2: Database Setup (15 minutes)

```bash
# 1. Create database initialization script
# (see init_database.py above)

# 2. Run initialization
python3 init_database.py

# 3. Verify tables created
sqlite3 data/trades.db "SELECT name FROM sqlite_master WHERE type='table';"
```

### Phase 3: Configuration (15 minutes)

```bash
# 1. Create config_live.json
# (see configuration section above)

# 2. Verify configuration loads
python3 -c "import json; print(json.load(open('config_live.json')))"
```

### Phase 4: Code Implementation (3-4 hours)

1. **Create scalping_engine.py** (90 minutes)
   - Adapt from bitcoin_scalping.py
   - Integrate with BingX data format
   - Add configuration loading
   - Test indicator calculations

2. **Create scalping_signal_generator.py** (45 minutes)
   - Wrapper around scalping engine
   - Signal filtering logic
   - Format for paper trader

3. **Modify live_trader.py** (45 minutes)
   - Copy from ADX version
   - Replace ADX imports with scalping
   - Update database table names
   - Test initialization

4. **Modify dashboard_web.py** (45 minutes)
   - Copy from ADX version
   - Change port to 5902
   - Update indicator endpoints
   - Update template references

5. **Modify dashboard.html** (30 minutes)
   - Update title and branding
   - Replace ADX indicators with scalping indicators
   - Update charts

### Phase 5: Systemd Setup (30 minutes)

```bash
# 1. Create service files
sudo nano /etc/systemd/system/scalping-trading-bot.service
sudo nano /etc/systemd/system/scalping-dashboard.service

# 2. Create startup script
nano start_bot.sh
chmod +x start_bot.sh

# 3. Reload systemd
sudo systemctl daemon-reload

# 4. Enable services (don't start yet)
sudo systemctl enable scalping-trading-bot
sudo systemctl enable scalping-dashboard
```

### Phase 6: Testing (1-2 hours)

```bash
# 1. Test bot startup manually
cd /var/www/dev/trading/scalping_v2
source venv/bin/activate
python3 live_trader.py --mode paper --config config_live.json

# 2. Verify:
# - Database connection works
# - BingX API fetches data
# - Indicators calculate correctly
# - Signals generate
# - Paper trader simulates trades
# - Logs write to logs/live_trading.log

# 3. Test dashboard manually
python3 dashboard_web.py
# Visit http://localhost:5902 to verify

# 4. Stop manual processes
# Ctrl+C

# 5. Start via systemd
sudo systemctl start scalping-trading-bot
sudo systemctl start scalping-dashboard

# 6. Verify services running
systemctl status scalping-trading-bot
systemctl status scalping-dashboard

# 7. Monitor logs
journalctl -u scalping-trading-bot -f

# 8. Check database for trades
sqlite3 data/trades.db "SELECT * FROM scalping_trades LIMIT 5;"
```

### Phase 7: Nginx Configuration (30 minutes)

Add reverse proxy for port 5902 → 5903 external access:

```bash
sudo nano /etc/nginx/sites-available/trading-dashboard
```

Add location block:
```nginx
# Scalping Strategy Dashboard (port 5903)
location /scalping/ {
    proxy_pass http://localhost:5902/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection 'upgrade';
    proxy_set_header Host $host;
    proxy_cache_bypass $http_upgrade;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Reload nginx:
```bash
sudo nginx -t
sudo systemctl reload nginx
```

Access at: `https://dev.ueipab.edu.ve:5900/scalping/`

---

## PART 8: MONITORING & VALIDATION

### 8.1 Service Health Checks

```bash
# Check both services running
systemctl status scalping-trading-bot scalping-dashboard

# Monitor logs in real-time
journalctl -u scalping-trading-bot -u scalping-dashboard -f

# Check listening ports
netstat -tlnp | grep 5902

# Check process IDs
ps aux | grep scalping
```

### 8.2 Database Verification

```bash
# Connect to database
sqlite3 /var/www/dev/trading/scalping_v2/data/trades.db

# Check tables exist
.tables

# View recent trades
SELECT id, timestamp, side, entry_price, pnl, exit_reason
FROM scalping_trades
ORDER BY timestamp DESC
LIMIT 5;

# Check performance snapshots
SELECT timestamp, balance, total_pnl, win_rate
FROM scalping_performance_snapshots
ORDER BY timestamp DESC
LIMIT 5;
```

### 8.3 Dashboard Access

**Internal:** http://localhost:5902
**External:** https://dev.ueipab.edu.ve:5900/scalping/

Verify displays:
- Current balance
- Open positions (should be 0-2)
- Scalping indicators (EMA, RSI, Stochastic)
- Recent trade history
- Performance metrics

### 8.4 Expected Behavior

**First 24 Hours:**
- Signal checks every 5 minutes
- 0-10 trade signals generated
- 0-5 trades executed (paper simulated)
- No real API orders placed
- Database grows with trade records
- Dashboard updates in real-time

**Key Metrics to Monitor:**
- Win rate (target: >60%)
- Average profit (target: >0.2% after fees)
- Average loss (target: <0.2%)
- Trades per day (target: 5-15 initially)
- Max drawdown (target: <5%)

---

## PART 9: MAINTENANCE & OPERATIONS

### 9.1 Daily Operations

```bash
# Morning check
sudo systemctl status scalping-trading-bot scalping-dashboard
tail -n 50 /var/www/dev/trading/scalping_v2/logs/live_trading.log

# Review dashboard
# Visit https://dev.ueipab.edu.ve:5900/scalping/

# Check database stats
sqlite3 /var/www/dev/trading/scalping_v2/data/trades.db \
  "SELECT COUNT(*), AVG(pnl), SUM(pnl) FROM scalping_trades WHERE DATE(timestamp) = DATE('now');"
```

### 9.2 Restarting Services

```bash
# Restart bot only
sudo systemctl restart scalping-trading-bot

# Restart dashboard only
sudo systemctl restart scalping-dashboard

# Restart both
sudo systemctl restart scalping-trading-bot scalping-dashboard

# View logs after restart
journalctl -u scalping-trading-bot --since "5 minutes ago"
```

### 9.3 Stopping Services

```bash
# Stop bot
sudo systemctl stop scalping-trading-bot

# Stop dashboard
sudo systemctl stop scalping-dashboard

# Disable auto-start on boot
sudo systemctl disable scalping-trading-bot scalping-dashboard
```

### 9.4 Log Management

```bash
# Rotate logs manually
cd /var/www/dev/trading/scalping_v2/logs
mv live_trading.log live_trading.log.$(date +%Y%m%d)
touch live_trading.log

# View systemd journal logs (last 100 lines)
journalctl -u scalping-trading-bot -n 100

# Clear old journal logs (keep last 7 days)
sudo journalctl --vacuum-time=7d
```

### 9.5 Database Backup

```bash
# Backup database daily
cp /var/www/dev/trading/scalping_v2/data/trades.db \
   /var/www/dev/trading/scalping_v2/data/trades.db.backup.$(date +%Y%m%d)

# Keep last 30 days of backups
find /var/www/dev/trading/scalping_v2/data/ -name "trades.db.backup.*" -mtime +30 -delete
```

---

## PART 10: TROUBLESHOOTING

### 10.1 Service Won't Start

**Check logs:**
```bash
journalctl -u scalping-trading-bot -n 50 --no-pager
```

**Common issues:**
1. **Port already in use:** Another service using 5902
   ```bash
   netstat -tlnp | grep 5902
   # Kill conflicting process or change port
   ```

2. **Python module not found:** Virtual environment not activated
   ```bash
   source /var/www/dev/trading/scalping_v2/venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Database locked:** Another process accessing database
   ```bash
   fuser /var/www/dev/trading/scalping_v2/data/trades.db
   # Kill process or wait for it to finish
   ```

4. **Config file not found:** Wrong path in service file
   ```bash
   ls -la /var/www/dev/trading/scalping_v2/config_live.json
   ```

### 10.2 No Trades Executing

**Check:**
1. **Signals generating?**
   ```bash
   tail -f logs/live_trading.log | grep "Signal detected"
   ```

2. **Risk limits reached?**
   ```bash
   tail -f logs/live_trading.log | grep "Risk check"
   ```

3. **Market data fetching?**
   ```bash
   tail -f logs/live_trading.log | grep "Fetching"
   ```

4. **Confidence too low?**
   ```json
   // In config_live.json, try lowering:
   "min_confidence": 0.5  // was 0.6
   ```

### 10.3 Dashboard Not Loading

**Check dashboard service:**
```bash
systemctl status scalping-dashboard
curl http://localhost:5902/health
```

**Check nginx proxy:**
```bash
sudo nginx -t
curl https://dev.ueipab.edu.ve:5900/scalping/
```

**Check firewall:**
```bash
sudo ufw status
sudo ufw allow 5902/tcp
```

### 10.4 High CPU Usage

**Check Python process:**
```bash
top -p $(pgrep -f scalping)
```

**Likely causes:**
1. Infinite loop in indicator calculation
2. Too frequent signal checks (reduce check_interval)
3. Memory leak in indicator engine

**Solution:**
```bash
# Restart service
sudo systemctl restart scalping-trading-bot

# If persists, increase check interval
# In config_live.json:
"signal_check_interval": 600  // 10 minutes instead of 5
```

---

## PART 11: PERFORMANCE EXPECTATIONS

### 11.1 Paper Trading Validation Criteria

**Before considering live deployment, require:**

| Metric | Minimum Target | Ideal Target | Current (to track) |
|--------|---------------|--------------|-------------------|
| **Total Trades** | 100+ | 200+ | ___ |
| **Win Rate** | 60% | 70%+ | ___% |
| **Profit Factor** | 1.5 | 2.0+ | ___ |
| **Max Drawdown** | <10% | <5% | ___% |
| **Daily Return** | >0.5% | >1.5% | ___% |
| **Avg Win** | >$0.30 | >$0.50 | $___ |
| **Avg Loss** | <$0.20 | <$0.15 | $___ |
| **Trades/Day** | 5-10 | 10-20 | ___ |
| **Trading Days** | 30+ | 60+ | ___ |

### 11.2 Red Flags (Stop Trading If)

- Win rate drops below 50% for 3+ consecutive days
- Daily loss exceeds 5%
- Max drawdown exceeds 15%
- Consecutive losses reach 5
- Average loss > average win
- Profit factor < 1.0

### 11.3 Expected Timeline

**Week 1-2:** Learning phase
- 20-50 trades
- Win rate: 50-60%
- Small profits/losses
- Tune confidence threshold

**Week 3-4:** Stabilization
- 50-100 trades total
- Win rate: 60-65%
- Consistent small gains
- Validate risk management

**Month 2-3:** Validation
- 200+ trades total
- Win rate: 65-70%
- Steady profitability
- Ready for small live capital ($50-100)

---

## PART 12: SUCCESS CRITERIA & NEXT STEPS

### 12.1 Implementation Success Checklist

**Phase 1: Setup Complete**
- [ ] Directory structure created
- [ ] Symlinks to shared code working
- [ ] Virtual environment setup
- [ ] Dependencies installed
- [ ] Database initialized
- [ ] Configuration file created

**Phase 2: Code Complete**
- [ ] scalping_engine.py implemented
- [ ] scalping_signal_generator.py implemented
- [ ] live_trader.py modified and working
- [ ] dashboard_web.py modified and working
- [ ] dashboard.html updated for scalping

**Phase 3: Services Running**
- [ ] Systemd service files created
- [ ] Services enabled and started
- [ ] Bot running in background
- [ ] Dashboard accessible at :5902
- [ ] Nginx proxy configured
- [ ] External access working

**Phase 4: Validation Complete**
- [ ] Signals generating correctly
- [ ] Trades executing in paper mode
- [ ] Database recording trades
- [ ] Dashboard displaying live data
- [ ] Logs writing correctly
- [ ] No errors in systemd logs

### 12.2 Week 1 Goals

- [ ] 10+ trades executed
- [ ] All trades recorded in database
- [ ] Dashboard shows real-time updates
- [ ] No service crashes or restarts
- [ ] Initial performance metrics calculated

### 12.3 Month 1 Goals

- [ ] 100+ trades executed
- [ ] Win rate >60%
- [ ] Profit factor >1.5
- [ ] Max drawdown <10%
- [ ] Ready for strategy refinement

### 12.4 Next Steps After Implementation

1. **Monitor for 1 week** - Ensure stability
2. **Analyze first 50 trades** - Review performance
3. **Tune parameters** - Adjust confidence, targets if needed
4. **Compare with ADX** - Which performs better?
5. **Document findings** - Keep detailed notes
6. **Scale gradually** - If profitable, increase capital slowly

### 12.5 Future Enhancements (Post-Validation)

- [ ] Reduce timeframe to 1-minute candles
- [ ] Increase signal check frequency to every 60s
- [ ] Add machine learning for confidence scoring
- [ ] Implement order book analysis
- [ ] Add sentiment analysis from Twitter/news
- [ ] Multi-symbol support (ETH, BNB, etc.)
- [ ] Advanced risk management (trailing stops)
- [ ] Automated parameter optimization

---

## PART 13: COMPARISON - ADX vs ScalpingV2

### 13.1 Side-by-Side Comparison

| Aspect | ADX Strategy v2 | Scalping Strategy v2 |
|--------|-----------------|----------------------|
| **Status** | Suspended (losses) | New (paper only) |
| **Indicators** | ADX, +DI, -DI, Slope | EMA, RSI, Stochastic, Volume |
| **Timeframe** | 5 minutes | 5 minutes (can reduce to 1m) |
| **Signals/Day** | 2-5 | 10-50 |
| **Avg Hold Time** | Hours | 5 minutes |
| **Profit Target** | 4% (TP distance) | 0.3% |
| **Stop Loss** | 2% (SL distance) | 0.15% |
| **Risk/Reward** | 2:1 | 2:1 |
| **Max Positions** | 2 | 2 |
| **Complexity** | Medium | High |
| **Transaction Costs** | Lower (fewer trades) | Higher (many trades) |
| **Slippage Risk** | Medium | Higher (tight stops) |

### 13.2 Which Strategy to Focus On?

**ADX Strategy:**
- ✅ Lower transaction costs
- ✅ Less monitoring required
- ❌ Recently failed (-16%)
- ❌ Needs fixes before resuming

**Scalping Strategy:**
- ✅ Fresh start, no bad history
- ✅ More trading opportunities
- ❌ Higher complexity
- ❌ Needs high win rate (70%+)
- ❌ More sensitive to fees/slippage

**Recommendation:**
1. **Implement ScalpingV2** as planned (paper only)
2. **Keep ADX suspended** until ScalpingV2 shows promise
3. **After 2-4 weeks:** Evaluate which to focus on
4. **If both fail:** Re-evaluate strategy approach entirely

---

## PART 14: RISK WARNINGS

### ⚠️ CRITICAL REMINDERS

1. **Paper Trading Only**
   - This implementation is for PAPER TRADING ONLY
   - No real funds at risk
   - BingX API used only for market data
   - All trades are simulated

2. **No Live Trading Yet**
   - Do NOT change `trading_mode` to "live" without:
     - 100+ successful paper trades
     - 70%+ win rate validated
     - 30+ days of consistent results
     - Explicit approval after review

3. **Transaction Costs Are Real**
   - Even if strategy looks profitable
   - Fees (0.12% per round trip) are significant
   - Slippage can double your stop loss
   - 50 trades/day = 6% in daily fees alone

4. **Scalping Is Hard**
   - Requires very high win rate (70%+)
   - Small edges get eaten by costs
   - More trades = more ways to lose
   - Your ADX strategy just failed - be cautious

5. **This Is Experimental**
   - New strategy, untested in production
   - May need significant tuning
   - May not be profitable
   - Treat as research project

---

## PART 15: DOCUMENTATION

### 15.1 README.md

Create `/var/www/dev/trading/scalping_v2/README.md`:

```markdown
# Bitcoin Scalping Strategy v2.0

High-frequency trading strategy for Bitcoin using EMA, RSI, and Stochastic indicators.

## Status
- **Mode:** Paper Trading Only
- **Started:** 2025-11-02
- **Current Balance:** $100 (initial)
- **Total Trades:** 0

## Quick Start

### Start Services
```bash
sudo systemctl start scalping-trading-bot scalping-dashboard
```

### Monitor Logs
```bash
journalctl -u scalping-trading-bot -f
```

### View Dashboard
https://dev.ueipab.edu.ve:5900/scalping/

### Stop Services
```bash
sudo systemctl stop scalping-trading-bot scalping-dashboard
```

## Configuration
- Config: `config_live.json`
- Database: `data/trades.db`
- Logs: `logs/live_trading.log`

## Performance Targets
- Win Rate: >60%
- Profit Factor: >1.5
- Max Drawdown: <10%
- Trades/Day: 10-20

## Warnings
⚠️ Paper trading only - no real funds
⚠️ Experimental - not validated yet
⚠️ High transaction costs (0.12% per trade)
⚠️ Requires 70%+ win rate to be profitable

## Next Steps
1. Monitor for 1 week
2. Analyze first 50 trades
3. Tune parameters if needed
4. Validate performance before any live trading
```

### 15.2 Change Log

Create `/var/www/dev/trading/scalping_v2/CHANGELOG.md`:

```markdown
# Change Log

## [2.0.0] - 2025-11-02
### Added
- Initial implementation of Bitcoin Scalping Strategy
- EMA (5, 8, 21) trend detection
- RSI (14) momentum indicators
- Stochastic oscillator for entry timing
- Volume analysis for confirmation
- Candlestick pattern detection
- Paper trading with BingX market data
- Web dashboard on port 5902
- SQLite database with scalping_trades table
- Systemd service integration
- Automated background execution

### Configuration
- Timeframe: 5 minutes
- Profit target: 0.3%
- Stop loss: 0.15%
- Max position time: 5 minutes
- Initial capital: $100
- Max positions: 2
```

---

## SUMMARY

This implementation plan provides:

✅ **Complete architecture** matching ADX v2 structure
✅ **Separate services** running in parallel
✅ **Shared codebase** via symlinks (BingX API, paper trader, etc.)
✅ **New strategy logic** (scalping indicators)
✅ **Database separation** (scalping_trades vs trades tables)
✅ **Different port** (5902/5903 vs 5901/5900)
✅ **Paper trading only** (no real funds risk)
✅ **Full monitoring** (dashboard, logs, systemd)

**Estimated Time:** 6-8 hours total
**Risk Level:** Low (paper trading)
**Success Criteria:** 100+ trades, 60%+ win rate, <10% drawdown

**Ready to proceed?** Review this plan and confirm to begin implementation.

---

**Questions Before Starting:**

1. Approve directory structure and port allocation?
2. Approve database table naming (scalping_trades)?
3. Approve configuration parameters (0.3% profit, 0.15% stop)?
4. Approve initial capital ($100)?
5. Any modifications needed before implementation?
