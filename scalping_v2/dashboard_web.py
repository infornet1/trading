#!/usr/bin/env python3
"""
Web Dashboard for Scalping Strategy v2.0
Provides real-time monitoring via web interface
"""

import sys
sys.path.insert(0, '/var/www/dev/trading/scalping_v2')

from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
import json
import os
from datetime import datetime, timedelta
import logging
import sqlite3

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/dashboard_web.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['APPLICATION_ROOT'] = '/scalping'
# Handle proxy headers to get correct URL generation
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
CORS(app)


def load_snapshot():
    """Load the latest bot snapshot"""
    try:
        snapshot_file = 'logs/final_snapshot.json'
        if os.path.exists(snapshot_file):
            with open(snapshot_file, 'r') as f:
                return json.load(f)
        return None
    except Exception as e:
        logger.error(f"Error loading snapshot: {e}")
        return None


def get_bot_status():
    """Check if bot is running"""
    import subprocess
    try:
        result = subprocess.run(
            ['ps', 'aux'],
            capture_output=True,
            text=True
        )

        # Check for scalping bot process
        if 'live_trader.py' in result.stdout and 'scalping_v2' in result.stdout:
            # Check if paper or live mode
            if '--mode paper' in result.stdout:
                return 'paper'
            elif '--mode live' in result.stdout:
                return 'live'
            return 'unknown'
        return 'stopped'
    except:
        return 'unknown'


@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('dashboard.html')


@app.route('/api/status')
def api_status():
    """Get current bot status"""
    snapshot = load_snapshot()
    bot_status = get_bot_status()

    if not snapshot:
        return jsonify({
            'status': bot_status,
            'error': 'No snapshot data available',
            'timestamp': datetime.now().isoformat()
        })

    # Get BTC price
    btc_price = 0
    try:
        from src.api.bingx_api import BingXAPI
        from dotenv import load_dotenv
        load_dotenv('config/.env')

        api_key = os.getenv('BINGX_API_KEY')
        api_secret = os.getenv('BINGX_API_SECRET')

        if api_key and api_secret:
            api = BingXAPI(api_key, api_secret)
            btc_price = api.get_ticker_price('BTC-USDT')
    except Exception as e:
        logger.error(f"Error fetching BTC price: {e}")

    # Format account data with required fields
    account = snapshot.get('account', {})
    positions = snapshot.get('positions', [])

    # Calculate unrealized PnL from positions
    unrealized_pnl = sum(pos.get('unrealized_pnl', 0) for pos in positions)

    # Add calculated fields to account
    account_data = {
        'balance': account.get('balance', 0),
        'equity': account.get('equity', account.get('balance', 0)),
        'total_pnl': account.get('pnl', 0),
        'total_return_percent': account.get('pnl_percent', 0),
        'unrealized_pnl': unrealized_pnl
    }

    return jsonify({
        'bot_status': {
            'running': bot_status in ['paper', 'live'],
            'mode': bot_status
        },
        'account': account_data,
        'positions': positions,
        'positions_count': len(positions),
        'btc_price': btc_price,
        'indicators': snapshot.get('indicators', {}),
        'price_action': snapshot.get('price_action', {}),
        'timestamp': snapshot.get('timestamp', datetime.now().isoformat())
    })


@app.route('/api/indicators')
def api_indicators():
    """Get current scalping indicators"""
    snapshot = load_snapshot()

    if not snapshot:
        return jsonify({'error': 'No data available'})

    return jsonify({
        'indicators': snapshot.get('indicators', {}),
        'price_action': snapshot.get('price_action', {}),
        'timestamp': snapshot.get('timestamp')
    })


@app.route('/api/trades')
def api_trades():
    """Get recent trades"""
    mode = request.args.get('mode', 'paper')
    limit = int(request.args.get('limit', 10))

    snapshot = load_snapshot()

    if not snapshot:
        return jsonify({'trades': []})

    trades = snapshot.get('recent_trades', [])
    return jsonify({'trades': trades[:limit]})


@app.route('/api/performance')
def api_performance():
    """Get performance statistics"""
    snapshot = load_snapshot()

    if not snapshot:
        return jsonify({
            'total_trades': 0,
            'wins': 0,
            'losses': 0,
            'win_rate': 0,
            'profit_factor': 0,
            'avg_pnl': 0,
            'best_trade': 0
        })

    account = snapshot.get('account', {})
    trades = snapshot.get('recent_trades', [])

    # Calculate performance metrics
    total_trades = len(trades)
    wins = sum(1 for t in trades if t.get('pnl', 0) > 0)
    losses = total_trades - wins
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

    winning_pnl = sum(t.get('pnl', 0) for t in trades if t.get('pnl', 0) > 0)
    losing_pnl = abs(sum(t.get('pnl', 0) for t in trades if t.get('pnl', 0) < 0))
    profit_factor = (winning_pnl / losing_pnl) if losing_pnl > 0 else 0

    avg_pnl = (sum(t.get('pnl', 0) for t in trades) / total_trades) if total_trades > 0 else 0
    best_trade = max((t.get('pnl', 0) for t in trades), default=0)

    stats = {
        'total_trades': total_trades,
        'wins': wins,
        'losses': losses,
        'win_rate': win_rate,
        'profit_factor': profit_factor,
        'avg_pnl': avg_pnl,
        'best_trade': best_trade,
        'balance': account.get('balance', 0),
        'pnl': account.get('pnl', 0),
        'pnl_percent': account.get('pnl_percent', 0),
        'timestamp': snapshot.get('timestamp')
    }

    return jsonify(stats)


@app.route('/api/risk')
def api_risk():
    """Get risk management status"""
    snapshot = load_snapshot()

    if not snapshot:
        return jsonify({
            'daily_pnl': 0,
            'daily_loss_limit': 5.0,
            'max_drawdown': 0,
            'max_drawdown_limit': 10.0,
            'consecutive_wins': 0,
            'consecutive_losses': 0,
            'circuit_breaker': False
        })

    risk = snapshot.get('risk', {})
    account = snapshot.get('account', {})

    # Get risk data with defaults
    risk_data = {
        'daily_pnl': risk.get('daily_pnl', account.get('pnl', 0)),
        'daily_loss_limit': 5.0,  # $5 daily loss limit
        'max_drawdown': abs(min(account.get('pnl', 0), 0)),
        'max_drawdown_limit': 10.0,  # 10% max drawdown
        'consecutive_wins': 0,
        'consecutive_losses': 0,
        'circuit_breaker': not risk.get('can_trade', [True])[0] if risk.get('can_trade') else False
    }

    return jsonify(risk_data)


@app.route('/api/signals')
def api_signals():
    """Get recent trading signals (executed and rejected)"""
    try:
        # Get query parameters
        limit = int(request.args.get('limit', 20))
        hours = int(request.args.get('hours', 24))
        executed_only = request.args.get('executed_only', 'false').lower() == 'true'

        # Calculate time threshold
        time_threshold = (datetime.now() - timedelta(hours=hours)).isoformat()

        # Connect to database
        db_path = 'data/trades.db'
        if not os.path.exists(db_path):
            return jsonify({'signals': [], 'count': 0})

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        cursor = conn.cursor()

        # Build query
        query = '''
            SELECT
                id, timestamp, side, confidence, entry_price, stop_loss, take_profit,
                position_size_usd, margin_required, risk_amount, risk_percent,
                conditions, executed, execution_status, rejection_reason
            FROM scalping_signals
            WHERE timestamp >= ?
        '''

        params = [time_threshold]

        if executed_only:
            query += ' AND executed = 1'

        query += ' ORDER BY timestamp DESC LIMIT ?'
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        # Convert to list of dictionaries
        signals = []
        for row in rows:
            signal = {
                'id': row['id'],
                'timestamp': row['timestamp'],
                'side': row['side'],
                'confidence': round(row['confidence'] * 100, 1),  # Convert to percentage
                'entry_price': row['entry_price'],
                'stop_loss': row['stop_loss'],
                'take_profit': row['take_profit'],
                'position_size_usd': row['position_size_usd'],
                'margin_required': row['margin_required'],
                'risk_amount': row['risk_amount'],
                'risk_percent': row['risk_percent'],
                'conditions': row['conditions'],
                'executed': bool(row['executed']),
                'execution_status': row['execution_status'],
                'rejection_reason': row['rejection_reason']
            }
            signals.append(signal)

        # Get statistics
        cursor.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN executed = 1 THEN 1 ELSE 0 END) as executed,
                SUM(CASE WHEN executed = 0 THEN 1 ELSE 0 END) as rejected,
                AVG(CASE WHEN executed = 1 THEN confidence ELSE NULL END) * 100 as avg_executed_confidence,
                AVG(CASE WHEN executed = 0 THEN confidence ELSE NULL END) * 100 as avg_rejected_confidence
            FROM scalping_signals
            WHERE timestamp >= ?
        ''', [time_threshold])

        stats_row = cursor.fetchone()
        stats = {
            'total': stats_row['total'] or 0,
            'executed': stats_row['executed'] or 0,
            'rejected': stats_row['rejected'] or 0,
            'execution_rate': round((stats_row['executed'] or 0) / max(stats_row['total'], 1) * 100, 1),
            'avg_executed_confidence': round(stats_row['avg_executed_confidence'] or 0, 1),
            'avg_rejected_confidence': round(stats_row['avg_rejected_confidence'] or 0, 1)
        }

        conn.close()

        return jsonify({
            'signals': signals,
            'count': len(signals),
            'stats': stats,
            'period_hours': hours
        })

    except Exception as e:
        logger.error(f"Error fetching signals: {e}", exc_info=True)
        return jsonify({
            'error': str(e),
            'signals': [],
            'count': 0
        }), 500


@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'scalping-dashboard',
        'version': '2.0',
        'timestamp': datetime.now().isoformat()
    })


if __name__ == '__main__':
    logger.info("="*80)
    logger.info("🌐 Starting Scalping Dashboard Web Server")
    logger.info("   Port: 5902")
    logger.info("   Internal: http://localhost:5902")
    logger.info("   External: https://dev.ueipab.edu.ve:5900/scalping/")
    logger.info("="*80)

    # Run on port 5902 (different from ADX which uses 5901)
    app.run(host='0.0.0.0', port=5902, debug=False)
