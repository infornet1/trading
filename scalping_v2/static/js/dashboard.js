// Scalping Strategy v2.0 - Dashboard JavaScript
// Auto-refresh and dynamic updates

const REFRESH_INTERVAL = 5000; // 5 seconds
let refreshTimer = null;
let countdownTimer = null;
let countdown = 5;

// Initialize dashboard on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 Scalping Dashboard initialized');
    fetchAllData();
    startAutoRefresh();
});

// Start auto-refresh cycle
function startAutoRefresh() {
    refreshTimer = setInterval(fetchAllData, REFRESH_INTERVAL);
    startCountdown();
}

// Countdown timer
function startCountdown() {
    countdown = 5;
    countdownTimer = setInterval(() => {
        countdown--;
        document.getElementById('countdown').textContent = countdown;
        if (countdown <= 0) {
            countdown = 5;
        }
    }, 1000);
}

// Fetch all data from API
async function fetchAllData() {
    try {
        await Promise.all([
            fetchStatus(),
            fetchIndicators(),
            fetchPerformance(),
            fetchRisk(),
            fetchTrades()
        ]);
        updateLastUpdateTime();
    } catch (error) {
        console.error('Error fetching data:', error);
    }
}

// Fetch status (account, positions, BTC price)
async function fetchStatus() {
    try {
        const response = await fetch('api/status');
        const data = await response.json();

        // Update bot status
        const statusIndicator = document.getElementById('botStatus');
        const statusDot = statusIndicator.querySelector('.status-dot');
        const statusText = statusIndicator.querySelector('.status-text');

        if (data.bot_status.running) {
            statusDot.classList.remove('inactive');
            statusDot.classList.add('active');
            statusText.textContent = 'LIVE';
        } else {
            statusDot.classList.remove('active');
            statusDot.classList.add('inactive');
            statusText.textContent = 'OFFLINE';
        }

        // Update account stats
        const account = data.account;
        // Scalping initial capital is $1000
        const INITIAL_CAPITAL = 1000.0;
        document.getElementById('balance').textContent = formatCurrency(account.balance);
        const balanceChange = account.balance - INITIAL_CAPITAL;
        document.getElementById('balanceChange').textContent = formatCurrency(balanceChange);
        setColorClass('balanceChange', balanceChange);

        document.getElementById('totalPnl').textContent = formatCurrency(account.total_pnl);
        document.getElementById('pnlPercent').textContent = formatPercent(account.total_return_percent);
        setColorClass('totalPnl', account.total_pnl);
        setColorClass('pnlPercent', account.total_pnl);

        document.getElementById('positions').textContent = `${data.positions_count}/2`;
        document.getElementById('unrealizedPnl').textContent = formatCurrency(account.unrealized_pnl);
        setColorClass('unrealizedPnl', account.unrealized_pnl);

        document.getElementById('btcPrice').textContent = formatCurrency(data.btc_price);

        // Update positions
        updatePositions(data.positions);

    } catch (error) {
        console.error('Error fetching status:', error);
    }
}

// Fetch Scalping Indicators (EMA, RSI, Stochastic, Volume, ATR)
async function fetchIndicators() {
    try {
        const response = await fetch('api/indicators');
        const data = await response.json();

        // EMA values
        document.getElementById('adxValue').textContent = data.ema_5 ? data.ema_5.toFixed(2) : '--';
        document.getElementById('plusDi').textContent = data.ema_8 ? data.ema_8.toFixed(2) : '--';
        document.getElementById('minusDi').textContent = data.ema_21 ? data.ema_21.toFixed(2) : '--';

        // RSI and Stochastic
        document.getElementById('diSpread').textContent = data.rsi ? data.rsi.toFixed(2) : '--';
        document.getElementById('adxSlope').textContent = data.stoch_k ? data.stoch_k.toFixed(2) : '--';
        document.getElementById('confidence').textContent = data.volume_ratio ? (data.volume_ratio * 100).toFixed(1) + '%' : '--';

        // Update indicator bar (use RSI 0-100 range)
        if (data.rsi) {
            const rsiPercent = data.rsi;
            document.getElementById('adxBar').style.width = rsiPercent + '%';
        }

        // Update market state based on scalping conditions
        const marketState = document.getElementById('marketState');
        if (data.signal) {
            marketState.textContent = data.signal.toUpperCase();
            marketState.classList.remove('trending', 'ranging', 'building');
            if (data.signal === 'LONG' || data.signal === 'SHORT') {
                marketState.classList.add('trending');
            } else {
                marketState.classList.add('ranging');
            }
        } else {
            marketState.textContent = 'ANALYZING';
            marketState.classList.remove('trending', 'ranging');
            marketState.classList.add('building');
        }

        // Color code metrics
        if (data.rsi) {
            setColorClass('adxValue', data.rsi > 30 && data.rsi < 70 ? 1 : -1);
        }

    } catch (error) {
        console.error('Error fetching indicators:', error);
    }
}

// Fetch performance stats
async function fetchPerformance() {
    try {
        const response = await fetch('api/performance');
        const data = await response.json();

        document.getElementById('totalTrades').textContent = data.total_trades;
        document.getElementById('winRate').textContent = data.win_rate.toFixed(1) + '%';
        document.getElementById('winsLosses').textContent = `${data.wins} / ${data.losses}`;
        document.getElementById('profitFactor').textContent = data.profit_factor ? data.profit_factor.toFixed(2) : '--';
        document.getElementById('avgPnl').textContent = formatCurrency(data.avg_pnl);
        document.getElementById('bestTrade').textContent = formatCurrency(data.best_trade);

        setColorClass('winRate', data.win_rate >= 50 ? 1 : -1);
        setColorClass('avgPnl', data.avg_pnl);
        setColorClass('bestTrade', data.best_trade);

    } catch (error) {
        console.error('Error fetching performance:', error);
    }
}

// Fetch risk status
async function fetchRisk() {
    try {
        const response = await fetch('api/risk');
        const data = await response.json();

        document.getElementById('dailyPnl').textContent = formatCurrency(data.daily_pnl);
        document.getElementById('maxDrawdown').textContent = data.max_drawdown.toFixed(2) + '%';
        document.getElementById('consecutive').textContent = `${data.consecutive_wins}W / ${data.consecutive_losses}L`;

        // Update progress bars
        const dailyPnlPercent = Math.abs(data.daily_pnl / data.daily_loss_limit) * 100;
        updateProgressBar('dailyPnlBar', dailyPnlPercent, data.daily_pnl < 0);

        const drawdownPercent = (data.max_drawdown / data.max_drawdown_limit) * 100;
        updateProgressBar('drawdownBar', drawdownPercent, true);

        // Circuit breaker status
        const circuitStatus = document.getElementById('circuitStatus');
        if (data.circuit_breaker) {
            circuitStatus.textContent = 'ACTIVE';
            circuitStatus.classList.add('active');
        } else {
            circuitStatus.textContent = 'OK';
            circuitStatus.classList.remove('active');
        }

        setColorClass('dailyPnl', data.daily_pnl);

    } catch (error) {
        console.error('Error fetching risk:', error);
    }
}

// Fetch trade history with optional filter
async function fetchTrades() {
    try {
        // Get selected filter mode
        const filterSelect = document.getElementById('tradeFilter');
        const mode = filterSelect ? filterSelect.value : '';

        // Build URL with filter
        let url = 'api/trades?limit=10';
        if (mode) {
            url += `&mode=${mode}`;
        }

        const response = await fetch(url);
        const data = await response.json();

        const container = document.getElementById('tradesContainer');

        if (data.trades.length === 0) {
            const filterText = mode ? ` (${mode} mode)` : '';
            container.innerHTML = `<div class="empty-state">No trades yet${filterText}</div>`;
            return;
        }

        container.innerHTML = data.trades.map(trade => `
            <div class="trade-item ${trade.pnl > 0 ? 'win' : 'loss'}">
                <div class="trade-header">
                    <span class="trade-side">${trade.side}</span>
                    <span class="trade-mode-badge ${trade.trading_mode || 'paper'}">${(trade.trading_mode || 'paper').toUpperCase()}</span>
                    <span class="trade-pnl ${trade.pnl > 0 ? 'positive' : 'negative'}">
                        ${formatCurrency(trade.pnl)}
                    </span>
                </div>
                <div class="trade-details">
                    <span>${formatCurrency(trade.entry_price)} → ${formatCurrency(trade.exit_price)}</span>
                    <span>${trade.exit_reason}</span>
                </div>
                <div class="trade-details">
                    <span>${formatHoldTime(trade.hold_duration * 3600)}</span>
                    <span>${formatPercent(trade.pnl_percent)}</span>
                </div>
                <div class="trade-timestamp">
                    ${formatTimestamp(trade.closed_at)}
                </div>
            </div>
        `).join('');

    } catch (error) {
        console.error('Error fetching trades:', error);
    }
}

// Update positions display
function updatePositions(positions) {
    const container = document.getElementById('positionsContainer');

    if (positions.length === 0) {
        container.innerHTML = '<div class="empty-state">No open positions</div>';
        return;
    }

    container.innerHTML = positions.map(pos => `
        <div class="position-card ${pos.side.toLowerCase()}">
            <div class="position-header">
                <span class="position-side">${pos.side}</span>
                <span class="position-pnl ${pos.unrealized_pnl > 0 ? 'positive' : 'negative'}">
                    ${formatCurrency(pos.unrealized_pnl)}
                </span>
            </div>
            <div class="position-details">
                <div class="position-detail">
                    <span>Entry:</span>
                    <span>${formatCurrency(pos.entry_price)}</span>
                </div>
                <div class="position-detail">
                    <span>Current:</span>
                    <span>${formatCurrency(pos.current_price)}</span>
                </div>
                <div class="position-detail">
                    <span>Stop Loss:</span>
                    <span>${formatCurrency(pos.stop_loss)}</span>
                </div>
                <div class="position-detail">
                    <span>Take Profit:</span>
                    <span>${formatCurrency(pos.take_profit)}</span>
                </div>
            </div>
        </div>
    `).join('');
}

// Update progress bar
function updateProgressBar(id, percent, isDanger) {
    const bar = document.getElementById(id);
    bar.style.width = Math.min(percent, 100) + '%';

    bar.classList.remove('warning', 'danger');
    if (isDanger && percent > 80) {
        bar.classList.add('danger');
    } else if (isDanger && percent > 50) {
        bar.classList.add('warning');
    }
}

// Update last update time
function updateLastUpdateTime() {
    const now = new Date();
    const timeStr = now.toLocaleTimeString();
    document.getElementById('lastUpdate').textContent = `Last update: ${timeStr}`;
}

// Utility: Format currency
function formatCurrency(value) {
    if (typeof value !== 'number') return '$0.00';
    const sign = value >= 0 ? '+' : '';
    return sign + '$' + Math.abs(value).toFixed(2);
}

// Utility: Format percent
function formatPercent(value) {
    if (typeof value !== 'number') return '0.00%';
    const sign = value >= 0 ? '+' : '';
    return sign + value.toFixed(2) + '%';
}

// Utility: Format hold time
function formatHoldTime(seconds) {
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m`;
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return `${hours}h ${mins}m`;
}

// Utility: Format timestamp
function formatTimestamp(timestamp) {
    if (!timestamp) return '--';
    const date = new Date(timestamp);
    const now = new Date();

    // If today, show time only
    if (date.toDateString() === now.toDateString()) {
        return '🕐 Today ' + date.toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        });
    }

    // If yesterday
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    if (date.toDateString() === yesterday.toDateString()) {
        return '🕐 Yesterday ' + date.toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit',
            hour12: false
        });
    }

    // Otherwise show full date and time
    return '🕐 ' + date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric'
    }) + ' ' + date.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
    });
}

// Utility: Set color class based on value
function setColorClass(id, value) {
    const element = document.getElementById(id);
    if (!element) return;

    element.classList.remove('positive', 'negative');
    if (value > 0) {
        element.classList.add('positive');
    } else if (value < 0) {
        element.classList.add('negative');
    }
}

// Filter trades by mode (called by dropdown onchange)
function filterTrades() {
    console.log('🔄 Filtering trades...');
    fetchTrades();
}

// Error handling for fetch
window.addEventListener('unhandledrejection', function(event) {
    console.error('Unhandled promise rejection:', event.reason);
});

// ===== SCALPING-SPECIFIC ENHANCEMENTS =====

// Scalping Dashboard Class
class ScalpingDashboard {
    constructor() {
        this.updateInterval = 5000; // 5 seconds
        this.positionTimers = new Map();
        this.previousEMAs = {};
        this.init();
    }

    init() {
        console.log('⚡ Scalping Dashboard Enhanced Features Initialized');
        this.startPositionTimers();
    }

    updateMarketIndicators(data) {
        if (!data || !data.indicators) return;

        const indicators = data.indicators;

        // Update RSI with color coding
        const rsi = indicators.rsi || 50;
        this.updateRSI(rsi);

        // Update Stochastic
        this.updateStochastic(indicators);

        // Update EMA values and trends
        this.updateEMAs(indicators);

        // Update volume and volatility
        this.updateVolumeData(indicators);

        // Update market regime
        this.updateMarketRegime(data.market_regime);

        // Update active signals
        if (data.long || data.short) {
            this.updateSignals({long: data.long, short: data.short});
        }

        // Update market conditions
        this.updateMarketConditions(indicators);
    }

    updateRSI(rsi) {
        const rsiElement = document.getElementById('rsiValue');
        const rsiBar = document.getElementById('rsiBar');

        if (!rsiElement || !rsiBar) return;

        rsiElement.textContent = rsi.toFixed(2);
        rsiBar.style.width = `${rsi}%`;

        // Color coding
        if (rsi > 70) {
            rsiBar.style.background = '#ff4444'; // Overbought - red
        } else if (rsi < 30) {
            rsiBar.style.background = '#00ff88'; // Oversold - green
        } else {
            rsiBar.style.background = '#00aaff'; // Neutral - blue
        }
    }

    updateStochastic(indicators) {
        const stochElement = document.getElementById('stochValue');
        if (!stochElement) return;

        const stochK = indicators.stoch_k || 0;
        const stochD = indicators.stoch_d || 0;
        stochElement.textContent = `${stochK.toFixed(1)}/${stochD.toFixed(1)}`;
    }

    updateEMAs(indicators) {
        const emaFields = [
            {key: 'ema_micro', id: 'ema5Value', trendId: 'ema5Trend'},
            {key: 'ema_fast', id: 'ema8Value', trendId: 'ema8Trend'},
            {key: 'ema_slow', id: 'ema21Value', trendId: 'ema21Trend'}
        ];

        emaFields.forEach(field => {
            const value = indicators[field.key];
            if (value) {
                const element = document.getElementById(field.id);
                const trendElement = document.getElementById(field.trendId);

                if (element) {
                    element.textContent = value.toFixed(2);
                }

                // Update trend indicator
                if (trendElement && this.previousEMAs[field.key]) {
                    const trend = value > this.previousEMAs[field.key] ? '↑' : value < this.previousEMAs[field.key] ? '↓' : '→';
                    trendElement.textContent = trend;
                    trendElement.classList.remove('up', 'down');
                    if (value > this.previousEMAs[field.key]) {
                        trendElement.classList.add('up');
                    } else if (value < this.previousEMAs[field.key]) {
                        trendElement.classList.add('down');
                    }
                }

                this.previousEMAs[field.key] = value;
            }
        });

        this.updateEMAAlignment(indicators);
    }

    updateEMAAlignment(indicators) {
        const alignmentElement = document.getElementById('alignmentStatus');
        if (!alignmentElement) return;

        const ema5 = indicators.ema_micro;
        const ema8 = indicators.ema_fast;
        const ema21 = indicators.ema_slow;

        if (ema5 && ema8 && ema21) {
            if (ema5 > ema8 && ema8 > ema21) {
                alignmentElement.innerHTML = '<span class="status-dot" style="background:#00ff88"></span><span>Alignment: Bullish</span>';
            } else if (ema5 < ema8 && ema8 < ema21) {
                alignmentElement.innerHTML = '<span class="status-dot" style="background:#ff4444"></span><span>Alignment: Bearish</span>';
            } else {
                alignmentElement.innerHTML = '<span class="status-dot" style="background:#ffaa00"></span><span>Alignment: Mixed</span>';
            }
        }
    }

    updateVolumeData(indicators) {
        const volumeRatio = indicators.volume_ratio || 1.0;
        const atrPct = indicators.atr_pct || 0;

        // Update volume ratio
        const volumeRatioElement = document.getElementById('volumeRatio');
        const volumeBar = document.getElementById('volumeBar');
        if (volumeRatioElement) {
            volumeRatioElement.textContent = volumeRatio.toFixed(2) + 'x';
        }
        if (volumeBar) {
            const volumePercent = Math.min((volumeRatio / 2.0) * 100, 100);
            volumeBar.style.width = `${volumePercent}%`;
            volumeBar.style.background = volumeRatio > 1.5 ? '#00ff88' : '#00aaff';
        }

        // Update ATR
        const atrElement = document.getElementById('atrPercent');
        if (atrElement) {
            atrElement.textContent = atrPct.toFixed(2) + '%';
        }

        // Update volatility meter
        this.updateVolatilityMeter(atrPct);
    }

    updateVolatilityMeter(atrPct) {
        const meterFill = document.getElementById('volatilityMeter');
        const meterValue = document.getElementById('volatilityValue');

        if (!meterFill || !meterValue) return;

        const volatilityPercent = Math.min((atrPct / 3.0) * 100, 100);
        meterFill.style.width = `${volatilityPercent}%`;

        if (atrPct < 1.0) {
            meterValue.textContent = 'LOW';
        } else if (atrPct < 2.0) {
            meterValue.textContent = 'MEDIUM';
        } else {
            meterValue.textContent = 'HIGH';
        }
    }

    updateSignals(signals) {
        const longSignal = document.getElementById('longSignal');
        const shortSignal = document.getElementById('shortSignal');

        this.updateSignalElement(longSignal, signals.long, 'LONG');
        this.updateSignalElement(shortSignal, signals.short, 'SHORT');

        // Update overall signal strength
        const signalStrength = document.getElementById('signalStrength');
        if (signalStrength) {
            const longConf = signals.long?.confidence || 0;
            const shortConf = signals.short?.confidence || 0;
            const maxConf = Math.max(longConf, shortConf);

            if (maxConf > 0.7) {
                signalStrength.textContent = 'STRONG';
                signalStrength.classList.add('strong');
                signalStrength.classList.remove('weak');
            } else if (maxConf > 0.5) {
                signalStrength.textContent = 'MODERATE';
                signalStrength.classList.remove('strong', 'weak');
            } else {
                signalStrength.textContent = 'WEAK';
                signalStrength.classList.add('weak');
                signalStrength.classList.remove('strong');
            }
        }
    }

    updateSignalElement(element, signal, type) {
        if (!element) return;

        if (signal && signal.confidence > 0.6) {
            element.classList.add('active');
            element.querySelector('.signal-confidence').textContent =
                `${(signal.confidence * 100).toFixed(1)}%`;

            const conditions = signal.conditions || [];
            element.querySelector('.signal-conditions').textContent =
                conditions.slice(0, 3).join(', ') || 'Conditions met';
        } else {
            element.classList.remove('active');
            element.querySelector('.signal-confidence').textContent = '--%';
            element.querySelector('.signal-conditions').textContent = 'No signal';
        }
    }

    updateMarketConditions(indicators) {
        // Trend Strength
        const trendStrength = document.getElementById('trendStrength');
        if (trendStrength) {
            const emaSpread = Math.abs((indicators.ema_micro - indicators.ema_slow) / indicators.ema_slow) * 100;
            if (emaSpread > 0.2) {
                trendStrength.textContent = 'Strong';
                trendStrength.style.color = '#00ff88';
            } else if (emaSpread > 0.1) {
                trendStrength.textContent = 'Moderate';
                trendStrength.style.color = '#ffaa00';
            } else {
                trendStrength.textContent = 'Weak';
                trendStrength.style.color = '#ff4444';
            }
        }

        // Volatility Level
        const volatilityLevel = document.getElementById('volatilityLevel');
        if (volatilityLevel) {
            const atrPct = indicators.atr_pct || 0;
            if (atrPct < 1.0) {
                volatilityLevel.textContent = 'Low';
                volatilityLevel.style.color = '#00aaff';
            } else if (atrPct < 2.5) {
                volatilityLevel.textContent = 'Normal';
                volatilityLevel.style.color = '#00ff88';
            } else {
                volatilityLevel.textContent = 'High';
                volatilityLevel.style.color = '#ff4444';
            }
        }

        // Volume Activity
        const volumeActivity = document.getElementById('volumeActivity');
        if (volumeActivity) {
            const volRatio = indicators.volume_ratio || 1.0;
            if (volRatio > 1.5) {
                volumeActivity.textContent = 'High';
                volumeActivity.style.color = '#00ff88';
            } else if (volRatio > 0.8) {
                volumeActivity.textContent = 'Normal';
                volumeActivity.style.color = '#00aaff';
            } else {
                volumeActivity.textContent = 'Low';
                volumeActivity.style.color = '#ffaa00';
            }
        }
    }

    updateMarketRegime(regime) {
        const marketState = document.getElementById('marketState');
        if (!marketState || !regime) return;

        marketState.textContent = regime.toUpperCase();
        marketState.classList.remove('trending', 'ranging', 'choppy');

        if (regime === 'trending') {
            marketState.classList.add('trending');
        } else if (regime === 'ranging') {
            marketState.classList.add('ranging');
        } else if (regime === 'choppy') {
            marketState.classList.add('choppy');
        }
    }

    startPositionTimers() {
        // Update position timers every second
        setInterval(() => {
            document.querySelectorAll('[data-start-time]').forEach(element => {
                const startTime = new Date(element.dataset.startTime);
                if (isNaN(startTime.getTime())) return;

                const now = new Date();
                const diffMs = now - startTime;
                const diffMins = Math.floor(diffMs / 60000);
                const diffSecs = Math.floor((diffMs % 60000) / 1000);

                element.textContent = `${diffMins}:${diffSecs.toString().padStart(2, '0')}`;
            });
        }, 1000);
    }
}

// Initialize Scalping Dashboard
let scalpingDashboard = null;
document.addEventListener('DOMContentLoaded', function() {
    scalpingDashboard = new ScalpingDashboard();
});

// Enhance existing fetchIndicators to use ScalpingDashboard
const originalFetchIndicators = fetchIndicators;
fetchIndicators = async function() {
    await originalFetchIndicators();

    // Also update scalping-specific indicators if available
    if (scalpingDashboard) {
        try {
            const response = await fetch('api/indicators');
            const data = await response.json();
            scalpingDashboard.updateMarketIndicators(data);
        } catch (error) {
            console.error('Error updating scalping indicators:', error);
        }
    }
};

// ============================================================================
// SIGNALS TRACKING FUNCTIONS
// ============================================================================

let allSignalsData = [];
let currentFilter = 'all';
let currentHours = 24;

async function fetchSignals() {
    try {
        const response = await fetch(`api/signals?limit=50&hours=${currentHours}`);
        const data = await response.json();

        allSignalsData = data.signals || [];
        updateSignalStats(data.stats || {});
        displaySignals();
    } catch (error) {
        console.error('Error fetching signals:', error);
        document.getElementById('signalsTableBody').innerHTML = `
            <tr><td colspan="8" class="error-state">Error loading signals</td></tr>
        `;
    }
}

function updateSignalStats(stats) {
    document.getElementById('totalSignals').textContent = stats.total || 0;
    document.getElementById('executedSignals').textContent = stats.executed || 0;
    document.getElementById('rejectedSignals').textContent = stats.rejected || 0;
    document.getElementById('executionRate').textContent = `${stats.execution_rate || 0}%`;
}

function displaySignals() {
    // Filter signals based on current filter
    let filtered = allSignalsData;
    if (currentFilter === 'executed') {
        filtered = allSignalsData.filter(s => s.executed);
    } else if (currentFilter === 'rejected') {
        filtered = allSignalsData.filter(s => !s.executed);
    }

    const tbody = document.getElementById('signalsTableBody');

    if (filtered.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="empty-state">No signals found</td></tr>';
        return;
    }

    tbody.innerHTML = filtered.map(signal => {
        const time = new Date(signal.timestamp).toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit'
        });

        const sideClass = signal.side === 'LONG' ? 'signal-long' : 'signal-short';
        const sideIcon = signal.side === 'LONG' ? '🟢' : '🔴';

        const statusClass = signal.executed ? 'status-executed' : 'status-rejected';
        const statusText = signal.execution_status || 'UNKNOWN';

        const stopDist = ((signal.stop_loss - signal.entry_price) / signal.entry_price * 100).toFixed(2);
        const targetDist = ((signal.take_profit - signal.entry_price) / signal.entry_price * 100).toFixed(2);

        return `
            <tr class="${sideClass}">
                <td>${time}</td>
                <td><span class="side-badge ${sideClass}">${sideIcon} ${signal.side}</span></td>
                <td><span class="confidence-badge">${signal.confidence}%</span></td>
                <td>$${signal.entry_price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                <td class="stop-target">
                    <div>SL: $${signal.stop_loss.toFixed(2)} (${stopDist}%)</div>
                    <div>TP: $${signal.take_profit.toFixed(2)} (${targetDist}%)</div>
                </td>
                <td class="conditions">${signal.conditions || 'N/A'}</td>
                <td><span class="status-badge ${statusClass}">${statusText}</span></td>
                <td class="rejection-reason">${signal.rejection_reason || '-'}</td>
            </tr>
        `;
    }).join('');
}

function filterSignals() {
    currentFilter = document.getElementById('signalFilter').value;
    displaySignals();
}

function changeSignalPeriod() {
    currentHours = parseInt(document.getElementById('signalHours').value);
    fetchSignals();
}

// Fetch signals every 10 seconds
setInterval(fetchSignals, 10000);

// Initial fetch
fetchSignals();
