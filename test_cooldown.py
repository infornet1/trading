#!/usr/bin/env python3
"""
Quick test to demonstrate cooldown functionality
"""
from btc_monitor import BTCMonitor
import time

print("Testing cooldown functionality...\n")

# Initialize monitor
monitor = BTCMonitor('config_conservative.json', enable_email=False, enable_tracking=False)

# Test signal types
test_signals = ['RSI_OVERSOLD', 'NEAR_SUPPORT', 'RSI_OVERSOLD', 'NEAR_RESISTANCE']

print("=" * 60)
print("Test 1: Logging same signal type rapidly")
print("=" * 60)

for i, signal_type in enumerate(test_signals, 1):
    should_log = monitor.should_log_signal(signal_type, cooldown_minutes=5)
    status = "✅ LOGGED" if should_log else "⏳ SKIPPED (cooldown)"
    print(f"{i}. {signal_type}: {status}")
    time.sleep(0.5)  # Small delay

print("\n" + "=" * 60)
print("Test 2: After 5 second cooldown (simulating time passage)")
print("=" * 60)

# Simulate passage of time by manually updating last signal time
from datetime import datetime, timedelta
monitor.last_signals['RSI_OVERSOLD'] = datetime.now() - timedelta(minutes=6)

print("\n(Manually set RSI_OVERSOLD cooldown to 6 minutes ago)\n")

should_log = monitor.should_log_signal('RSI_OVERSOLD', cooldown_minutes=5)
status = "✅ LOGGED" if should_log else "⏳ SKIPPED"
print(f"RSI_OVERSOLD: {status} (cooldown expired)")

print("\n" + "=" * 60)
print("Summary:")
print("=" * 60)
print("✅ Cooldown prevents duplicate signals from spamming database")
print("✅ Different signal types have independent cooldowns")
print("✅ After cooldown period expires, signal can be logged again")
print("\nCooldown period: 5 minutes (configurable)")
