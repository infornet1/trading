"""Uniswap v3 concentrated liquidity position math."""

import math
import logging

logger = logging.getLogger(__name__)


class ConcentratedLPPosition:
    """Simulates a Uniswap v3 concentrated liquidity position."""

    def __init__(self, capital_usd, price_lower, price_upper, entry_price):
        self.capital_usd = capital_usd
        self.price_lower = price_lower
        self.price_upper = price_upper
        self.entry_price = entry_price

        # Calculate initial liquidity and token amounts at entry
        self.liquidity = self._calculate_liquidity(entry_price)
        self.initial_token_x, self.initial_token_y = self._get_token_amounts(entry_price)

        logger.info(
            f"LP Position: ${capital_usd:.2f} | Range [{price_lower:.0f}, {price_upper:.0f}] | "
            f"Entry: ${entry_price:.0f} | BTC: {self.initial_token_x:.6f} | USDT: {self.initial_token_y:.2f}"
        )

    def _calculate_liquidity(self, current_price):
        """Calculate liquidity L for the concentrated position given capital."""
        sqrt_lower = math.sqrt(self.price_lower)
        sqrt_upper = math.sqrt(self.price_upper)
        sqrt_price = math.sqrt(min(max(current_price, self.price_lower), self.price_upper))

        # For a given amount of capital, split optimally between tokens
        # Amount of token X (BTC) per unit of L
        delta_inv_sqrt = (1.0 / sqrt_price) - (1.0 / sqrt_upper)
        # Amount of token Y (USDT) per unit of L
        delta_sqrt = sqrt_price - sqrt_lower

        if delta_inv_sqrt <= 0 and delta_sqrt <= 0:
            return 0.0

        # Cost per unit of liquidity in USD
        cost_per_l = current_price * delta_inv_sqrt + delta_sqrt
        if cost_per_l <= 0:
            return 0.0

        return self.capital_usd / cost_per_l

    def _get_token_amounts(self, current_price):
        """Get BTC (x) and USDT (y) amounts at a given price."""
        sqrt_lower = math.sqrt(self.price_lower)
        sqrt_upper = math.sqrt(self.price_upper)

        if current_price <= self.price_lower:
            # Below range: 100% BTC
            token_x = self.liquidity * (1.0 / sqrt_lower - 1.0 / sqrt_upper)
            token_y = 0.0
        elif current_price >= self.price_upper:
            # Above range: 100% USDT
            token_x = 0.0
            token_y = self.liquidity * (sqrt_upper - sqrt_lower)
        else:
            # In range: mix of both
            sqrt_price = math.sqrt(current_price)
            token_x = self.liquidity * (1.0 / sqrt_price - 1.0 / sqrt_upper)
            token_y = self.liquidity * (sqrt_price - sqrt_lower)

        return max(token_x, 0.0), max(token_y, 0.0)

    def get_position_value(self, current_price):
        """Total USD value of the LP position at current price."""
        token_x, token_y = self._get_token_amounts(current_price)
        return token_x * current_price + token_y

    def get_hold_value(self, current_price):
        """Value if we had just held the initial tokens instead of LPing."""
        return self.initial_token_x * current_price + self.initial_token_y

    def get_impermanent_loss(self, current_price):
        """IL as a ratio: negative means LP is worth less than holding."""
        position_value = self.get_position_value(current_price)
        hold_value = self.get_hold_value(current_price)
        if hold_value == 0:
            return 0.0
        return (position_value / hold_value) - 1.0

    def get_impermanent_loss_usd(self, current_price):
        """IL in absolute USD terms."""
        return self.get_position_value(current_price) - self.get_hold_value(current_price)

    def is_in_range(self, current_price):
        return self.price_lower <= current_price <= self.price_upper

    def get_btc_exposure(self, current_price):
        """Returns BTC amount held in the LP position."""
        token_x, _ = self._get_token_amounts(current_price)
        return token_x

    def get_btc_exposure_usd(self, current_price):
        """Returns USD value of BTC exposure in the LP."""
        return self.get_btc_exposure(current_price) * current_price
