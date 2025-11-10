#!/usr/bin/env python3
"""
Label Pending Signals Script
Processes all PENDING signals and updates their outcomes based on historical price data
"""

import sqlite3
import requests
from datetime import datetime, timedelta
import time
import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SignalLabeler:
    """Labels pending signals by fetching historical price data"""

    def __init__(self, db_path='signals.db', binance_api_base='https://api.binance.com'):
        self.db_path = db_path
        self.binance_api_base = binance_api_base
        self.rate_limit_delay = 0.2  # Delay between API calls to avoid rate limiting

    def get_historical_prices(self, start_time: datetime, end_time: datetime, interval='1m'):
        """
        Fetch historical kline data from Binance

        Args:
            start_time: Start datetime
            end_time: End datetime
            interval: Kline interval (1m, 5m, 15m, 1h, etc.)

        Returns:
            List of klines with high and low prices
        """
        try:
            start_ms = int(start_time.timestamp() * 1000)
            end_ms = int(end_time.timestamp() * 1000)

            url = f"{self.binance_api_base}/api/v3/klines"
            params = {
                'symbol': 'BTCUSDT',
                'interval': interval,
                'startTime': start_ms,
                'endTime': end_ms,
                'limit': 1000
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            klines = response.json()

            # Extract high and low prices
            highs = [float(k[2]) for k in klines]  # High price
            lows = [float(k[3]) for k in klines]   # Low price

            if not highs or not lows:
                return None, None

            return max(highs), min(lows)

        except Exception as e:
            logger.error(f"Error fetching historical prices: {e}")
            return None, None

    def label_signal(self, signal_id: int, timestamp: str, direction: str,
                    entry_price: float, stop: float, target: float) -> dict:
        """
        Label a single signal based on historical price data

        Returns:
            Dictionary with outcome and stats
        """
        try:
            signal_time = datetime.fromisoformat(timestamp)

            # Calculate time window (up to 1 hour after signal)
            end_time = signal_time + timedelta(hours=1)
            now = datetime.now()

            # If signal is recent (< 1 hour old), use current time as end
            if end_time > now:
                end_time = now

            # Fetch historical prices for this period
            price_high, price_low = self.get_historical_prices(signal_time, end_time, interval='1m')

            if price_high is None or price_low is None:
                logger.warning(f"Signal {signal_id}: Could not fetch historical data")
                return None

            # Determine outcome based on direction
            if direction == 'LONG':
                max_gain_pct = ((price_high - entry_price) / entry_price) * 100
                max_loss_pct = ((price_low - entry_price) / entry_price) * 100
                target_hit = price_high >= target
                stop_hit = price_low <= stop
            elif direction == 'SHORT':
                max_gain_pct = ((entry_price - price_low) / entry_price) * 100
                max_loss_pct = ((entry_price - price_high) / entry_price) * 100
                target_hit = price_low <= target
                stop_hit = price_high >= stop
            else:
                return {'outcome': 'NEUTRAL', 'exit_reason': 'Neutral direction'}

            # Determine outcome
            if target_hit and stop_hit:
                # Both hit - conservative assumption: stop hit first
                outcome = 'LOSS'
                exit_reason = 'Stop loss hit (both targets reached, stop assumed first)'
                strategy_profit = -abs(max_loss_pct)
            elif target_hit:
                outcome = 'WIN'
                exit_reason = 'Take profit target reached'
                strategy_profit = max_gain_pct
            elif stop_hit:
                outcome = 'LOSS'
                exit_reason = 'Stop loss triggered'
                strategy_profit = max_loss_pct
            else:
                # Neither target hit within 1 hour
                age_hours = (now - signal_time).total_seconds() / 3600
                if age_hours >= 1.0:
                    outcome = 'TIMEOUT'
                    exit_reason = 'Signal timeout (1 hour expired without hitting target/stop)'
                    strategy_profit = 0
                else:
                    # Still within 1 hour - keep as pending
                    return None

            return {
                'outcome': outcome,
                'actual_high': price_high,
                'actual_low': price_low,
                'target_hit': 1 if target_hit else 0,
                'stop_hit': 1 if stop_hit else 0,
                'max_gain_pct': max_gain_pct,
                'max_loss_pct': max_loss_pct,
                'final_result': outcome,
                'exit_reason': exit_reason,
                'strategy_profit': strategy_profit
            }

        except Exception as e:
            logger.error(f"Error labeling signal {signal_id}: {e}")
            return None

    def update_signal_outcome(self, signal_id: int, outcome_data: dict):
        """Update signal in database with outcome data"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE signals
                SET checked_at = ?,
                    outcome = ?,
                    actual_high = ?,
                    actual_low = ?,
                    target_hit = ?,
                    stop_hit = ?,
                    max_gain_pct = ?,
                    max_loss_pct = ?,
                    final_result = ?,
                    exit_reason = ?,
                    strategy_profit = ?
                WHERE id = ?
            ''', (
                datetime.now().isoformat(),
                outcome_data['outcome'],
                outcome_data['actual_high'],
                outcome_data['actual_low'],
                outcome_data['target_hit'],
                outcome_data['stop_hit'],
                outcome_data['max_gain_pct'],
                outcome_data['max_loss_pct'],
                outcome_data['final_result'],
                outcome_data['exit_reason'],
                outcome_data['strategy_profit'],
                signal_id
            ))

            conn.commit()
            conn.close()

            return True

        except Exception as e:
            logger.error(f"Error updating signal {signal_id}: {e}")
            return False

    def process_pending_signals(self, batch_size=50, max_signals=None, min_age_minutes=60):
        """
        Process all pending signals in batches

        Args:
            batch_size: Number of signals to process in each batch
            max_signals: Maximum number of signals to process (None = all)
            min_age_minutes: Minimum age in minutes for signals to process (default: 60)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get all pending signals older than min_age_minutes
        min_age_timestamp = (datetime.now() - timedelta(minutes=min_age_minutes)).isoformat()

        cursor.execute('''
            SELECT id, timestamp, direction, entry_price, suggested_stop, suggested_target
            FROM signals
            WHERE outcome = "PENDING"
            AND timestamp < ?
            ORDER BY timestamp ASC
        ''', (min_age_timestamp,))

        pending_signals = cursor.fetchall()
        total_pending = len(pending_signals)

        if max_signals:
            pending_signals = pending_signals[:max_signals]

        conn.close()

        logger.info(f"Found {total_pending} pending signals older than {min_age_minutes} minutes")
        logger.info(f"Processing {len(pending_signals)} signals in batches of {batch_size}")

        stats = {
            'processed': 0,
            'wins': 0,
            'losses': 0,
            'timeouts': 0,
            'errors': 0,
            'skipped': 0
        }

        for i, signal in enumerate(pending_signals, 1):
            signal_id, timestamp, direction, entry, stop, target = signal

            try:
                # Label the signal
                outcome_data = self.label_signal(signal_id, timestamp, direction, entry, stop, target)

                if outcome_data is None:
                    stats['skipped'] += 1
                    continue

                # Update database
                if self.update_signal_outcome(signal_id, outcome_data):
                    stats['processed'] += 1

                    if outcome_data['outcome'] == 'WIN':
                        stats['wins'] += 1
                        logger.info(f"✅ Signal {signal_id}: WIN (Target: ${target:.2f})")
                    elif outcome_data['outcome'] == 'LOSS':
                        stats['losses'] += 1
                        logger.info(f"❌ Signal {signal_id}: LOSS (Stop: ${stop:.2f})")
                    elif outcome_data['outcome'] == 'TIMEOUT':
                        stats['timeouts'] += 1
                        logger.info(f"⏱️  Signal {signal_id}: TIMEOUT")
                else:
                    stats['errors'] += 1

                # Progress update
                if i % 10 == 0:
                    logger.info(f"Progress: {i}/{len(pending_signals)} signals processed")

                # Rate limiting
                time.sleep(self.rate_limit_delay)

                # Batch pause
                if i % batch_size == 0:
                    logger.info(f"Batch complete. Pausing for 2 seconds...")
                    time.sleep(2)

            except Exception as e:
                logger.error(f"Error processing signal {signal_id}: {e}")
                stats['errors'] += 1
                continue

        return stats


def main():
    """Main execution function"""
    print("=" * 80)
    print("📊 SIGNAL LABELING SCRIPT")
    print("=" * 80)
    print()

    labeler = SignalLabeler()

    # Check for command line arguments
    batch_size = 50
    max_signals = None
    min_age_minutes = 60

    if len(sys.argv) > 1:
        try:
            max_signals = int(sys.argv[1])
            print(f"⚙️  Processing maximum {max_signals} signals")
        except ValueError:
            print(f"⚠️  Invalid argument. Usage: python3 {sys.argv[0]} [max_signals]")
            sys.exit(1)

    print(f"⚙️  Configuration:")
    print(f"   - Batch size: {batch_size}")
    print(f"   - Max signals: {max_signals if max_signals else 'ALL'}")
    print(f"   - Min age: {min_age_minutes} minutes")
    print()

    # Process signals
    start_time = time.time()
    stats = labeler.process_pending_signals(
        batch_size=batch_size,
        max_signals=max_signals,
        min_age_minutes=min_age_minutes
    )
    elapsed_time = time.time() - start_time

    # Print summary
    print()
    print("=" * 80)
    print("📊 LABELING COMPLETE")
    print("=" * 80)
    print(f"✅ Processed: {stats['processed']} signals")
    print(f"🏆 Wins: {stats['wins']}")
    print(f"❌ Losses: {stats['losses']}")
    print(f"⏱️  Timeouts: {stats['timeouts']}")
    print(f"⚠️  Errors: {stats['errors']}")
    print(f"⏭️  Skipped: {stats['skipped']}")
    print()

    if stats['processed'] > 0:
        win_rate = (stats['wins'] / stats['processed']) * 100
        print(f"📈 Win Rate: {win_rate:.1f}%")

    print(f"⏱️  Time elapsed: {elapsed_time:.1f} seconds")
    print("=" * 80)


if __name__ == '__main__':
    main()
