#!/usr/bin/env python3
"""
Quick Health Check - Fast crash detection (runs every 5 minutes)
Only restarts if bot has completely crashed, not for soft issues
"""

import sys
import subprocess
import logging
from pathlib import Path
from datetime import datetime

# Setup logging
SUPERVISOR_LOG = Path("/var/www/dev/trading/supervisor/logs/quick_check.log")
SUPERVISOR_LOG.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[logging.FileHandler(SUPERVISOR_LOG)]
)
logger = logging.getLogger(__name__)


def is_service_running(service_name):
    """Check if systemd service is active"""
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', service_name],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.stdout.strip() == 'active'
    except Exception as e:
        logger.error(f"Error checking {service_name}: {e}")
        return False


def restart_service(service_name):
    """Restart a systemd service"""
    try:
        logger.warning(f"🔄 Restarting crashed service: {service_name}")
        subprocess.run(['systemctl', 'restart', service_name], check=True, timeout=30)
        logger.info(f"✅ {service_name} restarted successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to restart {service_name}: {e}")
        return False


def main():
    """Quick check and restart if crashed"""

    services = {
        'scalping-trading-bot': 'Scalping v2 Bot',
        'adx-trading-bot.service': 'ADX v2 Bot',
        'scalping-dashboard': 'Scalping Dashboard',
        'adx-dashboard.service': 'ADX Dashboard'
    }

    crashed = []

    for service, name in services.items():
        if not is_service_running(service):
            logger.error(f"❌ {name} is DOWN!")
            crashed.append((service, name))

    # Restart crashed services
    if crashed:
        logger.warning(f"Found {len(crashed)} crashed service(s)")
        for service, name in crashed:
            restart_service(service)
    else:
        logger.info("✅ All services running")


if __name__ == '__main__':
    main()
