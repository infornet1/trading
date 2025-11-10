#!/usr/bin/env python3
"""
Strategy Comparison Dashboard
Real-time comparison of different trading strategies performance
"""

import sys
from signal_tracker import SignalTracker
from tabulate import tabulate
from datetime import datetime


def print_header():
    """Print dashboard header"""
    print("\n" + "=" * 80)
    print("📊 STRATEGY COMPARISON DASHBOARD")
    print("=" * 80)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80 + "\n")


def print_strategy_performance(comparison_data):
    """Display strategy performance comparison"""
    strategies = comparison_data['by_strategy']

    if not strategies:
        print("⚠️  No strategy data available yet")
        return

    print("📈 STRATEGY PERFORMANCE COMPARISON")
    print("-" * 80)

    headers = ['Strategy', 'Version', 'Signals', 'Wins', 'Losses', 'Win Rate', 'Avg Win', 'Avg Loss', 'Total P&L']
    table_data = []

    for strategy_key, stats in strategies.items():
        table_data.append([
            stats['name'],
            stats['version'],
            stats['total_signals'],
            stats['wins'],
            stats['losses'],
            f"{stats['win_rate']:.1f}%",
            f"{stats['avg_win']:.3f}%",
            f"{stats['avg_loss']:.3f}%",
            f"{stats['total_profit']:.3f}%"
        ])

    print(tabulate(table_data, headers=headers, tablefmt='grid'))
    print()


def print_quality_breakdown(comparison_data):
    """Display signal quality breakdown"""
    quality_stats = comparison_data['by_quality']

    if not quality_stats:
        print("⚠️  No quality data available yet")
        return

    print("⭐ SIGNAL QUALITY BREAKDOWN")
    print("-" * 80)

    headers = ['Quality', 'Total', 'Wins', 'Win Rate', 'Avg P&L']
    table_data = []

    # Sort by quality order
    quality_order = ['PERFECT', 'HIGH', 'MEDIUM', 'LOW']
    for quality in quality_order:
        if quality in quality_stats:
            stats = quality_stats[quality]
            table_data.append([
                quality,
                stats['total'],
                stats['wins'],
                f"{stats['win_rate']:.1f}%",
                f"{stats['avg_profit']:.3f}%"
            ])

    print(tabulate(table_data, headers=headers, tablefmt='grid'))
    print()


def print_market_condition_analysis(comparison_data):
    """Display performance by market condition"""
    condition_stats = comparison_data['by_market_condition']

    if not condition_stats:
        print("⚠️  No market condition data available yet")
        return

    print("🌐 PERFORMANCE BY MARKET CONDITION")
    print("-" * 80)

    headers = ['Market Condition', 'Total', 'Wins', 'Win Rate', 'Avg P&L']
    table_data = []

    # Sort by condition
    condition_order = ['BULLISH', 'BEARISH', 'NEUTRAL', 'UNKNOWN']
    for condition in condition_order:
        if condition in condition_stats:
            stats = condition_stats[condition]
            table_data.append([
                condition,
                stats['total'],
                stats['wins'],
                f"{stats['win_rate']:.1f}%",
                f"{stats['avg_profit']:.3f}%"
            ])

    print(tabulate(table_data, headers=headers, tablefmt='grid'))
    print()


def print_recommendations(comparison_data):
    """Print strategy recommendations based on data"""
    strategies = comparison_data['by_strategy']
    quality_stats = comparison_data['by_quality']

    print("💡 RECOMMENDATIONS")
    print("-" * 80)

    # Best performing strategy
    if strategies:
        best_strategy = max(strategies.items(), key=lambda x: x[1]['total_profit'])
        print(f"✅ Best Strategy: {best_strategy[1]['name']} {best_strategy[1]['version']}")
        print(f"   Total P&L: {best_strategy[1]['total_profit']:.3f}%")
        print(f"   Win Rate: {best_strategy[1]['win_rate']:.1f}%")
        print()

    # Quality recommendation
    if quality_stats:
        # Check if higher quality signals perform better
        if 'PERFECT' in quality_stats or 'HIGH' in quality_stats:
            high_qual_wr = quality_stats.get('PERFECT', {}).get('win_rate', 0) + \
                          quality_stats.get('HIGH', {}).get('win_rate', 0)
            low_qual_wr = quality_stats.get('MEDIUM', {}).get('win_rate', 0) + \
                         quality_stats.get('LOW', {}).get('win_rate', 0)

            if high_qual_wr > low_qual_wr * 1.2:  # 20% better
                print("⭐ Recommendation: Focus on HIGH and PERFECT quality signals")
                print("   High quality signals show significantly better win rates")
                print()

    # Market condition recommendation
    condition_stats = comparison_data['by_market_condition']
    if condition_stats:
        best_condition = max(condition_stats.items(), key=lambda x: x[1]['win_rate'])
        print(f"🌐 Best Market Condition: {best_condition[0]}")
        print(f"   Win Rate: {best_condition[1]['win_rate']:.1f}%")
        print(f"   Recommendation: Increase position sizes in {best_condition[0]} markets")
        print()

    print("-" * 80)


def main():
    """Main dashboard function"""
    # Get time period from command line args
    hours = int(sys.argv[1]) if len(sys.argv) > 1 else 24

    # Initialize tracker
    tracker = SignalTracker()

    # Print header
    print_header()

    # Get comparison data
    comparison = tracker.get_strategy_comparison(hours_back=hours)

    print(f"📅 Analyzing last {hours} hours of trading data\n")

    # Display all sections
    print_strategy_performance(comparison)
    print_quality_breakdown(comparison)
    print_market_condition_analysis(comparison)
    print_recommendations(comparison)

    # Footer
    print("=" * 80)
    print("💾 Data source: signals.db")
    print("🔄 Run 'python3 strategy_dashboard.py <hours>' to analyze different time periods")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
