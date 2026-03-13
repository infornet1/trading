"""Funding rate model for perps hedging cost estimation."""

import logging
import requests
import pandas as pd
from datetime import datetime

logger = logging.getLogger(__name__)

BINANCE_FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"


class FundingRateModel:
    """Manages funding rate data for perps cost calculation."""

    def __init__(self, default_rate=0.0001, fetch_real=True, symbol="BTCUSDT"):
        self.default_rate = default_rate  # 0.01% per 8h
        self.symbol = symbol
        self.rates = {}

        if fetch_real:
            self._fetch_historical_rates()

    def _fetch_historical_rates(self):
        """Fetch historical funding rates from Binance futures API."""
        logger.info(f"Fetching historical funding rates for {self.symbol}...")

        all_rates = []
        start_time = None

        for _ in range(20):  # Max 20 pages
            params = {"symbol": self.symbol, "limit": 1000}
            if start_time:
                params["startTime"] = start_time

            try:
                resp = requests.get(BINANCE_FUNDING_URL, params=params, timeout=10)
                resp.raise_for_status()
                data = resp.json()
            except requests.RequestException as e:
                logger.warning(f"Failed to fetch funding rates: {e}")
                break

            if not data:
                break

            all_rates.extend(data)
            start_time = data[-1]["fundingTime"] + 1

            if len(data) < 1000:
                break

        if all_rates:
            for r in all_rates:
                ts = datetime.fromtimestamp(r["fundingTime"] / 1000)
                self.rates[ts] = float(r["fundingRate"])
            logger.info(f"Loaded {len(self.rates)} funding rate data points")
        else:
            logger.warning("No funding rates fetched, using default rate")

    def get_rate(self, timestamp):
        """Get the funding rate applicable at a given timestamp."""
        if not self.rates:
            return self.default_rate

        # Find the closest funding rate before this timestamp
        closest = None
        for ts in sorted(self.rates.keys()):
            if ts <= timestamp:
                closest = ts
            else:
                break

        if closest is not None:
            return self.rates[closest]
        return self.default_rate

    def calculate_funding_cost(self, position_size_usd, hours_held, timestamp):
        """
        Calculate funding cost for holding a position.

        Funding is paid every 8 hours. This calculates the pro-rated cost.

        Args:
            position_size_usd: Size of the perp position in USD
            hours_held: Number of hours the position was held this period
            timestamp: Current timestamp for rate lookup

        Returns:
            Funding cost in USD (positive = you pay, negative = you receive)
        """
        rate = self.get_rate(timestamp)
        # Pro-rate: funding is per 8 hours
        funding_periods = hours_held / 8.0
        return position_size_usd * rate * funding_periods
