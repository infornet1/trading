"""Technical indicators: ADX, EMA, MA for regime detection and range management."""

import numpy as np
import pandas as pd
import logging

logger = logging.getLogger(__name__)


def calculate_adx(df, period=14):
    """Calculate ADX (Average Directional Index) from OHLC data.

    ADX < 20 = lateral/ranging market (good for LP)
    ADX 20-30 = developing trend (caution)
    ADX > 30 = strong trend (avoid LP, or hedge aggressively)
    """
    high = df["high"].values.astype(float)
    low = df["low"].values.astype(float)
    close = df["close"].values.astype(float)

    n = len(close)
    adx = np.full(n, np.nan)

    if n < period * 2:
        return adx

    # True Range
    tr = np.zeros(n)
    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)

    for i in range(1, n):
        h_l = high[i] - low[i]
        h_pc = abs(high[i] - close[i - 1])
        l_pc = abs(low[i] - close[i - 1])
        tr[i] = max(h_l, h_pc, l_pc)

        up_move = high[i] - high[i - 1]
        down_move = low[i - 1] - low[i]

        plus_dm[i] = up_move if (up_move > down_move and up_move > 0) else 0.0
        minus_dm[i] = down_move if (down_move > up_move and down_move > 0) else 0.0

    # Smoothed TR, +DM, -DM using Wilder's smoothing
    atr = np.zeros(n)
    smooth_plus = np.zeros(n)
    smooth_minus = np.zeros(n)

    atr[period] = np.sum(tr[1:period + 1])
    smooth_plus[period] = np.sum(plus_dm[1:period + 1])
    smooth_minus[period] = np.sum(minus_dm[1:period + 1])

    for i in range(period + 1, n):
        atr[i] = atr[i - 1] - (atr[i - 1] / period) + tr[i]
        smooth_plus[i] = smooth_plus[i - 1] - (smooth_plus[i - 1] / period) + plus_dm[i]
        smooth_minus[i] = smooth_minus[i - 1] - (smooth_minus[i - 1] / period) + minus_dm[i]

    # +DI and -DI
    plus_di = np.zeros(n)
    minus_di = np.zeros(n)
    dx = np.zeros(n)

    for i in range(period, n):
        if atr[i] > 0:
            plus_di[i] = 100 * smooth_plus[i] / atr[i]
            minus_di[i] = 100 * smooth_minus[i] / atr[i]
        di_sum = plus_di[i] + minus_di[i]
        if di_sum > 0:
            dx[i] = 100 * abs(plus_di[i] - minus_di[i]) / di_sum

    # ADX = smoothed DX
    adx_start = period * 2
    if adx_start < n:
        adx[adx_start] = np.mean(dx[period:adx_start + 1])
        for i in range(adx_start + 1, n):
            adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period

    return adx


def calculate_ema(series, period):
    """Calculate Exponential Moving Average."""
    values = series.values.astype(float)
    ema = np.full(len(values), np.nan)
    if len(values) < period:
        return ema

    ema[period - 1] = np.mean(values[:period])
    multiplier = 2.0 / (period + 1)
    for i in range(period, len(values)):
        ema[i] = (values[i] - ema[i - 1]) * multiplier + ema[i - 1]
    return ema


def calculate_sma(series, period):
    """Calculate Simple Moving Average."""
    return series.rolling(window=period).mean().values


def add_indicators(df, adx_period=14, ema_fast=10, ma_slow=25):
    """Add all technical indicators to the dataframe.

    Returns a copy with new columns: adx, ema_fast, ma_slow, trend_signal.
    trend_signal: 1 = bullish (EMA > MA), -1 = bearish (EMA < MA), 0 = neutral.
    """
    df = df.copy()

    df["adx"] = calculate_adx(df, period=adx_period)
    df["ema_fast"] = calculate_ema(df["close"], ema_fast)
    df["ma_slow"] = calculate_sma(df["close"], ma_slow)

    # Trend signal from EMA crossover
    df["trend_signal"] = 0
    mask = df["ema_fast"].notna() & df["ma_slow"].notna()
    df.loc[mask & (df["ema_fast"] > df["ma_slow"]), "trend_signal"] = 1
    df.loc[mask & (df["ema_fast"] < df["ma_slow"]), "trend_signal"] = -1

    logger.info(
        f"Indicators added: ADX({adx_period}), EMA({ema_fast}), MA({ma_slow}) | "
        f"Mean ADX: {df['adx'].mean():.1f} | "
        f"Bullish candles: {(df['trend_signal'] == 1).sum()} | "
        f"Bearish candles: {(df['trend_signal'] == -1).sum()}"
    )

    return df
