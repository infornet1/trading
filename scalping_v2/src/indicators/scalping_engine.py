#!/usr/bin/env python3
"""
Bitcoin Scalping Engine
Implements EMA, RSI, Stochastic, and Volume-based scalping signals
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from collections import deque

logger = logging.getLogger(__name__)


class BitcoinScalpingEngine:
    """
    High-frequency Bitcoin scalping strategy
    Uses EMA, RSI, Stochastic, Volume, and ATR for signal generation
    """

    def __init__(self, config: Dict = None):
        self.config = config or {}

        # Trading parameters from config
        self.target_profit_pct = self.config.get('target_profit_pct', 0.003)  # 0.3%
        self.max_loss_pct = self.config.get('max_loss_pct', 0.0015)  # 0.15%
        self.max_position_time = self.config.get('max_position_time', 300)  # 5 minutes

        # Technical indicator parameters
        self.ema_fast = self.config.get('ema_fast', 8)
        self.ema_slow = self.config.get('ema_slow', 21)
        self.ema_micro = self.config.get('ema_micro', 5)
        self.rsi_period = self.config.get('rsi_period', 14)
        self.rsi_oversold = self.config.get('rsi_oversold', 35)
        self.rsi_overbought = self.config.get('rsi_overbought', 65)
        self.stoch_period = self.config.get('stoch_period', 14)
        self.stoch_smooth = self.config.get('stoch_smooth', 3)
        self.volume_ma_period = self.config.get('volume_ma_period', 20)
        self.atr_period = self.config.get('atr_period', 14)
        self.min_volume_ratio = self.config.get('min_volume_ratio', 1.2)
        self.min_confidence = self.config.get('min_confidence', 0.6)

        # Performance tracking
        self.trade_history = deque(maxlen=100)
        self.consecutive_losses = 0
        self.consecutive_wins = 0

        logger.info(f"✅ Scalping Engine initialized - EMA: {self.ema_fast}/{self.ema_slow}, RSI: {self.rsi_period}")

    def analyze_market(self, df: pd.DataFrame) -> Dict:
        """
        Main analysis function - analyzes market for scalping opportunities

        Args:
            df: DataFrame with OHLCV data (columns: open, high, low, close, volume, timestamp)

        Returns:
            Dictionary with indicators, signals, and metadata
        """
        try:
            # 1. Validate DataFrame is not empty
            if df is None or df.empty:
                logger.warning("⚠️  Empty DataFrame received")
                return self._error_response("Empty DataFrame")

            # 2. Validate required columns exist
            required_columns = ['open', 'high', 'low', 'close', 'volume']
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                logger.error(f"❌ Missing required columns: {missing_columns}")
                return self._error_response(f"Missing columns: {missing_columns}")

            # 3. Handle NaN values
            if df[required_columns].isna().any().any():
                logger.warning("⚠️  NaN values detected, applying forward fill")
                df = df.fillna(method='ffill').fillna(method='bfill')

            # Validate minimum data requirements
            min_periods = max(self.ema_slow, self.rsi_period, self.volume_ma_period, self.stoch_period) + 10
            if len(df) < min_periods:
                return {
                    'signal': 'hold',
                    'reason': f'insufficient_data (need {min_periods}, have {len(df)})',
                    'timestamp': datetime.now().isoformat()
                }

            # Extract price and volume data
            closes = df['close'].values
            highs = df['high'].values
            lows = df['low'].values
            opens = df['open'].values
            volumes = df['volume'].values if 'volume' in df.columns else np.ones(len(closes))

            current_price = closes[-1]
            current_volume = volumes[-1]

            # Calculate all indicators
            indicators = self._calculate_indicators(closes, highs, lows, opens, volumes)

            # Analyze price action
            price_action = self._analyze_price_action(df)

            # Detect market regime
            market_regime = self._detect_market_regime(indicators, price_action)

            # Generate trading signals (market regime aware)
            signals = self._generate_signals(
                current_price=current_price,
                indicators=indicators,
                price_action=price_action
            )

            # Filter signals based on market regime
            if market_regime == 'choppy':
                # Reduce confidence in choppy markets or skip
                for signal_type in signals:
                    signals[signal_type]['confidence'] *= 0.7
                    signals[signal_type]['regime_warning'] = 'choppy_market'
            elif market_regime == 'ranging':
                # Slightly reduce confidence in ranging markets
                for signal_type in signals:
                    signals[signal_type]['confidence'] *= 0.9

            # Build result
            result = {
                'timestamp': datetime.now().isoformat(),
                'price': round(current_price, 2),
                'indicators': indicators,
                'price_action': price_action,
                'market_regime': market_regime,
                'signals': signals
            }

            return result

        except Exception as e:
            logger.error(f"Error in market analysis: {e}", exc_info=True)
            return {
                'signal': 'hold',
                'reason': f'error: {str(e)}',
                'timestamp': datetime.now().isoformat()
            }

    def _calculate_indicators(self, closes: np.ndarray, highs: np.ndarray,
                            lows: np.ndarray, opens: np.ndarray,
                            volumes: np.ndarray) -> Dict:
        """Calculate indicators with enhanced validation"""

        if len(closes) == 0:
            return {}

        current_price = closes[-1]

        try:
            # 1. EMA Trend Indicators with validation
            ema_micro = self._calculate_ema(closes, self.ema_micro)
            ema_fast = self._calculate_ema(closes, self.ema_fast)
            ema_slow = self._calculate_ema(closes, self.ema_slow)

            # Validate EMA calculations
            ema_micro_val = ema_micro[-1] if not np.isnan(ema_micro[-1]) and ema_micro[-1] > 0 else current_price
            ema_fast_val = ema_fast[-1] if not np.isnan(ema_fast[-1]) and ema_fast[-1] > 0 else current_price
            ema_slow_val = ema_slow[-1] if not np.isnan(ema_slow[-1]) and ema_slow[-1] > 0 else current_price

            # 2. RSI Momentum with bounds checking
            rsi = self._calculate_rsi(closes, self.rsi_period)
            rsi_val = max(0, min(100, rsi[-1])) if not np.isnan(rsi[-1]) else 50

            # 3. Stochastic Oscillator
            stoch_k, stoch_d = self._calculate_stochastic(highs, lows, closes, self.stoch_period, self.stoch_smooth)
            stoch_k_val = max(0, min(100, stoch_k[-1])) if not np.isnan(stoch_k[-1]) else 50
            stoch_d_val = max(0, min(100, stoch_d[-1])) if not np.isnan(stoch_d[-1]) else 50

            # 4. Volume Analysis with spike detection
            volume_sma = self._calculate_sma(volumes, self.volume_ma_period)
            current_volume = volumes[-1]
            volume_ratio = current_volume / volume_sma[-1] if volume_sma[-1] > 0 else 1.0
            volume_spike = volume_ratio > 2.0  # Significant volume spike

            # 5. ATR for Volatility with percentage
            atr = self._calculate_atr(highs, lows, closes, self.atr_period)
            atr_val = atr[-1] if not np.isnan(atr[-1]) and atr[-1] > 0 else 0
            atr_pct = (atr_val / current_price) * 100 if current_price > 0 else 0

            # Additional: Price rate of change (momentum)
            roc_1 = ((closes[-1] - closes[-2]) / closes[-2]) * 100 if len(closes) > 1 else 0
            roc_5 = ((closes[-1] - closes[-6]) / closes[-6]) * 100 if len(closes) > 5 else 0

            return {
                'ema_micro': round(ema_micro_val, 2),
                'ema_fast': round(ema_fast_val, 2),
                'ema_slow': round(ema_slow_val, 2),
                'rsi': round(rsi_val, 2),
                'stoch_k': round(stoch_k_val, 2),
                'stoch_d': round(stoch_d_val, 2),
                'volume_ratio': round(volume_ratio, 2),
                'volume_spike': volume_spike,
                'atr': round(atr_val, 2),
                'atr_pct': round(atr_pct, 3),
                'roc_1': round(roc_1, 3),
                'roc_5': round(roc_5, 3)
            }

        except Exception as e:
            logger.error(f"Error calculating indicators: {e}")
            return {}

    def _detect_market_regime(self, indicators: Dict, price_action: Dict) -> str:
        """
        Detect market regime: trending, ranging, or choppy
        This helps filter signals in unfavorable market conditions
        """
        try:
            ema_micro = indicators.get('ema_micro', 0)
            ema_fast = indicators.get('ema_fast', 0)
            ema_slow = indicators.get('ema_slow', 0)
            atr_pct = indicators.get('atr_pct', 0)
            roc_5 = indicators.get('roc_5', 0)
            volume_ratio = indicators.get('volume_ratio', 1)

            # Calculate EMA separation as % of price
            ema_separation = abs(ema_micro - ema_slow) / ema_slow if ema_slow > 0 else 0

            # Trending market conditions
            strong_trend = (
                (ema_micro > ema_fast > ema_slow or ema_micro < ema_fast < ema_slow) and
                ema_separation > 0.002 and  # EMAs separated by > 0.2%
                abs(roc_5) > 0.3 and  # Strong 5-candle momentum
                volume_ratio > 1.0  # Decent volume
            )

            # Ranging market conditions
            ranging = (
                ema_separation < 0.001 and  # EMAs close together
                abs(roc_5) < 0.2 and  # Low momentum
                atr_pct < 0.015  # Low volatility
            )

            # Choppy/volatile market
            roc_1 = indicators.get('roc_1', 0)
            choppy = (
                atr_pct > 0.025 or  # High volatility
                (volume_ratio > 2.5 and abs(roc_1) < 0.1)  # Volume spike with no direction
            )

            if strong_trend:
                return 'trending'
            elif ranging:
                return 'ranging'
            elif choppy:
                return 'choppy'
            else:
                return 'neutral'

        except Exception as e:
            logger.warning(f"Error detecting market regime: {e}")
            return 'neutral'

    def _analyze_price_action(self, df: pd.DataFrame) -> Dict:
        """Analyze recent price action patterns"""

        closes = df['close'].values
        highs = df['high'].values
        lows = df['low'].values
        opens = df['open'].values

        current_close = closes[-1]
        prev_close = closes[-2] if len(closes) > 1 else current_close

        # Price change
        price_change_pct = ((current_close - prev_close) / prev_close) * 100 if prev_close > 0 else 0

        # Support/Resistance levels
        recent_high = np.max(highs[-10:])
        recent_low = np.min(lows[-10:])

        # Distance to levels
        to_high_pct = ((recent_high - current_close) / current_close) * 100
        to_low_pct = ((current_close - recent_low) / current_close) * 100

        # Candlestick patterns
        bullish_pattern = self._detect_bullish_pattern(opens, highs, lows, closes)
        bearish_pattern = self._detect_bearish_pattern(opens, highs, lows, closes)

        return {
            'price_change_pct': round(price_change_pct, 3),
            'near_resistance': to_high_pct < 0.2,  # Within 0.2%
            'near_support': to_low_pct < 0.2,      # Within 0.2%
            'bullish_pattern': bullish_pattern,
            'bearish_pattern': bearish_pattern,
            'recent_high': round(recent_high, 2),
            'recent_low': round(recent_low, 2)
        }

    def _generate_signals(self, current_price: float, indicators: Dict, price_action: Dict) -> Dict:
        """Generate trading signals with improved logic"""

        signals = {}

        # Extract indicators with safety checks
        try:
            ema_micro = indicators.get('ema_micro', current_price)
            ema_fast = indicators.get('ema_fast', current_price)
            ema_slow = indicators.get('ema_slow', current_price)
            rsi = indicators.get('rsi', 50)
            stoch_k = indicators.get('stoch_k', 50)
            stoch_d = indicators.get('stoch_d', 50)
            volume_ratio = indicators.get('volume_ratio', 1)
            atr_pct = indicators.get('atr_pct', 0)
        except KeyError as e:
            logger.warning(f"Missing indicator in signal generation: {e}")
            return signals

        # Enhanced trend analysis
        ema_alignment_bullish = ema_micro > ema_fast > ema_slow
        ema_alignment_bearish = ema_micro < ema_fast < ema_slow
        ema_trend_strength = abs(ema_micro - ema_slow) / current_price

        # Strong trend requires minimum separation
        strong_bullish_trend = ema_alignment_bullish and ema_trend_strength > 0.001  # 0.1%
        strong_bearish_trend = ema_alignment_bearish and ema_trend_strength > 0.001

        # Enhanced momentum analysis
        rsi_oversold = rsi < self.rsi_oversold
        rsi_overbought = rsi > self.rsi_overbought
        rsi_trend = rsi > 50  # Simple bullish/bearish momentum

        stoch_bullish_cross = stoch_k > stoch_d and stoch_k < 80
        stoch_bearish_cross = stoch_k < stoch_d and stoch_k > 20
        stoch_momentum = stoch_k > 50  # Bullish momentum

        # Volume and volatility analysis
        volume_ok = volume_ratio > self.min_volume_ratio
        high_volatility = atr_pct > 0.02  # 2% ATR indicates high volatility

        # Price action
        near_support = price_action.get('near_support', False)
        near_resistance = price_action.get('near_resistance', False)
        bullish_pattern = price_action.get('bullish_pattern', False)
        bearish_pattern = price_action.get('bearish_pattern', False)

        # ENHANCED LONG SIGNAL CONDITIONS
        long_conditions = []
        long_confidence = 0.0

        # Primary condition: Strong trend + momentum
        if strong_bullish_trend and stoch_bullish_cross and volume_ok:
            base_confidence = 0.7
            # Boost confidence if RSI confirms
            if rsi_trend and not rsi_overbought:
                base_confidence += 0.1
            long_conditions.append(("strong_trend_momentum", base_confidence))

        # Secondary condition: Oversold bounce at support
        elif rsi_oversold and near_support:
            base_confidence = 0.6
            if bullish_pattern:
                base_confidence += 0.2
            if volume_ok:
                base_confidence += 0.1
            long_conditions.append(("oversold_bounce", base_confidence))

        # Tertiary condition: EMA micro crossover with volume
        elif ema_micro > ema_fast and volume_ratio > 1.5:
            long_conditions.append(("ema_micro_crossover", 0.5))

        # ENHANCED SHORT SIGNAL CONDITIONS
        short_conditions = []
        short_confidence = 0.0

        # Primary condition: Strong trend + momentum
        if strong_bearish_trend and stoch_bearish_cross and volume_ok:
            base_confidence = 0.7
            # Boost confidence if RSI confirms
            if not rsi_trend and not rsi_oversold:
                base_confidence += 0.1
            short_conditions.append(("strong_trend_momentum", base_confidence))

        # Secondary condition: Overbought rejection at resistance
        elif rsi_overbought and near_resistance:
            base_confidence = 0.6
            if bearish_pattern:
                base_confidence += 0.2
            if volume_ok:
                base_confidence += 0.1
            short_conditions.append(("overbought_rejection", base_confidence))

        # Tertiary condition: EMA micro crossover with volume
        elif ema_micro < ema_fast and volume_ratio > 1.5:
            short_conditions.append(("ema_micro_crossover", 0.5))

        # Calculate weighted confidence (prefer primary conditions)
        if long_conditions:
            # Weight primary conditions higher
            weights = [1.0 if "strong" in cond[0] else 0.8 if "oversold" in cond[0] else 0.6
                      for cond in long_conditions]
            total_weight = sum(weights)
            weighted_confidence = sum(conf * weight for (_, conf), weight in zip(long_conditions, weights)) / total_weight

            confidence = self._adjust_confidence(weighted_confidence, 'long')

            if confidence >= self.min_confidence:
                # Use ATR for dynamic stop loss in high volatility
                if high_volatility:
                    stop_loss_pct = min(self.max_loss_pct * 1.5, 0.003)  # Cap at 0.3%
                else:
                    stop_loss_pct = self.max_loss_pct

                stop_loss = current_price * (1 - stop_loss_pct)
                take_profit = current_price * (1 + self.target_profit_pct)

                signals['long'] = {
                    'confidence': round(confidence, 3),
                    'stop_loss': round(stop_loss, 2),
                    'take_profit': round(take_profit, 2),
                    'conditions': [cond for cond, _ in long_conditions],
                    'risk_reward': round(self.target_profit_pct / stop_loss_pct, 2),
                    'volatility_adjusted': high_volatility
                }

        if short_conditions:
            weights = [1.0 if "strong" in cond[0] else 0.8 if "overbought" in cond[0] else 0.6
                      for cond in short_conditions]
            total_weight = sum(weights)
            weighted_confidence = sum(conf * weight for (_, conf), weight in zip(short_conditions, weights)) / total_weight

            confidence = self._adjust_confidence(weighted_confidence, 'short')

            if confidence >= self.min_confidence:
                if high_volatility:
                    stop_loss_pct = min(self.max_loss_pct * 1.5, 0.003)
                else:
                    stop_loss_pct = self.max_loss_pct

                stop_loss = current_price * (1 + stop_loss_pct)
                take_profit = current_price * (1 - self.target_profit_pct)

                signals['short'] = {
                    'confidence': round(confidence, 3),
                    'stop_loss': round(stop_loss, 2),
                    'take_profit': round(take_profit, 2),
                    'conditions': [cond for cond, _ in short_conditions],
                    'risk_reward': round(self.target_profit_pct / stop_loss_pct, 2),
                    'volatility_adjusted': high_volatility
                }

        return signals

    def _adjust_confidence(self, base_confidence: float, side: str) -> float:
        """Adjust confidence based on recent trading performance"""

        if not self.trade_history:
            return base_confidence

        # Get recent trades of this type
        recent_trades = [t for t in list(self.trade_history)[-10:] if t.get('side') == side]

        if not recent_trades:
            return base_confidence

        # Calculate win rate
        wins = sum(1 for t in recent_trades if t.get('pnl', 0) > 0)
        win_rate = wins / len(recent_trades)

        # Adjust confidence
        if win_rate > 0.6:
            adjustment = 1.2
        elif win_rate < 0.4:
            adjustment = 0.8
        else:
            adjustment = 1.0

        # Apply consecutive loss penalty
        if self.consecutive_losses >= 3:
            adjustment *= 0.7

        adjusted = base_confidence * adjustment
        return min(adjusted, 0.95)  # Cap at 95%

    def record_trade(self, trade_data: Dict):
        """Record trade for performance tracking"""
        self.trade_history.append(trade_data)

        pnl = trade_data.get('pnl', 0)
        if pnl > 0:
            self.consecutive_wins += 1
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1
            self.consecutive_wins = 0

    # ==================== Helper Methods for Indicator Calculation ====================

    def _calculate_ema(self, data: np.ndarray, period: int) -> np.ndarray:
        """Calculate Exponential Moving Average using vectorized pandas operations"""
        # Convert to pandas Series for vectorized EWM calculation
        series = pd.Series(data)
        # Use pandas ewm (exponentially weighted moving average) - much faster than loop
        ema = series.ewm(span=period, adjust=False).mean()
        return ema.values

    def _calculate_sma(self, data: np.ndarray, period: int) -> np.ndarray:
        """Calculate Simple Moving Average"""
        sma = np.convolve(data, np.ones(period)/period, mode='valid')
        # Pad beginning with NaN
        return np.concatenate([np.full(period-1, np.nan), sma])

    def _calculate_rsi(self, closes: np.ndarray, period: int) -> np.ndarray:
        """Calculate Relative Strength Index using vectorized pandas operations"""
        # Convert to pandas Series for vectorized operations
        close_series = pd.Series(closes)

        # Calculate price changes
        delta = close_series.diff()

        # Separate gains and losses using vectorized operations
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        # Calculate exponential moving averages of gains and losses
        avg_gain = gain.ewm(span=period, adjust=False).mean()
        avg_loss = loss.ewm(span=period, adjust=False).mean()

        # Calculate RS and RSI
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        # Fill NaN values with 50 (neutral RSI)
        rsi = rsi.fillna(50)

        return rsi.values

    def _calculate_stochastic(self, highs: np.ndarray, lows: np.ndarray,
                             closes: np.ndarray, period: int, smooth: int) -> Tuple[np.ndarray, np.ndarray]:
        """Calculate Stochastic Oscillator"""

        stoch_k = np.zeros_like(closes)

        for i in range(period-1, len(closes)):
            highest_high = np.max(highs[i-period+1:i+1])
            lowest_low = np.min(lows[i-period+1:i+1])

            if highest_high - lowest_low != 0:
                stoch_k[i] = 100 * (closes[i] - lowest_low) / (highest_high - lowest_low)
            else:
                stoch_k[i] = 50

        # Smooth %K to get %D
        stoch_d = self._calculate_sma(stoch_k, smooth)
        stoch_d = np.nan_to_num(stoch_d, nan=50.0)
        stoch_k = np.nan_to_num(stoch_k, nan=50.0)

        return stoch_k, stoch_d

    def _calculate_atr(self, highs: np.ndarray, lows: np.ndarray,
                       closes: np.ndarray, period: int) -> np.ndarray:
        """Calculate Average True Range"""

        tr = np.zeros(len(closes))

        for i in range(1, len(closes)):
            hl = highs[i] - lows[i]
            hc = abs(highs[i] - closes[i-1])
            lc = abs(lows[i] - closes[i-1])
            tr[i] = max(hl, hc, lc)

        atr = self._calculate_sma(tr, period)
        atr = np.nan_to_num(atr, nan=tr[period:].mean() if len(tr) > period else 0)

        return atr

    def _detect_bullish_pattern(self, opens: np.ndarray, highs: np.ndarray,
                                lows: np.ndarray, closes: np.ndarray) -> bool:
        """Detect simple bullish candlestick pattern"""

        if len(closes) < 3:
            return False

        try:
            # Two consecutive green candles with higher lows
            candle1_green = closes[-2] > opens[-2]
            candle2_green = closes[-1] > opens[-1]
            higher_low = lows[-1] > lows[-2]

            return candle1_green and candle2_green and higher_low
        except:
            return False

    def _detect_bearish_pattern(self, opens: np.ndarray, highs: np.ndarray,
                                lows: np.ndarray, closes: np.ndarray) -> bool:
        """Detect simple bearish candlestick pattern"""

        if len(closes) < 3:
            return False

        try:
            # Two consecutive red candles with lower highs
            candle1_red = closes[-2] < opens[-2]
            candle2_red = closes[-1] < opens[-1]
            lower_high = highs[-1] < highs[-2]

            return candle1_red and candle2_red and lower_high
        except:
            return False

    def _error_response(self, error_msg: str) -> Dict:
        """Return standardized error response"""
        return {
            'timestamp': datetime.now().isoformat(),
            'signal': 'hold',
            'reason': f'validation_error: {error_msg}',
            'price': None,
            'indicators': {},
            'signals': {}
        }
