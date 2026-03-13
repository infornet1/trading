"""Fetch historical BTC/USDT OHLCV data from multiple sources (no auth needed)."""

import os
import time
import logging
import requests
import pandas as pd
from datetime import datetime

logger = logging.getLogger(__name__)

# Data sources (fallback order)
SOURCES = {
    "bybit": "https://api.bybit.com/v5/market/kline",
    "binance": "https://api.binance.com/api/v3/klines",
    "coingecko": "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart/range",
}

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data_cache")

# Map intervals to Bybit format
BYBIT_INTERVALS = {
    "1m": "1", "5m": "5", "15m": "15", "30m": "30",
    "1h": "60", "4h": "240", "1d": "D", "1w": "W",
}


class PriceFetcher:
    def __init__(self, symbol="BTCUSDT", interval="1h"):
        self.symbol = symbol
        self.interval = interval
        os.makedirs(CACHE_DIR, exist_ok=True)

    def _get_cache_path(self, start_date, end_date):
        return os.path.join(
            CACHE_DIR,
            f"{self.symbol}_{self.interval}_{start_date}_{end_date}.csv"
        )

    def fetch(self, start_date, end_date, use_cache=True):
        cache_path = self._get_cache_path(start_date, end_date)

        if use_cache and os.path.exists(cache_path):
            logger.info(f"Loading cached data from {cache_path}")
            df = pd.read_csv(cache_path, parse_dates=["timestamp"])
            return df

        # Try sources in order
        df = None
        for source_name, source_fn in [
            ("bingx", self._fetch_bingx),
            ("bybit", self._fetch_bybit),
            ("binance", self._fetch_binance),
        ]:
            try:
                logger.info(f"Trying {source_name}...")
                df = source_fn(start_date, end_date)
                if df is not None and len(df) > 0:
                    logger.info(f"Success with {source_name}: {len(df)} candles")
                    break
            except Exception as e:
                logger.warning(f"{source_name} failed: {e}")
                continue

        if df is None or len(df) == 0:
            raise ValueError("All data sources failed")

        if use_cache:
            df.to_csv(cache_path, index=False)
            logger.info(f"Cached {len(df)} candles to {cache_path}")

        logger.info(f"Fetched {len(df)} candles | {df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}")
        return df

    def _fetch_bingx(self, start_date, end_date):
        """Fetch from BingX public API (no auth needed, no geo-block)."""
        BINGX_URL = "https://open-api.bingx.com/openApi/swap/v3/quote/klines"

        # BingX interval mapping
        bingx_intervals = {
            "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
            "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1w",
        }
        bingx_interval = bingx_intervals.get(self.interval, "1h")

        # BingX symbol format: BTC-USDT
        bingx_symbol = self.symbol.replace("USDT", "-USDT")

        start_ms = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
        end_ms = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)

        all_candles = []
        current_start = start_ms

        # Interval in ms for pagination
        interval_ms_map = {
            "1m": 60000, "5m": 300000, "15m": 900000, "30m": 1800000,
            "1h": 3600000, "4h": 14400000, "1d": 86400000, "1w": 604800000,
        }
        interval_ms = interval_ms_map.get(self.interval, 3600000)

        while current_start < end_ms:
            params = {
                "symbol": bingx_symbol,
                "interval": bingx_interval,
                "startTime": current_start,
                "endTime": min(current_start + 1440 * interval_ms, end_ms),
                "limit": 1440,
            }

            resp = requests.get(BINGX_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") != 0:
                raise ValueError(f"BingX API error: {data.get('msg')}")

            candles = data.get("data", [])
            if not candles:
                break

            all_candles.extend(candles)

            # Move to next batch
            latest_ts = max(int(c["time"]) for c in candles)
            current_start = latest_ts + interval_ms

            if len(candles) < 1440:
                break

            time.sleep(0.3)

        if not all_candles:
            return None

        df = pd.DataFrame(all_candles)
        df["timestamp"] = pd.to_datetime(df["time"].astype(int), unit="ms")
        df["open"] = df["open"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["close"] = df["close"].astype(float)
        df["volume"] = df["volume"].astype(float)
        # BingX doesn't provide quote_volume directly, estimate it
        df["quote_volume"] = df["volume"] * (df["open"] + df["close"]) / 2

        df = df[["timestamp", "open", "high", "low", "close", "volume", "quote_volume"]]
        df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

        # Filter to requested range
        start_dt = pd.Timestamp(start_date)
        end_dt = pd.Timestamp(end_date)
        df = df[(df["timestamp"] >= start_dt) & (df["timestamp"] <= end_dt)].reset_index(drop=True)

        return df

    def _fetch_bybit(self, start_date, end_date):
        """Fetch from Bybit public API (no auth, no geo-block)."""
        start_ms = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
        end_ms = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)
        bybit_interval = BYBIT_INTERVALS.get(self.interval, "60")

        all_candles = []
        current_start = start_ms

        while current_start < end_ms:
            params = {
                "category": "linear",
                "symbol": self.symbol,
                "interval": bybit_interval,
                "start": current_start,
                "end": min(current_start + 1000 * 3600 * 1000, end_ms),  # ~1000 hourly candles
                "limit": 1000,
            }

            resp = requests.get(SOURCES["bybit"], params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            if data.get("retCode") != 0:
                raise ValueError(f"Bybit API error: {data.get('retMsg')}")

            candles = data.get("result", {}).get("list", [])
            if not candles:
                break

            all_candles.extend(candles)

            # Bybit returns newest first, so the last item has the earliest timestamp
            earliest_ts = int(candles[-1][0])
            latest_ts = int(candles[0][0])
            current_start = latest_ts + 1

            if len(candles) < 1000:
                break

            time.sleep(0.2)

        if not all_candles:
            return None

        # Bybit format: [timestamp, open, high, low, close, volume, turnover]
        df = pd.DataFrame(all_candles, columns=[
            "timestamp", "open", "high", "low", "close", "volume", "quote_volume"
        ])

        df["timestamp"] = pd.to_datetime(df["timestamp"].astype(int), unit="ms")
        for col in ["open", "high", "low", "close", "volume", "quote_volume"]:
            df[col] = df[col].astype(float)

        df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

        # Filter to requested range
        start_dt = pd.Timestamp(start_date)
        end_dt = pd.Timestamp(end_date)
        df = df[(df["timestamp"] >= start_dt) & (df["timestamp"] <= end_dt)].reset_index(drop=True)

        return df

    def _fetch_binance(self, start_date, end_date):
        """Fetch from Binance public API."""
        start_ms = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
        end_ms = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)

        all_candles = []
        current_start = start_ms

        while current_start < end_ms:
            params = {
                "symbol": self.symbol,
                "interval": self.interval,
                "startTime": current_start,
                "endTime": end_ms,
                "limit": 1000
            }

            resp = requests.get(SOURCES["binance"], params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            if not data:
                break

            all_candles.extend(data)
            current_start = data[-1][0] + 1

            if len(data) < 1000:
                break

            time.sleep(0.2)

        if not all_candles:
            return None

        df = pd.DataFrame(all_candles, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_buy_base",
            "taker_buy_quote", "ignore"
        ])

        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        for col in ["open", "high", "low", "close", "volume", "quote_volume"]:
            df[col] = df[col].astype(float)

        df = df[["timestamp", "open", "high", "low", "close", "volume", "quote_volume"]]
        df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

        return df
