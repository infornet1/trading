#!/bin/bash
# LP Signal Lab — Listener Watchdog
# Cron runs this every minute. Starts listener if not running.

PROJECT=/var/www/dev/trading/lp_hedge_backtest
LOG=$PROJECT/telegram_listener/logs/listener.log
PIDFILE=$PROJECT/telegram_listener/logs/listener.pid

# Check if already running via pid file
if [ -f "$PIDFILE" ]; then
    PID=$(cat "$PIDFILE")
    if kill -0 "$PID" 2>/dev/null; then
        exit 0   # already running, nothing to do
    fi
    rm -f "$PIDFILE"
fi

# Also check by process name as fallback
if pgrep -f "telegram_listener.listener" > /dev/null 2>&1; then
    exit 0
fi

# Not running — start it
echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] Listener not running — starting..." >> "$LOG"

cd "$PROJECT"
source venv/bin/activate

nohup python -m telegram_listener.listener >> "$LOG" 2>&1 &
NEW_PID=$!
echo $NEW_PID > "$PIDFILE"

echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] Listener started (PID=$NEW_PID)" >> "$LOG"
