"""Performance metrics calculation."""

import numpy as np
import pandas as pd


def calculate_metrics(equity_df, initial_capital, total_hours):
    """Calculate standard performance metrics from equity curve."""
    equity = equity_df["total_equity"].values

    # Returns
    returns = np.diff(equity) / equity[:-1]
    returns = returns[~np.isnan(returns) & ~np.isinf(returns)]

    # Total return
    total_return = (equity[-1] / initial_capital - 1) * 100

    # Annualized return (assuming hours)
    years = total_hours / 8760
    if years > 0 and equity[-1] > 0:
        annualized_return = ((equity[-1] / initial_capital) ** (1 / years) - 1) * 100
    else:
        annualized_return = 0.0

    # Max drawdown
    peak = np.maximum.accumulate(equity)
    drawdown = (peak - equity) / peak
    max_drawdown = np.max(drawdown) * 100

    # Sharpe ratio (annualized, assuming hourly returns)
    if len(returns) > 1 and np.std(returns) > 0:
        periods_per_year = 8760  # hourly
        sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(periods_per_year)
    else:
        sharpe = 0.0

    # Sortino ratio
    downside = returns[returns < 0]
    if len(downside) > 1 and np.std(downside) > 0:
        sortino = (np.mean(returns) / np.std(downside)) * np.sqrt(8760)
    else:
        sortino = 0.0

    # Profit factor
    gains = returns[returns > 0].sum()
    losses = abs(returns[returns < 0].sum())
    profit_factor = gains / losses if losses > 0 else float("inf")

    return {
        "total_return_pct": round(total_return, 2),
        "annualized_return_pct": round(annualized_return, 2),
        "max_drawdown_pct": round(max_drawdown, 2),
        "sharpe_ratio": round(sharpe, 2),
        "sortino_ratio": round(sortino, 2),
        "profit_factor": round(profit_factor, 2),
        "volatility_pct": round(np.std(returns) * np.sqrt(8760) * 100, 2) if len(returns) > 0 else 0,
        "best_return_pct": round(np.max(returns) * 100, 4) if len(returns) > 0 else 0,
        "worst_return_pct": round(np.min(returns) * 100, 4) if len(returns) > 0 else 0,
    }
