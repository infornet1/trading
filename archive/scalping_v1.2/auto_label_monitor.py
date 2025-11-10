#!/usr/bin/env python3
"""
Auto Label Monitor
Runs continuously in the background and labels timeout signals every 5 minutes
"""

import sqlite3
from datetime import datetime, timedelta
import logging
import time
import signal
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('auto_labeler.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class AutoLabeler:
    """Automatic signal labeler that runs in the background"""

    def __init__(self, db_path='signals.db', timeout_hours=1, check_interval=300):
        """
        Initialize auto labeler

        Args:
            db_path: Path to signals database
            timeout_hours: Hours before a signal should timeout
            check_interval: Seconds between checks (default: 300 = 5 minutes)
        """
        self.db_path = db_path
        self.timeout_hours = timeout_hours
        self.check_interval = check_interval
        self.running = True
        self.total_labeled = 0

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)

    def shutdown(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False

    def label_timeout_signals(self):
        """Label all pending signals that have exceeded timeout threshold"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Calculate timeout threshold
            timeout_threshold = datetime.now() - timedelta(hours=self.timeout_hours)
            timeout_threshold_iso = timeout_threshold.isoformat()

            # Get count of signals to update
            cursor.execute('''
                SELECT COUNT(*) FROM signals
                WHERE outcome = "PENDING"
                AND timestamp < ?
            ''', (timeout_threshold_iso,))

            count = cursor.fetchone()[0]

            if count == 0:
                conn.close()
                return 0

            # Update all timed-out signals
            cursor.execute('''
                UPDATE signals
                SET checked_at = ?,
                    outcome = "TIMEOUT",
                    final_result = "TIMEOUT",
                    exit_reason = "Signal timeout (>1 hour expired without hitting target/stop)",
                    strategy_profit = 0
                WHERE outcome = "PENDING"
                AND timestamp < ?
            ''', (datetime.now().isoformat(), timeout_threshold_iso))

            conn.commit()
            conn.close()

            logger.info(f"✅ Labeled {count} signals as TIMEOUT")
            self.total_labeled += count

            return count

        except Exception as e:
            logger.error(f"Error labeling signals: {e}")
            return 0

    def get_stats(self):
        """Get current signal statistics"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            stats = {}

            # Get overall counts
            cursor.execute('''
                SELECT
                    outcome,
                    COUNT(*) as count
                FROM signals
                GROUP BY outcome
            ''')

            for outcome, count in cursor.fetchall():
                outcome_str = outcome if outcome else 'NULL'
                stats[outcome_str] = count

            # Get 24h stats
            cutoff = datetime.now() - timedelta(hours=24)
            cursor.execute('''
                SELECT COUNT(*) FROM signals
                WHERE timestamp >= ?
            ''', (cutoff.isoformat(),))

            stats['last_24h'] = cursor.fetchone()[0]

            conn.close()
            return stats

        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {}

    def run(self):
        """Main monitoring loop"""
        logger.info("=" * 80)
        logger.info("🤖 AUTO LABEL MONITOR STARTED")
        logger.info("=" * 80)
        logger.info(f"⚙️  Configuration:")
        logger.info(f"   Database: {self.db_path}")
        logger.info(f"   Timeout threshold: {self.timeout_hours} hours")
        logger.info(f"   Check interval: {self.check_interval} seconds ({self.check_interval/60:.1f} minutes)")
        logger.info("=" * 80)
        logger.info("")

        iteration = 0

        while self.running:
            try:
                iteration += 1
                logger.info(f"🔄 Check #{iteration} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

                # Label timeout signals
                labeled = self.label_timeout_signals()

                # Get and display stats
                stats = self.get_stats()

                if labeled > 0:
                    logger.info(f"📊 Current statistics:")
                    logger.info(f"   PENDING: {stats.get('PENDING', 0)}")
                    logger.info(f"   WIN: {stats.get('WIN', 0)}")
                    logger.info(f"   LOSS: {stats.get('LOSS', 0)}")
                    logger.info(f"   TIMEOUT: {stats.get('TIMEOUT', 0)}")
                    logger.info(f"   Total labeled this session: {self.total_labeled}")
                else:
                    logger.info("✓ No signals to label")

                # Wait for next check
                logger.info(f"⏳ Next check in {self.check_interval} seconds...")
                logger.info("")

                time.sleep(self.check_interval)

            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(60)  # Wait 1 minute before retrying

        logger.info("=" * 80)
        logger.info(f"👋 AUTO LABEL MONITOR STOPPED")
        logger.info(f"📊 Total signals labeled: {self.total_labeled}")
        logger.info("=" * 80)


def main():
    """Main entry point"""
    # Parse command line arguments
    timeout_hours = 1
    check_interval = 300  # 5 minutes

    if len(sys.argv) > 1:
        try:
            check_interval = int(sys.argv[1])
        except ValueError:
            print(f"Usage: python3 {sys.argv[0]} [check_interval_seconds]")
            sys.exit(1)

    labeler = AutoLabeler(
        timeout_hours=timeout_hours,
        check_interval=check_interval
    )

    labeler.run()


if __name__ == '__main__':
    main()
