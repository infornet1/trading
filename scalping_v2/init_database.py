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
