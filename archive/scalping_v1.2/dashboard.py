#!/usr/bin/env python3
"""
Simple Web Dashboard for Signal Tracking
Shows win rate, statistics, and recent signals
"""

from flask import Flask, render_template, jsonify, send_from_directory
from signal_tracker import SignalTracker
from datetime import datetime
import json
import os

app = Flask(__name__)
tracker = SignalTracker()


@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('dashboard.html')


@app.route('/api/stats/<int:hours>')
def get_stats(hours):
    """Get statistics for specified time period"""
    stats = tracker.get_statistics(hours_back=hours)
    return jsonify(stats)


@app.route('/api/signals/recent/<int:limit>')
def get_recent_signals(limit):
    """Get recent signals"""
    signals = tracker.get_recent_signals(limit=limit)
    return jsonify(signals)


@app.route('/api/signals/unchecked')
def get_unchecked():
    """Get signals pending outcome check"""
    signals = tracker.get_unchecked_signals()
    return jsonify(signals)


@app.route('/favicon.ico')
def favicon():
    """Serve favicon (prevents 404 error)"""
    # Return a simple empty response for now
    return '', 204


if __name__ == '__main__':
    print("🚀 Starting Signal Tracker Dashboard...")
    print("📊 Dashboard URL: http://localhost:5800")
    print("📊 External Access: http://YOUR_SERVER_IP:5800")
    print("⌨️  Press Ctrl+C to stop\n")
    app.run(host='0.0.0.0', port=5800, debug=True)
