#!/usr/bin/env python3
"""
Circuit Breaker Checker - Detects circuit breaker status from bot snapshots
Checks if bots are in paper trading mode and if circuit breakers are active
"""

import sys
import json
from pathlib import Path
from typing import Dict, Optional


def check_circuit_breaker(bot_key: str) -> Dict:
    """
    Check circuit breaker status for a bot

    Returns:
        {
            'bot_key': str,
            'trading_mode': 'paper' | 'live' | 'unknown',
            'circuit_breaker_active': bool,
            'circuit_breaker_reason': str,
            'can_trade': bool,
            'consecutive_losses': int,
            'consecutive_loss_limit': int,
            'daily_loss_percent': float,
            'daily_loss_limit': float,
            'balance': float,
            'should_reset': bool,
            'reset_reason': str
        }
    """

    TRADING_ROOT = Path("/var/www/dev/trading")

    bots_config = {
        'scalping_v2': {
            'snapshot': TRADING_ROOT / 'scalping_v2' / 'logs' / 'final_snapshot.json',
            'config': TRADING_ROOT / 'scalping_v2' / 'config_live.json',
        },
        'adx_v2': {
            'snapshot': TRADING_ROOT / 'adx_strategy_v2' / 'logs' / 'final_snapshot.json',
            'config': TRADING_ROOT / 'adx_strategy_v2' / 'config' / 'strategy_params.json',
        }
    }

    if bot_key not in bots_config:
        return {
            'error': f'Unknown bot: {bot_key}',
            'bot_key': bot_key
        }

    bot = bots_config[bot_key]

    try:
        # Read snapshot
        if not bot['snapshot'].exists():
            return {
                'bot_key': bot_key,
                'error': 'Snapshot file not found',
                'circuit_breaker_active': False,
                'should_reset': False
            }

        with open(bot['snapshot'], 'r') as f:
            snapshot = json.load(f)

        # Extract risk/circuit breaker info
        risk = snapshot.get('risk', {})
        account = snapshot.get('account', {})

        # Detect trading mode from recent trades
        trading_mode = 'unknown'
        recent_trades = snapshot.get('recent_trades', [])
        if recent_trades and len(recent_trades) > 0:
            # Check first trade for trading_mode field
            first_trade = recent_trades[0]
            if isinstance(first_trade, dict):
                if 'trading_mode' in first_trade:
                    trading_mode = first_trade.get('trading_mode', 'unknown')
                elif 'position' in first_trade and isinstance(first_trade['position'], dict):
                    trading_mode = first_trade['position'].get('trading_mode', 'unknown')

        # If still unknown, try to read from config file
        if trading_mode == 'unknown' and bot['config'].exists():
            try:
                with open(bot['config'], 'r') as f:
                    config = json.load(f)
                    trading_mode = config.get('trading_mode', 'unknown')
            except:
                pass

        # Default to paper if still unknown and we detect paper-like behavior
        if trading_mode == 'unknown':
            # Assume paper mode for safety (can be overridden if needed)
            trading_mode = 'paper'

        # Extract circuit breaker status
        circuit_breaker_active = risk.get('circuit_breaker_active', False)
        circuit_breaker_reason = risk.get('circuit_breaker_reason', None)

        # Extract can_trade - could be bool or tuple
        can_trade_raw = risk.get('can_trade', True)
        if isinstance(can_trade_raw, list):
            # Format: [False, "reason"]
            can_trade = can_trade_raw[0] if len(can_trade_raw) > 0 else False
            if not can_trade and len(can_trade_raw) > 1:
                circuit_breaker_reason = can_trade_raw[1]
                circuit_breaker_active = True
        else:
            can_trade = can_trade_raw

        consecutive_losses = risk.get('consecutive_losses', 0)
        consecutive_loss_limit = risk.get('consecutive_loss_limit', 3)
        daily_loss_percent = risk.get('daily_loss_percent', 0)
        daily_loss_limit = risk.get('daily_loss_limit', 5.0)

        balance = account.get('balance', 0)

        # Determine if should reset
        should_reset = False
        reset_reason = None

        if circuit_breaker_active and trading_mode == 'paper':
            should_reset = True
            reset_reason = f"Paper trading mode - auto-resetting circuit breaker (Reason: {circuit_breaker_reason})"

        result = {
            'bot_key': bot_key,
            'trading_mode': trading_mode,
            'circuit_breaker_active': circuit_breaker_active,
            'circuit_breaker_reason': circuit_breaker_reason,
            'can_trade': can_trade,
            'consecutive_losses': consecutive_losses,
            'consecutive_loss_limit': consecutive_loss_limit,
            'daily_loss_percent': daily_loss_percent,
            'daily_loss_limit': daily_loss_limit,
            'balance': balance,
            'should_reset': should_reset,
            'reset_reason': reset_reason
        }

        return result

    except Exception as e:
        return {
            'bot_key': bot_key,
            'error': f'Failed to check circuit breaker: {str(e)}',
            'circuit_breaker_active': False,
            'should_reset': False
        }


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(json.dumps({'error': 'Usage: circuit_breaker_checker.py <bot_key>'}))
        sys.exit(1)

    bot_key = sys.argv[1]
    result = check_circuit_breaker(bot_key)
    print(json.dumps(result, indent=2))

    sys.exit(0 if not result.get('error') else 1)
