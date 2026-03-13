"""Estimate LP fee income based on trading volume and pool share."""

import logging

logger = logging.getLogger(__name__)


class FeeEstimator:
    """Estimates fees earned by an LP position in a concentrated liquidity pool.

    Models Uniswap v3 concentrated liquidity where:
    - Only LPs whose range covers the current price earn fees
    - User's share depends on their liquidity relative to total in-range liquidity
    - Concentrated positions earn more per dollar than full-range positions
    """

    def __init__(self, fee_tier=0.0005, assumed_pool_tvl=8_000_000,
                 daily_pool_volume=8_500_000):
        self.fee_tier = fee_tier
        self.assumed_pool_tvl = assumed_pool_tvl
        self.daily_pool_volume = daily_pool_volume

        # In concentrated LP, not all TVL is in the active range.
        # Typically ~30-50% of TVL is concentrated in the active tick range.
        self.active_tvl_ratio = 0.40

    def estimate_fees(self, candle_volume_usd, user_liquidity_usd, is_in_range,
                      candles_per_day=24):
        """
        Estimate fees earned for a single candle period.

        Uses the POOL's actual daily volume (not the CEX volume from price data).
        The candle_volume_usd from price data is ignored in favor of realistic
        pool volume estimates.
        """
        if not is_in_range or user_liquidity_usd <= 0:
            return 0.0

        # Use realistic pool volume per candle, not CEX volume
        volume_per_candle = self.daily_pool_volume / candles_per_day

        # User's share of active liquidity
        # In concentrated LP, user competes only with other LPs in the same range
        active_tvl = self.assumed_pool_tvl * self.active_tvl_ratio
        user_share = user_liquidity_usd / (active_tvl + user_liquidity_usd)

        # Fees earned: volume × fee_tier × user_share
        # Only ~70% of volume actually trades through the active tick range
        effective_volume = volume_per_candle * 0.70
        fees = effective_volume * self.fee_tier * user_share

        return fees
