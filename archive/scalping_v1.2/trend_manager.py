#!/usr/bin/env python3
"""
Trend Reversal Detection & Position Management System
Monitors trend changes and manages position reversals
"""

import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Tuple, Optional, Dict, List
from collections import deque

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TrendManager:
    """Manages trend detection and position reversal logic"""

    def __init__(self, db_path='signals.db', config=None):
        self.db_path = db_path
        self.config = config or {}

        # Current state
        self.current_trend = 'UNKNOWN'
        self.position_mode = 'BOTH'  # LONG_ONLY, SHORT_ONLY, or BOTH
        self.last_trend_change = None

        # EMA tracking for crossover detection
        self.ema_history = deque(maxlen=10)  # Keep last 10 EMA values

        # Consecutive failure tracking
        self.consecutive_failures = {'LONG': 0, 'SHORT': 0}

        # Alert thresholds from config
        reversal_config = self.config.get('trend_reversal', {})
        self.win_rate_window = reversal_config.get('win_rate_monitor', {}).get('window_size', 20)
        self.bullish_threshold = reversal_config.get('win_rate_monitor', {}).get('bullish_threshold', 60)
        self.bearish_threshold = reversal_config.get('win_rate_monitor', {}).get('bearish_threshold', 40)
        self.failure_threshold = reversal_config.get('failure_detection', {}).get('consecutive_count', 5)

        logger.info("TrendManager initialized")

    def update_ema_history(self, ema_50: float, ema_200: float, price: float):
        """Store EMA values for crossover detection"""
        self.ema_history.append({
            'timestamp': datetime.now(),
            'ema_50': ema_50,
            'ema_200': ema_200,
            'price': price
        })

    def check_ema_crossover(self, ema_50: float, ema_200: float) -> Tuple[Optional[str], Optional[str]]:
        """
        Detect EMA crossover events (Golden Cross / Death Cross)

        Returns:
            (crossover_type, new_trend) or (None, None)
        """
        if len(self.ema_history) < 2:
            return None, None

        # Get previous values
        prev = self.ema_history[-2]
        prev_ema_50 = prev['ema_50']
        prev_ema_200 = prev['ema_200']

        # Golden Cross: EMA50 crosses above EMA200 (BULLISH)
        if prev_ema_50 <= prev_ema_200 and ema_50 > ema_200:
            logger.info(f"🌟 GOLDEN CROSS DETECTED! EMA50 ({ema_50:.2f}) > EMA200 ({ema_200:.2f})")
            return 'GOLDEN_CROSS', 'BULLISH'

        # Death Cross: EMA50 crosses below EMA200 (BEARISH)
        elif prev_ema_50 >= prev_ema_200 and ema_50 < ema_200:
            logger.info(f"☠️  DEATH CROSS DETECTED! EMA50 ({ema_50:.2f}) < EMA200 ({ema_200:.2f})")
            return 'DEATH_CROSS', 'BEARISH'

        return None, None

    def get_win_rate(self, direction: str, window: int = 20) -> float:
        """Calculate win rate for a direction in recent trades"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN final_result = 'WIN' THEN 1 ELSE 0 END) as wins
            FROM (
                SELECT final_result
                FROM signals
                WHERE direction = ?
                AND final_result IN ('WIN', 'LOSS')
                ORDER BY checked_at DESC
                LIMIT ?
            )
        """, (direction, window))

        result = cursor.fetchone()
        conn.close()

        if result and result[0] > 0:
            total, wins = result
            wins = wins or 0
            return (wins / total) * 100

        return 0.0

    def check_win_rate_reversal(self) -> Optional[str]:
        """
        Check if win rates indicate trend reversal

        Returns:
            'BULLISH_REVERSAL', 'BEARISH_REVERSAL', or None
        """
        long_wr = self.get_win_rate('LONG', self.win_rate_window)
        short_wr = self.get_win_rate('SHORT', self.win_rate_window)

        # Need at least some data
        if long_wr == 0 and short_wr == 0:
            return None

        # Bullish reversal: LONG winning, SHORT losing
        if long_wr >= self.bullish_threshold and short_wr <= self.bearish_threshold:
            logger.info(f"📈 Win rate suggests BULLISH: LONG {long_wr:.0f}% vs SHORT {short_wr:.0f}%")
            return 'BULLISH_REVERSAL'

        # Bearish reversal: SHORT winning, LONG losing
        elif short_wr >= self.bullish_threshold and long_wr <= self.bearish_threshold:
            logger.info(f"📉 Win rate suggests BEARISH: SHORT {short_wr:.0f}% vs LONG {long_wr:.0f}%")
            return 'BEARISH_REVERSAL'

        return None

    def count_recent_losses(self, direction: str, last_n: int = 5) -> int:
        """Count consecutive losses in last N trades for a direction"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT final_result
            FROM signals
            WHERE direction = ?
            AND final_result IN ('WIN', 'LOSS')
            ORDER BY checked_at DESC
            LIMIT ?
        """, (direction, last_n))

        results = cursor.fetchall()
        conn.close()

        # Count consecutive losses from most recent
        consecutive = 0
        for (result,) in results:
            if result == 'LOSS':
                consecutive += 1
            else:
                break

        return consecutive

    def check_consecutive_failures(self) -> Optional[str]:
        """
        Detect consecutive failures as early warning

        Returns:
            'LONG_FAILURE_WARNING', 'SHORT_FAILURE_WARNING', or None
        """
        long_losses = self.count_recent_losses('LONG', self.failure_threshold)
        short_losses = self.count_recent_losses('SHORT', self.failure_threshold)

        if long_losses >= self.failure_threshold:
            logger.warning(f"⚠️  LONG FAILURE WARNING: {long_losses} consecutive losses")
            return 'LONG_FAILURE_WARNING'

        if short_losses >= self.failure_threshold:
            logger.warning(f"⚠️  SHORT FAILURE WARNING: {short_losses} consecutive losses")
            return 'SHORT_FAILURE_WARNING'

        return None

    def should_close_positions(self, trend_signal: str) -> Tuple[bool, Optional[str]]:
        """
        Decide if we should close all positions based on trend signal

        Args:
            trend_signal: 'GOLDEN_CROSS', 'DEATH_CROSS', etc.

        Returns:
            (should_close, direction_to_close)
        """
        # Golden Cross or Bullish reversal: close SHORT positions
        if trend_signal in ['GOLDEN_CROSS', 'BULLISH_REVERSAL']:
            if self.position_mode in ['SHORT_ONLY', 'BOTH']:
                return True, 'SHORT'

        # Death Cross or Bearish reversal: close LONG positions
        elif trend_signal in ['DEATH_CROSS', 'BEARISH_REVERSAL']:
            if self.position_mode in ['LONG_ONLY', 'BOTH']:
                return True, 'LONG'

        return False, None

    def update_position_mode(self, new_trend: str):
        """
        Update position mode based on detected trend

        Args:
            new_trend: 'BULLISH', 'BEARISH', or 'NEUTRAL'
        """
        old_mode = self.position_mode

        if new_trend == 'BULLISH':
            self.position_mode = 'LONG_ONLY'
        elif new_trend == 'BEARISH':
            self.position_mode = 'SHORT_ONLY'
        elif new_trend == 'NEUTRAL':
            self.position_mode = 'BOTH'

        if old_mode != self.position_mode:
            self.last_trend_change = datetime.now()
            logger.info(f"🔄 Position mode changed: {old_mode} → {self.position_mode}")
            self.log_mode_change(old_mode, self.position_mode, new_trend)

    def log_mode_change(self, old_mode: str, new_mode: str, new_trend: str):
        """Log trend change to database for tracking"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create trend_changes table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trend_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                old_mode TEXT,
                new_mode TEXT,
                new_trend TEXT,
                ema_50 REAL,
                ema_200 REAL
            )
        """)

        # Get current EMA values if available
        ema_50 = None
        ema_200 = None
        if len(self.ema_history) > 0:
            latest = self.ema_history[-1]
            ema_50 = latest['ema_50']
            ema_200 = latest['ema_200']

        cursor.execute("""
            INSERT INTO trend_changes
            (timestamp, old_mode, new_mode, new_trend, ema_50, ema_200)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (datetime.now().isoformat(), old_mode, new_mode, new_trend, ema_50, ema_200))

        conn.commit()
        conn.close()

    def get_current_status(self) -> Dict:
        """Get current trend manager status for monitoring"""
        long_wr = self.get_win_rate('LONG', self.win_rate_window)
        short_wr = self.get_win_rate('SHORT', self.win_rate_window)

        status = {
            'current_trend': self.current_trend,
            'position_mode': self.position_mode,
            'last_trend_change': self.last_trend_change.isoformat() if self.last_trend_change else None,
            'win_rates': {
                'LONG': long_wr,
                'SHORT': short_wr
            },
            'consecutive_failures': self.consecutive_failures,
            'ema_status': None
        }

        if len(self.ema_history) > 0:
            latest = self.ema_history[-1]
            status['ema_status'] = {
                'ema_50': latest['ema_50'],
                'ema_200': latest['ema_200'],
                'price': latest['price'],
                'spread': latest['ema_50'] - latest['ema_200']
            }

        return status

    def should_take_signal(self, signal_type: str, direction: str) -> Tuple[bool, str]:
        """
        Decide if we should take a signal based on current position mode

        Args:
            signal_type: Signal type (e.g., 'RSI_OVERSOLD')
            direction: 'LONG' or 'SHORT'

        Returns:
            (should_take, reason)
        """
        if self.position_mode == 'LONG_ONLY' and direction == 'SHORT':
            return False, f"Skipped {direction} signal - Position mode is {self.position_mode}"

        elif self.position_mode == 'SHORT_ONLY' and direction == 'LONG':
            return False, f"Skipped {direction} signal - Position mode is {self.position_mode}"

        return True, f"{direction} signal allowed in {self.position_mode} mode"


if __name__ == "__main__":
    # Test the trend manager
    manager = TrendManager()

    print("Testing TrendManager...")

    # Simulate EMA updates
    manager.update_ema_history(110000, 111000, 110500)  # Death Cross zone
    manager.update_ema_history(110500, 110800, 111000)  # Moving toward crossover
    manager.update_ema_history(111100, 111000, 111500)  # Golden Cross!

    crossover, trend = manager.check_ema_crossover(111100, 111000)
    if crossover:
        print(f"✅ Detected: {crossover} → Trend: {trend}")

    # Check status
    status = manager.get_current_status()
    print(f"\nCurrent Status:")
    print(f"  Position Mode: {status['position_mode']}")
    print(f"  WIN Rates: LONG {status['win_rates']['LONG']:.1f}%, SHORT {status['win_rates']['SHORT']:.1f}%")
