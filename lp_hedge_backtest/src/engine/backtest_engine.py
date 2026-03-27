"""Core backtest engine v2: LP + hedge with ADX regime detection and dynamic rebalancing.

Phase 3 addition: FuryBacktestEngine — standalone RSI perps strategy, no LP required.
"""

import logging
import numpy as np
import pandas as pd
from datetime import timedelta

from src.lp.concentrated_liquidity import ConcentratedLPPosition
from src.lp.fee_estimator import FeeEstimator
from src.hedge.perps_simulator import PerpsSimulator, LongTrailingSimulator
from src.hedge.funding_rate import FundingRateModel
from src.costs.cost_model import CostModel
from src.indicators.technical import add_indicators, add_fury_indicators
from src.hedge.standalone_perps_simulator import StandalonePerpsSimulator

logger = logging.getLogger(__name__)


class LPHedgeBacktestEngine:
    """Runs the LP + perps hedge simulation with ADX regime detection.

    Key improvements from Clase 2:
    - ADX-based regime detection: only open LP when ADX < 20 (lateral market)
    - STOP LIMIT hedge: trigger at lower_bound - 0.5% (not market order with buffer)
    - Hedge sizing: 50% of volatile capital (ETH side), not 70% of total exposure
    - Take Profit: close hedge at lower_bound price
    - Dynamic range rebalancing when price exits range for extended period
    - EMA 10 + MA 25 crossover for trend confirmation
    """

    def __init__(self, config):
        lp_cfg = config["lp_position"]
        hedge_cfg = config["hedge"]
        regime_cfg = config.get("regime", {})
        rebalance_cfg = config.get("rebalance", {})

        self.initial_capital = lp_cfg["initial_capital_usd"]
        self.price_lower = lp_cfg["lower_bound"]
        self.price_upper = lp_cfg["upper_bound"]

        # Hedge params (Clase 2 style)
        self.trigger_offset = hedge_cfg.get("trigger_offset_percent", 0.5) / 100.0
        self.hedge_coverage = hedge_cfg["hedge_coverage_percent"] / 100.0
        self.max_position_pct = hedge_cfg["max_position_percent"] / 100.0
        self.tp_at_lower_bound = hedge_cfg.get("take_profit_at_lower_bound", True)

        # Regime detection params
        self.adx_period = regime_cfg.get("adx_period", 14)
        self.adx_lateral = regime_cfg.get("adx_lateral_threshold", 20)
        self.adx_trend = regime_cfg.get("adx_trend_threshold", 30)
        self.ema_fast = regime_cfg.get("ema_fast_period", 10)
        self.ma_slow = regime_cfg.get("ma_slow_period", 25)
        self.require_lateral = regime_cfg.get("require_lateral_for_lp", True)

        # Rebalance params
        self.rebalance_enabled = rebalance_cfg.get("enabled", True)
        self.rebalance_oor_hours = rebalance_cfg.get("out_of_range_hours_trigger", 24)
        self.range_width_pct = rebalance_cfg.get("range_width_percent", 10) / 100.0
        self.gas_rebalance = rebalance_cfg.get("gas_cost_rebalance", 0.20)
        self.min_rebalance_dist = rebalance_cfg.get("min_rebalance_distance_percent", 3) / 100.0

        self.fee_estimator = FeeEstimator(
            fee_tier=lp_cfg["fee_tier"],
            assumed_pool_tvl=lp_cfg["assumed_pool_tvl"],
            daily_pool_volume=lp_cfg.get("daily_pool_volume", 8_500_000)
        )
        self.perps = PerpsSimulator(
            leverage=hedge_cfg["leverage"],
            commission_taker=hedge_cfg["commission_rate_taker"],
            slippage_pct=hedge_cfg["slippage_percent"] / 100.0
        )
        self.funding = FundingRateModel(
            default_rate=hedge_cfg["default_funding_rate"],
            fetch_real=True
        )
        self.cost_model = CostModel(gas_cost_per_tx=lp_cfg["gas_cost_per_tx"])

        # STOP LIMIT trigger: lower_bound - offset
        self.hedge_trigger_price = self.price_lower * (1 - self.trigger_offset)
        # Take profit: at lower_bound (price returned to range)
        self.hedge_tp_price = self.price_lower

    def _should_open_lp(self, adx_value, trend_signal):
        """Check if market regime is suitable for LP (lateral market)."""
        if not self.require_lateral:
            return True
        if pd.isna(adx_value):
            return True  # Not enough data yet, assume OK
        return adx_value < self.adx_lateral

    def _calculate_new_range(self, current_price):
        """Calculate new LP range centered on current price."""
        half_width = current_price * self.range_width_pct / 2
        new_lower = round(current_price - half_width, 2)
        new_upper = round(current_price + half_width, 2)
        return new_lower, new_upper

    def run(self, df):
        """Run the backtest simulation."""
        # Add technical indicators
        df = add_indicators(df, self.adx_period, self.ema_fast, self.ma_slow)

        entry_price = df.iloc[0]["close"]

        # Initialize LP position
        lp = ConcentratedLPPosition(
            capital_usd=self.initial_capital,
            price_lower=self.price_lower,
            price_upper=self.price_upper,
            entry_price=entry_price
        )

        # Track current range (can change with rebalancing)
        current_lower = self.price_lower
        current_upper = self.price_upper

        # Tracking
        equity_curve = []
        cumulative_fees = 0.0
        cumulative_hedge_pnl = 0.0
        cumulative_funding = 0.0
        hedge_activations = 0
        hours_hedged = 0
        hours_in_range = 0
        total_hours = 0
        rebalance_count = 0
        consecutive_oor_hours = 0  # out-of-range counter
        lp_active = True  # Whether LP is deployed
        regime_pauses = 0  # Times LP was paused due to ADX

        # Candle duration
        if len(df) > 1:
            candle_hours = (df.iloc[1]["timestamp"] - df.iloc[0]["timestamp"]).total_seconds() / 3600
        else:
            candle_hours = 1.0

        logger.info(f"Starting backtest v2 | Entry: ${entry_price:.0f} | "
                     f"Range: [{current_lower}, {current_upper}] | "
                     f"Hedge trigger: ${self.hedge_trigger_price:.0f} | "
                     f"Hedge TP: ${self.hedge_tp_price:.0f} | "
                     f"ADX lateral threshold: {self.adx_lateral}")

        for idx in range(len(df)):
            row = df.iloc[idx]
            price = row["close"]
            timestamp = row["timestamp"]
            adx_val = row["adx"]
            trend = row["trend_signal"]
            volume_usd = row.get("quote_volume", row.get("volume", 0) * price)
            total_hours += candle_hours

            in_range = current_lower <= price <= current_upper

            # --- ADX Regime Check ---
            regime_ok = self._should_open_lp(adx_val, trend)

            if lp_active and not regime_ok and not pd.isna(adx_val) and adx_val >= self.adx_trend:
                # Strong trend detected — mark LP as paused (in reality, would withdraw)
                # We still track position value but note the regime warning
                regime_pauses += 1
                logger.debug(f"ADX={adx_val:.1f} > {self.adx_trend} — regime warning at ${price:.0f}")

            # --- Track in-range time ---
            if in_range and lp_active:
                hours_in_range += candle_hours

            # --- LP Fees (only earned when in range and LP is active) ---
            lp_value = lp.get_position_value(price)
            fee_income = 0.0
            if lp_active and in_range:
                fee_income = self.fee_estimator.estimate_fees(volume_usd, lp_value, True)
                cumulative_fees += fee_income

            # --- Hedge Logic (STOP LIMIT style from Clase 2) ---
            # Trigger: price drops below lower_bound - offset (STOP LIMIT)
            hedge_trigger = current_lower * (1 - self.trigger_offset)
            hedge_tp = current_lower  # TP at lower bound

            if price <= hedge_trigger and not self.perps.is_open:
                # Hedge size = 50% of volatile (ETH) capital in the LP
                volatile_exposure_usd = lp.get_btc_exposure_usd(price)
                hedge_size = volatile_exposure_usd * self.hedge_coverage

                # Cap at max position
                max_size = self.initial_capital * self.max_position_pct * self.perps.leverage
                hedge_size = min(hedge_size, max_size)

                if hedge_size > 0:
                    fee = self.perps.open_short(price, hedge_size)
                    self.cost_model.add_trading_fee(fee)
                    hedge_activations += 1
                    adx_str = f"{adx_val:.1f}" if not pd.isna(adx_val) else "N/A"
                    logger.debug(f"HEDGE OPENED at ${price:.0f} (trigger ${hedge_trigger:.0f}) | "
                                f"Size: ${hedge_size:.0f} | ADX: {adx_str}")

            # Close hedge: TP at lower_bound (price recovered back to range)
            elif price >= hedge_tp and self.perps.is_open:
                net_pnl = self.perps.close_short(price)
                cumulative_hedge_pnl += net_pnl
                logger.debug(f"HEDGE CLOSED (TP) at ${price:.0f} | PnL: ${net_pnl:.2f}")

            # --- Funding Rate ---
            if self.perps.is_open:
                hours_hedged += candle_hours
                funding_cost = self.funding.calculate_funding_cost(
                    self.perps.position_size_usd, candle_hours, timestamp
                )
                self.perps.apply_funding(funding_cost)
                self.cost_model.add_funding_cost(funding_cost)
                cumulative_funding += funding_cost

                # Check liquidation
                if self.perps.is_liquidated(price):
                    logger.warning(f"LIQUIDATED at ${price:.0f}!")
                    loss = self.perps.margin_used * 0.9
                    cumulative_hedge_pnl -= loss
                    self.perps.is_open = False
                    self.perps.total_pnl -= loss

            # --- Dynamic Range Rebalancing ---
            if self.rebalance_enabled:
                if not in_range:
                    consecutive_oor_hours += candle_hours
                else:
                    consecutive_oor_hours = 0

                # Rebalance if out of range for too long
                if consecutive_oor_hours >= self.rebalance_oor_hours:
                    # Check distance from current range
                    if price < current_lower:
                        distance = (current_lower - price) / current_lower
                    else:
                        distance = (price - current_upper) / current_upper

                    if distance >= self.min_rebalance_dist:
                        # Close hedge if open before rebalancing
                        if self.perps.is_open:
                            net_pnl = self.perps.close_short(price)
                            cumulative_hedge_pnl += net_pnl

                        # Calculate new range
                        new_lower, new_upper = self._calculate_new_range(price)

                        # Recreate LP position at current value
                        current_capital = lp_value + cumulative_fees
                        lp = ConcentratedLPPosition(
                            capital_usd=current_capital,
                            price_lower=new_lower,
                            price_upper=new_upper,
                            entry_price=price
                        )
                        current_lower = new_lower
                        current_upper = new_upper
                        consecutive_oor_hours = 0
                        rebalance_count += 1

                        # Gas cost for rebalance (remove + add liquidity)
                        self.cost_model.add_gas_cost(self.gas_rebalance)

                        logger.info(f"REBALANCED at ${price:.0f} | "
                                   f"New range: [{new_lower:.0f}, {new_upper:.0f}] | "
                                   f"Capital: ${current_capital:.0f}")

            # --- Record equity ---
            unrealized_hedge = self.perps.get_unrealized_pnl(price) if self.perps.is_open else 0
            il_usd = lp.get_impermanent_loss_usd(price)

            total_equity = lp_value + cumulative_fees + cumulative_hedge_pnl + unrealized_hedge - cumulative_funding

            equity_curve.append({
                "timestamp": timestamp,
                "price": price,
                "lp_value": lp_value,
                "hold_value": lp.get_hold_value(price),
                "il_pct": lp.get_impermanent_loss(price) * 100,
                "il_usd": il_usd,
                "fees_earned": cumulative_fees,
                "hedge_pnl": cumulative_hedge_pnl + unrealized_hedge,
                "funding_cost": cumulative_funding,
                "total_equity": total_equity,
                "hedge_active": self.perps.is_open,
                "in_range": in_range,
                "adx": adx_val if not pd.isna(adx_val) else 0,
                "trend_signal": trend,
                "range_lower": current_lower,
                "range_upper": current_upper,
            })

        # Close any remaining position at end
        if self.perps.is_open:
            final_pnl = self.perps.close_short(df.iloc[-1]["close"])
            cumulative_hedge_pnl += final_pnl

        equity_df = pd.DataFrame(equity_curve)

        return {
            "strategy": "LP + Hedge v2",
            "equity_curve": equity_df,
            "initial_capital": self.initial_capital,
            "final_equity": equity_df.iloc[-1]["total_equity"],
            "total_return_pct": ((equity_df.iloc[-1]["total_equity"] / self.initial_capital) - 1) * 100,
            "lp_fees_earned": cumulative_fees,
            "hedge_pnl": cumulative_hedge_pnl,
            "funding_paid": cumulative_funding,
            "total_costs": self.cost_model.get_total_costs(),
            "hedge_activations": hedge_activations,
            "hours_hedged": hours_hedged,
            "hours_in_range": hours_in_range,
            "total_hours": total_hours,
            "pct_time_in_range": (hours_in_range / total_hours * 100) if total_hours > 0 else 0,
            "pct_time_hedged": (hours_hedged / total_hours * 100) if total_hours > 0 else 0,
            "rebalance_count": rebalance_count,
            "regime_pauses": regime_pauses,
            "perps_summary": self.perps.get_summary(),
            "cost_summary": self.cost_model.get_summary(),
        }


class LPOnlyEngine:
    """Simulates LP-only strategy (no hedge) for comparison."""

    def __init__(self, config):
        lp_cfg = config["lp_position"]
        rebalance_cfg = config.get("rebalance", {})

        self.initial_capital = lp_cfg["initial_capital_usd"]
        self.price_lower = lp_cfg["lower_bound"]
        self.price_upper = lp_cfg["upper_bound"]
        self.fee_estimator = FeeEstimator(
            fee_tier=lp_cfg["fee_tier"],
            assumed_pool_tvl=lp_cfg["assumed_pool_tvl"],
            daily_pool_volume=lp_cfg.get("daily_pool_volume", 8_500_000)
        )

        # Rebalance params (same as hedge engine for fair comparison)
        self.rebalance_enabled = rebalance_cfg.get("enabled", True)
        self.rebalance_oor_hours = rebalance_cfg.get("out_of_range_hours_trigger", 24)
        self.range_width_pct = rebalance_cfg.get("range_width_percent", 10) / 100.0
        self.gas_rebalance = rebalance_cfg.get("gas_cost_rebalance", 0.20)
        self.min_rebalance_dist = rebalance_cfg.get("min_rebalance_distance_percent", 3) / 100.0
        self.cost_model = CostModel(gas_cost_per_tx=lp_cfg["gas_cost_per_tx"])

    def run(self, df):
        entry_price = df.iloc[0]["close"]
        lp = ConcentratedLPPosition(
            self.initial_capital, self.price_lower, self.price_upper, entry_price
        )

        current_lower = self.price_lower
        current_upper = self.price_upper

        if len(df) > 1:
            candle_hours = (df.iloc[1]["timestamp"] - df.iloc[0]["timestamp"]).total_seconds() / 3600
        else:
            candle_hours = 1.0

        equity_curve = []
        cumulative_fees = 0.0
        hours_in_range = 0
        total_hours = 0
        rebalance_count = 0
        consecutive_oor_hours = 0

        for _, row in df.iterrows():
            price = row["close"]
            volume_usd = row.get("quote_volume", row.get("volume", 0) * price)
            total_hours += candle_hours
            in_range = current_lower <= price <= current_upper
            if in_range:
                hours_in_range += candle_hours
                consecutive_oor_hours = 0
            else:
                consecutive_oor_hours += candle_hours

            lp_value = lp.get_position_value(price)
            fee_income = self.fee_estimator.estimate_fees(volume_usd, lp_value, in_range)
            cumulative_fees += fee_income

            # Dynamic rebalance
            if self.rebalance_enabled and consecutive_oor_hours >= self.rebalance_oor_hours:
                if price < current_lower:
                    distance = (current_lower - price) / current_lower
                else:
                    distance = (price - current_upper) / current_upper

                if distance >= self.min_rebalance_dist:
                    half_width = price * self.range_width_pct / 2
                    current_lower = round(price - half_width, 2)
                    current_upper = round(price + half_width, 2)

                    current_capital = lp_value + cumulative_fees
                    lp = ConcentratedLPPosition(
                        current_capital, current_lower, current_upper, price
                    )
                    consecutive_oor_hours = 0
                    rebalance_count += 1
                    self.cost_model.add_gas_cost(self.gas_rebalance)

            total_equity = lp_value + cumulative_fees
            equity_curve.append({
                "timestamp": row["timestamp"],
                "price": price,
                "total_equity": total_equity,
                "lp_value": lp_value,
                "il_pct": lp.get_impermanent_loss(price) * 100,
                "fees_earned": cumulative_fees,
                "in_range": in_range,
            })

        equity_df = pd.DataFrame(equity_curve)
        return {
            "strategy": "LP Only",
            "equity_curve": equity_df,
            "initial_capital": self.initial_capital,
            "final_equity": equity_df.iloc[-1]["total_equity"],
            "total_return_pct": ((equity_df.iloc[-1]["total_equity"] / self.initial_capital) - 1) * 100,
            "lp_fees_earned": cumulative_fees,
            "pct_time_in_range": (hours_in_range / total_hours * 100) if total_hours > 0 else 0,
            "rebalance_count": rebalance_count,
        }


class HodlEngine:
    """Simulates simple HODL strategy (50/50 ETH+USDT) for comparison."""

    def __init__(self, config):
        self.initial_capital = config["lp_position"]["initial_capital_usd"]

    def run(self, df):
        entry_price = df.iloc[0]["close"]
        # 50/50 split
        eth_amount = (self.initial_capital * 0.5) / entry_price
        usdt_amount = self.initial_capital * 0.5

        equity_curve = []
        for _, row in df.iterrows():
            price = row["close"]
            total_equity = eth_amount * price + usdt_amount
            equity_curve.append({
                "timestamp": row["timestamp"],
                "price": price,
                "total_equity": total_equity,
            })

        equity_df = pd.DataFrame(equity_curve)
        return {
            "strategy": "HODL 50/50",
            "equity_curve": equity_df,
            "initial_capital": self.initial_capital,
            "final_equity": equity_df.iloc[-1]["total_equity"],
            "total_return_pct": ((equity_df.iloc[-1]["total_equity"] / self.initial_capital) - 1) * 100,
        }


class BotAvaroEngine:
    """Bot Avaro: LP + Hedge (short below) + Trading (long above) with trailing stop.

    From Clase 3: combines hedge coverage with upside capture.
    - SHORT when price drops below lower_bound (like Aragan/hedge engine)
    - LONG when price breaks above upper_bound (with trailing stop)
    - Trailing stop: -0.5% initial, then -2% from max price seen
    """

    def __init__(self, config):
        lp_cfg = config["lp_position"]
        hedge_cfg = config["hedge"]
        regime_cfg = config.get("regime", {})
        rebalance_cfg = config.get("rebalance", {})
        avaro_cfg = config.get("avaro", {})

        self.initial_capital = lp_cfg["initial_capital_usd"]
        self.price_lower = lp_cfg["lower_bound"]
        self.price_upper = lp_cfg["upper_bound"]

        # Hedge params
        self.trigger_offset = hedge_cfg.get("trigger_offset_percent", 0.5) / 100.0
        self.hedge_coverage = hedge_cfg["hedge_coverage_percent"] / 100.0
        self.max_position_pct = hedge_cfg["max_position_percent"] / 100.0

        # Long/trading params
        self.long_trigger_offset = avaro_cfg.get("long_trigger_offset_percent", 0.5) / 100.0
        self.long_size_pct = avaro_cfg.get("long_size_percent", 30) / 100.0
        self.initial_stop_pct = avaro_cfg.get("initial_stop_loss_percent", 0.5) / 100.0
        self.trailing_stop_pct = avaro_cfg.get("trailing_stop_percent", 2.0) / 100.0

        # Regime
        self.adx_period = regime_cfg.get("adx_period", 14)
        self.ema_fast = regime_cfg.get("ema_fast_period", 10)
        self.ma_slow = regime_cfg.get("ma_slow_period", 25)

        # Rebalance
        self.rebalance_enabled = rebalance_cfg.get("enabled", True)
        self.rebalance_oor_hours = rebalance_cfg.get("out_of_range_hours_trigger", 24)
        self.range_width_pct = rebalance_cfg.get("range_width_percent", 10) / 100.0
        self.gas_rebalance = rebalance_cfg.get("gas_cost_rebalance", 0.20)
        self.min_rebalance_dist = rebalance_cfg.get("min_rebalance_distance_percent", 3) / 100.0

        self.fee_estimator = FeeEstimator(
            fee_tier=lp_cfg["fee_tier"],
            assumed_pool_tvl=lp_cfg["assumed_pool_tvl"],
            daily_pool_volume=lp_cfg.get("daily_pool_volume", 8_500_000)
        )
        self.perps = PerpsSimulator(
            leverage=hedge_cfg["leverage"],
            commission_taker=hedge_cfg["commission_rate_taker"],
            slippage_pct=hedge_cfg["slippage_percent"] / 100.0
        )
        self.long_trader = LongTrailingSimulator(
            leverage=hedge_cfg["leverage"],
            commission_taker=hedge_cfg["commission_rate_taker"],
            slippage_pct=hedge_cfg["slippage_percent"] / 100.0,
            initial_stop_pct=self.initial_stop_pct,
            trailing_stop_pct=self.trailing_stop_pct
        )
        self.funding = FundingRateModel(
            default_rate=hedge_cfg["default_funding_rate"],
            fetch_real=True
        )
        self.cost_model = CostModel(gas_cost_per_tx=lp_cfg["gas_cost_per_tx"])

    def run(self, df):
        df = add_indicators(df, self.adx_period, self.ema_fast, self.ma_slow)
        entry_price = df.iloc[0]["close"]

        lp = ConcentratedLPPosition(
            self.initial_capital, self.price_lower, self.price_upper, entry_price
        )

        current_lower = self.price_lower
        current_upper = self.price_upper

        if len(df) > 1:
            candle_hours = (df.iloc[1]["timestamp"] - df.iloc[0]["timestamp"]).total_seconds() / 3600
        else:
            candle_hours = 1.0

        equity_curve = []
        cumulative_fees = 0.0
        cumulative_hedge_pnl = 0.0
        cumulative_long_pnl = 0.0
        cumulative_funding = 0.0
        hedge_activations = 0
        long_activations = 0
        hours_hedged = 0
        hours_in_range = 0
        total_hours = 0
        rebalance_count = 0
        consecutive_oor_hours = 0

        logger.info(f"Starting Bot Avaro | Entry: ${entry_price:.0f} | "
                     f"Range: [{current_lower}, {current_upper}]")

        for idx in range(len(df)):
            row = df.iloc[idx]
            price = row["close"]
            timestamp = row["timestamp"]
            volume_usd = row.get("quote_volume", row.get("volume", 0) * price)
            total_hours += candle_hours

            in_range = current_lower <= price <= current_upper
            if in_range:
                hours_in_range += candle_hours

            # --- LP Fees ---
            lp_value = lp.get_position_value(price)
            if in_range:
                fee_income = self.fee_estimator.estimate_fees(volume_usd, lp_value, True)
                cumulative_fees += fee_income

            # --- SHORT hedge (below range) ---
            hedge_trigger = current_lower * (1 - self.trigger_offset)
            hedge_tp = current_lower

            if price <= hedge_trigger and not self.perps.is_open:
                volatile_exposure = lp.get_btc_exposure_usd(price)
                hedge_size = volatile_exposure * self.hedge_coverage
                max_size = self.initial_capital * self.max_position_pct * self.perps.leverage
                hedge_size = min(hedge_size, max_size)
                if hedge_size > 0:
                    fee = self.perps.open_short(price, hedge_size)
                    self.cost_model.add_trading_fee(fee)
                    hedge_activations += 1

            elif price >= hedge_tp and self.perps.is_open:
                net_pnl = self.perps.close_short(price)
                cumulative_hedge_pnl += net_pnl

            # --- LONG trading (above range) ---
            long_trigger = current_upper * (1 + self.long_trigger_offset)

            if price >= long_trigger and not self.long_trader.is_open and not self.perps.is_open:
                long_size = lp_value * self.long_size_pct
                if long_size > 0:
                    fee = self.long_trader.open_long(price, long_size)
                    self.cost_model.add_trading_fee(fee)
                    long_activations += 1

            if self.long_trader.is_open:
                stop_hit = self.long_trader.update_trailing_stop(price)
                if stop_hit:
                    net_pnl = self.long_trader.close_long(price)
                    cumulative_long_pnl += net_pnl

                if self.long_trader.is_liquidated(price):
                    loss = self.long_trader.margin_used * 0.9
                    cumulative_long_pnl -= loss
                    self.long_trader.is_open = False

            # --- Funding ---
            if self.perps.is_open:
                hours_hedged += candle_hours
                funding_cost = self.funding.calculate_funding_cost(
                    self.perps.position_size_usd, candle_hours, timestamp
                )
                self.perps.apply_funding(funding_cost)
                self.cost_model.add_funding_cost(funding_cost)
                cumulative_funding += funding_cost

                if self.perps.is_liquidated(price):
                    loss = self.perps.margin_used * 0.9
                    cumulative_hedge_pnl -= loss
                    self.perps.is_open = False
                    self.perps.total_pnl -= loss

            if self.long_trader.is_open:
                funding_cost = self.funding.calculate_funding_cost(
                    self.long_trader.position_size_usd, candle_hours, timestamp
                )
                self.long_trader.apply_funding(funding_cost)
                self.cost_model.add_funding_cost(funding_cost)
                cumulative_funding += funding_cost

            # --- Rebalance ---
            if self.rebalance_enabled:
                if not in_range:
                    consecutive_oor_hours += candle_hours
                else:
                    consecutive_oor_hours = 0

                if consecutive_oor_hours >= self.rebalance_oor_hours:
                    if price < current_lower:
                        distance = (current_lower - price) / current_lower
                    else:
                        distance = (price - current_upper) / current_upper

                    if distance >= self.min_rebalance_dist:
                        if self.perps.is_open:
                            cumulative_hedge_pnl += self.perps.close_short(price)
                        if self.long_trader.is_open:
                            cumulative_long_pnl += self.long_trader.close_long(price)

                        half = price * self.range_width_pct / 2
                        current_lower = round(price - half, 2)
                        current_upper = round(price + half, 2)
                        current_capital = lp_value + cumulative_fees
                        lp = ConcentratedLPPosition(
                            current_capital, current_lower, current_upper, price
                        )
                        consecutive_oor_hours = 0
                        rebalance_count += 1
                        self.cost_model.add_gas_cost(self.gas_rebalance)

            # --- Equity ---
            unrealized_hedge = self.perps.get_unrealized_pnl(price) if self.perps.is_open else 0
            unrealized_long = self.long_trader.get_unrealized_pnl(price) if self.long_trader.is_open else 0

            total_equity = (lp_value + cumulative_fees + cumulative_hedge_pnl +
                           cumulative_long_pnl + unrealized_hedge + unrealized_long - cumulative_funding)

            equity_curve.append({
                "timestamp": timestamp,
                "price": price,
                "total_equity": total_equity,
                "lp_value": lp_value,
                "il_pct": lp.get_impermanent_loss(price) * 100,
                "fees_earned": cumulative_fees,
                "hedge_pnl": cumulative_hedge_pnl + unrealized_hedge,
                "long_pnl": cumulative_long_pnl + unrealized_long,
                "hedge_active": self.perps.is_open,
                "long_active": self.long_trader.is_open,
                "in_range": in_range,
            })

        # Close remaining positions
        if self.perps.is_open:
            cumulative_hedge_pnl += self.perps.close_short(df.iloc[-1]["close"])
        if self.long_trader.is_open:
            cumulative_long_pnl += self.long_trader.close_long(df.iloc[-1]["close"])

        equity_df = pd.DataFrame(equity_curve)

        return {
            "strategy": "Bot Avaro",
            "equity_curve": equity_df,
            "initial_capital": self.initial_capital,
            "final_equity": equity_df.iloc[-1]["total_equity"],
            "total_return_pct": ((equity_df.iloc[-1]["total_equity"] / self.initial_capital) - 1) * 100,
            "lp_fees_earned": cumulative_fees,
            "hedge_pnl": cumulative_hedge_pnl,
            "long_pnl": cumulative_long_pnl,
            "funding_paid": cumulative_funding,
            "total_costs": self.cost_model.get_total_costs(),
            "hedge_activations": hedge_activations,
            "long_activations": long_activations,
            "hours_hedged": hours_hedged,
            "hours_in_range": hours_in_range,
            "total_hours": total_hours,
            "pct_time_in_range": (hours_in_range / total_hours * 100) if total_hours > 0 else 0,
            "pct_time_hedged": (hours_hedged / total_hours * 100) if total_hours > 0 else 0,
            "rebalance_count": rebalance_count,
            "perps_summary": self.perps.get_summary(),
            "long_summary": self.long_trader.get_summary(),
            "cost_summary": self.cost_model.get_summary(),
        }


# ── FURY Backtest Engine ───────────────────────────────────────────────────────


class FuryBacktestEngine:
    """Standalone RSI perps backtest for VIZNAGO FURY mode.

    No LP position. Trades BTC or ETH perps using a 6-gate signal stack on
    15-minute candles with 1-hour MTF confirmation.

    Gates (all must score >= min_gates to open):
        1. EMA trend  — EMA-8 vs EMA-21 direction
        2. RSI level  — RSI(9/OHLC4) < long_th or > short_th on 15m
        3. MTF RSI    — 1h RSI confirms direction (< 50 long, > 50 short)
        4. Volume     — candle volume > 20-bar SMA
        5. OBV slope  — positive for longs (accumulation gate)
        6. Funding    — configurable funding bias (default: always passes)

    Leverage is dynamic: gate_score 3=3x, 4=5x, 5=8x, 6=12x.
    """

    WARMUP = 50  # candles before signals are evaluated

    def __init__(self, config: dict):
        self.symbol = config.get("symbol", "ETH")          # 'BTC' | 'ETH'
        self.initial_capital = config.get("initial_capital", 1000.0)
        self.rsi_period = config.get("rsi_period", 9)
        self.rsi_long_th = config.get("rsi_long_th", 35.0)    # oversold threshold
        self.rsi_short_th = config.get("rsi_short_th", 65.0)  # overbought threshold
        self.min_gates = config.get("min_gates", 3)           # minimum gates to enter
        self.atr_multiplier = config.get("atr_multiplier", 1.5)
        self.funding_short_bias_th = config.get("funding_short_bias_th", 0.0005)

    def run(self, df_15m: pd.DataFrame, df_1h: pd.DataFrame) -> dict:
        """Run the FURY backtest.

        Args:
            df_15m: 15-minute OHLCV DataFrame (must cover the full test period)
            df_1h:  1-hour OHLCV DataFrame (same period, for MTF confirmation)

        Returns:
            Results dict with equity_curve, trades, and summary metrics.
        """
        # Add FURY indicators to both timeframes
        df_15m = add_fury_indicators(
            df_15m,
            rsi_period=self.rsi_period,
        ).reset_index(drop=True)

        df_1h = add_fury_indicators(
            df_1h,
            rsi_period=self.rsi_period,
        ).reset_index(drop=True)

        sim = StandalonePerpsSimulator(
            initial_capital=self.initial_capital,
            symbol=self.symbol,
            atr_multiplier=self.atr_multiplier,
        )

        equity_curve = []

        for i in range(self.WARMUP, len(df_15m)):
            row = df_15m.iloc[i]
            ts = row.get("timestamp", pd.Timestamp(f"2025-01-01") + pd.Timedelta(minutes=15 * i))

            # Reset circuit breaker at day boundary
            if hasattr(ts, "date"):
                sim.maybe_reset_circuit_breaker(ts.date())

            # Lookup matching 1h candle (last 1h candle whose timestamp <= 15m ts)
            row_1h = self._get_1h_row(df_1h, ts)

            # Record equity before action
            equity_curve.append({
                "timestamp": ts,
                "price": row["close"],
                "balance": sim.capital,
                "position": sim.position.side if sim.position else None,
            })

            # Manage open position — check SL/TP on this candle's range
            if sim.position:
                sim.check_sl_tp(
                    candle_high=row["high"],
                    candle_low=row["low"],
                    candle_close=row["close"],
                    ts=ts,
                )
                continue  # one position at a time; don't look for new entry

            # Evaluate signal gates
            if sim.circuit_breaker_triggered:
                continue

            gates, score, side = self._evaluate_gates(row, row_1h)
            if score < self.min_gates or side is None:
                continue

            atr = row.get("atr")
            if atr is None or np.isnan(atr) or atr <= 0:
                continue

            sim.open_position(side, row["close"], atr=atr, gate_score=score, ts=ts)

        # Close any remaining position at last price
        if sim.position and len(df_15m) > 0:
            last = df_15m.iloc[-1]
            last_ts = last.get("timestamp", None)
            sim.force_close(last["close"], reason="END_OF_DATA", ts=last_ts)

        return self._build_results(sim, equity_curve, df_15m)

    # ── Gate evaluation ───────────────────────────────────────────────────────

    def _evaluate_gates(self, row_15m, row_1h):
        """Return (gates_dict, score, side) or (gates, 0, None) if no signal."""
        ema_signal = row_15m.get("ema_signal", 0)
        if ema_signal == 0:
            return {}, 0, None

        side = "LONG" if ema_signal > 0 else "SHORT"

        # BTC golden rule — silently block shorts
        if self.symbol == "BTC" and side == "SHORT":
            return {}, 0, None

        rsi_15m = row_15m.get("rsi")
        if rsi_15m is None or np.isnan(rsi_15m):
            return {}, 0, None

        # Gate 1: EMA direction (already determined above)
        g1 = True

        # Gate 2: RSI level on 15m
        g2 = (rsi_15m < self.rsi_long_th) if side == "LONG" else (rsi_15m > self.rsi_short_th)

        # Gate 3: 1h RSI MTF confirmation
        rsi_1h = row_1h.get("rsi") if row_1h is not None else None
        if rsi_1h is not None and not np.isnan(rsi_1h):
            g3 = (rsi_1h < 50) if side == "LONG" else (rsi_1h > 50)
        else:
            g3 = False

        # Gate 4: Volume above 20-bar SMA
        vol = row_15m.get("volume", 0)
        vol_sma = row_15m.get("vol_sma20")
        g4 = bool(vol > vol_sma) if (vol_sma and not np.isnan(vol_sma)) else False

        # Gate 5: OBV slope (positive for longs, skip gate for shorts)
        obv_slope = row_15m.get("obv_slope")
        if side == "LONG":
            g5 = bool(obv_slope > 0) if (obv_slope is not None and not np.isnan(obv_slope)) else False
        else:
            g5 = True  # not applied to shorts

        # Gate 6: Funding bias (pass by default — live bot will check real funding)
        g6 = True

        gates = {"ema": g1, "rsi": g2, "mtf": g3, "volume": g4, "obv": g5, "funding": g6}
        score = sum(1 for v in gates.values() if v)

        return gates, score, side

    def _get_1h_row(self, df_1h: pd.DataFrame, ts) -> dict | None:
        """Return the most recent 1h row whose timestamp <= ts."""
        if df_1h is None or len(df_1h) == 0:
            return None
        try:
            mask = df_1h["timestamp"] <= ts
            if not mask.any():
                return None
            return df_1h[mask].iloc[-1].to_dict()
        except Exception:
            return None

    # ── Results builder ───────────────────────────────────────────────────────

    def _build_results(self, sim: StandalonePerpsSimulator,
                       equity_curve: list, df_15m: pd.DataFrame) -> dict:
        trades = sim.trades
        n = len(trades)

        wins = [t for t in trades if t.net_pnl > 0]
        losses = [t for t in trades if t.net_pnl <= 0]
        win_rate = len(wins) / n if n > 0 else 0.0
        avg_win = sum(t.net_pnl for t in wins) / len(wins) if wins else 0.0
        avg_loss = sum(t.net_pnl for t in losses) / len(losses) if losses else 0.0
        gross_profit = sum(t.net_pnl for t in wins)
        gross_loss = abs(sum(t.net_pnl for t in losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0
        expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss) if n > 0 else 0.0

        final_capital = sim.capital
        total_return_pct = ((final_capital / self.initial_capital) - 1) * 100

        # Max drawdown from equity curve
        balances = [e["balance"] for e in equity_curve]
        max_dd_pct = 0.0
        if balances:
            peak = balances[0]
            for b in balances:
                if b > peak:
                    peak = b
                dd = (peak - b) / peak * 100 if peak > 0 else 0
                if dd > max_dd_pct:
                    max_dd_pct = dd

        # Sharpe (trade-level returns)
        if n >= 2:
            rets = [t.net_pnl / t.balance_before for t in trades]
            avg_r = np.mean(rets)
            std_r = np.std(rets)
            sharpe = (avg_r / std_r * np.sqrt(252)) if std_r > 0 else 0.0
        else:
            sharpe = 0.0

        side_counts = {"LONG": 0, "SHORT": 0}
        side_pnl = {"LONG": 0.0, "SHORT": 0.0}
        for t in trades:
            side_counts[t.side] += 1
            side_pnl[t.side] += t.net_pnl

        exit_reasons = {}
        for t in trades:
            exit_reasons[t.exit_reason] = exit_reasons.get(t.exit_reason, 0) + 1

        logger.info(
            f"FURY backtest ({self.symbol}) complete: "
            f"{n} trades | WR {win_rate:.1%} | Return {total_return_pct:+.1f}% | "
            f"MaxDD {max_dd_pct:.1f}% | Sharpe {sharpe:.2f}"
        )

        return {
            "strategy": f"fury_{self.symbol.lower()}",
            "symbol": self.symbol,
            "initial_capital": self.initial_capital,
            "final_capital": final_capital,
            "total_return_pct": total_return_pct,
            "max_drawdown_pct": max_dd_pct,
            "sharpe": sharpe,
            "total_trades": n,
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "expectancy": expectancy,
            "total_fees": sim.total_fees,
            "long_trades": side_counts["LONG"],
            "short_trades": side_counts["SHORT"],
            "long_pnl": side_pnl["LONG"],
            "short_pnl": side_pnl["SHORT"],
            "exit_reasons": exit_reasons,
            "equity_curve": equity_curve,
            "trades": [t.__dict__ for t in trades],
        }
