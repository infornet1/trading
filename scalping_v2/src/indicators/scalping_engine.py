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

            # Generate trading signals
            signals = self._generate_signals(
                current_price=current_price,
                indicators=indicators,
                price_action=price_action
            )

            # Build result
            result = {
                'timestamp': datetime.now().isoformat(),
                'price': round(current_price, 2),
                'indicators': indicators,
                'price_action': price_action,
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
        """Calculate all technical indicators"""

        current_price = closes[-1]

        # 1. EMA Trend Indicators
        ema_micro = self._calculate_ema(closes, self.ema_micro)
        ema_fast = self._calculate_ema(closes, self.ema_fast)
        ema_slow = self._calculate_ema(closes, self.ema_slow)

        # 2. RSI Momentum
        rsi = self._calculate_rsi(closes, self.rsi_period)

        # 3. Stochastic Oscillator
        stoch_k, stoch_d = self._calculate_stochastic(highs, lows, closes, self.stoch_period, self.stoch_smooth)

        # 4. Volume Analysis
        volume_sma = self._calculate_sma(volumes, self.volume_ma_period)
        volume_ratio = current_volume / volume_sma[-1] if volume_sma[-1] > 0 else 1.0

        # 5. ATR for Volatility
        atr = self._calculate_atr(highs, lows, closes, self.atr_period)
        atr_pct = (atr[-1] / current_price) if current_price > 0 else 0

        return {
            'ema_micro': round(ema_micro[-1], 2),
            'ema_fast': round(ema_fast[-1], 2),
            'ema_slow': round(ema_slow[-1], 2),
            'rsi': round(rsi[-1], 2),
            'stoch_k': round(stoch_k[-1], 2),
            'stoch_d': round(stoch_d[-1], 2),
            'volume_ratio': round(volume_ratio, 2),
            'atr': round(atr[-1], 2),
            'atr_pct': round(atr_pct * 100, 3)  # as percentage
        }

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
        """Generate trading signals based on indicators and price action"""

        signals = {}

        # Extract indicators
        ema_micro = indicators['ema_micro']
        ema_fast = indicators['ema_fast']
        ema_slow = indicators['ema_slow']
        rsi = indicators['rsi']
        stoch_k = indicators['stoch_k']
        stoch_d = indicators['stoch_d']
        volume_ratio = indicators['volume_ratio']
        atr_pct = indicators['atr_pct']

        # Trend conditions
        bullish_trend = ema_micro > ema_fast > ema_slow
        bearish_trend = ema_micro < ema_fast < ema_slow

        # Momentum conditions
        rsi_oversold = rsi < self.rsi_oversold
        rsi_overbought = rsi > self.rsi_overbought
        stoch_bullish = stoch_k > stoch_d and stoch_k < 80
        stoch_bearish = stoch_k < stoch_d and stoch_k > 20

        # Volume confirmation
        volume_ok = volume_ratio > self.min_volume_ratio

        # Price action
        near_support = price_action.get('near_support', False)
        near_resistance = price_action.get('near_resistance', False)
        bullish_pattern = price_action.get('bullish_pattern', False)
        bearish_pattern = price_action.get('bearish_pattern', False)

        # LONG SIGNAL CONDITIONS
        long_conditions = []

        if bullish_trend and stoch_bullish and volume_ok:
            long_conditions.append(("trend_momentum", 0.7))

        if rsi_oversold and near_support and bullish_pattern:
            long_conditions.append(("oversold_bounce", 0.8))

        if ema_micro > ema_fast and volume_ratio > 1.5:
            long_conditions.append(("ema_crossover", 0.6))

        # SHORT SIGNAL CONDITIONS
        short_conditions = []

        if bearish_trend and stoch_bearish and volume_ok:
            short_conditions.append(("trend_momentum", 0.7))

        if rsi_overbought and near_resistance and bearish_pattern:
            short_conditions.append(("overbought_rejection", 0.8))

        if ema_micro < ema_fast and volume_ratio > 1.5:
            short_conditions.append(("ema_crossover", 0.6))

        # Calculate confidence and create signals
        if long_conditions:
            confidence = sum(conf for _, conf in long_conditions) / len(long_conditions)
            confidence = self._adjust_confidence(confidence, 'long')

            if confidence >= self.min_confidence:
                stop_loss = current_price * (1 - self.max_loss_pct)
                take_profit = current_price * (1 + self.target_profit_pct)

                signals['long'] = {
                    'confidence': round(confidence, 3),
                    'stop_loss': round(stop_loss, 2),
                    'take_profit': round(take_profit, 2),
                    'conditions': [cond for cond, _ in long_conditions],
                    'risk_reward': round(self.target_profit_pct / self.max_loss_pct, 2)
                }

        if short_conditions:
            confidence = sum(conf for _, conf in short_conditions) / len(short_conditions)
            confidence = self._adjust_confidence(confidence, 'short')

            if confidence >= self.min_confidence:
                stop_loss = current_price * (1 + self.max_loss_pct)
                take_profit = current_price * (1 - self.target_profit_pct)

                signals['short'] = {
                    'confidence': round(confidence, 3),
                    'stop_loss': round(stop_loss, 2),
                    'take_profit': round(take_profit, 2),
                    'conditions': [cond for cond, _ in short_conditions],
                    'risk_reward': round(self.target_profit_pct / self.max_loss_pct, 2)
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
        """Calculate Exponential Moving Average"""
        ema = np.zeros_like(data, dtype=float)
        ema[0] = data[0]
        multiplier = 2 / (period + 1)

        for i in range(1, len(data)):
            ema[i] = (data[i] * multiplier) + (ema[i-1] * (1 - multiplier))

        return ema

    def _calculate_sma(self, data: np.ndarray, period: int) -> np.ndarray:
        """Calculate Simple Moving Average"""
        sma = np.convolve(data, np.ones(period)/period, mode='valid')
        # Pad beginning with NaN
        return np.concatenate([np.full(period-1, np.nan), sma])

    def _calculate_rsi(self, closes: np.ndarray, period: int) -> np.ndarray:
        """Calculate Relative Strength Index"""
        deltas = np.diff(closes)
        seed = deltas[:period]
        up = seed[seed >= 0].sum() / period
        down = -seed[seed < 0].sum() / period
        rs = up / down if down != 0 else 0
        rsi = np.zeros_like(closes)
        rsi[:period] = 100. - 100. / (1. + rs)

        for i in range(period, len(closes)):
            delta = deltas[i-1]
            if delta > 0:
                upval = delta
                downval = 0.
            else:
                upval = 0.
                downval = -delta

            up = (up * (period - 1) + upval) / period
            down = (down * (period - 1) + downval) / period
            rs = up / down if down != 0 else 0
            rsi[i] = 100. - 100. / (1. + rs)

        return rsi

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
