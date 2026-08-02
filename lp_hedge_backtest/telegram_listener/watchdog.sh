#!/bin/bash
# LP Signal Lab — Listener Watchdog
# Cron runs this every minute. Starts listener if not running.
# Also restarts a running listener whose log has gone stale — the listener
# writes a HEARTBEAT line every 15 min, so an old log means it is hung
# (e.g. half-open Telegram connection, see 2026-08-02 incident).

PROJECT=/var/www/dev/trading/lp_hedge_backtest
LOG=$PROJECT/telegram_listener/logs/listener.log
PIDFILE=$PROJECT/telegram_listener/logs/listener.pid
PAUSE_FLAG=$PROJECT/telegram_listener/logs/.pause
MAX_STALE_MIN=30   # > 1 heartbeat interval (15 min), < 2 missed heartbeats

# Honour maintenance pause (touch .pause to suppress auto-restart)
if [ -f "$PAUSE_FLAG" ]; then
    exit 0
fi

# Check if already running via pid file
if [ -f "$PIDFILE" ]; then
    PID=$(cat "$PIDFILE")
    if kill -0 "$PID" 2>/dev/null; then
        # Process alive — verify it is healthy via log freshness
        if [ -f "$LOG" ] && [ -n "$(find "$LOG" -mmin +$MAX_STALE_MIN 2>/dev/null)" ]; then
            echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] Listener PID=$PID alive but log stale >${MAX_STALE_MIN}m (hung connection?) — killing for restart..." >> "$LOG"
            kill "$PID" 2>/dev/null
            sleep 5
            kill -9 "$PID" 2>/dev/null
        else
            exit 0   # running and healthy, nothing to do
        fi
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

# Make API env vars available to the crash-alert email script
set -a
source "$PROJECT/api/.env"
set +a

# Send crash alert email
python3 -c "
import sys; sys.path.insert(0, '.')
from api.signal_email import send_signal_email
send_signal_email(
    '⚠️ Listener reiniciado por watchdog',
    'El listener de Telegram se cayó y fue reiniciado automáticamente por el watchdog.\n\n'
    'Si esto ocurre con frecuencia, revisa los logs:\n'
    '  telegram_listener/logs/listener.log\n\n'
    'Para pausar el watchdog:\n'
    '  touch telegram_listener/logs/.pause'
)
" 2>/dev/null || true

nohup python -m telegram_listener.listener >> "$LOG" 2>&1 &
NEW_PID=$!
echo $NEW_PID > "$PIDFILE"

echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] Listener started (PID=$NEW_PID)" >> "$LOG"
