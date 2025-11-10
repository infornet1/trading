#!/usr/bin/env python3
"""
Signal Tracking and Backtesting System
Logs all signals and tracks their outcomes to calculate win rate and performance
"""

import sqlite3
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging

logger = logging.getLogger('SignalTracker')


class SignalTracker:
    """Track trading signals and their outcomes"""

    def __init__(self, db_path='signals.db'):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Initialize SQLite database with tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Signals table - stores all detected signals
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                signal_type TEXT NOT NULL,
                direction TEXT NOT NULL,
                severity TEXT NOT NULL,
                price REAL NOT NULL,
                rsi REAL,
                ema_fast REAL,
                ema_slow REAL,
                support REAL,
                resistance REAL,
                entry_price REAL NOT NULL,
                suggested_stop REAL NOT NULL,
                suggested_target REAL NOT NULL,
                has_conflict INTEGER DEFAULT 0,
                message TEXT,
                checked_at DATETIME,
                outcome TEXT,
                actual_high REAL,
                actual_low REAL,
                target_hit INTEGER DEFAULT 0,
                stop_hit INTEGER DEFAULT 0,
                max_gain_pct REAL,
                max_loss_pct REAL,
                final_result TEXT,
                notes TEXT
            )
        ''')

        # Performance stats table - aggregated statistics
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS performance_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                calculated_at DATETIME NOT NULL,
                total_signals INTEGER,
                checked_signals INTEGER,
                wins INTEGER,
                losses INTEGER,
                pending INTEGER,
                win_rate REAL,
                avg_gain REAL,
                avg_loss REAL,
                profit_factor REAL,
                best_signal_type TEXT,
                worst_signal_type TEXT,
                conflicting_signals INTEGER,
                json_data TEXT
            )
        ''')

        # Index for faster queries
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_timestamp
            ON signals(timestamp)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_outcome
            ON signals(outcome)
        ''')

        conn.commit()
        conn.close()
        logger.info(f"Database initialized at {self.db_path}")

    def calculate_signal_quality(self, alert: dict, indicators: dict,
                                 has_conflict: bool, strategy_name: str = 'SCALPING') -> str:
        """
        Calculate signal quality based on indicator confluence and conditions

        Args:
            alert: Alert dictionary
            indicators: Technical indicators
            has_conflict: Whether conflicting signals exist
            strategy_name: Strategy being used

        Returns:
            Quality rating: 'PERFECT', 'HIGH', 'MEDIUM', or 'LOW'
        """
        if strategy_name == 'SCALPING':
            score = 0

            # RSI strength scoring
            rsi = indicators.get('rsi', 50)
            if alert['type'] == 'RSI_OVERSOLD':
                if rsi < 25:
                    score += 3  # Very oversold
                elif rsi < 30:
                    score += 2  # Oversold
                else:
                    score += 1  # Mild oversold
            elif alert['type'] == 'RSI_OVERBOUGHT':
                if rsi > 75:
                    score += 3  # Very overbought
                elif rsi > 70:
                    score += 2  # Overbought
                else:
                    score += 1  # Mild overbought

            # Trend alignment (using trend filter data)
            trend = indicators.get('trend', 'UNKNOWN')
            signal_direction = 'LONG' if alert['type'] in ['RSI_OVERSOLD', 'NEAR_SUPPORT', 'EMA_BULLISH_CROSS'] else 'SHORT'

            if (trend == 'BULLISH' and signal_direction == 'LONG') or \
               (trend == 'BEARISH' and signal_direction == 'SHORT'):
                score += 2  # Aligned with trend
            elif trend in ['BULLISH', 'BEARISH']:
                score -= 1  # Against trend

            # EMA crossover signals
            if alert['type'] in ['EMA_BULLISH_CROSS', 'EMA_BEARISH_CROSS']:
                score += 2  # EMA crossovers are strong

            # Support/Resistance proximity
            if alert['type'] in ['NEAR_SUPPORT', 'NEAR_RESISTANCE']:
                score += 2  # Key level bounces are reliable

            # No conflicting signals
            if not has_conflict:
                score += 1
            else:
                score -= 2  # Penalty for conflicts

            # ATR presence (dynamic targets)
            if indicators.get('atr'):
                score += 1  # Dynamic targets better than fixed

            # Classify quality
            if score >= 8:
                return 'PERFECT'
            elif score >= 5:
                return 'HIGH'
            elif score >= 2:
                return 'MEDIUM'
            else:
                return 'LOW'

        elif strategy_name == 'TRADING_LATINO':
            # Placeholder for Trading Latino quality calculation
            score = 0

            # Squeeze momentum strength
            if alert.get('squeeze_momentum'):
                score += 3

            # ADX > 23 (strong trend)
            adx = indicators.get('adx', 0)
            if adx > 30:
                score += 3
            elif adx > 23:
                score += 2
            else:
                score += 1

            # Volume confirmation
            if indicators.get('high_volume'):
                score += 2

            if score >= 7:
                return 'PERFECT'
            elif score >= 5:
                return 'HIGH'
            elif score >= 3:
                return 'MEDIUM'
            else:
                return 'LOW'

        return 'MEDIUM'  # Default

    def log_signal(self, alert: dict, price_data: dict, indicators: dict,
                   has_conflict: bool = False, suggested_stop: float = None,
                   suggested_target: float = None, strategy_name: str = 'SCALPING',
                   strategy_version: str = 'v1.2', timeframe: str = '5s',
                   signal_quality: str = None, trade_group_id: str = None,
                   entry_reason: str = None, tags: list = None,
                   market_condition: str = None, session_id: str = None) -> int:
        """
        Log a trading signal to database

        Args:
            alert: Alert dictionary with type, severity, message
            price_data: Price data dictionary
            indicators: Technical indicators dictionary
            has_conflict: Whether signal has conflicting signals
            suggested_stop: Optional custom stop loss price (ATR-based)
            suggested_target: Optional custom target price (ATR-based)
            strategy_name: Name of strategy ('SCALPING', 'TRADING_LATINO', etc.)
            strategy_version: Version of strategy (e.g., 'v1.2')
            timeframe: Timeframe used (e.g., '5s', '4h')
            signal_quality: Quality rating (HIGH/MEDIUM/LOW/PERFECT)
            trade_group_id: Optional group ID for related signals
            entry_reason: Why this signal was taken
            tags: List of tags for categorization
            market_condition: Market state (BULLISH/BEARISH/RANGING)
            session_id: Trading session identifier

        Returns:
            signal_id: ID of the logged signal
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Determine direction
        direction = 'LONG' if alert['type'] in ['RSI_OVERSOLD', 'NEAR_SUPPORT', 'EMA_BULLISH_CROSS'] else 'SHORT'
        if alert['type'] == 'RAPID_PRICE_CHANGE':
            direction = 'NEUTRAL'

        # Use provided targets or calculate default fixed targets
        entry_price = price_data['price']

        if suggested_stop is None or suggested_target is None:
            # Fall back to fixed targets if not provided
            if direction == 'LONG':
                suggested_stop = entry_price * 0.997  # -0.3%
                suggested_target = entry_price * 1.005  # +0.5%
            elif direction == 'SHORT':
                suggested_stop = entry_price * 1.003  # +0.3%
                suggested_target = entry_price * 0.995  # -0.5%
            else:
                suggested_stop = entry_price
                suggested_target = entry_price

        # Convert tags list to JSON string if provided
        tags_json = json.dumps(tags) if tags else None

        cursor.execute('''
            INSERT INTO signals (
                timestamp, signal_type, direction, severity, price,
                rsi, ema_fast, ema_slow, support, resistance,
                entry_price, suggested_stop, suggested_target,
                has_conflict, message,
                strategy_name, strategy_version, timeframe, signal_quality,
                trade_group_id, entry_reason, tags, market_condition, session_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now().isoformat(),
            alert['type'],
            direction,
            alert['severity'],
            price_data['price'],
            indicators.get('rsi'),
            indicators.get('ema_fast'),
            indicators.get('ema_slow'),
            indicators.get('support'),
            indicators.get('resistance'),
            entry_price,
            suggested_stop,
            suggested_target,
            1 if has_conflict else 0,
            alert['message'],
            strategy_name,
            strategy_version,
            timeframe,
            signal_quality,
            trade_group_id,
            entry_reason,
            tags_json,
            market_condition,
            session_id
        ))

        signal_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Log with ATR info if available
        quality_str = f", Quality={signal_quality}" if signal_quality else ""
        strategy_str = f"[{strategy_name} {strategy_version}]"

        if indicators.get('atr'):
            atr_pct = indicators.get('atr_pct', 0)
            target_pct = indicators.get('target_pct', 0)
            stop_pct = indicators.get('stop_pct', 0)
            logger.info(f"Signal logged: ID={signal_id}, {strategy_str} Type={alert['type']}, Direction={direction}, ATR={atr_pct:.3f}%, Target={target_pct:.2f}%, Stop={stop_pct:.2f}%{quality_str}")
        else:
            logger.info(f"Signal logged: ID={signal_id}, {strategy_str} Type={alert['type']}, Direction={direction} (Fixed targets){quality_str}")

        return signal_id

    def check_signal_outcome(self, signal_id: int, current_price: float,
                            price_high: float, price_low: float) -> Optional[str]:
        """
        Check if a signal hit target or stop loss

        Args:
            signal_id: ID of signal to check
            current_price: Current BTC price
            price_high: Highest price since signal
            price_low: Lowest price since signal

        Returns:
            'WIN', 'LOSS', 'PENDING', or None if already checked
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get signal details
        cursor.execute('''
            SELECT direction, entry_price, suggested_stop, suggested_target,
                   outcome, timestamp
            FROM signals
            WHERE id = ?
        ''', (signal_id,))

        result = cursor.fetchone()
        if not result:
            conn.close()
            return None

        direction, entry, stop, target, outcome, timestamp = result

        # Skip if already checked
        if outcome is not None:
            conn.close()
            return outcome

        # Calculate price movements
        if direction == 'LONG':
            max_gain_pct = ((price_high - entry) / entry) * 100
            max_loss_pct = ((price_low - entry) / entry) * 100
            target_hit = price_high >= target
            stop_hit = price_low <= stop
        elif direction == 'SHORT':
            max_gain_pct = ((entry - price_low) / entry) * 100
            max_loss_pct = ((entry - price_high) / entry) * 100
            target_hit = price_low <= target
            stop_hit = price_high >= stop
        else:
            conn.close()
            return 'NEUTRAL'

        # Determine outcome and exit reason
        if target_hit and stop_hit:
            # Both hit - which came first? Assume stop (conservative)
            final_result = 'LOSS'
            exit_reason = 'Stop loss hit (both targets reached, stop assumed first)'
            strategy_profit = -abs(max_loss_pct)  # Negative profit
        elif target_hit:
            final_result = 'WIN'
            exit_reason = 'Take profit target reached'
            strategy_profit = max_gain_pct  # Positive profit
        elif stop_hit:
            final_result = 'LOSS'
            exit_reason = 'Stop loss triggered'
            strategy_profit = max_loss_pct  # Negative (max_loss_pct is already negative for LONG, positive for SHORT)
        else:
            # Check if signal is old (>1 hour) without hitting either
            signal_time = datetime.fromisoformat(timestamp)
            if datetime.now() - signal_time > timedelta(hours=1):
                final_result = 'TIMEOUT'
                exit_reason = 'Signal timeout (1 hour expired without hitting target/stop)'
                strategy_profit = 0
            else:
                final_result = 'PENDING'
                exit_reason = None
                strategy_profit = None

        # Update database
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
            final_result,
            price_high,
            price_low,
            1 if target_hit else 0,
            1 if stop_hit else 0,
            max_gain_pct,
            max_loss_pct,
            final_result,
            exit_reason,
            strategy_profit,
            signal_id
        ))

        conn.commit()
        conn.close()

        logger.info(f"Signal {signal_id} outcome: {final_result}")
        return final_result

    def get_statistics(self, hours_back: int = 24) -> Dict:
        """
        Calculate performance statistics

        Args:
            hours_back: How many hours of history to analyze

        Returns:
            Dictionary with statistics
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cutoff_time = (datetime.now() - timedelta(hours=hours_back)).isoformat()

        # Overall stats
        cursor.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN final_result = 'WIN' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN final_result = 'LOSS' THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN final_result = 'TIMEOUT' THEN 1 ELSE 0 END) as timeouts,
                SUM(CASE WHEN final_result = 'PENDING' OR final_result IS NULL THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN has_conflict = 1 THEN 1 ELSE 0 END) as conflicts,
                AVG(CASE WHEN final_result = 'WIN' THEN max_gain_pct END) as avg_win,
                AVG(CASE WHEN final_result = 'LOSS' THEN ABS(max_loss_pct) END) as avg_loss
            FROM signals
            WHERE timestamp >= ?
        ''', (cutoff_time,))

        row = cursor.fetchone()
        total, wins, losses, timeouts, pending, conflicts, avg_win, avg_loss = row

        wins = wins or 0
        losses = losses or 0
        timeouts = timeouts or 0

        # Calculate metrics
        completed = wins + losses + timeouts
        win_rate = (wins / completed * 100) if completed > 0 else 0
        profit_factor = (avg_win / avg_loss) if avg_loss and avg_loss > 0 else 0

        # Stats by signal type
        cursor.execute('''
            SELECT
                signal_type,
                COUNT(*) as count,
                SUM(CASE WHEN final_result = 'WIN' THEN 1 ELSE 0 END) as wins,
                AVG(CASE WHEN final_result = 'WIN' THEN max_gain_pct END) as avg_gain
            FROM signals
            WHERE timestamp >= ? AND final_result IS NOT NULL
            GROUP BY signal_type
            ORDER BY wins DESC
        ''', (cutoff_time,))

        signal_types = {}
        for row in cursor.fetchall():
            sig_type, count, type_wins, avg_gain = row
            signal_types[sig_type] = {
                'count': count,
                'wins': type_wins or 0,
                'win_rate': (type_wins / count * 100) if count > 0 else 0,
                'avg_gain': avg_gain or 0
            }

        # Best and worst signal types
        best_type = max(signal_types.items(), key=lambda x: x[1]['win_rate'])[0] if signal_types else 'N/A'
        worst_type = min(signal_types.items(), key=lambda x: x[1]['win_rate'])[0] if signal_types else 'N/A'

        stats = {
            'period_hours': hours_back,
            'total_signals': total,
            'completed': completed,
            'wins': wins,
            'losses': losses,
            'timeouts': timeouts,
            'pending': pending,
            'conflicts': conflicts,
            'win_rate': win_rate,
            'avg_win_pct': avg_win or 0,
            'avg_loss_pct': avg_loss or 0,
            'profit_factor': profit_factor,
            'best_signal_type': best_type,
            'worst_signal_type': worst_type,
            'by_signal_type': signal_types
        }

        # Save stats snapshot
        cursor.execute('''
            INSERT INTO performance_stats (
                calculated_at, total_signals, checked_signals, wins, losses,
                pending, win_rate, avg_gain, avg_loss, profit_factor,
                best_signal_type, worst_signal_type, conflicting_signals, json_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now().isoformat(),
            total, completed, wins, losses, pending,
            win_rate, avg_win or 0, avg_loss or 0, profit_factor,
            best_type, worst_type, conflicts,
            json.dumps(stats)
        ))

        conn.commit()
        conn.close()

        return stats

    def get_strategy_comparison(self, hours_back: int = 24) -> Dict:
        """
        Compare performance across different strategies

        Args:
            hours_back: How many hours of history to analyze

        Returns:
            Dictionary with strategy comparison data
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cutoff_time = (datetime.now() - timedelta(hours=hours_back)).isoformat()

        # Get stats by strategy
        cursor.execute('''
            SELECT
                strategy_name,
                strategy_version,
                COUNT(*) as total,
                SUM(CASE WHEN final_result = 'WIN' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN final_result = 'LOSS' THEN 1 ELSE 0 END) as losses,
                AVG(CASE WHEN final_result = 'WIN' THEN strategy_profit END) as avg_win,
                AVG(CASE WHEN final_result = 'LOSS' THEN strategy_profit END) as avg_loss,
                SUM(strategy_profit) as total_profit,
                AVG(strategy_profit) as avg_profit
            FROM signals
            WHERE timestamp >= ? AND final_result IS NOT NULL
            GROUP BY strategy_name, strategy_version
            ORDER BY total_profit DESC
        ''', (cutoff_time,))

        strategies = {}
        for row in cursor.fetchall():
            strategy_name, version, total, wins, losses, avg_win, avg_loss, total_profit, avg_profit = row
            wins = wins or 0
            losses = losses or 0
            completed = wins + losses
            win_rate = (wins / completed * 100) if completed > 0 else 0

            strategies[f"{strategy_name}_{version}"] = {
                'name': strategy_name,
                'version': version,
                'total_signals': total,
                'wins': wins,
                'losses': losses,
                'win_rate': win_rate,
                'avg_win': avg_win or 0,
                'avg_loss': avg_loss or 0,
                'total_profit': total_profit or 0,
                'avg_profit': avg_profit or 0
            }

        # Get stats by signal quality
        cursor.execute('''
            SELECT
                signal_quality,
                COUNT(*) as total,
                SUM(CASE WHEN final_result = 'WIN' THEN 1 ELSE 0 END) as wins,
                AVG(strategy_profit) as avg_profit
            FROM signals
            WHERE timestamp >= ? AND final_result IS NOT NULL AND signal_quality IS NOT NULL
            GROUP BY signal_quality
            ORDER BY avg_profit DESC
        ''', (cutoff_time,))

        quality_stats = {}
        for row in cursor.fetchall():
            quality, total, wins, avg_profit = row
            wins = wins or 0
            win_rate = (wins / total * 100) if total > 0 else 0
            quality_stats[quality] = {
                'total': total,
                'wins': wins,
                'win_rate': win_rate,
                'avg_profit': avg_profit or 0
            }

        # Get stats by market condition
        cursor.execute('''
            SELECT
                market_condition,
                COUNT(*) as total,
                SUM(CASE WHEN final_result = 'WIN' THEN 1 ELSE 0 END) as wins,
                AVG(strategy_profit) as avg_profit
            FROM signals
            WHERE timestamp >= ? AND final_result IS NOT NULL AND market_condition IS NOT NULL
            GROUP BY market_condition
        ''', (cutoff_time,))

        condition_stats = {}
        for row in cursor.fetchall():
            condition, total, wins, avg_profit = row
            wins = wins or 0
            win_rate = (wins / total * 100) if total > 0 else 0
            condition_stats[condition] = {
                'total': total,
                'wins': wins,
                'win_rate': win_rate,
                'avg_profit': avg_profit or 0
            }

        conn.close()

        return {
            'period_hours': hours_back,
            'by_strategy': strategies,
            'by_quality': quality_stats,
            'by_market_condition': condition_stats
        }

    def get_recent_signals(self, limit: int = 20) -> List[Dict]:
        """Get recent signals with their outcomes"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM signals
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (limit,))

        signals = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return signals

    def get_unchecked_signals(self, max_age_hours: int = 2) -> List[Dict]:
        """Get signals that haven't been outcome-checked yet"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cutoff_time = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()

        cursor.execute('''
            SELECT * FROM signals
            WHERE (outcome IS NULL OR outcome = 'PENDING')
            AND timestamp >= ?
            ORDER BY timestamp ASC
        ''', (cutoff_time,))

        signals = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return signals


if __name__ == "__main__":
    # Test the tracker
    tracker = SignalTracker()
    print("Signal tracker initialized successfully!")
    print(f"Database: {tracker.db_path}")

    # Show stats
    stats = tracker.get_statistics(hours_back=24)
    print(f"\nStatistics (last 24h):")
    print(f"  Total signals: {stats['total_signals']}")
    print(f"  Win rate: {stats['win_rate']:.1f}%")
    print(f"  Wins: {stats['wins']}, Losses: {stats['losses']}, Pending: {stats['pending']}")
