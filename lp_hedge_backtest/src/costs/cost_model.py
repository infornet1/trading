"""Aggregated cost model for the LP + hedge strategy."""

import logging

logger = logging.getLogger(__name__)


class CostModel:
    """Tracks all costs: trading fees, gas, slippage, funding."""

    def __init__(self, gas_cost_per_tx=0.50):
        self.gas_cost_per_tx = gas_cost_per_tx

        # Cumulative costs
        self.total_gas = 0.0
        self.total_trading_fees = 0.0
        self.total_slippage = 0.0
        self.total_funding = 0.0
        self.gas_tx_count = 0

    def add_gas_cost(self, num_transactions=1):
        """Add gas cost for LP operations (rebalance, add/remove)."""
        cost = self.gas_cost_per_tx * num_transactions
        self.total_gas += cost
        self.gas_tx_count += num_transactions
        return cost

    def add_trading_fee(self, amount):
        self.total_trading_fees += amount

    def add_funding_cost(self, amount):
        self.total_funding += amount

    def get_total_costs(self):
        return self.total_gas + self.total_trading_fees + self.total_funding

    def get_summary(self):
        return {
            "total_costs": round(self.get_total_costs(), 2),
            "gas_costs": round(self.total_gas, 2),
            "gas_transactions": self.gas_tx_count,
            "trading_fees": round(self.total_trading_fees, 2),
            "funding_costs": round(self.total_funding, 2),
        }
