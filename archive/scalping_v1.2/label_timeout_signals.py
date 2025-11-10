#!/usr/bin/env python3
"""
Label Timeout Signals Script
Marks all PENDING signals older than the timeout threshold as TIMEOUT
This is a simplified version that doesn't require historical price data
"""

import sqlite3
from datetime import datetime, timedelta
import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def label_timeout_signals(db_path='signals.db', timeout_hours=1, dry_run=False):
    """
    Label all PENDING signals older than timeout_hours as TIMEOUT

    Args:
        db_path: Path to SQLite database
        timeout_hours: Hours after which a signal should timeout
        dry_run: If True, don't actually update the database

    Returns:
        Dictionary with statistics
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Calculate timeout threshold
    timeout_threshold = datetime.now() - timedelta(hours=timeout_hours)
    timeout_threshold_iso = timeout_threshold.isoformat()

    # Get all pending signals older than threshold
    cursor.execute('''
        SELECT id, timestamp, signal_type, direction, entry_price, suggested_stop, suggested_target
        FROM signals
        WHERE outcome = "PENDING"
        AND timestamp < ?
        ORDER BY timestamp ASC
    ''', (timeout_threshold_iso,))

    pending_signals = cursor.fetchall()
    total_found = len(pending_signals)

    logger.info(f"Found {total_found} PENDING signals older than {timeout_hours} hour(s)")

    if total_found == 0:
        conn.close()
        return {'updated': 0, 'errors': 0}

    stats = {
        'updated': 0,
        'errors': 0
    }

    if dry_run:
        logger.info("DRY RUN - No changes will be made to the database")
        conn.close()
        return {'updated': 0, 'errors': 0, 'dry_run': total_found}

    # Update all pending signals to TIMEOUT
    for signal in pending_signals:
        signal_id, timestamp, sig_type, direction, entry, stop, target = signal

        try:
            signal_time = datetime.fromisoformat(timestamp)
            age_hours = (datetime.now() - signal_time).total_seconds() / 3600

            cursor.execute('''
                UPDATE signals
                SET checked_at = ?,
                    outcome = "TIMEOUT",
                    final_result = "TIMEOUT",
                    exit_reason = "Signal timeout (>1 hour expired without hitting target/stop)",
                    strategy_profit = 0
                WHERE id = ?
            ''', (datetime.now().isoformat(), signal_id))

            stats['updated'] += 1

            if stats['updated'] % 50 == 0:
                logger.info(f"Progress: {stats['updated']}/{total_found} signals updated")

        except Exception as e:
            logger.error(f"Error updating signal {signal_id}: {e}")
            stats['errors'] += 1
            continue

    conn.commit()
    conn.close()

    return stats


def main():
    """Main execution function"""
    print("=" * 80)
    print("⏱️  TIMEOUT SIGNAL LABELING SCRIPT")
    print("=" * 80)
    print()

    # Parse command line arguments
    timeout_hours = 1
    dry_run = False

    if len(sys.argv) > 1:
        if sys.argv[1] == '--dry-run':
            dry_run = True
            print("🔍 DRY RUN MODE - No changes will be made")
            print()
        else:
            try:
                timeout_hours = float(sys.argv[1])
                print(f"⚙️  Using custom timeout: {timeout_hours} hours")
                print()
            except ValueError:
                print(f"⚠️  Invalid argument. Usage: python3 {sys.argv[0]} [timeout_hours] or --dry-run")
                sys.exit(1)

    # Show current status
    conn = sqlite3.connect('signals.db')
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) FROM signals WHERE outcome = "PENDING"')
    total_pending = cursor.fetchone()[0]

    timeout_threshold = datetime.now() - timedelta(hours=timeout_hours)
    cursor.execute('''
        SELECT COUNT(*) FROM signals
        WHERE outcome = "PENDING"
        AND timestamp < ?
    ''', (timeout_threshold.isoformat(),))
    old_pending = cursor.fetchone()[0]

    conn.close()

    print(f"📊 Current Status:")
    print(f"   Total PENDING signals: {total_pending}")
    print(f"   PENDING older than {timeout_hours}h: {old_pending}")
    print()

    if old_pending == 0:
        print("✅ No signals to update!")
        return

    if not dry_run:
        print(f"⚠️  About to mark {old_pending} signals as TIMEOUT")
        print()

    # Process signals
    stats = label_timeout_signals(
        timeout_hours=timeout_hours,
        dry_run=dry_run
    )

    # Print summary
    print()
    print("=" * 80)
    print("📊 LABELING COMPLETE")
    print("=" * 80)

    if dry_run:
        print(f"🔍 DRY RUN: Would have updated {stats.get('dry_run', 0)} signals")
    else:
        print(f"✅ Updated: {stats['updated']} signals")
        print(f"⚠️  Errors: {stats['errors']}")

        if stats['updated'] > 0:
            # Verify the update
            conn = sqlite3.connect('signals.db')
            cursor = conn.cursor()

            cursor.execute('SELECT COUNT(*) FROM signals WHERE outcome = "PENDING"')
            remaining_pending = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM signals WHERE outcome = "TIMEOUT"')
            total_timeout = cursor.fetchone()[0]

            conn.close()

            print()
            print(f"📈 Updated Statistics:")
            print(f"   Remaining PENDING: {remaining_pending}")
            print(f"   Total TIMEOUT: {total_timeout}")

    print("=" * 80)


if __name__ == '__main__':
    main()
