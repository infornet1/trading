"""Perpetual futures position simulator (short + long with trailing stop)."""

import logging

logger = logging.getLogger(__name__)


class PerpsSimulator:
    """Simulates opening/closing short perp positions for hedging."""

    def __init__(self, leverage=2, commission_taker=0.00075, slippage_pct=0.0002):
        self.leverage = leverage
        self.commission_taker = commission_taker
        self.slippage_pct = slippage_pct

        # Current position state
        self.is_open = False
        self.entry_price = 0.0
        self.position_size_usd = 0.0
        self.margin_used = 0.0

        # Cumulative tracking
        self.total_pnl = 0.0
        self.total_fees = 0.0
        self.total_funding = 0.0
        self.trade_count = 0

    def open_short(self, price, size_usd):
        """Open a short position."""
        if self.is_open:
            logger.warning("Short already open, skipping")
            return 0.0

        # Apply slippage (worse fill for short = lower price)
        fill_price = price * (1 - self.slippage_pct)

        self.entry_price = fill_price
        self.position_size_usd = size_usd
        self.margin_used = size_usd / self.leverage
        self.is_open = True
        self.trade_count += 1

        # Trading fee
        fee = size_usd * self.commission_taker
        self.total_fees += fee

        logger.debug(f"SHORT opened at ${fill_price:.2f} | Size: ${size_usd:.2f} | Fee: ${fee:.4f}")
        return fee

    def close_short(self, price):
        """Close the short position. Returns PnL."""
        if not self.is_open:
            return 0.0

        # Apply slippage (worse fill for closing short = higher price)
        fill_price = price * (1 + self.slippage_pct)

        # Short PnL: profit when price goes down
        price_change_pct = (self.entry_price - fill_price) / self.entry_price
        pnl = self.position_size_usd * price_change_pct

        # Trading fee
        fee = self.position_size_usd * self.commission_taker
        self.total_fees += fee

        net_pnl = pnl - fee
        self.total_pnl += net_pnl

        logger.debug(
            f"SHORT closed at ${fill_price:.2f} | Entry: ${self.entry_price:.2f} | "
            f"PnL: ${pnl:.2f} | Fee: ${fee:.4f} | Net: ${net_pnl:.2f}"
        )

        self.is_open = False
        self.entry_price = 0.0
        self.position_size_usd = 0.0
        self.margin_used = 0.0

        return net_pnl

    def get_unrealized_pnl(self, current_price):
        """Get unrealized PnL of open position."""
        if not self.is_open:
            return 0.0
        price_change_pct = (self.entry_price - current_price) / self.entry_price
        return self.position_size_usd * price_change_pct

    def apply_funding(self, cost):
        """Apply a funding rate cost/credit."""
        self.total_funding += cost

    def is_liquidated(self, current_price):
        """Check if position would be liquidated."""
        if not self.is_open:
            return False
        # For a short, liquidated when price rises enough to eat margin
        max_loss = self.margin_used * 0.9  # 90% of margin = liquidation
        unrealized = self.get_unrealized_pnl(current_price)
        return unrealized <= -max_loss

    def get_summary(self):
        return {
            "total_trades": self.trade_count,
            "total_pnl": round(self.total_pnl, 2),
            "total_fees": round(self.total_fees, 2),
            "total_funding": round(self.total_funding, 2),
            "net_hedge_result": round(self.total_pnl - self.total_funding, 2),
        }


class LongTrailingSimulator:
    """Simulates LONG positions with trailing stop for Bot Avaro mode.

    From Clase 3: When price breaks above upper_bound, open LONG.
    Trailing stop follows price up, closes when price drops X% from max.
    """

    def __init__(self, leverage=2, commission_taker=0.00075, slippage_pct=0.0002,
                 initial_stop_pct=0.005, trailing_stop_pct=0.02):
        self.leverage = leverage
        self.commission_taker = commission_taker
        self.slippage_pct = slippage_pct
        self.initial_stop_pct = initial_stop_pct  # -0.5% initial stop loss
        self.trailing_stop_pct = trailing_stop_pct  # -2% trailing stop

        # Position state
        self.is_open = False
        self.entry_price = 0.0
        self.position_size_usd = 0.0
        self.margin_used = 0.0
        self.max_price_seen = 0.0  # For trailing stop
        self.stop_price = 0.0

        # Tracking
        self.total_pnl = 0.0
        self.total_fees = 0.0
        self.total_funding = 0.0
        self.trade_count = 0
        self.wins = 0
        self.losses = 0

    def open_long(self, price, size_usd):
        """Open a long position at breakout."""
        if self.is_open:
            return 0.0

        fill_price = price * (1 + self.slippage_pct)

        self.entry_price = fill_price
        self.position_size_usd = size_usd
        self.margin_used = size_usd / self.leverage
        self.is_open = True
        self.trade_count += 1
        self.max_price_seen = fill_price
        self.stop_price = fill_price * (1 - self.initial_stop_pct)

        fee = size_usd * self.commission_taker
        self.total_fees += fee

        logger.debug(f"LONG opened at ${fill_price:.2f} | Size: ${size_usd:.2f} | "
                     f"Stop: ${self.stop_price:.2f}")
        return fee

    def update_trailing_stop(self, current_price):
        """Update trailing stop if price made new high."""
        if not self.is_open:
            return False

        if current_price > self.max_price_seen:
            self.max_price_seen = current_price
            new_stop = current_price * (1 - self.trailing_stop_pct)
            if new_stop > self.stop_price:
                self.stop_price = new_stop

        # Check if stop hit
        return current_price <= self.stop_price

    def close_long(self, price):
        """Close the long position. Returns PnL."""
        if not self.is_open:
            return 0.0

        fill_price = price * (1 - self.slippage_pct)

        price_change_pct = (fill_price - self.entry_price) / self.entry_price
        pnl = self.position_size_usd * price_change_pct

        fee = self.position_size_usd * self.commission_taker
        self.total_fees += fee

        net_pnl = pnl - fee
        self.total_pnl += net_pnl

        if net_pnl > 0:
            self.wins += 1
        else:
            self.losses += 1

        logger.debug(
            f"LONG closed at ${fill_price:.2f} | Entry: ${self.entry_price:.2f} | "
            f"Max: ${self.max_price_seen:.2f} | PnL: ${net_pnl:.2f}"
        )

        self.is_open = False
        self.entry_price = 0.0
        self.position_size_usd = 0.0
        self.margin_used = 0.0
        self.max_price_seen = 0.0
        self.stop_price = 0.0

        return net_pnl

    def get_unrealized_pnl(self, current_price):
        if not self.is_open:
            return 0.0
        price_change_pct = (current_price - self.entry_price) / self.entry_price
        return self.position_size_usd * price_change_pct

    def apply_funding(self, cost):
        self.total_funding += cost

    def is_liquidated(self, current_price):
        if not self.is_open:
            return False
        max_loss = self.margin_used * 0.9
        unrealized = self.get_unrealized_pnl(current_price)
        return unrealized <= -max_loss

    def get_summary(self):
        return {
            "total_trades": self.trade_count,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": round(self.wins / self.trade_count * 100, 1) if self.trade_count > 0 else 0,
            "total_pnl": round(self.total_pnl, 2),
            "total_fees": round(self.total_fees, 2),
            "total_funding": round(self.total_funding, 2),
            "net_result": round(self.total_pnl - self.total_funding, 2),
        }
