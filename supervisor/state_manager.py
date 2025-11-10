#!/usr/bin/env python3
"""
State Manager - Cleans up stuck states, old logs, etc.
"""

import sys
import os
import sqlite3
import shutil
from datetime import datetime, timedelta
from pathlib import Path


def cleanup_bot_state(bot_key):
    """Clean up bot state"""

    TRADING_ROOT = Path("/var/www/dev/trading")

    bots_config = {
        'scalping_v2': {
            'path': TRADING_ROOT / 'scalping_v2',
            'db': TRADING_ROOT / 'scalping_v2' / 'data' / 'trades.db',
            'logs': TRADING_ROOT / 'scalping_v2' / 'logs'
        },
        'adx_v2': {
            'path': TRADING_ROOT / 'adx_strategy_v2',
            'db': TRADING_ROOT / 'adx_strategy_v2' / 'data' / 'trades.db',
            'logs': TRADING_ROOT / 'adx_strategy_v2' / 'logs'
        }
    }

    if bot_key not in bots_config:
        print(f"Unknown bot: {bot_key}")
        return 1

    bot = bots_config[bot_key]
    print(f"Cleaning up state for {bot_key}...")

    try:
        # 1. Archive old log files (>7 days)
        if bot['logs'].exists():
            print("  Archiving old logs...")
            archive_dir = bot['logs'] / 'archive'
            archive_dir.mkdir(exist_ok=True)

            cutoff_date = datetime.now() - timedelta(days=7)

            for log_file in bot['logs'].glob('*.log'):
                if log_file.stat().st_mtime < cutoff_date.timestamp():
                    archive_name = f"{log_file.stem}_{datetime.fromtimestamp(log_file.stat().st_mtime).strftime('%Y%m%d')}{log_file.suffix}"
                    shutil.move(str(log_file), str(archive_dir / archive_name))
                    print(f"    Archived: {log_file.name}")

        # 2. Close any stuck database connections (vacuum)
        if bot['db'].exists():
            print("  Optimizing database...")
            try:
                conn = sqlite3.connect(str(bot['db']))
                conn.execute("VACUUM")
                conn.close()
                print("    Database optimized")
            except Exception as e:
                print(f"    Database optimization failed: {e}")

        # 3. Clear any temporary files
        temp_patterns = ['*.tmp', '*.lock', '*.pid']
        for pattern in temp_patterns:
            for temp_file in bot['path'].glob(pattern):
                temp_file.unlink()
                print(f"    Removed: {temp_file.name}")

        # 4. Reset error flags (if any exist in config)
        # This would depend on your specific implementation

        print(f"✅ Cleanup complete for {bot_key}")
        return 0

    except Exception as e:
        print(f"❌ Cleanup failed: {e}")
        return 1


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: state_manager.py <bot_key> [--cleanup]")
        sys.exit(1)

    bot_key = sys.argv[1]
    sys.exit(cleanup_bot_state(bot_key))
