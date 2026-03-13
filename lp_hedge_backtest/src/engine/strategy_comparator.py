"""Runs all strategy variants and compares results side by side."""

import logging
from src.engine.backtest_engine import (
    LPHedgeBacktestEngine, LPOnlyEngine, HodlEngine, BotAvaroEngine
)

logger = logging.getLogger(__name__)


class StrategyComparator:
    """Runs and compares Bot Aragan (hedge) vs Bot Avaro (hedge+long) vs LP Only vs HODL."""

    def __init__(self, config):
        self.config = config
        self.results = {}

    def run_all(self, df):
        """Run all four strategies on the same price data."""
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
