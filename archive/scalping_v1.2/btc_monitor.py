#!/usr/bin/env python3
"""
Bitcoin Scalping Monitor
Monitors BTC/USD price and provides alerts for trading opportunities
"""

import requests
import time
import json
from datetime import datetime
from collections import deque
import statistics
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Import email notifier (optional)
try:
    from btc_email_notifier import BTCEmailNotifier
    EMAIL_ENABLED = True
except ImportError:
    EMAIL_ENABLED = False
    print("⚠️  Email notifications disabled (btc_email_notifier not found)")

# Import signal tracker (optional)
try:
    from signal_tracker import SignalTracker
    TRACKING_ENABLED = True
except ImportError:
    TRACKING_ENABLED = False
    print("⚠️  Signal tracking disabled (signal_tracker not found)")

class BTCMonitor:
    def __init__(self, config_file='config.json', enable_email=True, enable_tracking=True):
        """Initialize the Bitcoin monitor"""
        self.load_config(config_file)
        self.price_history = deque(maxlen=200)  # Store last 200 prices
        self.alerts = []
        self.price_tracker = {}  # Track price highs/lows for signal outcome checking
        self.last_signals = {}  # Track last signal time for cooldown (format: {signal_type: timestamp})

        # Generate unique session ID for this monitoring session
        import uuid
        self.session_id = datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + str(uuid.uuid4())[:8]

        # ATR-related variables
        self.current_atr = None
        self.last_candle_fetch = 0  # Timestamp of last candle fetch
        self.candle_cache = []  # Cache candles to reduce API calls

        # Initialize email notifier if enabled
        self.email_notifier = None
        if enable_email and EMAIL_ENABLED:
            try:
                self.email_notifier = BTCEmailNotifier()
                print("✅ Email notifications enabled")
            except Exception as e:
                print(f"⚠️  Email notifications disabled: {e}")
                self.email_notifier = None

        # Initialize signal tracker if enabled
        self.signal_tracker = None
        if enable_tracking and TRACKING_ENABLED:
            try:
                self.signal_tracker = SignalTracker()
                print("✅ Signal tracking enabled")
            except Exception as e:
                print(f"⚠️  Signal tracking disabled: {e}")
                self.signal_tracker = None

        # Fetch initial candles for ATR if enabled
        if self.config.get('use_atr_targets', True):
            self._update_atr()
            if self.current_atr:
                atr_pct = (self.current_atr / 112000) * 100  # Approximate for display
                print(f"✅ ATR initialized: ${self.current_atr:.2f} ({atr_pct:.3f}%)")
            else:
                print("⚠️  ATR calculation failed, will use fixed targets")

    def load_config(self, config_file):
        """Load configuration from JSON file"""
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
        except FileNotFoundError:
            # Default configuration
            config = {
                "exchange": "binance",
                "symbol": "BTCUSDT",
                "interval": 5,  # seconds between checks
                "rsi_period": 14,
                "rsi_oversold": 30,
                "rsi_overbought": 70,
                "ema_fast": 5,
                "ema_slow": 15,
                "support_resistance_periods": 50,
                "price_change_alert": 0.5,  # Alert on 0.5% rapid change
                "volume_spike_multiplier": 2.0
            }

        self.config = config

    def fetch_price_binance(self):
        """Fetch current BTC price from Binance"""
        try:
            # Try Binance US API first (more accessible)
            url = "https://api.binance.us/api/v3/ticker/24hr?symbol=BTCUSD"
            response = requests.get(url, timeout=5)
            data = response.json()

            if 'lastPrice' in data:
                return {
                    'price': float(data['lastPrice']),
                    'volume': float(data['volume']),
                    'high_24h': float(data['highPrice']),
                    'low_24h': float(data['lowPrice']),
                    'price_change_24h': float(data['priceChangePercent']),
                    'timestamp': datetime.now()
                }
        except Exception as e:
            print(f"Error fetching from Binance: {e}")

        return None

    def fetch_price_coinbase(self):
        """Fetch current BTC price from Coinbase"""
        try:
            url = "https://api.coinbase.com/v2/prices/BTC-USD/spot"
            response = requests.get(url, timeout=5)
            data = response.json()

            return {
                'price': float(data['data']['amount']),
                'volume': None,
                'timestamp': datetime.now()
            }
        except Exception as e:
            print(f"Error fetching from Coinbase: {e}")
            return None

    def fetch_price_coingecko(self):
        """Fetch current BTC price from CoinGecko (no geo-restrictions)"""
        try:
            url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true&include_24hr_vol=true"
            response = requests.get(url, timeout=5)
            data = response.json()

            btc_data = data.get('bitcoin', {})
            price = btc_data.get('usd')
            change_24h = btc_data.get('usd_24h_change')

            if price:
                return {
                    'price': float(price),
                    'volume': None,
                    'price_change_24h': float(change_24h) if change_24h else None,
                    'timestamp': datetime.now()
                }
        except Exception as e:
            print(f"Error fetching from CoinGecko: {e}")
            return None

    def fetch_price(self):
        """Fetch price from configured exchange with fallback"""
        data = None

        # Try primary exchange
        if self.config.get('exchange') == 'binance':
            data = self.fetch_price_binance()
        elif self.config.get('exchange') == 'coinbase':
            data = self.fetch_price_coinbase()
        elif self.config.get('exchange') == 'coingecko':
            data = self.fetch_price_coingecko()

        # Fallback to CoinGecko if primary fails (most reliable, no restrictions)
        if not data:
            data = self.fetch_price_coingecko()

        # Last resort: try Coinbase
        if not data:
            data = self.fetch_price_coinbase()

        return data

    def calculate_rsi(self, prices, period=14):
        """Calculate Relative Strength Index"""
        if len(prices) < period + 1:
            return None

        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]

        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def calculate_ema(self, prices, period):
        """Calculate Exponential Moving Average"""
        if len(prices) < period:
            return None

        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period

        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema

        return ema

    def _update_atr(self):
        """Update ATR value by fetching recent candles (called periodically)"""
        current_time = time.time()

        # Only fetch candles every 60 seconds to reduce API calls
        if current_time - self.last_candle_fetch < 60:
            return

        interval = self.config.get('atr_timeframe', '1m')
        period = self.config.get('atr_period', 14)

        candles = self.fetch_candles_binance(interval=interval, limit=period + 10)

        if candles:
            self.candle_cache = candles
            self.current_atr = self.calculate_atr(candles, period=period)
            self.last_candle_fetch = current_time

            if self.current_atr:
                logging.debug(f"ATR updated: ${self.current_atr:.2f}")

    def calculate_atr(self, candles, period=14):
        """
        Calculate Average True Range (ATR) from candle data

        Args:
            candles: List of candles with 'high', 'low', 'close' keys
            period: Number of periods to average (default: 14)

        Returns:
            float: ATR value or None if insufficient data
        """
        if len(candles) < period + 1:
            return None

        true_ranges = []

        for i in range(1, len(candles)):
            high = candles[i]['high']
            low = candles[i]['low']
            prev_close = candles[i-1]['close']

            # True Range = max of:
            # 1. High - Low
            # 2. |High - Previous Close|
            # 3. |Low - Previous Close|
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)

        # Calculate ATR as average of last 'period' true ranges
        if len(true_ranges) >= period:
            atr = sum(true_ranges[-period:]) / period
        else:
            atr = sum(true_ranges) / len(true_ranges)

        return atr

    def fetch_candles_binance(self, symbol='BTCUSDT', interval='1m', limit=50):
        """
        Fetch recent candles from BingX (Binance geo-blocked) for ATR calculation

        Args:
            symbol: Trading pair (default: BTCUSDT or BTC-USDT)
            interval: Candle interval (1m, 5m, 15m, etc.)
            limit: Number of candles to fetch

        Returns:
            list: List of candle dicts or None on error
        """
        try:
            # Convert symbol format for BingX (BTC-USDT instead of BTCUSDT)
            if 'USDT' in symbol and '-' not in symbol:
                symbol = symbol.replace('USDT', '-USDT')

            # BingX kline endpoint
            url = "https://open-api.bingx.com/openApi/swap/v3/quote/klines"
            params = {
                'symbol': symbol,
                'interval': interval,
                'limit': limit
            }

            response = requests.get(url, params=params, timeout=10)

            if response.status_code != 200:
                # Fallback: try Binance (might work from some locations)
                try:
                    url_binance = "https://api.binance.com/api/v3/klines"
                    params_binance = {
                        'symbol': symbol.replace('-', ''),
                        'interval': interval,
                        'limit': limit
                    }
                    response = requests.get(url_binance, params=params_binance, timeout=10)
                    if response.status_code == 200:
                        raw_candles = response.json()
                        candles = []
                        for candle in raw_candles:
                            candles.append({
                                'timestamp': candle[0],
                                'open': float(candle[1]),
                                'high': float(candle[2]),
                                'low': float(candle[3]),
                                'close': float(candle[4]),
                                'volume': float(candle[5])
                            })
                        return candles
                except:
                    pass
                return None

            data = response.json()

            if data.get('code') != 0 or 'data' not in data:
                logging.error(f"BingX API error: {data.get('msg')}")
                return None

            raw_candles = data['data']

            # Parse BingX candles into dict format
            candles = []
            for candle in raw_candles:
                candles.append({
                    'timestamp': candle['time'],
                    'open': float(candle['open']),
                    'high': float(candle['high']),
                    'low': float(candle['low']),
                    'close': float(candle['close']),
                    'volume': float(candle['volume'])
                })

            return candles

        except Exception as e:
            logging.error(f"Error fetching candles: {e}")
            return None

    def calculate_dynamic_targets(self, entry_price, direction, atr):
        """
        Calculate dynamic take-profit and stop-loss based on ATR

        Args:
            entry_price: Entry price for the trade
            direction: 'LONG' or 'SHORT'
            atr: Current ATR value

        Returns:
            tuple: (target_price, stop_price, target_pct, stop_pct, atr_pct)
        """
        # Get config values (with defaults)
        use_atr = self.config.get('use_atr_targets', True)

        # If ATR disabled, use fixed targets
        if not use_atr or atr is None:
            if direction == 'LONG':
                target = entry_price * 1.005  # +0.5%
                stop = entry_price * 0.997    # -0.3%
            else:  # SHORT
                target = entry_price * 0.995  # -0.5%
                stop = entry_price * 1.003    # +0.3%

            target_pct = abs(target - entry_price) / entry_price * 100
            stop_pct = abs(entry_price - stop) / entry_price * 100

            return target, stop, target_pct, stop_pct, 0.0

        # ATR-based dynamic targets
        tp_multiplier = self.config.get('atr_tp_multiplier', 1.5)
        sl_multiplier = self.config.get('atr_sl_multiplier', 0.75)

        # Calculate raw targets
        if direction == 'LONG':
            target = entry_price + (atr * tp_multiplier)
            stop = entry_price - (atr * sl_multiplier)
        else:  # SHORT
            target = entry_price - (atr * tp_multiplier)
            stop = entry_price + (atr * sl_multiplier)

        # Calculate percentages
        target_pct = abs(target - entry_price) / entry_price * 100
        stop_pct = abs(entry_price - stop) / entry_price * 100
        atr_pct = (atr / entry_price) * 100

        # Apply min/max limits for safety
        min_target = self.config.get('min_target_pct', 0.25)
        max_target = self.config.get('max_target_pct', 2.0)
        min_stop = self.config.get('min_stop_pct', 0.15)
        max_stop = self.config.get('max_stop_pct', 1.2)

        target_pct = max(min_target, min(target_pct, max_target))
        stop_pct = max(min_stop, min(stop_pct, max_stop))

        # Recalculate prices with limited percentages
        if direction == 'LONG':
            target = entry_price * (1 + target_pct / 100)
            stop = entry_price * (1 - stop_pct / 100)
        else:
            target = entry_price * (1 - target_pct / 100)
            stop = entry_price * (1 + stop_pct / 100)

        return target, stop, target_pct, stop_pct, atr_pct

    def find_support_resistance(self, prices, periods=50):
        """Find support and resistance levels"""
        if len(prices) < periods:
            return None, None

        recent_prices = list(prices)[-periods:]
        support = min(recent_prices)
        resistance = max(recent_prices)

        return support, resistance

    def calculate_trend_emas(self, prices):
        """
        Calculate trend EMAs (50 and 200 period) for trend detection

        Args:
            prices: List of prices

        Returns:
            tuple: (ema_50, ema_200) or (None, None) if insufficient data
        """
        ema_50_period = self.config.get('ema_trend_medium', 50)
        ema_200_period = self.config.get('ema_trend_long', 200)

        ema_50 = self.calculate_ema(prices, ema_50_period) if len(prices) >= ema_50_period else None
        ema_200 = self.calculate_ema(prices, ema_200_period) if len(prices) >= ema_200_period else None

        return ema_50, ema_200

    def determine_trend(self, current_price, ema_50, ema_200):
        """
        Determine market trend based on price position relative to EMAs

        Args:
            current_price: Current BTC price
            ema_50: 50-period EMA value
            ema_200: 200-period EMA value

        Returns:
            str: 'BULLISH', 'BEARISH', 'NEUTRAL', or 'UNKNOWN'
        """
        if ema_50 is None or ema_200 is None:
            return 'UNKNOWN'

        # Strong trend: price on same side of both EMAs
        if current_price > ema_50 and current_price > ema_200:
            return 'BULLISH'
        elif current_price < ema_50 and current_price < ema_200:
            return 'BEARISH'
        else:
            # Price between EMAs = uncertain/transitioning
            return 'NEUTRAL'

    def should_take_signal(self, signal_type, current_price, ema_50, ema_200):
        """
        Determine if signal should be taken based on trend filter

        Args:
            signal_type: Type of signal (e.g., 'RSI_OVERSOLD', 'NEAR_RESISTANCE')
            current_price: Current BTC price
            ema_50: 50-period EMA
            ema_200: 200-period EMA

        Returns:
            tuple: (should_take: bool, reason: str)
        """
        # Check if trend filter is enabled
        if not self.config.get('use_trend_filter', True):
            return True, "Trend filter disabled"

        # Determine signal direction
        long_signals = ['RSI_OVERSOLD', 'NEAR_SUPPORT', 'EMA_BULLISH_CROSS']
        short_signals = ['RSI_OVERBOUGHT', 'NEAR_RESISTANCE', 'EMA_BEARISH_CROSS']

        is_long_signal = signal_type in long_signals
        is_short_signal = signal_type in short_signals

        # Get current trend
        trend = self.determine_trend(current_price, ema_50, ema_200)

        # Apply trend filter rules
        if trend == 'UNKNOWN':
            # Not enough data for trend, allow all signals
            return True, "Insufficient trend data"

        elif trend == 'BULLISH':
            # In uptrend, only take LONG signals
            if is_long_signal:
                return True, "LONG signal aligned with BULLISH trend"
            elif is_short_signal:
                return False, "SHORT signal blocked - fighting BULLISH trend"

        elif trend == 'BEARISH':
            # In downtrend, only take SHORT signals
            if is_short_signal:
                return True, "SHORT signal aligned with BEARISH trend"
            elif is_long_signal:
                return False, "LONG signal blocked - fighting BEARISH trend"

        elif trend == 'NEUTRAL':
            # Uncertain trend, allow both directions (range-bound)
            return True, f"Signal allowed in NEUTRAL/ranging market"

        return True, "Default allow"

    def check_alerts(self, data):
        """Check for trading opportunities and generate alerts"""
        if not data:
            return [], {}

        alerts = []
        current_price = data['price']

        # Store price in history
        self.price_history.append(current_price)

        if len(self.price_history) < self.config['rsi_period'] + 1:
            return [], {}  # Not enough data yet

        # Calculate indicators
        prices = list(self.price_history)
        rsi = self.calculate_rsi(prices, self.config['rsi_period'])
        ema_fast = self.calculate_ema(prices, self.config['ema_fast'])
        ema_slow = self.calculate_ema(prices, self.config['ema_slow'])
        support, resistance = self.find_support_resistance(
            prices,
            self.config['support_resistance_periods']
        )

        # Calculate trend EMAs (50 and 200)
        ema_50, ema_200 = self.calculate_trend_emas(prices)
        trend = self.determine_trend(current_price, ema_50, ema_200)

        # RSI Alerts
        if rsi and rsi <= self.config['rsi_oversold']:
            alerts.append({
                'type': 'RSI_OVERSOLD',
                'severity': 'HIGH',
                'message': f'RSI is oversold at {rsi:.2f} - Potential BUY opportunity',
                'price': current_price,
                'rsi': rsi
            })

        if rsi and rsi >= self.config['rsi_overbought']:
            alerts.append({
                'type': 'RSI_OVERBOUGHT',
                'severity': 'HIGH',
                'message': f'RSI is overbought at {rsi:.2f} - Potential SELL opportunity',
                'price': current_price,
                'rsi': rsi
            })

        # EMA Crossover
        if ema_fast and ema_slow:
            if len(self.price_history) >= self.config['ema_slow'] + 1:
                prev_prices = prices[:-1]
                prev_ema_fast = self.calculate_ema(prev_prices, self.config['ema_fast'])
                prev_ema_slow = self.calculate_ema(prev_prices, self.config['ema_slow'])

                # Bullish crossover
                if prev_ema_fast <= prev_ema_slow and ema_fast > ema_slow:
                    alerts.append({
                        'type': 'EMA_BULLISH_CROSS',
                        'severity': 'MEDIUM',
                        'message': f'Bullish EMA crossover - Potential BUY signal',
                        'price': current_price,
                        'ema_fast': ema_fast,
                        'ema_slow': ema_slow
                    })

                # Bearish crossover
                if prev_ema_fast >= prev_ema_slow and ema_fast < ema_slow:
                    alerts.append({
                        'type': 'EMA_BEARISH_CROSS',
                        'severity': 'MEDIUM',
                        'message': f'Bearish EMA crossover - Potential SELL signal',
                        'price': current_price,
                        'ema_fast': ema_fast,
                        'ema_slow': ema_slow
                    })

        # Support/Resistance Alerts
        if support and resistance:
            # Near support (within 0.3%)
            if abs(current_price - support) / support <= 0.003:
                alerts.append({
                    'type': 'NEAR_SUPPORT',
                    'severity': 'MEDIUM',
                    'message': f'Price near support at ${support:.2f} - Potential BUY opportunity',
                    'price': current_price,
                    'support': support
                })

            # Near resistance (within 0.3%)
            if abs(current_price - resistance) / resistance <= 0.003:
                alerts.append({
                    'type': 'NEAR_RESISTANCE',
                    'severity': 'MEDIUM',
                    'message': f'Price near resistance at ${resistance:.2f} - Potential SELL opportunity',
                    'price': current_price,
                    'resistance': resistance
                })

        # Rapid price change
        if len(self.price_history) >= 10:
            price_10_ago = prices[-10]
            change_pct = ((current_price - price_10_ago) / price_10_ago) * 100

            if abs(change_pct) >= self.config['price_change_alert']:
                direction = "UP" if change_pct > 0 else "DOWN"
                alerts.append({
                    'type': 'RAPID_PRICE_CHANGE',
                    'severity': 'HIGH',
                    'message': f'Rapid price movement {direction}: {abs(change_pct):.2f}% in last 50 seconds',
                    'price': current_price,
                    'change_pct': change_pct
                })

        return alerts, {
            'rsi': rsi,
            'ema_fast': ema_fast,
            'ema_slow': ema_slow,
            'support': support,
            'resistance': resistance,
            'ema_50': ema_50,
            'ema_200': ema_200,
            'trend': trend
        }

    def display_status(self, data, indicators, alerts):
        """Display current status and alerts"""
        print("\n" + "="*80)
        print(f"⏰ {data['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80)
        print(f"\n💰 BTC/USD Price: ${data['price']:,.2f}")

        if 'price_change_24h' in data and data['price_change_24h'] is not None:
            change_color = "📈" if data['price_change_24h'] >= 0 else "📉"
            print(f"{change_color} 24h Change: {data['price_change_24h']:.2f}%")

        if 'high_24h' in data and data['high_24h'] is not None:
            print(f"   24h High: ${data['high_24h']:,.2f} | Low: ${data['low_24h']:,.2f}")

        print(f"\n📊 Technical Indicators:")
        if indicators.get('rsi'):
            rsi_status = "🔴 Overbought" if indicators['rsi'] >= 70 else "🟢 Oversold" if indicators['rsi'] <= 30 else "🟡 Neutral"
            print(f"   RSI({self.config['rsi_period']}): {indicators['rsi']:.2f} {rsi_status}")
        elif len(self.price_history) < self.config['rsi_period'] + 1:
            print(f"   Collecting data... ({len(self.price_history)}/{self.config['rsi_period'] + 1} prices needed)")

        if indicators.get('ema_fast') and indicators.get('ema_slow'):
            trend = "🔵 Bullish" if indicators['ema_fast'] > indicators['ema_slow'] else "🔴 Bearish"
            print(f"   EMA({self.config['ema_fast']}): ${indicators['ema_fast']:,.2f}")
            print(f"   EMA({self.config['ema_slow']}): ${indicators['ema_slow']:,.2f} - {trend}")

        if indicators.get('support') and indicators.get('resistance'):
            support_dist = ((data['price'] - indicators['support']) / indicators['support']) * 100
            resistance_dist = ((indicators['resistance'] - data['price']) / data['price']) * 100
            print(f"   Support: ${indicators['support']:,.2f} ({support_dist:.2f}% below)")
            print(f"   Resistance: ${indicators['resistance']:,.2f} ({resistance_dist:.2f}% above)")

        # Show trend filter status
        if indicators.get('trend'):
            trend = indicators['trend']
            if trend == 'BULLISH':
                trend_icon = "🟢"
                trend_msg = "BULLISH - Only taking LONG signals"
            elif trend == 'BEARISH':
                trend_icon = "🔴"
                trend_msg = "BEARISH - Only taking SHORT signals"
            elif trend == 'NEUTRAL':
                trend_icon = "🟡"
                trend_msg = "NEUTRAL - Taking both LONG & SHORT"
            else:
                trend_icon = "⚪"
                trend_msg = "UNKNOWN - Collecting data"

            print(f"\n📈 Market Trend: {trend_icon} {trend_msg}")

            if indicators.get('ema_50'):
                print(f"   EMA(50): ${indicators['ema_50']:,.2f}")
            if indicators.get('ema_200'):
                print(f"   EMA(200): ${indicators['ema_200']:,.2f}")

        if alerts:
            # Check for conflicting signals
            buy_alerts = [a for a in alerts if a['type'] in ['RSI_OVERSOLD', 'NEAR_SUPPORT', 'EMA_BULLISH_CROSS']]
            sell_alerts = [a for a in alerts if a['type'] in ['RSI_OVERBOUGHT', 'NEAR_RESISTANCE', 'EMA_BEARISH_CROSS']]
            has_conflict = len(buy_alerts) > 0 and len(sell_alerts) > 0

            if has_conflict:
                print(f"\n⚠️  CONFLICTING SIGNALS - DO NOT TRADE! ⚠️")
                print(f"{'='*80}")
                print(f"❌ Both BUY and SELL signals detected - price squeezed in range")
                print(f"❌ Not enough room to profit - wait for clear breakout")
                print(f"{'='*80}")

            print(f"\n🚨 ALERTS ({len(alerts)}):")
            for alert in alerts:
                severity_icon = "🔴" if alert['severity'] == 'HIGH' else "🟡"
                print(f"   {severity_icon} [{alert['type']}] {alert['message']}")

            if has_conflict:
                print(f"\n⛔ RECOMMENDATION: SIT OUT - Wait for clear direction")
        else:
            print(f"\n✅ No alerts - Market is stable")

        print("="*80)

    def should_log_signal(self, signal_type, cooldown_minutes=5):
        """
        Check if a signal should be logged based on cooldown period.
        Prevents duplicate signals from being logged too frequently.

        Args:
            signal_type: Type of signal (e.g., 'RSI_OVERSOLD', 'NEAR_SUPPORT')
            cooldown_minutes: Minimum minutes between same signal types (default: 5)

        Returns:
            bool: True if signal should be logged, False if still in cooldown
        """
        now = datetime.now()

        # Check if this signal type was recently logged
        if signal_type in self.last_signals:
            last_time = self.last_signals[signal_type]
            time_diff = (now - last_time).total_seconds() / 60  # Convert to minutes

            if time_diff < cooldown_minutes:
                # Still in cooldown period
                return False

        # Update last signal time for this type
        self.last_signals[signal_type] = now
        return True

    def run(self):
        """Main monitoring loop"""
        print("🚀 Bitcoin Scalping Monitor Started")
        print(f"📍 Exchange: {self.config['exchange'].upper()}")
        print(f"⏱️  Update interval: {self.config['interval']} seconds")
        if self.email_notifier:
            print(f"📧 Email notifications: ENABLED (to {self.email_notifier.recipient_email})")
        else:
            print(f"📧 Email notifications: DISABLED")
        if self.signal_tracker:
            print(f"📊 Signal tracking: ENABLED (database: signals.db)")
            print(f"📈 View dashboard: python dashboard.py (then visit http://localhost:5800)")
        else:
            print(f"📊 Signal tracking: DISABLED")
        print(f"⌨️  Press Ctrl+C to stop\n")

        try:
            while True:
                data = self.fetch_price()

                if data:
                    current_price = data['price']

                    # Update per-signal price highs/lows for outcome checking
                    # Each tracked signal gets its own high/low since it was created
                    for signal_id in list(self.price_tracker.keys()):
                        if isinstance(signal_id, int):  # Only process signal IDs (integers)
                            if 'highest_price' not in self.price_tracker[signal_id]:
                                # Initialize if not present (for existing tracked signals)
                                self.price_tracker[signal_id]['highest_price'] = current_price
                                self.price_tracker[signal_id]['lowest_price'] = current_price
                            else:
                                # Update highs/lows for this signal
                                self.price_tracker[signal_id]['highest_price'] = max(
                                    self.price_tracker[signal_id]['highest_price'],
                                    current_price
                                )
                                self.price_tracker[signal_id]['lowest_price'] = min(
                                    self.price_tracker[signal_id]['lowest_price'],
                                    current_price
                                )

                    alerts, indicators = self.check_alerts(data)
                    self.display_status(data, indicators, alerts)

                    # Check for conflicting signals
                    buy_alerts = [a for a in alerts if a['type'] in ['RSI_OVERSOLD', 'NEAR_SUPPORT', 'EMA_BULLISH_CROSS']]
                    sell_alerts = [a for a in alerts if a['type'] in ['RSI_OVERBOUGHT', 'NEAR_RESISTANCE', 'EMA_BEARISH_CROSS']]
                    has_conflict = len(buy_alerts) > 0 and len(sell_alerts) > 0

                    # Update ATR periodically (if ATR targets enabled)
                    if self.config.get('use_atr_targets', True):
                        self._update_atr()

                    # Log signals to tracker (with cooldown to prevent duplicates)
                    if alerts and self.signal_tracker:
                        logged_count = 0
                        skipped_count = 0
                        filtered_count = 0
                        for alert in alerts:
                            # Check cooldown - only log if not recently logged
                            if self.should_log_signal(alert['type'], cooldown_minutes=5):
                                # Check trend filter - only take signals aligned with trend
                                should_take, filter_reason = self.should_take_signal(
                                    alert['type'],
                                    current_price,
                                    indicators.get('ema_50'),
                                    indicators.get('ema_200')
                                )

                                if not should_take:
                                    filtered_count += 1
                                    logging.info(f"🚫 Filtered {alert['type']}: {filter_reason}")
                                    continue

                                try:
                                    # Determine signal direction
                                    if alert['type'] in ['RSI_OVERSOLD', 'NEAR_SUPPORT', 'EMA_BULLISH_CROSS']:
                                        direction = 'LONG'
                                    elif alert['type'] in ['RSI_OVERBOUGHT', 'NEAR_RESISTANCE', 'EMA_BEARISH_CROSS']:
                                        direction = 'SHORT'
                                    else:
                                        direction = 'NEUTRAL'

                                    # Calculate dynamic targets
                                    if direction != 'NEUTRAL':
                                        target, stop, target_pct, stop_pct, atr_pct = self.calculate_dynamic_targets(
                                            current_price, direction, self.current_atr
                                        )

                                        # Add target info to indicators for logging
                                        indicators['atr'] = self.current_atr
                                        indicators['atr_pct'] = atr_pct
                                        indicators['target'] = target
                                        indicators['stop'] = stop
                                        indicators['target_pct'] = target_pct
                                        indicators['stop_pct'] = stop_pct
                                    else:
                                        target = None
                                        stop = None

                                    # Calculate signal quality using tracker's method
                                    signal_quality = self.signal_tracker.calculate_signal_quality(
                                        alert, indicators, has_conflict, strategy_name='SCALPING'
                                    )

                                    # Build entry reason
                                    entry_reason_parts = [alert['type']]
                                    if indicators.get('trend'):
                                        entry_reason_parts.append(f"Trend: {indicators['trend']}")
                                    if indicators.get('rsi'):
                                        entry_reason_parts.append(f"RSI: {indicators['rsi']:.1f}")
                                    entry_reason = " | ".join(entry_reason_parts)

                                    # Build tags
                                    tags = [alert['severity'], direction]
                                    if indicators.get('atr'):
                                        tags.append('ATR_DYNAMIC')
                                    else:
                                        tags.append('FIXED_TARGETS')
                                    if has_conflict:
                                        tags.append('CONFLICTED')

                                    # Get market condition from trend
                                    market_condition = indicators.get('trend', 'UNKNOWN')

                                    signal_id = self.signal_tracker.log_signal(
                                        alert, data, indicators, has_conflict,
                                        suggested_stop=stop, suggested_target=target,
                                        strategy_name='SCALPING',
                                        strategy_version='v1.2',
                                        timeframe='5s',
                                        signal_quality=signal_quality,
                                        trade_group_id=None,  # Can be used to group related signals later
                                        entry_reason=entry_reason,
                                        tags=tags,
                                        market_condition=market_condition,
                                        session_id=self.session_id
                                    )

                                    # Store signal ID for outcome checking with per-signal tracking
                                    if signal_id not in self.price_tracker:
                                        self.price_tracker[signal_id] = {
                                            'start_price': current_price,
                                            'start_time': datetime.now(),
                                            'highest_price': current_price,
                                            'lowest_price': current_price
                                        }
                                    logged_count += 1
                                except Exception as e:
                                    print(f"⚠️  Failed to log signal: {e}")
                            else:
                                skipped_count += 1

                        # Show feedback
                        if filtered_count > 0:
                            print(f"   🚫 Filtered {filtered_count} signal(s) (trend filter - wrong direction)")
                        if skipped_count > 0:
                            print(f"   ⏳ Skipped {skipped_count} duplicate signal(s) (cooldown active)")
                        if logged_count > 0:
                            print(f"   📝 Logged {logged_count} new signal(s) to database")

                    # Check outcomes of previous signals
                    if self.signal_tracker:
                        try:
                            unchecked = self.signal_tracker.get_unchecked_signals(max_age_hours=2)
                            checked_count = 0

                            for sig in unchecked:
                                sig_id = sig['id']

                                # Get per-signal highs/lows, or use current price if not tracked yet
                                if sig_id in self.price_tracker:
                                    price_high = self.price_tracker[sig_id].get('highest_price', current_price)
                                    price_low = self.price_tracker[sig_id].get('lowest_price', current_price)
                                else:
                                    # Signal exists in DB but not yet tracked - start tracking it now
                                    self.price_tracker[sig_id] = {
                                        'start_price': current_price,
                                        'start_time': datetime.now(),
                                        'highest_price': current_price,
                                        'lowest_price': current_price
                                    }
                                    price_high = current_price
                                    price_low = current_price

                                outcome = self.signal_tracker.check_signal_outcome(
                                    sig_id,
                                    current_price,
                                    price_high,
                                    price_low
                                )

                                if outcome and outcome != 'PENDING':
                                    print(f"   📊 Signal {sig_id} outcome: {outcome}")
                                    checked_count += 1

                                    # Remove from tracker once outcome determined
                                    if sig_id in self.price_tracker:
                                        del self.price_tracker[sig_id]

                            if checked_count > 0:
                                logging.info(f"✅ Checked {checked_count} signal outcome(s)")

                        except Exception as e:
                            logging.error(f"❌ Error checking signal outcomes: {e}")
                            import traceback
                            logging.error(traceback.format_exc())

                    # Send email notification if alerts detected
                    if alerts and self.email_notifier:
                        try:
                            self.email_notifier.send_alert_email(alerts, data, indicators)
                        except Exception as e:
                            print(f"⚠️  Failed to send email notification: {e}")

                time.sleep(self.config['interval'])

        except KeyboardInterrupt:
            print("\n\n👋 Monitor stopped by user")
            if self.signal_tracker:
                stats = self.signal_tracker.get_statistics(hours_back=24)
                print(f"\n📊 Session Stats (last 24h):")
                print(f"   Total signals: {stats['total_signals']}")
                print(f"   Win rate: {stats['win_rate']:.1f}%")
                print(f"   Wins: {stats['wins']}, Losses: {stats['losses']}, Pending: {stats['pending']}")
        except Exception as e:
            print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    monitor = BTCMonitor()
    monitor.run()
