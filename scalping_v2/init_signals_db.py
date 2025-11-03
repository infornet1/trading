#!/usr/bin/env python3
"""
Initialize Signals Tracking Database for Scalping Bot v2.0
Creates database table to track all detected signals (executed and rejected)
"""

import sqlite3
import os
from datetime import datetime

def init_signals_database(db_path='data/trades.db'):
    """
    Create signals tracking table in database

    Tracks all signals detected, including:
    - Executed trades
    - Rejected signals (position sizing, risk limits, etc.)
    - Signal confidence and conditions
    """

    # Ensure directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create signals table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS scalping_signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        side TEXT NOT NULL,
        confidence REAL NOT NULL,
        entry_price REAL NOT NULL,
        stop_loss REAL NOT NULL,
        take_profit REAL NOT NULL,
        position_size_usd REAL,
        margin_required REAL,
        risk_amount REAL,
        risk_percent REAL,
        conditions TEXT,
        executed BOOLEAN NOT NULL DEFAULT 0,
        execution_status TEXT,
        rejection_reason TEXT,
        trade_id INTEGER,
        indicators_json TEXT,
        FOREIGN KEY (trade_id) REFERENCES scalping_trades(id)
    )
    ''')

    # Create index for faster queries
    cursor.execute('''
    CREATE INDEX IF NOT EXISTS idx_signals_timestamp
    ON scalping_signals(timestamp DESC)
    ''')

    cursor.execute('''
    CREATE INDEX IF NOT EXISTS idx_signals_executed
    ON scalping_signals(executed)
    ''')

    cursor.execute('''
    CREATE INDEX IF NOT EXISTS idx_signals_confidence
    ON scalping_signals(confidence DESC)
    ''')

    conn.commit()
    conn.close()

    print(f"✅ Signals tracking database initialized: {db_path}")
    print("   Table: scalping_signals")
    print("   Indexes: timestamp, executed, confidence")


if __name__ == '__main__':
    # Run initialization
    db_path = 'data/trades.db'
    print("="*60)
    print("Signal Tracking Database Initialization")
    print("="*60)
    print(f"Database: {db_path}")
    print()

    init_signals_database(db_path)

    # Verify table creation
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scalping_signals'")
    result = cursor.fetchone()

    if result:
        print()
        print("✅ Verification successful!")
        print(f"   Table 'scalping_signals' exists")

        # Get column info
        cursor.execute("PRAGMA table_info(scalping_signals)")
        columns = cursor.fetchall()
        print(f"   Columns: {len(columns)}")
        for col in columns:
            print(f"      - {col[1]} ({col[2]})")
    else:
        print()
        print("❌ Verification failed!")
        print("   Table 'scalping_signals' not found")

    conn.close()

    print()
    print("="*60)
    print("Initialization complete!")
    print("="*60)
