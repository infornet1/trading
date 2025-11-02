#!/bin/bash
# ScalpingV2 Trading Bot Startup Script

set -e

# Navigate to project directory
cd /var/www/dev/trading/scalping_v2

# Activate virtual environment
source venv/bin/activate

# Export environment variables
export PYTHONUNBUFFERED=1

# Start the bot in paper mode
exec python3 live_trader.py \
    --mode paper \
    --config config_live.json \
    --skip-confirmation
