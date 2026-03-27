"""Runs all strategy variants and compares results side by side."""

import logging
from src.engine.backtest_engine import (
    LPHedgeBacktestEngine, LPOnlyEngine, HodlEngine, BotAvaroEngine,
    FuryBacktestEngine,
)

logger = logging.getLogger(__name__)


class StrategyComparator:
    """Runs and compares Bot Aragan (hedge) vs Bot Avaro (hedge+long) vs LP Only vs HODL."""

    def __init__(self, config):
        self.config = config
        self.results = {}

    def run_all(self, df):
        """Run all four LP strategies on the same price data."""
        logger.info("=" * 60)
        logger.info("Running Strategy 1/4: HODL 50/50")
        logger.info("=" * 60)
        hodl = HodlEngine(self.config)
        self.results["hodl"] = hodl.run(df)

        logger.info("=" * 60)
        logger.info("Running Strategy 2/4: LP Only (no hedge)")
        logger.info("=" * 60)
        lp_only = LPOnlyEngine(self.config)
        self.results["lp_only"] = lp_only.run(df)

        logger.info("=" * 60)
        logger.info("Running Strategy 3/4: Bot Aragan (LP + Hedge)")
        logger.info("=" * 60)
        lp_hedge = LPHedgeBacktestEngine(self.config)
        self.results["lp_hedge"] = lp_hedge.run(df)

        logger.info("=" * 60)
        logger.info("Running Strategy 4/4: Bot Avaro (LP + Hedge + Long)")
        logger.info("=" * 60)
        avaro = BotAvaroEngine(self.config)
        self.results["avaro"] = avaro.run(df)

        return self.results


class FuryComparator:
    """Runs FURY RSI Trader vs HODL baseline on the same price data.

    Requires no LP parameters — operates purely on perps.
    Accepts separate 15m and 1h DataFrames.

    Usage:
        comp = FuryComparator(fury_config)
        results = comp.run(df_15m, df_1h)
        # results keys: 'hodl', 'fury'
    """

    def __init__(self, fury_config: dict):
        """
        fury_config keys:
            symbol           — 'BTC' | 'ETH'
            initial_capital  — starting USDC
            rsi_period       — default 9
            rsi_long_th      — default 35
            rsi_short_th     — default 65
            min_gates        — minimum gates to open (default 3)
            atr_multiplier   — default 1.5
        """
        self.config = fury_config
        self.results = {}

    def run(self, df_15m, df_1h):
        """Run FURY and HODL on the provided price data."""
        capital = self.config.get("initial_capital", 1000.0)

        logger.info("=" * 60)
        logger.info("FURY Comparator — Strategy 1/2: HODL baseline")
        logger.info("=" * 60)
        # HODL uses 15m close prices; start/end prices determine return
        start_price = df_15m["close"].iloc[self.config.get("warmup", 50)]
        end_price = df_15m["close"].iloc[-1]
        hodl_return = ((end_price / start_price) - 1) * 100
        self.results["hodl"] = {
            "strategy": "hodl",
            "initial_capital": capital,
            "final_capital": capital * (1 + hodl_return / 100),
            "total_return_pct": hodl_return,
            "symbol": self.config.get("symbol", "ETH"),
        }

        logger.info("=" * 60)
        logger.info(f"FURY Comparator — Strategy 2/2: FURY ({self.config.get('symbol','ETH')})")
        logger.info("=" * 60)
        engine = FuryBacktestEngine(self.config)
        self.results["fury"] = engine.run(df_15m, df_1h)

        self._log_summary()
        return self.results

    def _log_summary(self):
        hodl = self.results["hodl"]
        fury = self.results["fury"]
        logger.info("=" * 60)
        logger.info("FURY vs HODL Summary")
        logger.info("=" * 60)
        logger.info(f"  HODL return:       {hodl['total_return_pct']:+.2f}%")
        logger.info(f"  FURY return:       {fury['total_return_pct']:+.2f}%")
        logger.info(f"  FURY trades:       {fury['total_trades']}")
        logger.info(f"  FURY win rate:     {fury['win_rate']:.1%}")
        logger.info(f"  FURY max DD:       {fury['max_drawdown_pct']:.1f}%")
        logger.info(f"  FURY Sharpe:       {fury['sharpe']:.2f}")
        logger.info(f"  FURY fees paid:    ${fury['total_fees']:.2f}")
