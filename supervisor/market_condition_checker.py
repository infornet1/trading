#!/usr/bin/env python3
"""
Market Condition Checker - Analyzes if market is tradeable
Returns JSON with market conditions
"""

import sys
import os
sys.path.insert(0, '/var/www/dev/trading/adx_strategy_v2')

import json
import requests
from datetime import datetime
import pandas as pd
import numpy as np


def check_market_conditions():
    """Check current market conditions"""

    try:
        # Fetch BTC-USDT data from BingX
        url = "https://open-api.bingx.com/openApi/swap/v2/quote/klines"
        params = {
            'symbol': 'BTC-USDT',
            'interval': '5m',
            'limit': 100
        }

        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if data.get('code') != 0:
            raise Exception(f"API error: {data}")

        # Parse candles
        candles = []
        for candle in data['data']:
            candles.append({
                'timestamp': candle['time'],
                'open': float(candle['open']),
                'high': float(candle['high']),
                'low': float(candle['low']),
                'close': float(candle['close']),
                'volume': float(candle['volume'])
            })

        df = pd.DataFrame(candles)

        # Calculate ADX (simplified)
        def calculate_adx(df, period=14):
            high = df['high']
            low = df['low']
            close = df['close']

            # True Range
            tr1 = high - low
            tr2 = abs(high - close.shift())
            tr3 = abs(low - close.shift())
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.rolling(period).mean()

            # Directional Movement
            up_move = high - high.shift()
            down_move = low.shift() - low

            plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
            minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

            plus_di = 100 * (pd.Series(plus_dm).rolling(period).mean() / atr)
            minus_di = 100 * (pd.Series(minus_dm).rolling(period).mean() / atr)

            # ADX
            dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
            adx = dx.rolling(period).mean()

            return adx.iloc[-1] if len(adx) > 0 else 0

        adx_value = calculate_adx(df)

        # Calculate volatility
        returns = df['close'].pct_change()
        volatility = returns.std() * 100  # as percentage

        # Current price
        current_price = df['close'].iloc[-1]

        # Determine market regime
        if adx_value > 25:
            regime = 'trending'
            tradeable = True
        elif volatility < 0.5:
            regime = 'ranging'
            tradeable = False
        else:
            regime = 'choppy'
            tradeable = True  # Scalping bot can handle this

        # Return conditions
        conditions = {
            'timestamp': datetime.now().isoformat(),
            'tradeable': tradeable,
            'regime': regime,
            'adx': float(adx_value),
            'volatility': float(volatility),
            'btc_price': float(current_price)
        }

        # Output as JSON
        print(json.dumps(conditions))
        return 0

    except Exception as e:
        error_result = {
            'timestamp': datetime.now().isoformat(),
            'tradeable': False,
            'regime': 'unknown',
            'adx': 0,
            'volatility': 0,
            'btc_price': 0,
            'error': str(e)
        }
        print(json.dumps(error_result))
        return 1


if __name__ == '__main__':
    sys.exit(check_market_conditions())
