#!/usr/bin/env python3
"""
Scalping Signal Generator
Wraps the scalping engine and integrates with BingX API for signal generation
"""

import logging
from typing import Dict, Optional
from datetime import datetime
import pandas as pd

from ..indicators.scalping_engine import BitcoinScalpingEngine

logger = logging.getLogger(__name__)


class ScalpingSignalGenerator:
    """
    Generates trading signals using the Scalping Engine
    Fetches market data and produces actionable trading signals
    """

    def __init__(self, api_client, config: Dict):
        """
        Initialize the signal generator

        Args:
            api_client: BingX API client instance
            config: Configuration dictionary
        """
        self.api = api_client
        self.config = config
        self.symbol = config.get('symbol', 'BTC-USDT')
        self.timeframe = config.get('timeframe', '5m')
        self.engine = BitcoinScalpingEngine(config)

        self.last_signal_time = None
        self.last_signal_type = None

        # Signal cooldown to prevent rapid re-detection
        self.signal_cooldown_seconds = config.get('signal_cooldown_seconds', 120)
        self.last_signal_time_by_side = {}  # Track cooldown per side

        logger.info(f"✅ Scalping Signal Generator initialized - Symbol: {self.symbol}, Timeframe: {self.timeframe}, Cooldown: {self.signal_cooldown_seconds}s")

    def generate_signals(self) -> Dict:
        """
        Check for trading opportunities

        Returns:
            Dictionary with signal information:
            {
                'timestamp': str,
                'has_signal': bool,
                'long': {...} or None,
                'short': {...} or None,
                'indicators': {...},
                'market_data': {...}
            }
        """
        try:
            # Fetch market data from BingX
            df = self._fetch_market_data()

            if df is None or len(df) == 0:
                logger.warning("⚠️  No market data available - Cannot generate signals")
                return {
                    'timestamp': datetime.now().isoformat(),
                    'has_signal': False,
                    'error': 'No market data available',
                    'critical_error': False  # Not critical, just temporary unavailability
                }

            # Analyze market using scalping engine
            analysis = self.engine.analyze_market(df)

            # Check if we have signals
            signals = analysis.get('signals', {})
            has_signal = len(signals) > 0

            # Apply cooldown filter to prevent rapid re-detection
            signals = self._apply_cooldown_filter(signals)
            has_signal = len(signals) > 0

            # Format response
            response = {
                'timestamp': analysis.get('timestamp'),
                'has_signal': has_signal,
                'current_price': analysis.get('price'),
                'indicators': analysis.get('indicators', {}),
                'price_action': analysis.get('price_action', {}),
                'long': signals.get('long'),
                'short': signals.get('short')
            }

            # Log signal if found
            if has_signal:
                if 'long' in signals:
                    logger.info(f"🟢 LONG signal detected - Confidence: {signals['long']['confidence']*100:.1f}%, "
                              f"Conditions: {signals['long']['conditions']}")
                if 'short' in signals:
                    logger.info(f"🔴 SHORT signal detected - Confidence: {signals['short']['confidence']*100:.1f}%, "
                              f"Conditions: {signals['short']['conditions']}")

            return response

        except Exception as e:
            logger.error(f"❌ CRITICAL: Signal generation failed: {e}", exc_info=True)
            return {
                'timestamp': datetime.now().isoformat(),
                'has_signal': False,
                'error': f'Signal generation failed: {str(e)}',
                'critical_error': True  # Flag for critical errors vs normal "no signal"
            }

    def _apply_cooldown_filter(self, signals: Dict) -> Dict:
        """
        Filter signals based on cooldown period to prevent rapid re-detection

        Args:
            signals: Dictionary with 'long' and/or 'short' signal data

        Returns:
            Filtered signals dictionary (may be empty if all signals in cooldown)
        """
        if not signals or self.signal_cooldown_seconds <= 0:
            return signals

        current_time = datetime.now()
        filtered_signals = {}

        for side in ['long', 'short']:
            if side in signals:
                last_signal_time = self.last_signal_time_by_side.get(side)

                # Check if cooldown period has elapsed
                if last_signal_time is None:
                    # First signal of this side
                    filtered_signals[side] = signals[side]
                    self.last_signal_time_by_side[side] = current_time
                    logger.debug(f"✅ {side.upper()} signal accepted - first signal")
                else:
                    elapsed_seconds = (current_time - last_signal_time).total_seconds()

                    if elapsed_seconds >= self.signal_cooldown_seconds:
                        # Cooldown period has elapsed
                        filtered_signals[side] = signals[side]
                        self.last_signal_time_by_side[side] = current_time
                        logger.debug(f"✅ {side.upper()} signal accepted - cooldown elapsed ({elapsed_seconds:.0f}s)")
                    else:
                        # Still in cooldown
                        remaining = self.signal_cooldown_seconds - elapsed_seconds
                        logger.info(f"🔒 {side.upper()} signal suppressed - cooldown active ({remaining:.0f}s remaining)")

        return filtered_signals

    def _fetch_market_data(self) -> Optional[pd.DataFrame]:
        """
        Fetch market data from BingX API

        Returns:
            DataFrame with OHLCV data or None on error
        """
        try:
            # Fetch klines (need enough data for indicators)
            # Request 100 candles to ensure we have enough for all indicators
            limit = 100

            klines = self.api.get_kline_data(
                symbol=self.symbol,
                interval=self.timeframe,
                limit=limit
            )

            if klines is None or len(klines) == 0:
                logger.error("❌ Failed to fetch market data from BingX - API returned empty response")
                return None

            # Convert list of dicts to DataFrame
            df = pd.DataFrame(klines)

            # Ensure required columns exist
            required_columns = ['open', 'high', 'low', 'close', 'volume', 'timestamp']
            missing_columns = [col for col in required_columns if col not in df.columns]

            if missing_columns:
                logger.error(f"❌ Missing required columns in API response: {missing_columns}")
                return None

            logger.debug(f"✅ Fetched {len(df)} candles from BingX - Latest price: {df['close'].iloc[-1]:.2f}")
            return df

        except Exception as e:
            logger.error(f"❌ CRITICAL: Error fetching market data: {e}", exc_info=True)
            return None

    def should_update_signal(self, position_side: str) -> bool:
        """
        Check if we should update/close a position based on new signals

        Args:
            position_side: Current position side ('LONG' or 'SHORT')

        Returns:
            True if position should be closed
        """
        try:
            # Fetch fresh data
            df = self._fetch_market_data()
            if df is None:
                return False

            # Analyze current market
            analysis = self.engine.analyze_market(df)
            signals = analysis.get('signals', {})

            # Check for reverse signal
            if position_side == 'LONG' and 'short' in signals:
                short_confidence = signals['short']['confidence']
                if short_confidence > 0.7:  # Strong reverse signal
                    logger.info(f"🔄 Strong SHORT signal detected while holding LONG - Confidence: {short_confidence*100:.1f}%")
                    return True

            elif position_side == 'SHORT' and 'long' in signals:
                long_confidence = signals['long']['confidence']
                if long_confidence > 0.7:  # Strong reverse signal
                    logger.info(f"🔄 Strong LONG signal detected while holding SHORT - Confidence: {long_confidence*100:.1f}%")
                    return True

            return False

        except Exception as e:
            logger.error(f"Error checking signal update: {e}")
            return False

    def get_current_market_state(self) -> Dict:
        """
        Get current market indicators without generating signals

        Returns:
            Dictionary with current market state
        """
        try:
            df = self._fetch_market_data()
            if df is None:
                return {}

            analysis = self.engine.analyze_market(df)

            return {
                'price': analysis.get('price'),
                'indicators': analysis.get('indicators', {}),
                'price_action': analysis.get('price_action', {}),
                'timestamp': analysis.get('timestamp')
            }

        except Exception as e:
            logger.error(f"Error getting market state: {e}")
            return {}

    def record_trade_result(self, trade_data: Dict):
        """
        Record trade result to improve future signal confidence

        Args:
            trade_data: Trade information including side, pnl, etc.
        """
        try:
            # Ensure we have all required fields for complete trades
            required_fields = ['side', 'entry_price', 'exit_price', 'pnl', 'confidence']
            if not all(field in trade_data for field in required_fields):
                logger.debug(f"Incomplete trade data (position opened): {trade_data.keys()}")
                # For position opens, we don't have exit data yet - that's OK
                return

            self.engine.record_trade(trade_data)
            logger.info(f"📊 Trade recorded - {trade_data.get('side')} | "
                       f"PNL: ${trade_data.get('pnl', 0):.2f} | "
                       f"Confidence: {trade_data.get('confidence', 0)*100:.1f}%")
        except Exception as e:
            logger.error(f"Error recording trade: {e}")

    def get_performance_stats(self) -> Dict:
        """
        Get signal generator performance statistics

        Returns:
            Dictionary with performance metrics
        """
        if not self.engine.trade_history:
            return {
                'total_signals': 0,
                'win_rate': 0,
                'consecutive_wins': 0,
                'consecutive_losses': 0
            }

        trades = list(self.engine.trade_history)
        winning_trades = [t for t in trades if t.get('pnl', 0) > 0]

        return {
            'total_signals': len(trades),
            'win_rate': len(winning_trades) / len(trades) if trades else 0,
            'consecutive_wins': self.engine.consecutive_wins,
            'consecutive_losses': self.engine.consecutive_losses,
            'avg_confidence': sum(t.get('confidence', 0.5) for t in trades) / len(trades) if trades else 0
        }
