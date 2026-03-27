"""Technical indicators: ADX, EMA, MA for regime detection and range management.

FURY additions (Phase 1):
  - calculate_rsi        — RSI on OHLC4 source, period 9 default
  - calculate_ema_crossover — EMA-8 vs EMA-21 direction signal
  - calculate_obv_slope  — 5-bar OBV slope for volume confirmation
  - calculate_atr        — ATR-12, standalone (no Wilder smoothing dependency)
  - add_fury_indicators  — adds all FURY columns to a dataframe in one call
"""

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


# ── FURY Indicators ───────────────────────────────────────────────────────────


def calculate_rsi(df, period=9):
    """Calculate RSI using OHLC4 source: (open+high+low+close)/4.

    Using OHLC4 instead of close reduces noise and improves divergence detection
    without introducing new parameters.

    Returns a numpy array aligned to df index. First (period) values are NaN.
    """
    ohlc4 = (df["open"] + df["high"] + df["low"] + df["close"]).values.astype(float) / 4.0
    n = len(ohlc4)
    rsi = np.full(n, np.nan)

    if n < period + 1:
        return rsi

    deltas = np.diff(ohlc4)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    # Seed with simple average over first period
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    for i in range(period, n):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        if avg_loss == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100.0 - (100.0 / (1.0 + rs))

    return rsi


def calculate_ema_crossover(df, fast=8, slow=21):
    """EMA-fast vs EMA-slow crossover signal.

    Returns numpy array:
      +1 = bullish  (fast EMA > slow EMA)
      -1 = bearish  (fast EMA < slow EMA)
       0 = neutral  (either EMA not yet seeded)
    """
    ema_fast = calculate_ema(df["close"], fast)
    ema_slow = calculate_ema(df["close"], slow)

    signal = np.zeros(len(df))
    valid = ~np.isnan(ema_fast) & ~np.isnan(ema_slow)
    signal[valid & (ema_fast > ema_slow)] = 1
    signal[valid & (ema_fast < ema_slow)] = -1
    return signal


def calculate_obv_slope(df, bars=5):
    """On-Balance Volume 5-bar slope.

    Positive slope = accumulation (smart money buying) → gates RSI long entries.
    Negative slope = distribution → blocks RSI long entries.

    Returns numpy array (NaN for first `bars` rows).
    """
    close = df["close"].values.astype(float)
    volume = df["volume"].values.astype(float)
    n = len(close)

    obv = np.zeros(n)
    for i in range(1, n):
        if close[i] > close[i - 1]:
            obv[i] = obv[i - 1] + volume[i]
        elif close[i] < close[i - 1]:
            obv[i] = obv[i - 1] - volume[i]
        else:
            obv[i] = obv[i - 1]

    slope = np.full(n, np.nan)
    for i in range(bars, n):
        slope[i] = obv[i] - obv[i - bars]

    return slope


def calculate_atr(df, period=12):
    """ATR using Wilder's smoothing, period 12.

    ATR-12 preferred over ATR-14 for crypto: slightly more responsive
    to intraday volatility without excessive noise.

    Returns numpy array aligned to df index.
    """
    high = df["high"].values.astype(float)
    low = df["low"].values.astype(float)
    close = df["close"].values.astype(float)
    n = len(close)

    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        )

    atr = np.full(n, np.nan)
    if n < period + 1:
        return atr

    atr[period] = np.mean(tr[1: period + 1])
    for i in range(period + 1, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

    return atr


def add_fury_indicators(df, rsi_period=9, ema_fast=8, ema_slow=21,
                        obv_bars=5, atr_period=12, vol_sma_bars=20):
    """Add all FURY signal indicators to a dataframe in one call.

    New columns added:
      rsi          — RSI(9) on OHLC4
      ema_fast     — EMA-8 on close
      ema_slow     — EMA-21 on close
      ema_signal   — +1 bullish / -1 bearish / 0 neutral
      obv_slope    — 5-bar OBV slope
      atr          — ATR-12
      vol_sma20    — 20-bar SMA of volume (volume gate threshold)

    Existing columns (adx, trend_signal, etc.) are preserved.
    """
    df = df.copy()

    df["rsi"] = calculate_rsi(df, period=rsi_period)
    ema_f = calculate_ema(df["close"], ema_fast)
    ema_s = calculate_ema(df["close"], ema_slow)
    df["ema_fast"] = ema_f
    df["ema_slow"] = ema_s
    df["ema_signal"] = calculate_ema_crossover(df, fast=ema_fast, slow=ema_slow)
    df["obv_slope"] = calculate_obv_slope(df, bars=obv_bars)
    df["atr"] = calculate_atr(df, period=atr_period)
    df["vol_sma20"] = df["volume"].rolling(window=vol_sma_bars).mean().values

    logger.info(
        f"FURY indicators added: RSI({rsi_period}/OHLC4), EMA({ema_fast}/{ema_slow}), "
        f"OBV-slope({obv_bars}), ATR({atr_period}), VolSMA({vol_sma_bars}) | "
        f"Valid RSI rows: {(~np.isnan(df['rsi'])).sum()}/{len(df)}"
    )

    return df


# ── LP / Regime Indicators ────────────────────────────────────────────────────


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
