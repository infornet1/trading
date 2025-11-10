-- ADX Trading Strategy v2.0 - Database Schema
-- Created: 2025-10-15
-- Database: bitcoin_trading

USE bitcoin_trading;

-- Table 1: ADX Signals
CREATE TABLE IF NOT EXISTS adx_signals (
    id INT AUTO_INCREMENT PRIMARY KEY,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    symbol VARCHAR(20) NOT NULL DEFAULT 'BTC-USDT',
    timeframe VARCHAR(10) DEFAULT '5m',

    -- Price data
    open_price DECIMAL(20,8) NOT NULL,
    high_price DECIMAL(20,8) NOT NULL,
    low_price DECIMAL(20,8) NOT NULL,
    close_price DECIMAL(20,8) NOT NULL,
    volume DECIMAL(20,8),

    -- ADX indicators (6 core indicators)
    adx_value DECIMAL(10,4) NOT NULL,
    plus_di DECIMAL(10,4) NOT NULL,
    minus_di DECIMAL(10,4) NOT NULL,
    adx_slope DECIMAL(10,4) DEFAULT 0,
    di_spread DECIMAL(10,4) COMMENT 'Difference between +DI and -DI',
    trend_strength ENUM('NONE', 'WEAK', 'EMERGING', 'STRONG', 'VERY_STRONG', 'EXTREME') DEFAULT 'NONE',

    -- Signal data
    signal_type ENUM('BUY', 'SELL', 'HOLD', 'EXIT') NOT NULL,
    entry_condition VARCHAR(255) COMMENT 'Description of entry logic triggered',
    confidence DECIMAL(5,4) DEFAULT 0.5000 COMMENT 'Signal confidence score 0-1',

    -- Risk management
    stop_loss_price DECIMAL(20,8),
    take_profit_price DECIMAL(20,8),
    risk_reward_ratio DECIMAL(5,2),
    position_size DECIMAL(20,8) COMMENT 'Recommended position size in BTC',

    -- Outcome tracking
    outcome ENUM('PENDING', 'WIN', 'LOSS', 'TIMEOUT', 'CANCELLED') DEFAULT 'PENDING',
    entry_price DECIMAL(20,8),
    exit_price DECIMAL(20,8),
    exit_timestamp DATETIME,
    pnl_percent DECIMAL(10,4),
    pnl_amount DECIMAL(20,8),

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_timestamp (timestamp),
    INDEX idx_signal_type (signal_type),
    INDEX idx_outcome (outcome),
    INDEX idx_adx_value (adx_value),
    INDEX idx_symbol_time (symbol, timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table 2: ADX Trades
CREATE TABLE IF NOT EXISTS adx_trades (
    id INT AUTO_INCREMENT PRIMARY KEY,
    signal_id INT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    symbol VARCHAR(20) NOT NULL DEFAULT 'BTC-USDT',

    -- Order details
    side ENUM('LONG', 'SHORT') NOT NULL,
    order_type ENUM('MARKET', 'LIMIT', 'STOP_MARKET', 'STOP_LIMIT') DEFAULT 'MARKET',
    quantity DECIMAL(20,8) NOT NULL COMMENT 'Position size in BTC',
    entry_price DECIMAL(20,8) NOT NULL,
    leverage INT DEFAULT 5 CHECK (leverage BETWEEN 1 AND 20),

    -- Risk management
    stop_loss DECIMAL(20,8) NOT NULL,
    take_profit DECIMAL(20,8) NOT NULL,
    risk_reward_ratio DECIMAL(5,2),
    risk_amount DECIMAL(20,8) COMMENT 'Dollar amount at risk',

    -- Execution details
    order_id VARCHAR(100) UNIQUE COMMENT 'Exchange order ID',
    status ENUM('PENDING', 'OPEN', 'FILLED', 'PARTIAL', 'CANCELLED', 'ERROR', 'CLOSED') DEFAULT 'PENDING',
    filled_quantity DECIMAL(20,8) DEFAULT 0,
    avg_fill_price DECIMAL(20,8),
    commission DECIMAL(20,8) DEFAULT 0,

    -- Results
    exit_timestamp DATETIME,
    exit_price DECIMAL(20,8),
    exit_reason ENUM('TAKE_PROFIT', 'STOP_LOSS', 'MANUAL', 'TIMEOUT', 'SIGNAL_EXIT', 'ERROR') COMMENT 'Why trade was closed',
    realized_pnl DECIMAL(20,8),
    realized_pnl_percent DECIMAL(10,4),

    -- Duration tracking
    hold_duration_minutes INT COMMENT 'Minutes position was held',

    -- Metadata
    notes TEXT COMMENT 'Trade notes or error messages',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (signal_id) REFERENCES adx_signals(id) ON DELETE SET NULL,
    INDEX idx_status (status),
    INDEX idx_timestamp (timestamp),
    INDEX idx_symbol (symbol),
    INDEX idx_side (side),
    INDEX idx_pnl (realized_pnl)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table 3: Strategy Parameters
CREATE TABLE IF NOT EXISTS adx_strategy_params (
    id INT AUTO_INCREMENT PRIMARY KEY,
    parameter_name VARCHAR(50) UNIQUE NOT NULL,
    parameter_value VARCHAR(200) NOT NULL,
    data_type ENUM('INT', 'FLOAT', 'STRING', 'BOOL', 'JSON') DEFAULT 'STRING',
    category ENUM('ADX', 'RISK', 'EXECUTION', 'FILTERS', 'SYSTEM') DEFAULT 'SYSTEM',
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_category (category),
    INDEX idx_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table 4: Performance Metrics
CREATE TABLE IF NOT EXISTS adx_performance (
    id INT AUTO_INCREMENT PRIMARY KEY,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    period VARCHAR(20) NOT NULL COMMENT '1h, 4h, 24h, 7d, 30d',

    -- Trade statistics
    total_trades INT DEFAULT 0,
    winning_trades INT DEFAULT 0,
    losing_trades INT DEFAULT 0,
    timeout_trades INT DEFAULT 0,
    win_rate DECIMAL(5,4) DEFAULT 0,

    -- Financial metrics
    total_pnl DECIMAL(20,8) DEFAULT 0,
    total_pnl_percent DECIMAL(10,4) DEFAULT 0,
    avg_win DECIMAL(20,8) DEFAULT 0,
    avg_loss DECIMAL(20,8) DEFAULT 0,
    largest_win DECIMAL(20,8) DEFAULT 0,
    largest_loss DECIMAL(20,8) DEFAULT 0,
    profit_factor DECIMAL(10,4) DEFAULT 0 COMMENT 'Gross profit / Gross loss',

    -- Risk metrics
    max_drawdown DECIMAL(10,4) DEFAULT 0,
    max_drawdown_duration_hours INT DEFAULT 0,
    sharpe_ratio DECIMAL(10,4) DEFAULT 0,

    -- Signal metrics
    total_signals INT DEFAULT 0,
    buy_signals INT DEFAULT 0,
    sell_signals INT DEFAULT 0,
    avg_adx DECIMAL(10,4) DEFAULT 0,
    avg_confidence DECIMAL(5,4) DEFAULT 0,

    -- Execution metrics
    avg_hold_duration_minutes INT DEFAULT 0,
    avg_slippage_percent DECIMAL(10,6) DEFAULT 0,

    -- Capital tracking
    starting_balance DECIMAL(20,8),
    ending_balance DECIMAL(20,8),
    peak_balance DECIMAL(20,8),

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_period (period),
    INDEX idx_timestamp (timestamp),
    UNIQUE KEY unique_period_timestamp (period, timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table 5: System Logs (for monitoring)
CREATE TABLE IF NOT EXISTS adx_system_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    log_level ENUM('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL') DEFAULT 'INFO',
    component VARCHAR(50) COMMENT 'Which module generated the log',
    message TEXT NOT NULL,
    details JSON COMMENT 'Additional structured data',

    INDEX idx_timestamp (timestamp),
    INDEX idx_level (log_level),
    INDEX idx_component (component)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Insert default strategy parameters
INSERT INTO adx_strategy_params (parameter_name, parameter_value, data_type, category, description) VALUES
-- ADX Parameters
('adx_period', '14', 'INT', 'ADX', 'ADX calculation period'),
('adx_threshold_strong', '25', 'FLOAT', 'ADX', 'Minimum ADX for strong trend'),
('adx_threshold_very_strong', '35', 'FLOAT', 'ADX', 'Minimum ADX for very strong trend'),
('adx_threshold_weak', '20', 'FLOAT', 'ADX', 'Below this is weak/no trend'),
('di_crossover_confirmation', '2', 'INT', 'ADX', 'Candles to confirm DI crossover'),
('adx_slope_min', '0.5', 'FLOAT', 'ADX', 'Minimum ADX slope for entry'),

-- Risk Management
('risk_per_trade_percent', '2', 'FLOAT', 'RISK', 'Percent of capital to risk per trade'),
('max_concurrent_positions', '2', 'INT', 'RISK', 'Maximum open positions'),
('daily_loss_limit_percent', '5', 'FLOAT', 'RISK', 'Daily loss limit percentage'),
('max_drawdown_percent', '15', 'FLOAT', 'RISK', 'Maximum allowed drawdown'),
('leverage', '5', 'INT', 'RISK', 'Default leverage multiplier'),
('stop_loss_atr_multiplier', '2', 'FLOAT', 'RISK', 'Stop loss distance in ATR'),
('take_profit_atr_multiplier', '4', 'FLOAT', 'RISK', 'Take profit distance in ATR'),
('min_risk_reward_ratio', '2', 'FLOAT', 'RISK', 'Minimum risk:reward ratio'),

-- Execution
('timeframe', '5m', 'STRING', 'EXECUTION', 'Candle timeframe'),
('order_type', 'MARKET', 'STRING', 'EXECUTION', 'Default order type'),
('slippage_tolerance_percent', '0.1', 'FLOAT', 'EXECUTION', 'Maximum acceptable slippage'),
('timeout_minutes', '60', 'INT', 'EXECUTION', 'Signal timeout duration'),

-- Filters
('enable_short_bias', 'true', 'BOOL', 'FILTERS', 'Prioritize SHORT signals (from SCALPING v1.2 learning)'),
('min_signal_confidence', '0.6', 'FLOAT', 'FILTERS', 'Minimum confidence to take trade'),
('enable_time_filter', 'false', 'BOOL', 'FILTERS', 'Filter trades by time of day'),
('min_volume', '100', 'FLOAT', 'FILTERS', 'Minimum volume for valid signal'),

-- System
('paper_trading_mode', 'true', 'BOOL', 'SYSTEM', 'Enable paper trading mode'),
('enable_logging', 'true', 'BOOL', 'SYSTEM', 'Enable database logging'),
('alert_on_signal', 'false', 'BOOL', 'SYSTEM', 'Send alerts on new signals'),
('auto_trade', 'false', 'BOOL', 'SYSTEM', 'Auto-execute trades (DANGEROUS)'),
('initial_capital', '100', 'FLOAT', 'SYSTEM', 'Starting capital in USDT')
ON DUPLICATE KEY UPDATE parameter_value=VALUES(parameter_value);

-- Create view for active signals
CREATE OR REPLACE VIEW v_active_signals AS
SELECT
    s.id,
    s.timestamp,
    s.symbol,
    s.signal_type,
    s.adx_value,
    s.plus_di,
    s.minus_di,
    s.trend_strength,
    s.confidence,
    s.entry_price,
    s.stop_loss_price,
    s.take_profit_price,
    s.outcome,
    t.order_id,
    t.status as trade_status,
    t.realized_pnl
FROM adx_signals s
LEFT JOIN adx_trades t ON s.id = t.signal_id
WHERE s.outcome = 'PENDING'
ORDER BY s.timestamp DESC;

-- Create view for performance summary
CREATE OR REPLACE VIEW v_performance_summary AS
SELECT
    'ALL_TIME' as period,
    COUNT(*) as total_trades,
    SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) as wins,
    SUM(CASE WHEN outcome = 'LOSS' THEN 1 ELSE 0 END) as losses,
    ROUND(SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) * 100.0 /
          NULLIF(COUNT(CASE WHEN outcome IN ('WIN', 'LOSS') THEN 1 END), 0), 2) as win_rate_percent,
    SUM(pnl_amount) as total_pnl,
    AVG(CASE WHEN outcome = 'WIN' THEN pnl_amount END) as avg_win,
    AVG(CASE WHEN outcome = 'LOSS' THEN pnl_amount END) as avg_loss,
    AVG(adx_value) as avg_adx
FROM adx_signals
WHERE outcome IN ('WIN', 'LOSS');

-- Success message
SELECT 'ADX v2.0 Database Schema Created Successfully!' as status;
SELECT COUNT(*) as total_parameters FROM adx_strategy_params;
