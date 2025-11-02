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

        logger.info(f"✅ Scalping Signal Generator initialized - Symbol: {self.symbol}, Timeframe: {self.timeframe}")

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
                logger.warning("No market data available")
                return {
                    'timestamp': datetime.now().isoformat(),
                    'has_signal': False,
                    'error': 'No market data'
                }

            # Analyze market using scalping engine
            analysis = self.engine.analyze_market(df)

            # Check if we have signals
            signals = analysis.get('signals', {})
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
            logger.error(f"Error generating signals: {e}", exc_info=True)
            return {
                'timestamp': datetime.now().isoformat(),
                'has_signal': False,
                'error': str(e)
            }

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

            df = self.api.get_kline_data(
                symbol=self.symbol,
                interval=self.timeframe,
                limit=limit
            )

            if df is None or len(df) == 0:
                logger.error("Failed to fetch market data from BingX")
                return None

            # Ensure required columns exist
            required_columns = ['open', 'high', 'low', 'close', 'volume', 'timestamp']
            missing_columns = [col for col in required_columns if col not in df.columns]

            if missing_columns:
                logger.error(f"Missing required columns: {missing_columns}")
                return None

            logger.debug(f"Fetched {len(df)} candles from BingX - Latest price: {df['close'].iloc[-1]:.2f}")
            return df

        except Exception as e:
            logger.error(f"Error fetching market data: {e}", exc_info=True)
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
            self.engine.record_trade(trade_data)
            logger.debug(f"Trade result recorded - Side: {trade_data.get('side')}, PNL: {trade_data.get('pnl', 0):.2f}")
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
