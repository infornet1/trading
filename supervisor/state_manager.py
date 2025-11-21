#!/usr/bin/env python3
"""
State Manager - Cleans up stuck states, old logs, circuit breakers, etc.
"""

import sys
import os
import sqlite3
import shutil
import json
from datetime import datetime, timedelta
from pathlib import Path


def check_circuit_breaker_status(bot_key):
    """Check if circuit breaker is active and should be reset"""
    import subprocess

    try:
        result = subprocess.run(
            [sys.executable, str(Path("/var/www/dev/trading/supervisor/circuit_breaker_checker.py")), bot_key],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            return {'should_reset': False}
    except Exception as e:
        print(f"Error checking circuit breaker: {e}")
        return {'should_reset': False}


def reset_circuit_breaker_in_db(bot_key, db_path):
    """
    Reset circuit breaker state in database (if stored there)

    Note: For this implementation, circuit breaker state is in-memory in the bots.
    The reset will take effect when the bot restarts OR we need to signal the bot.

    For now, we'll create a flag file that the bot can check on next iteration.
    """
    flag_file = db_path.parent.parent / 'logs' / 'reset_circuit_breaker.flag'

    try:
        with open(flag_file, 'w') as f:
            json.dump({
                'reset_requested': True,
                'timestamp': datetime.now().isoformat(),
                'reason': 'Supervisor auto-reset for paper trading mode'
            }, f, indent=2)
        return True
    except Exception as e:
        print(f"Failed to create reset flag: {e}")
        return False


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

        # 4. Reset circuit breaker (if in paper trading mode)
        try:
            print("  Checking circuit breaker status...")
            circuit_status = check_circuit_breaker_status(bot_key)

            if circuit_status.get('should_reset', False):
                print(f"    Circuit breaker active: {circuit_status.get('circuit_breaker_reason')}")
                print(f"    Trading mode: {circuit_status.get('trading_mode')}")
                print(f"    Attempting reset via database...")

                if reset_circuit_breaker_in_db(bot_key, bot['db']):
                    print(f"    ✅ Circuit breaker reset in database")
                else:
                    print(f"    ⚠️  Circuit breaker reset requires bot restart")
            else:
                if circuit_status.get('circuit_breaker_active'):
                    print(f"    Circuit breaker active but NOT auto-resetting (Live mode)")
                else:
                    print(f"    Circuit breaker inactive - no action needed")

        except Exception as e:
            print(f"    Circuit breaker check failed: {e}")

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
