"""Generate console reports and save results."""

import os
import json
import logging
from datetime import datetime

from src.reporting.metrics import calculate_metrics

logger = logging.getLogger(__name__)


def print_header(text):
    print(f"\n{'=' * 80}")
    print(f"  {text}")
    print(f"{'=' * 80}")


def print_comparison_report(results, config):
    """Print side-by-side comparison of all strategies."""
    print_header("LP + PERPS HEDGE STRATEGY BACKTEST (Aragan vs Avaro)")

    bt_cfg = config["backtest"]
    lp_cfg = config["lp_position"]
    hedge_cfg = config["hedge"]

    print(f"\n  Period:      {bt_cfg['start_date']} to {bt_cfg['end_date']}")
    print(f"  Symbol:      {bt_cfg['symbol']}")
    print(f"  Interval:    {bt_cfg['interval']}")
    print(f"  Capital:     ${lp_cfg['initial_capital_usd']:,.0f}")
    print(f"  LP Range:    [{lp_cfg['lower_bound']:,.0f} - {lp_cfg['upper_bound']:,.0f}]")
    print(f"  Hedge:       {hedge_cfg['hedge_coverage_percent']}% coverage, {hedge_cfg['leverage']}x leverage")
    print(f"  Trigger:     lower_bound - {hedge_cfg.get('trigger_offset_percent', 0.5)}% (STOP LIMIT)")

    regime_cfg = config.get("regime", {})
    if regime_cfg:
        print(f"  ADX:         lateral < {regime_cfg.get('adx_lateral_threshold', 20)}, "
              f"trend > {regime_cfg.get('adx_trend_threshold', 30)}")

    rebalance_cfg = config.get("rebalance", {})
    if rebalance_cfg.get("enabled"):
        print(f"  Rebalance:   after {rebalance_cfg.get('out_of_range_hours_trigger', 24)}h OOR, "
              f"{rebalance_cfg.get('range_width_percent', 10)}% width")

    avaro_cfg = config.get("avaro", {})
    if avaro_cfg:
        print(f"  Avaro Long:  trigger +{avaro_cfg.get('long_trigger_offset_percent', 0.5)}%, "
              f"trailing stop -{avaro_cfg.get('trailing_stop_percent', 2)}%")

    # Calculate metrics for each
    all_metrics = {}
    for key, result in results.items():
        eq_df = result["equity_curve"]
        total_hours = result.get("total_hours", len(eq_df))
        all_metrics[key] = calculate_metrics(eq_df, result["initial_capital"], total_hours)

    # Summary table - 4 columns
    print_header("STRATEGY COMPARISON")

    cw = 15  # column width

    print(f"\n  {'Metric':<22} {'HODL':>{cw}} {'LP Only':>{cw}} {'Aragan':>{cw}} {'Avaro':>{cw}}")
    print(f"  {'-' * 22} {'-' * cw} {'-' * cw} {'-' * cw} {'-' * cw}")

    def row(label, hodl, lp, aragan, avaro):
        print(f"  {label:<22} {hodl:>{cw}} {lp:>{cw}} {aragan:>{cw}} {avaro:>{cw}}")

    r = results
    m = all_metrics

    row("Final Value",
        f"${r['hodl']['final_equity']:,.0f}",
        f"${r['lp_only']['final_equity']:,.0f}",
        f"${r['lp_hedge']['final_equity']:,.0f}",
        f"${r['avaro']['final_equity']:,.0f}")

    row("Total Return",
        f"{r['hodl']['total_return_pct']:+.1f}%",
        f"{r['lp_only']['total_return_pct']:+.1f}%",
        f"{r['lp_hedge']['total_return_pct']:+.1f}%",
        f"{r['avaro']['total_return_pct']:+.1f}%")

    row("Max Drawdown",
        f"{m['hodl']['max_drawdown_pct']:.1f}%",
        f"{m['lp_only']['max_drawdown_pct']:.1f}%",
        f"{m['lp_hedge']['max_drawdown_pct']:.1f}%",
        f"{m['avaro']['max_drawdown_pct']:.1f}%")

    row("Sharpe Ratio",
        f"{m['hodl']['sharpe_ratio']:.2f}",
        f"{m['lp_only']['sharpe_ratio']:.2f}",
        f"{m['lp_hedge']['sharpe_ratio']:.2f}",
        f"{m['avaro']['sharpe_ratio']:.2f}")

    row("Sortino Ratio",
        f"{m['hodl']['sortino_ratio']:.2f}",
        f"{m['lp_only']['sortino_ratio']:.2f}",
        f"{m['lp_hedge']['sortino_ratio']:.2f}",
        f"{m['avaro']['sortino_ratio']:.2f}")

    # LP metrics
    print(f"\n  {'--- LP Metrics ---':<22}")
    row("LP Fees", "N/A",
        f"${r['lp_only']['lp_fees_earned']:,.0f}",
        f"${r['lp_hedge']['lp_fees_earned']:,.0f}",
        f"${r['avaro']['lp_fees_earned']:,.0f}")
    row("Time in Range", "N/A",
        f"{r['lp_only']['pct_time_in_range']:.1f}%",
        f"{r['lp_hedge']['pct_time_in_range']:.1f}%",
        f"{r['avaro']['pct_time_in_range']:.1f}%")
    row("Rebalances", "N/A",
        f"{r['lp_only'].get('rebalance_count', 0)}",
        f"{r['lp_hedge'].get('rebalance_count', 0)}",
        f"{r['avaro'].get('rebalance_count', 0)}")

    # Hedge metrics
    print(f"\n  {'--- Hedge (Short) ---':<22}")
    row("Hedge P&L", "N/A", "N/A",
        f"${r['lp_hedge']['hedge_pnl']:+,.0f}",
        f"${r['avaro']['hedge_pnl']:+,.0f}")
    row("Hedge Count", "N/A", "N/A",
        f"{r['lp_hedge']['hedge_activations']}",
        f"{r['avaro']['hedge_activations']}")

    # Long/trading metrics (Avaro only)
    print(f"\n  {'--- Trading (Long) ---':<22}")
    row("Long P&L", "N/A", "N/A", "N/A",
        f"${r['avaro'].get('long_pnl', 0):+,.0f}")
    row("Long Count", "N/A", "N/A", "N/A",
        f"{r['avaro'].get('long_activations', 0)}")

    long_summary = r['avaro'].get('long_summary', {})
    if long_summary:
        row("Long Win Rate", "N/A", "N/A", "N/A",
            f"{long_summary.get('win_rate', 0):.0f}%")

    # Costs
    print(f"\n  {'--- Costs ---':<22}")
    row("Funding Paid", "N/A", "N/A",
        f"${r['lp_hedge']['funding_paid']:,.0f}",
        f"${r['avaro']['funding_paid']:,.0f}")
    row("Total Costs", "N/A", "N/A",
        f"${r['lp_hedge']['total_costs']:,.0f}",
        f"${r['avaro']['total_costs']:,.0f}")

    # Winner
    print_header("VERDICT")
    returns = {
        "HODL 50/50": r["hodl"]["total_return_pct"],
        "LP Only": r["lp_only"]["total_return_pct"],
        "Bot Aragan": r["lp_hedge"]["total_return_pct"],
        "Bot Avaro": r["avaro"]["total_return_pct"],
    }
    winner = max(returns, key=returns.get)
    print(f"\n  Best Strategy: {winner} ({returns[winner]:+.1f}%)")

    aragan_vs_lp = r["lp_hedge"]["total_return_pct"] - r["lp_only"]["total_return_pct"]
    avaro_vs_aragan = r["avaro"]["total_return_pct"] - r["lp_hedge"]["total_return_pct"]
    print(f"  Aragan vs LP Only:  {aragan_vs_lp:+.1f}%")
    print(f"  Avaro vs Aragan:    {avaro_vs_aragan:+.1f}%")

    avaro_extra = r["avaro"]["final_equity"] - r["lp_hedge"]["final_equity"]
    if avaro_extra > 0:
        print(f"\n  >> Avaro long trading adds: +${avaro_extra:,.0f}")
    else:
        print(f"\n  >> Avaro long trading costs: ${avaro_extra:,.0f}")

    print()


def save_results(results, metrics, config, output_dir="results"):
    """Save results to JSON file."""
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(output_dir, f"backtest_{timestamp}.json")

    output = {
        "config": config,
        "run_date": timestamp,
        "results": {},
    }

    for key, result in results.items():
        r = {k: v for k, v in result.items() if k != "equity_curve"}
        output["results"][key] = r

    output["metrics"] = metrics

    with open(filename, "w") as f:
        json.dump(output, f, indent=2, default=str)

    logger.info(f"Results saved to {filename}")
    print(f"  Results saved to: {filename}")
    return filename


def plot_equity_curves(results, config, output_dir="results"):
    """Plot equity curves with ADX and range rebalancing visualization."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError:
        logger.warning("matplotlib not available, skipping plot")
        return

    os.makedirs(output_dir, exist_ok=True)

    fig, axes = plt.subplots(4, 1, figsize=(14, 16), sharex=True)

    # Plot 1: Equity curves (all 4 strategies)
    ax1 = axes[0]
    colors = {"hodl": "gray", "lp_only": "blue", "lp_hedge": "green", "avaro": "gold"}
    for key, result in results.items():
        eq = result["equity_curve"]
        ax1.plot(eq["timestamp"], eq["total_equity"],
                 label=result["strategy"],
                 color=colors.get(key, "black"),
                 linewidth=1.2)

    ax1.set_ylabel("Portfolio Value (USD)")
    ax1.set_title(f"Bot Aragan vs Bot Avaro | {config['backtest']['symbol']} | "
                  f"{config['backtest']['start_date']} to {config['backtest']['end_date']}")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # Plot 2: Price with dynamic LP range
    ax2 = axes[1]
    # Use avaro equity curve for price/range data
    eq_main = results.get("avaro", results.get("lp_hedge", {})).get("equity_curve")
    if eq_main is not None:
        ax2.plot(eq_main["timestamp"], eq_main["price"], color="orange", linewidth=1, label="Price")

    eq_hedge = results["lp_hedge"]["equity_curve"]
    if "range_lower" in eq_hedge.columns:
        ax2.plot(eq_hedge["timestamp"], eq_hedge["range_lower"], color="red",
                 linestyle="--", alpha=0.7, linewidth=0.8, label="LP Range")
        ax2.plot(eq_hedge["timestamp"], eq_hedge["range_upper"], color="green",
                 linestyle="--", alpha=0.7, linewidth=0.8)
        ax2.fill_between(eq_hedge["timestamp"], eq_hedge["range_lower"],
                         eq_hedge["range_upper"], alpha=0.05, color="green")

    ax2.set_ylabel("Price (USD)")
    ax2.legend(fontsize=8)
    ax2.grid(True, alpha=0.3)

    # Plot 3: ADX
    ax3 = axes[2]
    if "adx" in eq_hedge.columns:
        ax3.plot(eq_hedge["timestamp"], eq_hedge["adx"], color="purple", linewidth=1, label="ADX")
        ax3.axhline(y=config.get("regime", {}).get("adx_lateral_threshold", 20),
                     color="green", linestyle="--", alpha=0.7, label="Lateral (<20)")
        ax3.axhline(y=config.get("regime", {}).get("adx_trend_threshold", 30),
                     color="red", linestyle="--", alpha=0.7, label="Trend (>30)")
        ax3.fill_between(eq_hedge["timestamp"], 0, eq_hedge["adx"],
                         where=eq_hedge["adx"] < 20, alpha=0.1, color="green")
        ax3.fill_between(eq_hedge["timestamp"], 0, eq_hedge["adx"],
                         where=eq_hedge["adx"] > 30, alpha=0.1, color="red")
    ax3.set_ylabel("ADX")
    ax3.legend(fontsize=8)
    ax3.grid(True, alpha=0.3)

    # Plot 4: IL + hedge/long PnL
    ax4 = axes[3]
    ax4.plot(eq_hedge["timestamp"], eq_hedge["il_pct"], color="red", linewidth=1, label="IL %")
    ax4.fill_between(eq_hedge["timestamp"], eq_hedge["il_pct"], 0, alpha=0.1, color="red")
    ax4.set_ylabel("IL %")
    ax4.set_xlabel("Date")
    ax4.legend()
    ax4.grid(True, alpha=0.3)

    ax4.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.tight_layout()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    plot_path = os.path.join(output_dir, f"aragan_vs_avaro_{timestamp}.png")
    plt.savefig(plot_path, dpi=150)
    plt.close()

    print(f"  Chart saved to: {plot_path}")
    return plot_path
