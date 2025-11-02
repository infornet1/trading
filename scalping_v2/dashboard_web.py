#!/usr/bin/env python3
"""
Web Dashboard for Scalping Strategy v2.0
Provides real-time monitoring via web interface
"""

import sys
sys.path.insert(0, '/var/www/dev/trading/scalping_v2')

from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import json
import os
from datetime import datetime
import logging

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

    return jsonify({
        'status': bot_status,
        'account': snapshot.get('account', {}),
        'positions': snapshot.get('positions', []),
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
        return jsonify([])

    trades = snapshot.get('recent_trades', [])
    return jsonify(trades[:limit])


@app.route('/api/performance')
def api_performance():
    """Get performance statistics"""
    snapshot = load_snapshot()

    if not snapshot:
        return jsonify({'error': 'No data available'})

    account = snapshot.get('account', {})

    # Calculate basic stats from snapshot
    stats = {
        'balance': account.get('balance', 0),
        'pnl': account.get('pnl', 0),
        'pnl_percent': account.get('pnl_percent', 0),
        'total_trades': len(snapshot.get('recent_trades', [])),
        'timestamp': snapshot.get('timestamp')
    }

    return jsonify(stats)


@app.route('/api/risk')
def api_risk():
    """Get risk management status"""
    snapshot = load_snapshot()

    if not snapshot:
        return jsonify({'error': 'No data available'})

    risk = snapshot.get('risk', {})
    return jsonify(risk)


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
