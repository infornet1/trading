#!/bin/bash
#
# Install Cron Jobs for Bot Supervisor
# This script sets up automated monitoring for trading bots
#

echo "==================================="
echo "Bot Supervisor - Cron Installation"
echo "==================================="

# Make scripts executable
chmod +x /var/www/dev/trading/supervisor/*.py

echo "✅ Made scripts executable"

# Create cron configuration
CRON_FILE="/tmp/trading_bot_cron.txt"

cat > "$CRON_FILE" << 'EOF'
# Bitcoin Trading Bot Supervisor - Cron Jobs
# Installed: $(date)
#
# Format: minute hour day month weekday command

# ============================================================
# MAIN SUPERVISOR - Every 15 minutes
# Checks market conditions, bot health, and restarts if needed
# ============================================================
*/15 * * * * /usr/bin/python3 /var/www/dev/trading/supervisor/bot_supervisor.py >> /var/www/dev/trading/supervisor/logs/cron.log 2>&1

# ============================================================
# QUICK HEALTH CHECK - Every 5 minutes
# Fast check to catch crashes immediately
# ============================================================
*/5 * * * * /usr/bin/python3 /var/www/dev/trading/supervisor/quick_health_check.py >> /var/www/dev/trading/supervisor/logs/quick_check.log 2>&1

# ============================================================
# STATE CLEANUP - Every 6 hours
# Cleans up old logs, optimizes database
# ============================================================
0 */6 * * * /usr/bin/python3 /var/www/dev/trading/supervisor/state_manager.py scalping_v2 --cleanup >> /var/www/dev/trading/supervisor/logs/cleanup.log 2>&1
15 */6 * * * /usr/bin/python3 /var/www/dev/trading/supervisor/state_manager.py adx_v2 --cleanup >> /var/www/dev/trading/supervisor/logs/cleanup.log 2>&1

# ============================================================
# DAILY REPORT - Every day at 8 AM
# Generates comprehensive daily report
# ============================================================
0 8 * * * /usr/bin/python3 /var/www/dev/trading/supervisor/bot_supervisor.py --report >> /var/www/dev/trading/supervisor/logs/reports.log 2>&1

# ============================================================
# DISK SPACE CHECK - Every hour
# Ensures system has enough disk space
# ============================================================
0 * * * * df -h / | tail -1 | awk '{if($5+0 > 80) print "WARNING: Disk usage at "$5}' >> /var/www/dev/trading/supervisor/logs/disk_check.log

EOF

echo ""
echo "Cron configuration created:"
echo "-----------------------------------"
cat "$CRON_FILE"
echo "-----------------------------------"
echo ""

read -p "Install these cron jobs for root user? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]
then
    # Install cron jobs
    crontab -l > /tmp/current_cron.txt 2>/dev/null || true
    cat "$CRON_FILE" >> /tmp/current_cron.txt
    crontab /tmp/current_cron.txt

    echo "✅ Cron jobs installed!"
    echo ""
    echo "View installed cron jobs:"
    echo "  crontab -l"
    echo ""
    echo "Monitor supervisor logs:"
    echo "  tail -f /var/www/dev/trading/supervisor/logs/cron.log"
    echo ""
else
    echo "❌ Installation cancelled"
    echo "To install manually:"
    echo "  crontab -e"
    echo "Then paste the contents of: $CRON_FILE"
fi

# Create log directories
mkdir -p /var/www/dev/trading/supervisor/logs
mkdir -p /var/www/dev/trading/supervisor/reports

echo ""
echo "✅ Setup complete!"
