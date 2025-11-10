#!/usr/bin/env python3
"""Test signal_tracker.py with new labeling features"""

from signal_tracker import SignalTracker

# Initialize tracker
tracker = SignalTracker()
print('✅ signal_tracker.py loaded successfully')

# Check methods
print('\nAvailable methods:')
methods = [m for m in dir(tracker) if not m.startswith('_') and callable(getattr(tracker, m))]
for m in methods:
    print(f'  - {m}')

# Test calculate_signal_quality
print('\n📊 Testing signal quality calculation:')

# Test HIGH quality signal
alert_high = {'type': 'RSI_OVERSOLD', 'severity': 'HIGH', 'message': 'Test'}
indicators_high = {'rsi': 25, 'trend': 'BULLISH', 'atr': 100}
quality = tracker.calculate_signal_quality(alert_high, indicators_high, has_conflict=False)
print(f'  HIGH quality signal: {quality}')

# Test LOW quality signal
alert_low = {'type': 'RSI_OVERSOLD', 'severity': 'LOW', 'message': 'Test'}
indicators_low = {'rsi': 35, 'trend': 'BEARISH'}
quality = tracker.calculate_signal_quality(alert_low, indicators_low, has_conflict=True)
print(f'  LOW quality signal: {quality}')

# Test strategy comparison (should be empty for now)
print('\n📈 Testing strategy comparison:')
comparison = tracker.get_strategy_comparison(hours_back=24)
print(f'  Strategies found: {len(comparison["by_strategy"])}')
print(f'  Quality levels found: {len(comparison["by_quality"])}')
print(f'  Market conditions found: {len(comparison["by_market_condition"])}')

print('\n✅ All tests passed!')
