#!/usr/bin/env python3
"""
LP + Perps Hedge Strategy Backtester
=====================================
Simulates providing concentrated liquidity (Uniswap v3 style) in a BTC/USDT pool
and hedging impermanent loss by opening SHORT perps when price drops below LP range.

Compares 3 strategies:
  1. HODL 50/50 (baseline)
  2. LP Only (earn fees, suffer IL)
  3. LP + Hedge (earn fees, hedge IL with shorts)

Usage:
  python run_backtest.py
  python run_backtest.py --config custom_config.json
"""

import os
import sys
import json
import logging
import argparse

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.data.price_fetcher import PriceFetcher
from src.engine.strategy_comparator import StrategyComparator
from src.reporting.report_generator import (
    print_comparison_report,
    save_results,
    plot_equity_curves,
)
from src.reporting.metrics import calculate_metrics


def setup_logging(level=logging.INFO):
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main():
    parser = argparse.ArgumentParser(description="LP + Hedge Strategy Backtester")
    parser.add_argument("--config", default="config.json", help="Config file path")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    setup_logging(logging.DEBUG if args.debug else logging.INFO)
    logger = logging.getLogger("backtest")

    # Load config
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), args.config)
    with open(config_path) as f:
        config = json.load(f)

    logger.info(f"Loaded config from {config_path}")

    # Step 1: Fetch price data
    bt_cfg = config["backtest"]
    fetcher = PriceFetcher(symbol=bt_cfg["symbol"], interval=bt_cfg["interval"])
    df = fetcher.fetch(bt_cfg["start_date"], bt_cfg["end_date"])

    logger.info(f"Price data: {len(df)} candles from {df.iloc[0]['timestamp']} to {df.iloc[-1]['timestamp']}")
    logger.info(f"Price range in data: ${df['close'].min():,.0f} - ${df['close'].max():,.0f}")

    # Step 2: Run all strategies
    comparator = StrategyComparator(config)
    results = comparator.run_all(df)

    # Step 3: Calculate metrics
    all_metrics = {}
    for key, result in results.items():
        eq_df = result["equity_curve"]
        total_hours = result.get("total_hours", len(eq_df))
        all_metrics[key] = calculate_metrics(eq_df, result["initial_capital"], total_hours)

    # Step 4: Print report
    print_comparison_report(results, config)

    # Step 5: Save results
    output_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        config["output"]["results_dir"]
    )

    if config["output"]["save_results"]:
        save_results(results, all_metrics, config, output_dir)

    if config["output"]["plot_equity_curves"]:
        plot_equity_curves(results, config, output_dir)

    return results


if __name__ == "__main__":
    main()
