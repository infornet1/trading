#!/usr/bin/env python3
"""
Update database schema with labeling columns for hybrid strategy tracking
"""

import sqlite3
import sys
from datetime import datetime

def backup_database(db_path='signals.db'):
    """Create backup before schema changes"""
    import shutil
    backup_name = f"signals_backup_schema_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    shutil.copy2(db_path, backup_name)
    print(f"✅ Created backup: {backup_name}")
    return backup_name

def add_labeling_columns(db_path='signals.db'):
    """Add new columns for strategy labeling and tracking"""

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # List of columns to add
    new_columns = [
        ("strategy_name", "TEXT DEFAULT 'SCALPING'"),
        ("strategy_version", "TEXT DEFAULT 'v1.2'"),
        ("timeframe", "TEXT DEFAULT '5s'"),
        ("signal_quality", "TEXT"),
        ("trade_group_id", "TEXT"),
        ("entry_reason", "TEXT"),
        ("exit_reason", "TEXT"),
        ("strategy_profit", "REAL"),
        ("tags", "TEXT"),  # JSON array of tags
        ("market_condition", "TEXT"),  # BULLISH/BEARISH/RANGING
        ("session_id", "TEXT")
    ]

    print("Adding labeling columns to signals table...")
    print("-" * 60)

    added = 0
    skipped = 0

    for col_name, col_type in new_columns:
        try:
            cursor.execute(f"ALTER TABLE signals ADD COLUMN {col_name} {col_type}")
            print(f"✅ Added: {col_name} ({col_type})")
            added += 1
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print(f"⏭️  Skipped: {col_name} (already exists)")
                skipped += 1
            else:
                print(f"❌ Error adding {col_name}: {e}")
                raise

    conn.commit()
    conn.close()

    print("-" * 60)
    print(f"✅ Schema update complete!")
    print(f"   Added: {added} columns")
    print(f"   Skipped: {skipped} columns (already existed)")

    return added, skipped

def verify_schema(db_path='signals.db'):
    """Verify all columns are present"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute('PRAGMA table_info(signals)')
    columns = cursor.fetchall()

    print("\n📋 Current signals table schema:")
    print("-" * 60)

    for col in columns:
        col_id, col_name, col_type, not_null, default_val, pk = col
        default_str = f" DEFAULT {default_val}" if default_val else ""
        print(f"  {col_id:2d}. {col_name:20s} {col_type:15s}{default_str}")

    conn.close()

    print("-" * 60)
    print(f"Total columns: {len(columns)}")

    # Check for labeling columns
    labeling_cols = [
        'strategy_name', 'strategy_version', 'timeframe', 'signal_quality',
        'trade_group_id', 'entry_reason', 'exit_reason', 'strategy_profit',
        'tags', 'market_condition', 'session_id'
    ]

    existing_cols = [col[1] for col in columns]
    missing = [col for col in labeling_cols if col not in existing_cols]

    if missing:
        print(f"\n⚠️  Missing labeling columns: {', '.join(missing)}")
        return False
    else:
        print(f"\n✅ All labeling columns present!")
        return True

if __name__ == "__main__":
    print("=" * 60)
    print("DATABASE SCHEMA UPDATE - LABELING SYSTEM")
    print("=" * 60)
    print()

    # Step 1: Backup
    backup_file = backup_database()

    print()

    # Step 2: Add columns
    try:
        added, skipped = add_labeling_columns()
    except Exception as e:
        print(f"\n❌ Schema update failed: {e}")
        print(f"💾 Database backup available at: {backup_file}")
        sys.exit(1)

    print()

    # Step 3: Verify
    success = verify_schema()

    print()
    print("=" * 60)
    if success:
        print("✅ SCHEMA UPDATE SUCCESSFUL!")
        print("   Hybrid strategy labeling system is ready to use")
    else:
        print("⚠️  SCHEMA UPDATE INCOMPLETE")
        print("   Some columns may be missing")
    print("=" * 60)
