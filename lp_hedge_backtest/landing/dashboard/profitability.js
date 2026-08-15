/* ── Profitability Dashboard ───────────────────────────────────────────────
   Fetches /performance/* endpoints and renders KPIs, equity curve,
   drawdown, trade journal, and breakdown tables.
   This module is only active when the server-side feature flag is enabled.
   ───────────────────────────────────────────────────────────────────────── */

(function () {
  'use strict';

  const API_BASE = window.API_BASE || '/trading/lp-hedge/api';

  // ── State ─────────────────────────────────────────────────────────────────
  let perfState = {
    enabled: false,
    summary: null,
    equity: [],
    trades: [],
    tradeTotal: null,   // total row count from backend (null = unknown, use heuristic)
    breakdownBy: 'pair',
    dateFrom: '',
    dateTo: '',
    tradeOffset: 0,
    tradeLimit: 25,
    includeEstimates: false,
  };

  // ── Helpers ───────────────────────────────────────────────────────────────

  function formatUsd(value) {
    if (value === null || value === undefined || isNaN(value)) return '—';
    const n = Number(value);
    const sign = n >= 0 ? '+' : '';
    return `${sign}$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  function formatPct(value) {
    if (value === null || value === undefined || isNaN(value)) return '—';
    const n = Number(value);
    const sign = n >= 0 ? '+' : '';
    return `${sign}${n.toFixed(2)}%`;
  }

  function getJwt() {
    // Align with dashboard.js token key
    return localStorage.getItem('vf_jwt') || sessionStorage.getItem('vf_jwt') || '';
  }

  async function perfFetch(path) {
    const res = await fetch(`${API_BASE}${path}`, {
      headers: { Authorization: `Bearer ${getJwt()}` },
    });
    if (res.status === 404) {
      perfState.enabled = false;
      throw new Error('feature_disabled');
    }
    if (!res.ok) {
      const err = await res.text();
      throw new Error(err);
    }
    return res.json();
  }

  function setDateRangeDefaults() {
    const to = new Date();
    const from = new Date();
    from.setDate(from.getDate() - 30);
    perfState.dateTo = to.toISOString().split('T')[0];
    perfState.dateFrom = from.toISOString().split('T')[0];
  }

  // ── Feedback UI (loading spinner, error/notice banner, timestamp) ──────────

  function setPerfLoading(on) {
    document.getElementById('perf-loading')?.classList.toggle('hidden', !on);
  }

  function showPerfBanner(kind, msg) {
    const el = document.getElementById('perf-banner');
    if (!el) return;
    el.classList.remove('hidden', 'perf-banner--error', 'perf-banner--notice');
    el.classList.add(`perf-banner--${kind}`);
    el.textContent = msg;
  }

  function clearPerfBanner() {
    document.getElementById('perf-banner')?.classList.add('hidden');
  }

  function updatePerfTimestamp() {
    const el = document.getElementById('perf-updated');
    if (!el) return;
    el.textContent = `${t('perf.updated')} ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
  }

  // ── Rendering ─────────────────────────────────────────────────────────────

  function renderSummary() {
    const s = perfState.summary || {};
    const grid = document.getElementById('perf-kpi-grid');
    if (!grid) return;

    const items = [
      { label: t('perf.netRealizedPnl'), value: formatUsd(s.net_realized_pnl_usd), cls: valueClass(s.net_realized_pnl_usd) },
      { label: t('perf.totalTrades'), value: s.total_trades ?? '—' },
      { label: t('perf.winRate'), value: formatPct(s.win_rate_pct) },
      { label: t('perf.profitFactor'), value: s.profit_factor?.toFixed(2) ?? '—' },
      { label: t('perf.botPnl'), value: formatUsd(s.bot_realized_pnl_usd), cls: valueClass(s.bot_realized_pnl_usd) },
      { label: t('perf.signalPnl'), value: formatUsd(s.signal_realized_pnl_usd), cls: valueClass(s.signal_realized_pnl_usd) },
      { label: t('perf.feesPaid'), value: formatUsd((s.bot_fees_usd || 0) + (s.signal_fees_usd || 0)) },
      { label: t('perf.fundingPaid'), value: formatUsd(s.bot_funding_usd) },
    ];

    grid.innerHTML = items.map(it => `
      <div class="perf-kpi-card">
        <div class="perf-kpi-label">${it.label}</div>
        <div class="perf-kpi-value ${it.cls || ''}">${it.value}</div>
      </div>
    `).join('');
  }

  function valueClass(val) {
    if (val === null || val === undefined) return '';
    return Number(val) >= 0 ? 'perf-pos' : 'perf-neg';
  }

  // Equity chart is created once and reused across refreshes — recreating it
  // per render leaked chart instances and window resize listeners.
  let equityChart = null;
  let equitySeries = null;
  let equityChartContainer = null;

  window.addEventListener('resize', () => {
    if (equityChart && equityChartContainer) {
      equityChart.applyOptions({ width: equityChartContainer.clientWidth });
    }
  });

  function renderEquityChart() {
    const container = document.getElementById('perf-equity-chart');
    if (!container || !window.LightweightCharts) return;

    // (Re)create only on first render or if the section DOM was rebuilt.
    if (!equityChart || equityChartContainer !== container) {
      if (equityChart) equityChart.remove();
      equityChartContainer = container;
      equityChart = LightweightCharts.createChart(container, {
        width: container.clientWidth,
        height: 300,
        layout: { background: { color: 'transparent' }, textColor: '#cbd5e1' },
        grid: { vertLines: { color: 'rgba(255,255,255,0.05)' }, horzLines: { color: 'rgba(255,255,255,0.05)' } },
        rightPriceScale: { borderColor: 'rgba(255,255,255,0.1)' },
        timeScale: { borderColor: 'rgba(255,255,255,0.1)' },
      });

      equitySeries = equityChart.addAreaSeries({
        lineColor: '#00d4ff',
        topColor: 'rgba(0, 212, 255, 0.3)',
        bottomColor: 'rgba(0, 212, 255, 0.01)',
      });
    }

    // Snapshots are written every 15 min → up to 96 points share the same
    // date string. Lightweight-Charts v4 rejects duplicate `time` keys
    // ("data must be asc ordered by time"), so keep only the LAST snapshot
    // of each day (later Map sets overwrite) and sort ascending.
    const byDay = new Map();
    for (const p of perfState.equity) {
      if (!p.ts) continue;
      byDay.set(p.ts.split('T')[0], Number(p.equity || 0));
    }
    const data = [...byDay.entries()]
      .sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0))
      .map(([time, value]) => ({ time, value }));

    equitySeries.setData(data);
    equityChart.timeScale().fitContent();
  }

  function renderTradeJournal() {
    const tbody = document.getElementById('perf-trade-table-body');
    if (!tbody) return;

    if (!perfState.trades.length) {
      tbody.innerHTML = `<tr><td colspan="8" class="perf-empty">${t('perf.noTrades')}</td></tr>`;
      return;
    }

    tbody.innerHTML = perfState.trades.map(tr => `
      <tr>
        <td>${tr.closed_at ? new Date(tr.closed_at).toLocaleDateString() : '—'}</td>
        <td>${tr.mode || '—'}</td>
        <td>${tr.pair || '—'}</td>
        <td>${tr.side || '—'}</td>
        <td>${formatUsd(tr.net_pnl_usd)} ${tr.is_estimate ? '<span class="perf-est">est</span>' : ''}</td>
        <td>${formatUsd(tr.realized_pnl_usd)}</td>
        <td>${formatUsd(tr.fees_usd)}</td>
        <td>${tr.exit_reason || '—'}</td>
      </tr>
    `).join('');
  }

  function updatePaginationButtons() {
    const prev = document.getElementById('perf-prev');
    const next = document.getElementById('perf-next');
    if (!prev || !next) return;
    prev.disabled = perfState.tradeOffset === 0;
    const rows = perfState.trades.length;
    if (perfState.tradeTotal != null) {
      next.disabled = perfState.tradeOffset + rows >= perfState.tradeTotal;
    } else {
      // Heuristic fallback when the backend does not return a total count
      next.disabled = rows < perfState.tradeLimit;
    }
  }

  function renderBreakdown() {
    const container = document.getElementById('perf-breakdown-table-body');
    if (!container) return;

    const rows = perfState.breakdown?.rows || [];
    if (!rows.length) {
      container.innerHTML = `<tr><td colspan="6" class="perf-empty">${t('perf.noData')}</td></tr>`;
      return;
    }

    container.innerHTML = rows.map(r => `
      <tr>
        <td>${r.key}</td>
        <td>${r.trades}</td>
        <td>${formatUsd(r.net_pnl_usd)}</td>
        <td>${formatUsd(r.realized_pnl_usd)}</td>
        <td>${formatUsd(r.fees_usd)}</td>
        <td>${r.wins}/${r.losses}</td>
      </tr>
    `).join('');
  }

  // ── Data loading ──────────────────────────────────────────────────────────

  async function loadSummary() {
    const params = dateParams();
    const est = estimateParam();
    perfState.summary = await perfFetch(`/performance/summary${params}${est}`);
    renderSummary();
  }

  async function loadEquity() {
    const params = dateParams();
    perfState.equity = await perfFetch(`/performance/equity-curve${params}`);
    // A chart failure must not reject the whole load — KPIs/tables matter more.
    try {
      renderEquityChart();
    } catch (e) {
      console.error('[Performance] Equity chart render failed:', e);
    }
  }

  async function loadTrades() {
    const params = dateParams();
    const est = estimateParam();
    const sep = params ? '&' : '?';
    const data = await perfFetch(`/performance/trades${params}${sep}limit=${perfState.tradeLimit}&offset=${perfState.tradeOffset}${est.replace('?', '&')}`);
    perfState.trades = data.rows || [];
    perfState.tradeTotal = typeof data.total === 'number' ? data.total : null;
    renderTradeJournal();
    updatePaginationButtons();
  }

  async function loadBreakdown() {
    const params = dateParams();
    const est = estimateParam();
    perfState.breakdown = await perfFetch(`/performance/breakdown?by=${perfState.breakdownBy}${params.replace('?', '&')}${est.replace('?', '&')}`);
    renderBreakdown();
  }

  function dateParams() {
    const parts = [];
    if (perfState.dateFrom) parts.push(`from=${perfState.dateFrom}`);
    if (perfState.dateTo) parts.push(`to=${perfState.dateTo}`);
    return parts.length ? `?${parts.join('&')}` : '';
  }

  function estimateParam() {
    return perfState.includeEstimates ? '&include_estimates=true' : '';
  }

  async function loadAllPerformanceData() {
    setPerfLoading(true);
    try {
      // allSettled: one failing section must not blank the others.
      const results = await Promise.allSettled([
        loadSummary(),
        loadEquity(),
        loadTrades(),
        loadBreakdown(),
      ]);
      const failed = results.filter(r => r.status === 'rejected');
      if (failed.length) {
        console.error('[Performance] Load errors:', failed.map(f => f.reason));
        showPerfBanner('error', t('perf.loadError'));
      } else {
        clearPerfBanner();
        updatePerfTimestamp();
      }
    } finally {
      setPerfLoading(false);
    }
  }

  // Runs a partial refresh (toggle/tab/pagination) with inline error reporting.
  // On failure the previous data stays visible and a banner is shown.
  async function guarded(promise) {
    try {
      await promise;
      clearPerfBanner();
      updatePerfTimestamp();
      return true;
    } catch (err) {
      console.error('[Performance]', err);
      showPerfBanner('error', t('perf.loadError'));
      return false;
    }
  }

  // ── Initialization ────────────────────────────────────────────────────────

  function buildPerformanceSection() {
    const section = document.getElementById('performance-section');
    if (!section) return;

    section.innerHTML = `
      <div class="perf-controls">
        <label>${t('perf.from')}</label>
        <input type="date" id="perf-from" value="${perfState.dateFrom}">
        <label>${t('perf.to')}</label>
        <input type="date" id="perf-to" value="${perfState.dateTo}">
        <button class="btn btn--primary" id="perf-refresh">${t('perf.refresh')}</button>
        <button class="btn" id="perf-export">${t('perf.exportCsv')}</button>
        <label class="perf-toggle">
          <input type="checkbox" id="perf-include-estimates">
          ${t('perf.includeEstimates') || 'Incluir estimados'}
        </label>
        <span id="perf-updated" class="perf-updated"></span>
      </div>
      <div id="perf-banner" class="perf-banner hidden"></div>
      <div id="perf-loading" class="perf-loading hidden">
        <div class="spinner perf-spinner"></div>
        <span>${t('perf.loading')}</span>
      </div>
      <div id="perf-kpi-grid" class="perf-kpi-grid"></div>
      <div class="perf-chart-row">
        <div class="perf-chart-box">
          <h4>${t('perf.equityCurve')}</h4>
          <div id="perf-equity-chart" class="perf-chart"></div>
        </div>
      </div>
      <div class="perf-breakdown">
        <div class="perf-breakdown-header">
          <h4>${t('perf.breakdown')}</h4>
          <div class="perf-breakdown-tabs">
            <button class="perf-breakdown-tab ${perfState.breakdownBy === 'pair' ? 'active' : ''}" data-by="pair">${t('perf.byPair')}</button>
            <button class="perf-breakdown-tab ${perfState.breakdownBy === 'mode' ? 'active' : ''}" data-by="mode">${t('perf.byMode')}</button>
            <button class="perf-breakdown-tab ${perfState.breakdownBy === 'month' ? 'active' : ''}" data-by="month">${t('perf.byMonth')}</button>
          </div>
        </div>
        <table class="perf-table">
          <thead>
            <tr><th>${t('perf.key')}</th><th>${t('perf.trades')}</th><th>${t('perf.netPnl')}</th><th>${t('perf.realizedPnl')}</th><th>${t('perf.fees')}</th><th>${t('perf.winsLosses')}</th></tr>
          </thead>
          <tbody id="perf-breakdown-table-body"></tbody>
        </table>
      </div>
      <div class="perf-journal">
        <h4>${t('perf.tradeJournal')}</h4>
        <table class="perf-table">
          <thead>
            <tr><th>${t('perf.date')}</th><th>${t('perf.mode')}</th><th>${t('perf.pair')}</th><th>${t('perf.side')}</th><th>${t('perf.netPnl')}</th><th>${t('perf.realizedPnl')}</th><th>${t('perf.fees')}</th><th>${t('perf.reason')}</th></tr>
          </thead>
          <tbody id="perf-trade-table-body"></tbody>
        </table>
        <div class="perf-pagination">
          <button class="btn" id="perf-prev" ${perfState.tradeOffset === 0 ? 'disabled' : ''}>${t('perf.prev')}</button>
          <button class="btn" id="perf-next">${t('perf.next')}</button>
        </div>
      </div>
    `;

    document.getElementById('perf-refresh').addEventListener('click', () => {
      perfState.dateFrom = document.getElementById('perf-from').value;
      perfState.dateTo = document.getElementById('perf-to').value;
      loadAllPerformanceData();
    });

    document.getElementById('perf-export').addEventListener('click', async () => {
      const btn = document.getElementById('perf-export');
      const qs = new URLSearchParams();
      if (perfState.dateFrom) qs.set('from', perfState.dateFrom);
      if (perfState.dateTo) qs.set('to', perfState.dateTo);
      if (perfState.includeEstimates) qs.set('include_estimates', 'true');
      if (btn) btn.disabled = true;
      try {
        // window.open cannot send the Authorization header — fetch + blob instead
        const res = await fetch(`${API_BASE}/performance/export?${qs.toString()}`, {
          headers: { Authorization: `Bearer ${getJwt()}` },
        });
        if (!res.ok) throw new Error(await res.text());
        const truncated = res.headers.get('X-Truncated') === 'true';
        const totalRows = res.headers.get('X-Total-Rows');
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `vizniago_performance_${perfState.dateFrom || 'all'}_${perfState.dateTo || 'all'}.csv`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 5000);
        if (truncated) {
          showPerfBanner('notice', t('perf.exportTruncated').replace('{total}', totalRows || '?'));
        } else {
          clearPerfBanner();
        }
      } catch (err) {
        console.error('[Performance] Export failed:', err);
        showPerfBanner('error', t('perf.exportError'));
      } finally {
        if (btn) btn.disabled = false;
      }
    });

    document.getElementById('perf-include-estimates').addEventListener('change', (e) => {
      perfState.includeEstimates = e.target.checked;
      perfState.tradeOffset = 0;
      guarded(Promise.all([loadSummary(), loadTrades(), loadBreakdown()]));
    });

    document.querySelectorAll('.perf-breakdown-tab').forEach(btn => {
      btn.addEventListener('click', () => {
        perfState.breakdownBy = btn.dataset.by;
        document.querySelectorAll('.perf-breakdown-tab').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        guarded(loadBreakdown());
      });
    });

    document.getElementById('perf-prev').addEventListener('click', async () => {
      const prevOffset = perfState.tradeOffset;
      perfState.tradeOffset = Math.max(0, prevOffset - perfState.tradeLimit);
      const ok = await guarded(loadTrades());
      if (!ok) perfState.tradeOffset = prevOffset; // revert so buttons stay truthful
    });
    document.getElementById('perf-next').addEventListener('click', async () => {
      const prevOffset = perfState.tradeOffset;
      perfState.tradeOffset += perfState.tradeLimit;
      const ok = await guarded(loadTrades());
      if (!ok) perfState.tradeOffset = prevOffset;
    });
  }

  // ── Public API ────────────────────────────────────────────────────────────

  window.initPerformanceDashboard = async function () {
    try {
      // Lightweight probe: if summary 404s, feature is disabled.
      await perfFetch('/performance/summary');
      perfState.enabled = true;
    } catch (e) {
      if (e.message === 'feature_disabled') {
        console.log('[Performance] Feature disabled on server');
        return;
      }
      console.error('[Performance] Init error:', e);
      return;
    }

    // Show tab
    const tab = document.getElementById('tab-performance');
    if (tab) tab.classList.remove('hidden');

    setDateRangeDefaults();
    buildPerformanceSection();
    await loadAllPerformanceData();
  };

  window.refreshPerformanceTab = function () {
    if (!perfState.enabled) return;
    loadAllPerformanceData();
  };
})();
