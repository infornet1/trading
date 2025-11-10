#!/usr/bin/env python3
"""
Bot Health Monitor - Checks bot health beyond just process running
"""

import sys
import os
import json
import subprocess
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


def check_bot_health(bot_key):
    """Check if bot is healthy"""

    TRADING_ROOT = Path("/var/www/dev/trading")

    bots_config = {
        'scalping_v2': {
            'service': 'scalping-trading-bot',
            'db': TRADING_ROOT / 'scalping_v2' / 'data' / 'trades.db',
            'log': TRADING_ROOT / 'scalping_v2' / 'logs' / 'live_trading.log'
        },
        'adx_v2': {
            'service': 'adx-trading-bot.service',
            'db': TRADING_ROOT / 'adx_strategy_v2' / 'data' / 'trades.db',
            'log': TRADING_ROOT / 'adx_strategy_v2' / 'logs' / 'live_trading.log'
        }
    }

    if bot_key not in bots_config:
        print(json.dumps({'error': f'Unknown bot: {bot_key}'}))
        return 1

    bot = bots_config[bot_key]
    issues = []

    try:
        # 1. Check if service is running
        result = subprocess.run(
            ['systemctl', 'is-active', bot['service']],
            capture_output=True,
            text=True
        )
        running = result.stdout.strip() == 'active'

        if not running:
            issues.append("Service not active")

        # 2. Check if database is being updated (bot is actually working)
        last_update = None
        if bot['db'].exists():
            try:
                conn = sqlite3.connect(str(bot['db']))
                cur = conn.cursor()

                # Check performance snapshots table (updated regularly)
                cur.execute("""
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name='performance_snapshots'
                """)

                if cur.fetchone():
                    cur.execute("SELECT MAX(timestamp) FROM performance_snapshots")
                    last_update_str = cur.fetchone()[0]

                    if last_update_str:
                        last_update = datetime.fromisoformat(last_update_str)

                        # If no update in last 10 minutes, bot might be stuck
                        if datetime.now() - last_update > timedelta(minutes=10):
                            issues.append(f"No database updates in {(datetime.now() - last_update).seconds // 60} minutes")

                conn.close()
            except Exception as e:
                issues.append(f"Database check error: {str(e)}")
        else:
            issues.append("Database file not found")

        # 3. Check for error patterns in recent logs
        if bot['log'].exists():
            try:
                # Read last 100 lines
                result = subprocess.run(
                    ['tail', '-100', str(bot['log'])],
                    capture_output=True,
                    text=True
                )
                log_content = result.stdout.lower()

                # Check for error indicators
                if 'traceback' in log_content or 'exception' in log_content:
                    error_count = log_content.count('error')
                    if error_count > 5:
                        issues.append(f"Multiple errors in recent logs ({error_count})")

            except Exception as e:
                issues.append(f"Log check error: {str(e)}")

        # 4. Check if process is consuming CPU (not frozen)
        if running:
            try:
                # Get service PID
                result = subprocess.run(
                    ['systemctl', 'show', bot['service'], '--property=MainPID'],
                    capture_output=True,
                    text=True
                )
                pid_line = result.stdout.strip()
                pid = pid_line.split('=')[1]

                if pid and pid != '0':
                    # Check if process exists
                    result = subprocess.run(
                        ['ps', '-p', pid],
                        capture_output=True
                    )
                    if result.returncode != 0:
                        issues.append("Process PID not found")
                else:
                    issues.append("No valid PID")

            except Exception as e:
                issues.append(f"Process check error: {str(e)}")

        # Determine health
        healthy = len(issues) == 0

        health_report = {
            'timestamp': datetime.now().isoformat(),
            'bot_key': bot_key,
            'running': running,
            'healthy': healthy,
            'last_update': last_update.isoformat() if last_update else None,
            'issues': issues
        }

        print(json.dumps(health_report))
        return 0

    except Exception as e:
        error_report = {
            'timestamp': datetime.now().isoformat(),
            'bot_key': bot_key,
            'running': False,
            'healthy': False,
            'last_update': None,
            'issues': [f"Health check failed: {str(e)}"]
        }
        print(json.dumps(error_report))
        return 1


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(json.dumps({'error': 'Usage: bot_health_monitor.py <bot_key>'}))
        sys.exit(1)

    bot_key = sys.argv[1]
    sys.exit(check_bot_health(bot_key))
