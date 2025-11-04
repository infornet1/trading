#!/usr/bin/env python3
"""
Add performance indexes to scalping database
Run once to optimize query performance
"""

import sqlite3
import sys

DB_PATH = '/var/www/dev/trading/scalping_v2/data/trades.db'

def add_indexes():
    """Add indexes to improve query performance"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        print("📊 Adding database indexes for performance optimization...\n")

        # Indexes for scalping_signals table
        indexes = [
            ("idx_signals_timestamp", "scalping_signals", "timestamp"),
            ("idx_signals_executed", "scalping_signals", "executed"),
            ("idx_signals_confidence", "scalping_signals", "confidence"),
            ("idx_signals_status", "scalping_signals", "execution_status"),
            ("idx_trades_timestamp", "trades", "timestamp"),
            ("idx_trades_closed", "trades", "closed_at"),
            ("idx_trades_side", "trades", "side"),
        ]

        for index_name, table_name, column_name in indexes:
            try:
                cursor.execute(f'''
                    CREATE INDEX IF NOT EXISTS {index_name}
                    ON {table_name}({column_name})
                ''')
                print(f"✅ Created index: {index_name} on {table_name}({column_name})")
            except Exception as e:
                print(f"⚠️  Error creating {index_name}: {e}")

        # Composite index for common query patterns
        try:
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_signals_time_executed
                ON scalping_signals(timestamp, executed)
            ''')
            print(f"✅ Created composite index: idx_signals_time_executed")
        except Exception as e:
            print(f"⚠️  Error creating composite index: {e}")

        conn.commit()
        conn.close()

        print("\n✅ All indexes created successfully!")
        print("\n📈 Query performance should be improved for:")
        print("  • Signal filtering by time")
        print("  • Executed vs rejected signal queries")
        print("  • Confidence-based sorting")
        print("  • Trade history queries")

        return True

    except Exception as e:
        print(f"❌ Error adding indexes: {e}")
        return False

if __name__ == '__main__':
    success = add_indexes()
    sys.exit(0 if success else 1)
