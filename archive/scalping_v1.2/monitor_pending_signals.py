#!/usr/bin/env python3
"""
Pending Signals Monitor
Tracks pending signals and shows how close they are to WIN/LOSS
"""

import sqlite3
import requests
import time
from datetime import datetime, timedelta
from tabulate import tabulate
import os

def clear_screen():
    """Clear terminal screen"""
    os.system('clear' if os.name == 'posix' else 'cls')

def get_current_btc_price():
    """Fetch current BTC price from BingX"""
    try:
        url = "https://open-api.bingx.com/openApi/swap/v2/quote/ticker"
        params = {"symbol": "BTC-USDT"}
        response = requests.get(url, params=params, timeout=5)

        if response.status_code == 200:
            data = response.json()
            if data.get('code') == 0:
                return float(data['data']['lastPrice'])
    except:
        pass

    return None

def get_pending_signals():
    """Get all pending signals from database"""
    conn = sqlite3.connect('signals.db')
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            timestamp,
            signal_type,
            direction,
            entry_price,
            suggested_target,
            suggested_stop,
            actual_high,
            actual_low,
            target_hit,
            stop_hit
        FROM signals
        WHERE final_result = 'PENDING' OR final_result IS NULL
        ORDER BY timestamp DESC
        LIMIT 50
    """)

    signals = []
    for row in cursor.fetchall():
        signals.append({
            'id': row[0],
            'timestamp': row[1],
            'signal_type': row[2],
            'direction': row[3],
            'entry_price': row[4],
            'target': row[5],
            'stop': row[6],
            'actual_high': row[7],
            'actual_low': row[8],
            'target_hit': row[9],
            'stop_hit': row[10]
        })

    conn.close()
    return signals

def analyze_signal_progress(signal, current_price):
    """Calculate how close signal is to target/stop using actual tracked data"""
    entry = signal['entry_price']
    target = signal['target']
    stop = signal['stop']
    direction = signal['direction']

    # Get tracked highs/lows from database if available
    actual_high = signal.get('actual_high')
    actual_low = signal.get('actual_low')
    target_hit_db = signal.get('target_hit')
    stop_hit_db = signal.get('stop_hit')

    # Use tracked data if available, otherwise use current price
    if actual_high is not None and actual_low is not None:
        # Signal has been tracked - use actual highs/lows
        high_price = actual_high
        low_price = actual_low
        is_tracked = True
    else:
        # Signal not tracked yet - use current price as both high and low
        high_price = current_price
        low_price = current_price
        is_tracked = False

    if direction == 'LONG':
        # LONG: target above, stop below
        # Use actual_high for target progress, actual_low for stop progress
        progress_to_target = ((high_price - entry) / (target - entry)) * 100
        progress_to_stop = ((entry - low_price) / (entry - stop)) * 100
        current_pnl_pct = ((current_price - entry) / entry) * 100
    elif direction == 'SHORT':
        # SHORT: target below, stop above
        # Use actual_low for target progress, actual_high for stop progress
        progress_to_target = ((entry - low_price) / (entry - target)) * 100
        progress_to_stop = ((high_price - entry) / (stop - entry)) * 100
        current_pnl_pct = ((entry - current_price) / entry) * 100
    else:
        return None

    # Determine status based on ACTUAL tracked data
    # Only show TARGET HIT or STOP HIT if signal has been tracked
    if is_tracked and target_hit_db == 1:
        status = "🎯 TARGET HIT!"
        status_color = "green"
    elif is_tracked and stop_hit_db == 1:
        status = "❌ STOP HIT!"
        status_color = "red"
    elif progress_to_target >= 100 and is_tracked:
        # Tracked and reached target zone (but may not have hit exact target)
        status = "🎯 TARGET REACHED!"
        status_color = "green"
    elif progress_to_stop >= 100 and is_tracked:
        # Tracked and reached stop zone (but may not have hit exact stop)
        status = "❌ STOP REACHED!"
        status_color = "red"
    elif progress_to_target >= 80:
        status = "🔥 Very Close to Target"
        status_color = "yellow"
    elif progress_to_stop >= 80:
        status = "⚠️ Close to Stop"
        status_color = "yellow"
    elif current_pnl_pct > 0:
        status = "📈 In Profit"
        status_color = "green"
    elif current_pnl_pct < 0:
        status = "📉 In Loss"
        status_color = "red"
    else:
        status = "⏸️ Flat"
        status_color = "white"

    # Add tracking indicator to status if not tracked
    if not is_tracked:
        status = "⚪ Not Tracked Yet"
        status_color = "white"

    # Calculate signal age
    signal_time = datetime.fromisoformat(signal['timestamp'])
    age_minutes = (datetime.now() - signal_time).total_seconds() / 60

    return {
        'id': signal['id'],
        'age_min': age_minutes,
        'signal_type': signal['signal_type'],
        'direction': direction,
        'entry': entry,
        'current': current_price,
        'target': target,
        'stop': stop,
        'progress_target': progress_to_target,
        'progress_stop': progress_to_stop,
        'current_pnl_pct': current_pnl_pct,
        'status': status,
        'status_color': status_color,
        'is_tracked': is_tracked,
        'actual_high': actual_high,
        'actual_low': actual_low
    }

def display_pending_signals(signals_analysis, current_price):
    """Display pending signals in a nice table"""
    clear_screen()

    print("="*100)
    print("📊 PENDING SIGNALS MONITOR")
    print("="*100)
    print(f"🕐 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"💰 Current BTC Price: ${current_price:,.2f}")
    print(f"📝 Monitoring {len(signals_analysis)} pending signal(s)")
    print("="*100)
    print()

    if not signals_analysis:
        print("✅ No pending signals - all have been resolved!")
        return

    # Categorize signals
    near_target = [s for s in signals_analysis if s['progress_target'] >= 80 and s['progress_target'] < 100]
    near_stop = [s for s in signals_analysis if s['progress_stop'] >= 80 and s['progress_stop'] < 100]
    in_profit = [s for s in signals_analysis if s['current_pnl_pct'] > 0 and s['progress_target'] < 80]
    in_loss = [s for s in signals_analysis if s['current_pnl_pct'] < 0 and s['progress_stop'] < 80]
    neutral = [s for s in signals_analysis if abs(s['current_pnl_pct']) < 0.05]

    # Summary
    print("📈 SUMMARY:")
    print(f"   🎯 Near Target (80%+):  {len(near_target)} signals")
    print(f"   ⚠️  Near Stop (80%+):    {len(near_stop)} signals")
    print(f"   📈 In Profit:           {len(in_profit)} signals")
    print(f"   📉 In Loss:             {len(in_loss)} signals")
    print(f"   ⏸️  Neutral:             {len(neutral)} signals")
    print()

    # Display near target signals
    if near_target:
        print("🔥 SIGNALS NEAR TARGET (80%+)")
        print("-"*100)
        table_data = []
        for s in near_target:
            table_data.append([
                s['id'],
                s['signal_type'][:20],
                s['direction'],
                f"${s['entry']:,.2f}",
                f"${s['target']:,.2f}",
                f"{s['progress_target']:.1f}%",
                f"{s['current_pnl_pct']:+.2f}%",
                f"{s['age_min']:.0f}m"
            ])

        print(tabulate(table_data,
                      headers=['ID', 'Type', 'Dir', 'Entry', 'Target', 'Progress', 'P&L', 'Age'],
                      tablefmt='simple'))
        print()

    # Display near stop signals
    if near_stop:
        print("⚠️  SIGNALS NEAR STOP LOSS (80%+)")
        print("-"*100)
        table_data = []
        for s in near_stop:
            table_data.append([
                s['id'],
                s['signal_type'][:20],
                s['direction'],
                f"${s['entry']:,.2f}",
                f"${s['stop']:,.2f}",
                f"{s['progress_stop']:.1f}%",
                f"{s['current_pnl_pct']:+.2f}%",
                f"{s['age_min']:.0f}m"
            ])

        print(tabulate(table_data,
                      headers=['ID', 'Type', 'Dir', 'Entry', 'Stop', 'Progress', 'P&L', 'Age'],
                      tablefmt='simple'))
        print()

    # Display all pending signals in detail
    print("📊 ALL PENDING SIGNALS")
    print("-"*100)
    table_data = []
    for s in signals_analysis:
        # Color-code status
        status_display = s['status']

        table_data.append([
            s['id'],
            s['signal_type'][:18],
            s['direction'],
            f"${s['entry']:,.2f}",
            f"{s['progress_target']:5.1f}%",
            f"{s['progress_stop']:5.1f}%",
            f"{s['current_pnl_pct']:+.2f}%",
            f"{s['age_min']:.0f}m",
            status_display
        ])

    print(tabulate(table_data,
                  headers=['ID', 'Type', 'Dir', 'Entry', 'To Target', 'To Stop', 'P&L', 'Age', 'Status'],
                  tablefmt='simple'))

    print()
    print("="*100)
    print("Legend: To Target/Stop = % progress towards target/stop | P&L = Current profit/loss")
    print("🎯 = Target HIT (tracked) | ❌ = Stop HIT (tracked) | 🔥 = Near target | ⚠️ = Near stop")
    print("📈 = In Profit | 📉 = In Loss | ⏸️ = Flat | ⚪ = Not tracked yet (monitor wasn't running)")
    print("="*100)

def monitor_pending_signals(refresh_seconds=10):
    """Main monitoring loop"""
    print("Starting Pending Signals Monitor...")
    print(f"Refresh rate: {refresh_seconds} seconds")
    print("Press Ctrl+C to stop\n")

    try:
        while True:
            # Get current price
            current_price = get_current_btc_price()

            if current_price is None:
                print("⚠️  Could not fetch BTC price, retrying...")
                time.sleep(refresh_seconds)
                continue

            # Get pending signals
            pending_signals = get_pending_signals()

            # Analyze each signal
            signals_analysis = []
            for signal in pending_signals:
                analysis = analyze_signal_progress(signal, current_price)
                if analysis:
                    signals_analysis.append(analysis)

            # Display
            display_pending_signals(signals_analysis, current_price)

            # Wait before next refresh
            time.sleep(refresh_seconds)

    except KeyboardInterrupt:
        print("\n\n✅ Monitor stopped by user")
        print("Final statistics:")
        if signals_analysis:
            avg_pnl = sum(s['current_pnl_pct'] for s in signals_analysis) / len(signals_analysis)
            print(f"   Average P&L: {avg_pnl:+.2f}%")
            print(f"   Signals monitored: {len(signals_analysis)}")

if __name__ == "__main__":
    import sys

    # Check if refresh rate provided
    refresh_rate = 10
    if len(sys.argv) > 1:
        try:
            refresh_rate = int(sys.argv[1])
        except:
            print(f"Invalid refresh rate, using default: {refresh_rate}s")

    monitor_pending_signals(refresh_seconds=refresh_rate)
