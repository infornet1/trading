#!/usr/bin/env python3
"""
Test script to create a labeled signal and verify all fields are populated
"""

from signal_tracker import SignalTracker
from datetime import datetime
import uuid

# Initialize tracker
tracker = SignalTracker()

# Create test alert and data
alert = {
    'type': 'RSI_OVERSOLD',
    'severity': 'HIGH',
    'message': 'Test signal for labeling verification'
}

price_data = {
    'price': 110500.0
}

indicators = {
    'rsi': 28.5,
    'ema_fast': 110450,
    'ema_slow': 110600,
    'trend': 'BEARISH',
    'atr': 150.0,
    'atr_pct': 0.136
}

# Calculate quality
signal_quality = tracker.calculate_signal_quality(alert, indicators, has_conflict=False, strategy_name='SCALPING')

# Build entry reason
entry_reason = f"RSI_OVERSOLD | Trend: BEARISH | RSI: 28.5"

# Build tags
tags = ['HIGH', 'LONG', 'ATR_DYNAMIC', 'TEST']

# Generate session ID
session_id = datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + str(uuid.uuid4())[:8] + '_TEST'

# Log signal with full labeling
print("Creating test signal with full labeling...")
signal_id = tracker.log_signal(
    alert=alert,
    price_data=price_data,
    indicators=indicators,
    has_conflict=False,
    suggested_stop=110250.0,
    suggested_target=110800.0,
    strategy_name='SCALPING',
    strategy_version='v1.2',
    timeframe='5s',
    signal_quality=signal_quality,
    trade_group_id='TEST_GROUP_001',
    entry_reason=entry_reason,
    tags=tags,
    market_condition='BEARISH',
    session_id=session_id
)

print(f"\n✅ Test signal created: ID={signal_id}")

# Retrieve and verify
import sqlite3
conn = sqlite3.connect('signals.db')
cursor = conn.cursor()

cursor.execute("SELECT * FROM signals WHERE id = ?", (signal_id,))
columns = [description[0] for description in cursor.description]
row = cursor.fetchone()
conn.close()

# Display all fields
print(f"\n📋 Signal #{signal_id} - All Fields:")
print("=" * 80)

for col, val in zip(columns, row):
    if val is not None:
        print(f"  {col:25s}: {val}")

# Check labeling fields specifically
print(f"\n🏷️  Labeling Fields Verification:")
print("=" * 80)

labeling_fields = {
    'strategy_name': row[columns.index('strategy_name')],
    'strategy_version': row[columns.index('strategy_version')],
    'timeframe': row[columns.index('timeframe')],
    'signal_quality': row[columns.index('signal_quality')],
    'trade_group_id': row[columns.index('trade_group_id')],
    'entry_reason': row[columns.index('entry_reason')],
    'tags': row[columns.index('tags')],
    'market_condition': row[columns.index('market_condition')],
    'session_id': row[columns.index('session_id')]
}

all_populated = True
for field, value in labeling_fields.items():
    status = "✅" if value is not None else "❌"
    print(f"  {status} {field:25s}: {value}")
    if value is None:
        all_populated = False

print("=" * 80)

if all_populated:
    print("\n✅ SUCCESS: All labeling fields are populated correctly!")
else:
    print("\n❌ FAILURE: Some labeling fields are missing!")

# Test outcome checking with exit reason
print(f"\n🔄 Testing outcome checking with exit_reason...")

# Simulate price movement to hit target
outcome = tracker.check_signal_outcome(
    signal_id=signal_id,
    current_price=110800.0,  # At target
    price_high=110850.0,     # Hit target
    price_low=110400.0       # Didn't hit stop
)

print(f"  Outcome: {outcome}")

# Check exit_reason was set
conn = sqlite3.connect('signals.db')
cursor = conn.cursor()
cursor.execute("SELECT exit_reason, strategy_profit FROM signals WHERE id = ?", (signal_id,))
exit_reason, strategy_profit = cursor.fetchone()
conn.close()

print(f"  Exit Reason: {exit_reason}")
print(f"  Strategy Profit: {strategy_profit}%")

if exit_reason and strategy_profit is not None:
    print("\n✅ EXIT TRACKING SUCCESS: exit_reason and strategy_profit populated!")
else:
    print("\n❌ EXIT TRACKING FAILURE: exit_reason or strategy_profit missing!")

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)
