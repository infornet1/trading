#!/usr/bin/env python3
"""
Bot Supervisor - Master orchestrator for trading bots
Runs via cron to check market conditions, bot health, and manage states

Author: Trading System
Created: 2025-11-10
"""

import sys
import os
import json
import logging
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Setup paths
TRADING_ROOT = Path("/var/www/dev/trading")
SUPERVISOR_LOG = TRADING_ROOT / "supervisor" / "logs" / "supervisor.log"
SUPERVISOR_LOG.parent.mkdir(parents=True, exist_ok=True)

# Import email notifier
try:
    from supervisor_email_notifier import SupervisorEmailNotifier
    EMAIL_ENABLED = True
except ImportError:
    EMAIL_ENABLED = False
    print("⚠️  Email notifier not available")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(SUPERVISOR_LOG),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class BotSupervisor:
    """Master supervisor for all trading bots"""

    def __init__(self):
        self.trading_root = TRADING_ROOT

        # Initialize email notifier
        if EMAIL_ENABLED:
            try:
                self.email_notifier = SupervisorEmailNotifier()
            except Exception as e:
                logger.warning(f"Failed to initialize email notifier: {e}")
                self.email_notifier = None
        else:
            self.email_notifier = None

        self.bots = {
            'scalping_v2': {
                'name': 'Scalping v2',
                'service': 'scalping-trading-bot',
                'path': self.trading_root / 'scalping_v2',
                'db': self.trading_root / 'scalping_v2' / 'data' / 'trades.db',
                'enabled': True,
                'min_adx': None,  # No ADX requirement
                'market_conditions': ['trending', 'choppy']  # Can trade in both
            },
            'adx_v2': {
                'name': 'ADX v2',
                'service': 'adx-trading-bot.service',
                'path': self.trading_root / 'adx_strategy_v2',
                'db': self.trading_root / 'adx_strategy_v2' / 'data' / 'trades.db',
                'enabled': True,
                'min_adx': 25,  # Requires strong trend
                'market_conditions': ['trending']  # Only trending markets
            }
        }

    def check_market_conditions(self) -> Dict:
        """
        Check current market conditions
        Returns: {
            'tradeable': bool,
            'regime': 'trending' | 'choppy' | 'ranging',
            'adx': float,
            'volatility': float,
            'btc_price': float
        }
        """
        logger.info("🔍 Checking market conditions...")

        try:
            # Run market condition checker
            result = subprocess.run(
                [sys.executable, str(self.trading_root / 'supervisor' / 'market_condition_checker.py')],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                conditions = json.loads(result.stdout)
                logger.info(f"   Market Regime: {conditions['regime']}")
                logger.info(f"   ADX: {conditions['adx']:.2f}")
                logger.info(f"   BTC Price: ${conditions['btc_price']:,.2f}")
                logger.info(f"   Tradeable: {conditions['tradeable']}")
                return conditions
            else:
                logger.error(f"Market check failed: {result.stderr}")
                return {'tradeable': False, 'regime': 'unknown', 'adx': 0, 'volatility': 0, 'btc_price': 0}

        except Exception as e:
            logger.error(f"Error checking market conditions: {e}")
            return {'tradeable': False, 'regime': 'unknown', 'adx': 0, 'volatility': 0, 'btc_price': 0}

    def check_bot_health(self, bot_key: str) -> Dict:
        """
        Check if bot is healthy beyond just process running
        Returns: {
            'running': bool,
            'healthy': bool,
            'last_update': datetime,
            'issues': List[str]
        }
        """
        bot = self.bots[bot_key]
        logger.info(f"🏥 Checking health: {bot['name']}...")

        try:
            # Run bot health monitor
            result = subprocess.run(
                [sys.executable, str(self.trading_root / 'supervisor' / 'bot_health_monitor.py'), bot_key],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                health = json.loads(result.stdout)
                logger.info(f"   Running: {health['running']}")
                logger.info(f"   Healthy: {health['healthy']}")
                if health['issues']:
                    logger.warning(f"   Issues: {', '.join(health['issues'])}")
                return health
            else:
                logger.error(f"Health check failed: {result.stderr}")
                return {'running': False, 'healthy': False, 'last_update': None, 'issues': ['Health check failed']}

        except Exception as e:
            logger.error(f"Error checking bot health: {e}")
            return {'running': False, 'healthy': False, 'last_update': None, 'issues': [str(e)]}

    def restart_bot(self, bot_key: str, reason: str) -> bool:
        """Restart a bot service"""
        bot = self.bots[bot_key]
        logger.warning(f"🔄 Restarting {bot['name']} - Reason: {reason}")

        try:
            # Stop service
            subprocess.run(['systemctl', 'stop', bot['service']], check=True)
            logger.info(f"   Stopped {bot['service']}")

            # Clean up state (optional)
            self.cleanup_state(bot_key)

            # Start service
            subprocess.run(['systemctl', 'start', bot['service']], check=True)
            logger.info(f"   Started {bot['service']}")

            logger.info(f"✅ {bot['name']} restarted successfully")

            # Send email notification
            if self.email_notifier:
                try:
                    self.email_notifier.send_crash_alert(
                        bot_name=bot['name'],
                        restart_successful=True,
                        error_details=f"Reason: {reason}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to send email notification: {e}")

            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Failed to restart {bot['name']}: {e}")

            # Send failure email
            if self.email_notifier:
                try:
                    self.email_notifier.send_crash_alert(
                        bot_name=bot['name'],
                        restart_successful=False,
                        error_details=f"Error: {str(e)}\nReason: {reason}"
                    )
                except Exception as e2:
                    logger.warning(f"Failed to send email notification: {e2}")

            return False

    def cleanup_state(self, bot_key: str):
        """Clean up stuck states, old logs, etc."""
        bot = self.bots[bot_key]
        logger.info(f"🧹 Cleaning up state: {bot['name']}...")

        try:
            # Run state manager
            result = subprocess.run(
                [sys.executable, str(self.trading_root / 'supervisor' / 'state_manager.py'), bot_key, '--cleanup'],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                logger.info(f"   State cleanup completed")
            else:
                logger.warning(f"   State cleanup had issues: {result.stderr}")

        except Exception as e:
            logger.error(f"Error cleaning up state: {e}")

    def should_bot_run(self, bot_key: str, market_conditions: Dict) -> Tuple[bool, str]:
        """
        Determine if bot should be running given market conditions
        Returns: (should_run: bool, reason: str)
        """
        bot = self.bots[bot_key]

        # Check if bot is enabled
        if not bot['enabled']:
            return False, "Bot disabled in configuration"

        # Check market conditions
        if not market_conditions['tradeable']:
            return False, f"Market not tradeable (regime: {market_conditions['regime']})"

        # Check ADX requirement (for ADX bot)
        if bot['min_adx'] and market_conditions['adx'] < bot['min_adx']:
            return False, f"ADX too low ({market_conditions['adx']:.1f} < {bot['min_adx']})"

        # Check market regime
        if market_conditions['regime'] not in bot['market_conditions']:
            return False, f"Market regime '{market_conditions['regime']}' not suitable for this bot"

        return True, "All conditions met"

    def supervise(self):
        """Main supervision cycle"""
        logger.info("=" * 80)
        logger.info("🤖 BOT SUPERVISOR - Starting supervision cycle")
        logger.info("=" * 80)

        # 1. Check market conditions
        market_conditions = self.check_market_conditions()

        # 2. Check each bot
        for bot_key, bot in self.bots.items():
            logger.info(f"\n--- {bot['name']} ---")

            # Check if bot should be running
            should_run, reason = self.should_bot_run(bot_key, market_conditions)
            logger.info(f"Should run: {should_run} - {reason}")

            # Check bot health
            health = self.check_bot_health(bot_key)

            # Decision logic
            if should_run:
                if not health['running']:
                    logger.warning(f"⚠️  Bot should be running but isn't!")
                    self.restart_bot(bot_key, "Bot not running but market conditions are favorable")

                elif not health['healthy']:
                    logger.warning(f"⚠️  Bot is running but unhealthy!")
                    if 'stuck' in str(health['issues']).lower() or 'frozen' in str(health['issues']).lower():
                        self.restart_bot(bot_key, f"Bot unhealthy: {', '.join(health['issues'])}")
                    else:
                        logger.info(f"   Monitoring issues: {', '.join(health['issues'])}")

                else:
                    logger.info(f"✅ Bot is running and healthy")

            else:
                if health['running']:
                    logger.info(f"ℹ️  Bot is running but market conditions not ideal")
                    logger.info(f"   Bot will internally block signals - no action needed")
                else:
                    logger.info(f"ℹ️  Bot not running - market conditions not suitable anyway")

        logger.info("\n" + "=" * 80)
        logger.info("🤖 BOT SUPERVISOR - Cycle complete")
        logger.info("=" * 80 + "\n")

    def generate_report(self):
        """Generate daily supervisor report"""
        logger.info("📊 Generating supervisor report...")

        report = {
            'timestamp': datetime.now().isoformat(),
            'market_conditions': self.check_market_conditions(),
            'bots': {}
        }

        for bot_key in self.bots.keys():
            report['bots'][bot_key] = self.check_bot_health(bot_key)

        # Save report
        report_file = self.trading_root / 'supervisor' / 'reports' / f"report_{datetime.now().strftime('%Y%m%d')}.json"
        report_file.parent.mkdir(parents=True, exist_ok=True)

        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)

        logger.info(f"   Report saved: {report_file}")

        # Send email report
        if self.email_notifier:
            try:
                logger.info("📧 Sending daily email report...")
                self.email_notifier.send_daily_report(report)
                logger.info("   Email report sent successfully")
            except Exception as e:
                logger.warning(f"   Failed to send email report: {e}")


def main():
    """Main entry point"""
    supervisor = BotSupervisor()

    # Parse command line arguments
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == '--report':
            supervisor.generate_report()
        elif command == '--check-market':
            conditions = supervisor.check_market_conditions()
            print(json.dumps(conditions, indent=2))
        elif command == '--restart':
            if len(sys.argv) > 2:
                bot_key = sys.argv[2]
                supervisor.restart_bot(bot_key, "Manual restart requested")
            else:
                print("Usage: bot_supervisor.py --restart <bot_key>")
        else:
            print("Unknown command. Use: --report, --check-market, or --restart <bot_key>")
    else:
        # Default: run supervision cycle
        supervisor.supervise()


if __name__ == '__main__':
    main()
