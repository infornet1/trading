#!/usr/bin/env python3
"""
Live Paper Trading Bot for Scalping Strategy v2.0
Runs the complete scalping trading system in real-time with live market data
"""

import sys
import os
sys.path.insert(0, '/var/www/dev/trading/scalping_v2')

import time
import signal
import json
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Optional
import pandas as pd
import logging
from dotenv import load_dotenv

# Load environment variables (use absolute path)
load_dotenv('/var/www/dev/trading/adx_strategy_v2/config/.env')

# Import shared components (via symlinks)
from src.api.bingx_api import BingXAPI
from src.risk.position_sizer import PositionSizer
from src.risk.risk_manager import RiskManager
from src.execution.order_executor import OrderExecutor
from src.execution.position_manager import PositionManager
from src.execution.paper_trader import PaperTrader
from src.monitoring.dashboard import Dashboard
from src.monitoring.performance_tracker import PerformanceTracker
from src.monitoring.alerts import AlertSystem, AlertType, AlertLevel
from src.monitoring.system_monitor import SystemMonitor

# Import scalping-specific components
from src.signals.scalping_signal_generator import ScalpingSignalGenerator


# Custom JSON Encoder to handle numpy types and other non-serializable objects
class NumpyEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles numpy types"""
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, np.bool_):
            return bool(obj)
        elif isinstance(obj, (datetime, pd.Timestamp)):
            return obj.isoformat()
        return super(NumpyEncoder, self).default(obj)


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/live_trading.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ScalpingTradingBot:
    """
    Live Paper Trading Bot for Scalping Strategy

    Features:
    - Real-time scalping signal generation
    - Fast entry/exit based on EMA, RSI, Stochastic
    - Automatic position management
    - Risk controls enforcement
    - Live monitoring dashboard
    - Performance tracking
    """

    def __init__(self, config_file: str = 'config_live.json', mode: str = 'paper'):
        """
        Initialize scalping trading bot

        Args:
            config_file: Path to configuration file
            mode: Trading mode - 'paper' or 'live' (default: 'paper')
        """

        self.mode = mode.lower()

        logger.info("="*80)
        if self.mode == 'live':
            logger.warning("🔴 SCALPING STRATEGY v2.0 - LIVE TRADING MODE")
            logger.warning("⚠️  REAL MONEY AT RISK ⚠️")
        else:
            logger.info("📊 SCALPING STRATEGY v2.0 - PAPER TRADING MODE")
        logger.info("="*80)

        # Load configuration
        self.config = self._load_config(config_file)

        # Initialize components
        self._initialize_components()

        # Bot state
        self.running = False
        self.start_time = None
        self.last_signal_check = None
        self.last_dashboard_update = None
        self.signal_check_interval = self.config.get('signal_check_interval', 300)  # 5 minutes
        self.dashboard_update_interval = 60  # 1 minute

        # Restore previous session data - DISABLED to start with fresh capital
        # self._restore_previous_session()

        logger.info("✅ Scalping Trading Bot initialized successfully")

    def _load_config(self, config_file: str) -> Dict:
        """Load configuration from file"""
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
            logger.info(f"✅ Configuration loaded from {config_file}")
            return config
        except FileNotFoundError:
            logger.warning(f"⚠️  Config file not found, using defaults")
            return self._get_default_config()

    def _get_default_config(self) -> Dict:
        """Get default configuration for scalping"""
        return {
            'initial_capital': 100.0,
            'leverage': 5,
            'risk_per_trade': 2.0,
            'daily_loss_limit': 5.0,
            'max_drawdown': 15.0,
            'max_positions': 2,
            'consecutive_loss_limit': 3,
            'max_daily_trades': 50,
            'symbol': 'BTC-USDT',
            'timeframe': '5m',
            'signal_check_interval': 300,
            'target_profit_pct': 0.003,
            'max_loss_pct': 0.0015,
            'max_position_time': 300,
            'min_confidence': 0.6
        }

    def _initialize_components(self):
        """Initialize all trading components"""

        logger.info("Initializing components...")

        cfg = self.config

        # API Client
        api_key = os.getenv('BINGX_API_KEY')
        api_secret = os.getenv('BINGX_API_SECRET')

        if not api_key or not api_secret:
            logger.warning("⚠️  BingX API credentials not found, using demo mode")
            self.api = None
        else:
            self.api = BingXAPI(api_key=api_key, api_secret=api_secret)
            logger.info("  ✅ BingX API initialized")

        # Scalping Signal Generator
        if self.api:
            self.signal_gen = ScalpingSignalGenerator(
                api_client=self.api,
                config=cfg
            )
            logger.info("  ✅ Scalping Signal Generator initialized")
        else:
            self.signal_gen = None
            logger.warning("  ⚠️  Signal Generator not initialized (no API)")

        # Risk Manager
        self.risk_mgr = RiskManager(
            initial_capital=cfg.get('initial_capital', 100.0),
            daily_loss_limit_percent=cfg.get('daily_loss_limit', 5.0),
            max_drawdown_percent=cfg.get('max_drawdown', 15.0),
            max_concurrent_positions=cfg.get('max_positions', 2),
            consecutive_loss_limit=cfg.get('consecutive_loss_limit', 3)
        )
        logger.info("  ✅ Risk Manager initialized")

        # Position Sizer
        self.sizer = PositionSizer(
            initial_capital=cfg.get('initial_capital', 100.0),
            risk_per_trade_percent=cfg.get('risk_per_trade', 2.0),
            leverage=cfg.get('leverage', 5)
        )
        logger.info("  ✅ Position Sizer initialized")

        # Order Executor
        self.executor = OrderExecutor(
            api_client=self.api,
            enable_live_trading=(self.mode == 'live')
        )
        logger.info(f"  ✅ Order Executor initialized ({'LIVE' if self.mode == 'live' else 'PAPER'} MODE)")

        # Position Manager
        self.position_mgr = PositionManager(order_executor=self.executor)
        logger.info("  ✅ Position Manager initialized")

        # Initialize Trader (Paper mode only for now)
        if self.mode == 'live':
            logger.error("❌ LIVE TRADING NOT YET ENABLED FOR SCALPING")
            logger.error("❌ Please use --mode paper until strategy is validated")
            sys.exit(1)

        # Paper Trader
        self.trader = PaperTrader(
            initial_balance=cfg.get('initial_capital', 100.0),
            leverage=cfg.get('leverage', 5),
            order_executor=self.executor,
            position_manager=self.position_mgr,
            risk_manager=self.risk_mgr
        )
        logger.info("  ✅ Paper Trader initialized")

        # Monitoring
        self.dashboard = Dashboard(
            paper_trader=self.trader,
            position_manager=self.position_mgr,
            order_executor=self.executor,
            risk_manager=self.risk_mgr
        )
        logger.info("  ✅ Dashboard initialized")

        self.perf_tracker = PerformanceTracker(
            paper_trader=self.trader,
            position_manager=self.position_mgr,
            risk_manager=self.risk_mgr
        )
        logger.info("  ✅ Performance Tracker initialized")

        self.alert_system = AlertSystem()
        logger.info("  ✅ Alert System initialized")

        self.system_monitor = SystemMonitor()
        logger.info("  ✅ System Monitor initialized")

    def _restore_previous_session(self):
        """Restore state from previous session if available"""
        try:
            # Try to load previous snapshot
            snapshot_file = 'logs/final_snapshot.json'
            if os.path.exists(snapshot_file):
                with open(snapshot_file, 'r') as f:
                    snapshot = json.load(f)

                # Restore balance
                if 'account' in snapshot:
                    previous_balance = snapshot['account'].get('balance', self.config.get('initial_capital', 100.0))
                    self.trader.balance = previous_balance
                    logger.info(f"  ✅ Restored balance from previous session: ${previous_balance:.2f}")

        except Exception as e:
            logger.warning(f"  ⚠️  Could not restore previous session: {e}")

    def run(self, duration_hours: Optional[int] = None):
        """
        Run the trading bot

        Args:
            duration_hours: Run duration in hours (None = run indefinitely)
        """

        self.running = True
        self.start_time = datetime.now()
        end_time = self.start_time + timedelta(hours=duration_hours) if duration_hours else None

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        logger.info("="*80)
        logger.info("🚀 STARTING SCALPING BOT")
        logger.info(f"   Mode: {self.mode.upper()}")
        logger.info(f"   Symbol: {self.config.get('symbol', 'BTC-USDT')}")
        logger.info(f"   Timeframe: {self.config.get('timeframe', '5m')}")
        logger.info(f"   Initial Capital: ${self.config.get('initial_capital', 100.0):.2f}")
        logger.info(f"   Signal Check Interval: {self.signal_check_interval}s")
        if duration_hours:
            logger.info(f"   Duration: {duration_hours} hours")
        logger.info("="*80)

        try:
            update_count = 0
            while self.running:
                current_time = datetime.now()

                # Check if we've reached end time
                if end_time and current_time >= end_time:
                    logger.info(f"⏰ Reached end time ({end_time}), stopping bot...")
                    break

                # Main update cycle
                self._update_cycle()
                update_count += 1

                # Export snapshot for web dashboard (every 5 seconds)
                if update_count % 1 == 0:  # Every iteration (5 seconds)
                    self._export_snapshot()

                # Update console dashboard (every 60 seconds)
                if self.last_dashboard_update is None or \
                   (current_time - self.last_dashboard_update).total_seconds() >= self.dashboard_update_interval:
                    self.dashboard.display()
                    self.last_dashboard_update = current_time

                # Sleep for 5 seconds between updates
                time.sleep(5)

        except KeyboardInterrupt:
            logger.info("\n⚠️  Keyboard interrupt received...")
        except Exception as e:
            logger.error(f"❌ Fatal error in main loop: {e}", exc_info=True)
        finally:
            self._shutdown()

    def _update_cycle(self):
        """Main update cycle - runs every 5 seconds"""

        current_time = datetime.now()

        # 1. Update current BTC price
        if self.api:
            try:
                ticker = self.api.get_ticker_price(self.config.get('symbol', 'BTC-USDT'))
                if ticker and 'price' in ticker:
                    self.trader.current_price = float(ticker['price'])
                elif isinstance(ticker, (int, float)):
                    self.trader.current_price = float(ticker)
            except Exception as e:
                logger.warning(f"Could not fetch current price: {e}")

        # 2. Monitor open positions (check stop loss, take profit, time exits)
        if hasattr(self.trader, 'current_price') and self.trader.current_price:
            self.trader.monitor_positions(self.trader.current_price)

        # 3. Record closed positions for learning
        self._monitor_and_record_closed_positions()

        # 4. Check for new signals (every signal_check_interval seconds)
        if self.signal_gen and (self.last_signal_check is None or \
           (current_time - self.last_signal_check).total_seconds() >= self.signal_check_interval):

            self._check_signals()
            self.last_signal_check = current_time

    def _check_signals(self):
        """Check for trading signals and execute if valid"""

        # Check if we can open new positions
        if not self.risk_mgr.can_open_position():
            logger.debug("⛔ Cannot open new position - risk limits reached")
            return

        # Check daily trade limit
        max_daily_trades = self.config.get('max_daily_trades', 50)
        # Count today's trades
        # (This would need to be implemented in trader/database)

        # Generate signals
        try:
            signals = self.signal_gen.generate_signals()

            if not signals.get('has_signal', False):
                logger.debug("No signals detected")
                return

            current_price = signals.get('current_price', 0)

            # Process LONG signal
            if signals.get('long'):
                self._process_signal(signals['long'], 'LONG', current_price)

            # Process SHORT signal
            elif signals.get('short'):
                self._process_signal(signals['short'], 'SHORT', current_price)

        except Exception as e:
            logger.error(f"Error checking signals: {e}", exc_info=True)

    def _process_signal(self, signal: Dict, side: str, current_price: float):
        """Process and execute a trading signal"""

        try:
            confidence = signal.get('confidence', 0)
            stop_loss = signal.get('stop_loss')
            take_profit = signal.get('take_profit')
            conditions = signal.get('conditions', [])

            logger.info(f"{'🟢' if side == 'LONG' else '🔴'} {side} SIGNAL DETECTED")
            logger.info(f"   Price: ${current_price:.2f}")
            logger.info(f"   Confidence: {confidence*100:.1f}%")
            logger.info(f"   Conditions: {', '.join(conditions)}")
            logger.info(f"   Stop Loss: ${stop_loss:.2f}")
            logger.info(f"   Take Profit: ${take_profit:.2f}")

            # Calculate position size
            position_size_usd = self.sizer.calculate_position_size(
                account_balance=self.trader.balance,
                stop_loss_pct=abs((current_price - stop_loss) / current_price) * 100,
                current_price=current_price
            )

            # Convert to BTC quantity
            quantity = position_size_usd / current_price

            logger.info(f"   Position Size: ${position_size_usd:.2f} ({quantity:.6f} BTC)")

            # Execute trade via paper trader
            success = self.trader.open_position(
                side=side,
                quantity=quantity,
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit
            )

            if success:
                logger.info(f"✅ {side} position opened successfully")

                # Send alert
                self.alert_system.send_alert(
                    alert_type=AlertType.SIGNAL_GENERATED,
                    level=AlertLevel.INFO,
                    message=f"{side} signal executed - Confidence: {confidence*100:.1f}%",
                    data={'side': side, 'price': current_price, 'confidence': confidence}
                )

                # Record trade in signal generator
                self.signal_gen.record_trade_result({
                    'side': side,
                    'entry_price': current_price,
                    'confidence': confidence,
                    'timestamp': datetime.now().isoformat()
                })
            else:
                logger.warning(f"⚠️  Failed to open {side} position")

        except Exception as e:
            logger.error(f"Error processing signal: {e}", exc_info=True)

    def _monitor_and_record_closed_positions(self):
        """Monitor for closed positions and record their results"""
        try:
            # Get recently closed positions (if PaperTrader supports it)
            if hasattr(self.trader, 'get_recently_closed_positions'):
                closed_positions = self.trader.get_recently_closed_positions()

                for position in closed_positions:
                    # Record trade result with PNL
                    trade_data = {
                        'side': position.side,
                        'entry_price': position.entry_price,
                        'exit_price': position.exit_price,
                        'pnl': position.pnl,
                        'confidence': getattr(position, 'confidence', 0.5),
                        'timestamp': position.exit_time.isoformat() if hasattr(position, 'exit_time') else datetime.now().isoformat(),
                        'reason': getattr(position, 'exit_reason', 'unknown')
                    }

                    self.signal_gen.record_trade_result(trade_data)
                    logger.info(f"📊 Position closed - {position.side}: ${position.pnl:.2f}")

        except Exception as e:
            logger.debug(f"Closed position monitoring not available: {e}")

    def _export_snapshot(self):
        """Export current state snapshot for web dashboard"""
        try:
            snapshot = {
                'timestamp': datetime.now().isoformat(),
                'account': {
                    'balance': self.trader.balance,
                    'equity': getattr(self.trader, 'equity', self.trader.balance),
                    'pnl': self.trader.balance - self.config.get('initial_capital', 100.0),
                    'pnl_percent': ((self.trader.balance - self.config.get('initial_capital', 100.0)) /
                                   self.config.get('initial_capital', 100.0)) * 100
                },
                'positions': [pos.to_dict() for pos in self.position_mgr.get_open_positions()],
                'orders': [],
                'risk': {
                    'daily_pnl': self.risk_mgr.daily_pnl,
                    'can_trade': self.risk_mgr.can_open_position()
                },
                'recent_trades': getattr(self.trader, 'trade_history', [])[-10:] if hasattr(self.trader, 'trade_history') else [],
                'system': {
                    'last_update': datetime.now().isoformat(),
                    'update_count': getattr(self, '_update_count', 0)
                }
            }

            # Add scalping indicators if available
            if self.signal_gen:
                market_state = self.signal_gen.get_current_market_state()
                snapshot['indicators'] = market_state.get('indicators', {})
                snapshot['price_action'] = market_state.get('price_action', {})

            # Write to file
            with open('logs/final_snapshot.json', 'w') as f:
                json.dump(snapshot, f, indent=2, cls=NumpyEncoder)

        except Exception as e:
            logger.error(f"Error exporting snapshot: {e}")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"\n⚠️  Received signal {signum}, shutting down...")
        self.running = False

    def _shutdown(self):
        """Graceful shutdown"""
        logger.info("="*80)
        logger.info("🛑 SHUTTING DOWN SCALPING BOT")
        logger.info("="*80)

        # Close all open positions
        if self.trader:
            open_positions = self.position_mgr.get_open_positions()
            if open_positions:
                logger.info(f"Closing {len(open_positions)} open positions...")
                for position in open_positions:
                    try:
                        self.trader.close_position(position.position_id, "shutdown")
                    except Exception as e:
                        logger.error(f"Error closing position {position.position_id}: {e}")

        # Generate final report
        if self.perf_tracker:
            logger.info("\n" + "="*80)
            logger.info("📊 FINAL PERFORMANCE REPORT")
            logger.info("="*80)

            stats = self.perf_tracker.get_performance_metrics()

            logger.info(f"Trading Duration: {datetime.now() - self.start_time}")
            logger.info(f"Final Balance: ${self.trader.balance:.2f}")
            logger.info(f"Total P&L: ${stats.get('total_pnl', 0):.2f}")
            logger.info(f"Total Trades: {stats.get('total_trades', 0)}")
            logger.info(f"Win Rate: {stats.get('win_rate', 0)*100:.1f}%")
            logger.info(f"Max Drawdown: {stats.get('max_drawdown', 0):.2f}%")
            logger.info("="*80)

        # Export final snapshot
        self._export_snapshot()

        logger.info("✅ Shutdown complete")


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Scalping Strategy v2.0 - Live Trading Bot')
    parser.add_argument('--mode', choices=['paper', 'live'], default='paper',
                       help='Trading mode (default: paper)')
    parser.add_argument('--config', default='config_live.json',
                       help='Configuration file (default: config_live.json)')
    parser.add_argument('--duration', type=int, default=None,
                       help='Run duration in hours (default: run indefinitely)')
    parser.add_argument('--skip-confirmation', action='store_true',
                       help='Skip manual confirmation prompt')

    args = parser.parse_args()

    # Confirmation for live trading
    if args.mode == 'live' and not args.skip_confirmation:
        print("\n" + "="*80)
        print("⚠️  WARNING: LIVE TRADING MODE ⚠️")
        print("="*80)
        print("You are about to start LIVE TRADING with REAL MONEY.")
        print("This is the SCALPING STRATEGY v2.0 - High frequency trading.")
        print("\nRisks:")
        print("- Multiple trades per hour")
        print("- Transaction fees add up quickly")
        print("- Slippage can be significant")
        print("- NOT YET VALIDATED ON LIVE MARKETS")
        print("\nAre you absolutely sure you want to continue?")
        print("="*80)

        confirmation = input("\nType 'YES, I UNDERSTAND THE RISKS' to continue: ")

        if confirmation != 'YES, I UNDERSTAND THE RISKS':
            print("\n❌ Live trading cancelled.")
            sys.exit(0)

    # Initialize and run bot
    bot = ScalpingTradingBot(config_file=args.config, mode=args.mode)
    bot.run(duration_hours=args.duration)


if __name__ == "__main__":
    main()
