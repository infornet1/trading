'use strict';

// ── Config ─────────────────────────────────────────────────────────────────
const API_BASE      = '/trading/lp-hedge/api';
const NEAR_EDGE_PCT = 0.05;   // 5% from boundary = yellow warning

const REFRESH_OPTIONS = [
  { label: 'Off', value: 0        },
  { label: '30s', value: 30_000   },
  { label: '1m',  value: 60_000   },
  { label: '3m',  value: 180_000  },
  { label: '5m',  value: 300_000  },
];

// ── State ──────────────────────────────────────────────────────────────────
const state = {
  jwt:             localStorage.getItem('vf_jwt') || null,
  provider:        null,
  address:         null,
  ethPrice:        null,
  refreshTimer:    null,
  refreshInterval: parseInt(localStorage.getItem('vf_admin_refresh') || '30000', 10),
  expanded:        new Set(),   // config_ids with open detail drawers
  hlLoading:       new Set(),   // config_ids currently fetching HL data
  historicalOpen:  true,        // Configured (stopped) section open by default
};

// ── Boot ───────────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  if (state.jwt && jwtIsAdmin(state.jwt) && !jwtExpired(state.jwt)) {
    showContent();
    doRefresh();
    applyRefreshInterval();
  } else {
    const reason = state.jwt
      ? (jwtExpired(state.jwt) ? 'expired' : 'not-admin')
      : 'none';
    state.jwt = null;
    localStorage.removeItem('vf_jwt');
    showGate(reason);
  }

  document.getElementById('btn-signin').addEventListener('click', signIn);
});

// ── Auth helpers ───────────────────────────────────────────────────────────
function jwtPayload(token) {
  try { return JSON.parse(atob(token.split('.')[1])); } catch { return {}; }
}
function jwtIsAdmin(token)  { return jwtPayload(token).is_admin === true; }
function jwtExpired(token)  { return (jwtPayload(token).exp || 0) * 1000 < Date.now(); }

// reason: 'none' | 'expired' | 'not-admin' | 'api-expired' | 'api-forbidden'
function showGate(reason = 'none') {
  const subtitles = {
    'expired':      '⏰ Tu sesión expiró. Vuelve a conectar tu wallet para continuar.',
    'not-admin':    '⛔ Esta wallet no tiene permisos de administrador.',
    'api-expired':  '⏰ Sesión expirada mientras usabas el panel. Reconecta para continuar.',
    'api-forbidden':'⛔ Acceso denegado — la wallet no tiene permisos de administrador.',
    'none':         'Solo wallets administradoras pueden acceder a este panel.',
  };
  const sub = document.getElementById('gate-sub');
  if (sub) sub.textContent = subtitles[reason] ?? subtitles['none'];
  document.getElementById('signin-gate').classList.remove('hidden');
  document.getElementById('admin-content').classList.add('hidden');
}
function showContent() {
  document.getElementById('signin-gate').classList.add('hidden');
  document.getElementById('admin-content').classList.remove('hidden');
  const p = jwtPayload(state.jwt);
  document.getElementById('admin-wallet').textContent = shortAddr(p.sub || '');
  if (jwtIsAdmin(state.jwt)) {
    document.getElementById('btn-nuclear').classList.remove('hidden');
    document.getElementById('btn-maintenance').classList.remove('hidden');
    syncMaintenanceBtn();
  }
  renderRefreshControl();
}

// ── Sign in ────────────────────────────────────────────────────────────────
async function signIn() {
  const errEl = document.getElementById('signin-error');
  errEl.classList.add('hidden');
  try {
    if (!window.ethereum) throw new Error('No se detectó wallet. Instala Rabby o MetaMask.');
    state.provider = new ethers.BrowserProvider(window.ethereum);
    await state.provider.send('eth_requestAccounts', []);
    const signer  = await state.provider.getSigner();
    state.address = (await signer.getAddress()).toLowerCase();

    const nonceRes = await fetch(`${API_BASE}/auth/nonce?address=${state.address}`);
    if (!nonceRes.ok) throw new Error('Error al obtener nonce.');
    const { nonce } = await nonceRes.json();

    const sig = await signer.signMessage(`Sign in to VIZNAGO FURY\nNonce: ${nonce}`);

    const verRes = await fetch(`${API_BASE}/auth/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address: state.address, signature: sig }),
    });
    if (!verRes.ok) throw new Error('Firma rechazada por el servidor.');
    const { access_token } = await verRes.json();

    if (!jwtIsAdmin(access_token)) {
      throw new Error('Esta wallet no tiene permisos de administrador.');
    }

    state.jwt = access_token;
    localStorage.setItem('vf_jwt', access_token);
    showContent();
    doRefresh();
    applyRefreshInterval();
  } catch (e) {
    errEl.textContent = e.message || 'Error desconocido.';
    errEl.classList.remove('hidden');
  }
}

// ── API calls ──────────────────────────────────────────────────────────────
function _handleAuthError(status) {
  state.jwt = null;
  localStorage.removeItem('vf_jwt');
  showGate(status === 403 ? 'api-forbidden' : 'api-expired');
}

async function apiGet(path) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { Authorization: `Bearer ${state.jwt}` },
  });
  if (res.status === 401 || res.status === 403) {
    _handleAuthError(res.status);
    throw new Error('Session expired');
  }
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

async function apiPost(path, body) {
  const opts = {
    method:  'POST',
    headers: { Authorization: `Bearer ${state.jwt}`, 'Content-Type': 'application/json' },
  };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(`${API_BASE}${path}`, opts);
  if (res.status === 401 || res.status === 403) {
    _handleAuthError(res.status);
    throw new Error('Session expired');
  }
  if (!res.ok) throw new Error(`API ${res.status}`);
  if (res.status === 204) return null;
  return res.json();
}

// ── Price fetch (CoinGecko free) ───────────────────────────────────────────
async function fetchEthPrice() {
  try {
    const r = await fetch(API_BASE + '/prices');
    const d = await r.json();
    state.ethPrice = d?.ethereum?.usd || null;
  } catch { /* keep last known price */ }
}

// ── Refresh cycle ──────────────────────────────────────────────────────────
async function doRefresh() {
  setStatus('Actualizando...');
  try {
    await Promise.all([fetchEthPrice(), renderOverview()]);
    const now = new Date().toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    setStatus(state.refreshInterval > 0
      ? `Actualizado ${now} · Auto ${msToLabel(state.refreshInterval)}`
      : `Actualizado ${now}`);
  } catch (e) {
    setStatus(`Error: ${e.message}`);
  }
}

function setStatus(msg) {
  document.getElementById('refresh-status').textContent = msg;
}

// ── Auto-refresh control ───────────────────────────────────────────────────
function applyRefreshInterval() {
  clearInterval(state.refreshTimer);
  state.refreshTimer = null;
  if (state.refreshInterval > 0) {
    state.refreshTimer = setInterval(doRefresh, state.refreshInterval);
  }
}

function renderRefreshControl() {
  const el = document.getElementById('refresh-control');
  if (!el) return;
  el.classList.remove('hidden');
  const cur = state.refreshInterval;
  el.innerHTML = `
    <span class="refresh-label">Auto</span>
    <div class="refresh-opts">
      ${REFRESH_OPTIONS.map(o => `
        <button class="refresh-opt${o.value === cur ? ' refresh-opt--active' : ''}"
                onclick="setRefreshInterval(${o.value})">${o.label}</button>
      `).join('')}
    </div>`;
}

function setRefreshInterval(ms) {
  state.refreshInterval = ms;
  localStorage.setItem('vf_admin_refresh', String(ms));
  applyRefreshInterval();
  renderRefreshControl();
  if (ms === 0) {
    const now = new Date().toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    setStatus(`Actualizado ${now} · Auto-refresh desactivado`);
  }
}

function msToLabel(ms) {
  return REFRESH_OPTIONS.find(o => o.value === ms)?.label || `${ms/1000}s`;
}

// ── Overview render ────────────────────────────────────────────────────────
async function renderOverview() {
  const data = await apiGet('/admin/overview');
  state.lastPools = data.pools;
  renderStats(data.stats);
  renderPools(data.pools);
  // Re-load HL detail for any currently expanded cards
  for (const configId of state.expanded) {
    loadHlDetail(configId);
  }
}

function renderStats(s) {
  document.getElementById('stat-registered').textContent = s.total_registered;
  document.getElementById('stat-wallets').textContent    = s.wallets_with_pools;
  document.getElementById('stat-inactive').textContent   = s.inactive_wallets;
  document.getElementById('stat-new24h').textContent     = s.new_wallets_24h > 0
    ? '+' + s.new_wallets_24h : s.new_wallets_24h;
  document.getElementById('stat-pools').textContent      = s.total_pools;
  document.getElementById('stat-bots').textContent       = s.active_bots;
  document.getElementById('stat-shorts').textContent     = s.active_shorts;
  document.getElementById('stat-volume').textContent     = '$' + fmtNum(s.total_volume_usd);

  // Whale bots stat (graceful — element may not exist in older HTML)
  const whaleEl = document.getElementById('stat-whale-bots');
  if (whaleEl) {
    const whaleBots = s.whale_bots ?? '—';
    whaleEl.textContent = whaleBots;
  }
}

function renderPools(pools) {
  const grid = document.getElementById('pools-grid');
  if (!pools.length) {
    grid.innerHTML = '<div class="loading-msg">No hay pools registrados aún.</div>';
    return;
  }

  const price   = state.ethPrice;
  const running = pools.filter(p => p.running);
  const stopped = pools.filter(p => !p.running);

  let html = '';

  // ── Running section ─────────────────────────────────────────────────
  html += `<div class="pools-section">
  <div class="pools-section-header">
    <span>Running <span class="pools-count">${running.length}</span></span>
  </div>
  <div class="pools-cards-grid">
    ${running.length
      ? running.map(p => poolCard(p, price)).join('')
      : '<div class="loading-msg">Sin bots corriendo ahora.</div>'}
  </div>
</div>`;

  // ── Configured / stopped section (always visible) ───────────────────
  if (stopped.length) {
    html += `<div class="pools-section">
  <div class="pools-section-header pools-section-header--muted" onclick="toggleHistorical()">
    <span>Configured <span class="pools-count">${stopped.length}</span></span>
    <button class="btn-outline-sm" style="pointer-events:none">${state.historicalOpen ? '▲ Hide' : '▼ Show'}</button>
  </div>
  <div class="pools-cards-grid ${state.historicalOpen ? '' : 'hidden'}" id="historical-cards">
    ${stopped.map(p => poolCard(p, price, true)).join('')}
  </div>
</div>`;
  }

  grid.innerHTML = html;
}

function toggleHistorical() {
  state.historicalOpen = !state.historicalOpen;
  if (state.lastPools) renderPools(state.lastPools);
}

// ── Health logic ───────────────────────────────────────────────────────────
function poolHealth(p, currentPrice) {
  const lastType = p.last_event?.type;

  if (p.active && !p.running) return { level: 'red', reason: 'Bot caído (proceso detenido)' };

  if (lastType === 'hedge_opened' && p.running) {
    return { level: 'yellow', reason: 'Short activo — cobertura en curso' };
  }

  if (currentPrice && (p.pair.startsWith('ETH') || p.pair.startsWith('WETH'))) {
    const pct_to_lower = (currentPrice - p.lower_bound) / currentPrice;
    const pct_to_upper = (p.upper_bound - currentPrice) / currentPrice;

    if (currentPrice < p.lower_bound) {
      return lastType === 'hedge_opened'
        ? { level: 'yellow', reason: 'Fuera de rango (abajo) — short cubriendo' }
        : { level: 'red',    reason: 'Fuera de rango (abajo) — SIN cobertura' };
    }
    if (currentPrice > p.upper_bound) {
      return { level: 'yellow', reason: 'Fuera de rango (arriba) — en espera' };
    }
    if (pct_to_lower < NEAR_EDGE_PCT) {
      return { level: 'yellow', reason: `Cerca del límite inferior (${(pct_to_lower*100).toFixed(1)}%)` };
    }
    if (pct_to_upper < NEAR_EDGE_PCT) {
      return { level: 'yellow', reason: `Cerca del límite superior (${(pct_to_upper*100).toFixed(1)}%)` };
    }
  }

  if (!p.running && !p.active) {
    return { level: 'yellow', reason: 'Bot detenido manualmente' };
  }

  return { level: 'green', reason: 'En rango — fees activos' };
}

// ── Whale card HTML ────────────────────────────────────────────────────────
function whaleCard(p, isHistorical = false) {
  const isExpanded  = state.expanded.has(p.config_id);
  const lastEvt     = p.last_event;
  const lastEvtStr  = lastEvt ? evtLabel(lastEvt.type) : 'Sin eventos';
  const lastTimeStr = lastEvt?.ts ? relTime(lastEvt.ts) : '';

  const botStatus = p.running
    ? `<span class="badge badge--green">RUNNING</span>`
    : p.active
      ? `<span class="badge badge--red">CAÍDO</span>`
      : `<span class="badge badge--muted">DETENIDO</span>`;

  let heartbeatBadge = '';
  if (p.running && p.last_heartbeat) {
    const ageSec = Math.floor((Date.now() - new Date(
      p.last_heartbeat.endsWith('Z') ? p.last_heartbeat : p.last_heartbeat + 'Z'
    ).getTime()) / 1000);
    const cls   = ageSec < 120 ? 'green' : ageSec < 300 ? 'yellow' : 'red';
    const label = ageSec < 60 ? `${ageSec}s` : `${Math.floor(ageSec/60)}min`;
    heartbeatBadge = `<span class="badge badge--${cls}" title="Último output">⏱ ${label}</span>`;
  }

  const recentEventsHtml = (p.recent_events || []).slice(0, 3).map(e => `
    <div class="mini-evt mini-evt--muted">
      <span>${evtLabel(e.type)}</span>
      <span class="muted">${e.ts ? relTime(e.ts) : ''}</span>
    </div>`).join('');

  const wsMode    = p.whale_use_websocket;
  const modeTag   = wsMode ? 'WebSocket' : 'Poll';
  const topN      = p.whale_top_n || 50;
  const minNot    = p.whale_min_notional ? '$' + fmtNum(p.whale_min_notional) : '—';
  const assets    = p.whale_watch_assets || 'All';
  const pollInt   = p.whale_poll_interval || 30;
  const isPaper   = p.paper_trade;

  return `
<div class="pool-card pool-card--muted${isHistorical ? ' pool-card--historical' : ''}" id="card-${p.config_id}">
  <div class="pool-card-header">
    <div class="health-dot health-dot--${p.running ? 'green' : 'muted'}"></div>
    <span class="pool-pair">🐋 WHALE</span>
    <span class="pool-nft">ID #${p.config_id}</span>
  </div>

  <div class="pool-row">
    <span class="pool-label">Modo</span>
    <span class="pool-val">${modeTag} · ${pollInt}s poll</span>
  </div>
  <div class="pool-row">
    <span class="pool-label">Top-N / Min. notional</span>
    <span class="pool-val">Top ${topN} · ${minNot}</span>
  </div>
  <div class="pool-row">
    <span class="pool-label">Assets vigilados</span>
    <span class="pool-val">${assets}</span>
  </div>
  <div class="pool-row">
    <span class="pool-label">Último evento</span>
    <span class="pool-val">${lastEvtStr} <span style="color:var(--muted)">${lastTimeStr}</span></span>
  </div>

  ${recentEventsHtml ? `<div class="mini-events">${recentEventsHtml}</div>` : ''}

  <div class="pool-footer">
    <div style="display:flex;gap:.4rem;align-items:center;flex-wrap:wrap">
      ${botStatus}${heartbeatBadge}
      <span class="badge badge--muted">🐋 WHALE</span>
      ${isPaper ? `<span class="badge badge--yellow">PAPER</span>` : ''}
      <span class="badge badge--muted">${p.user_plan.toUpperCase()}</span>
    </div>
  </div>
  <div class="pool-wallet">${p.user_address}</div>

  <button class="detail-toggle" onclick="toggleDetail(${p.config_id})">
    ${isExpanded ? '▲ Ocultar historial' : '▼ Ver historial de señales'}
  </button>

  <div class="detail-drawer ${isExpanded ? '' : 'hidden'}" id="drawer-${p.config_id}">
    <div class="detail-loading" id="hl-loading-${p.config_id}">Cargando señales…</div>
    <div class="detail-content hidden" id="hl-content-${p.config_id}"></div>
  </div>
</div>`;
}

// ── Pool card HTML ─────────────────────────────────────────────────────────
function poolCard(p, ethPrice, isHistorical = false) {
  if (p.mode === 'whale') return whaleCard(p, isHistorical);

  const h = poolHealth(p, ethPrice);
  const isExpanded = state.expanded.has(p.config_id);

  let barPct = 50, cursorPct = 50, priceStr = '—';
  if (ethPrice && (p.pair.startsWith('ETH') || p.pair.startsWith('WETH'))) {
    const range  = p.upper_bound - p.lower_bound;
    cursorPct = Math.max(0, Math.min(100,
      ((ethPrice - p.lower_bound) / range) * 100
    ));
    barPct   = cursorPct;
    priceStr = '$' + fmtNum(ethPrice);
  }

  const lastEvt     = p.last_event;
  const lastEvtStr  = lastEvt
    ? `${evtLabel(lastEvt.type)}${lastEvt.price ? ' @ $'+fmtNum(lastEvt.price) : ''}`
    : 'Sin eventos';
  const lastTimeStr = lastEvt?.ts ? relTime(lastEvt.ts) : '';

  const pnlStr = (lastEvt?.pnl != null)
    ? `${lastEvt.pnl >= 0 ? '+' : ''}${lastEvt.pnl.toFixed(2)}%`
    : null;

  const botStatus = p.running
    ? `<span class="badge badge--green">RUNNING</span>`
    : p.active
      ? `<span class="badge badge--red">CAÍDO</span>`
      : `<span class="badge badge--muted">DETENIDO</span>`;

  let heartbeatBadge = '';
  if (p.running) {
    if (p.last_heartbeat) {
      const ageSec = Math.floor((Date.now() - new Date(p.last_heartbeat).getTime()) / 1000);
      const cls    = ageSec < 120 ? 'green' : ageSec < 300 ? 'yellow' : 'red';
      const label  = ageSec < 60 ? `${ageSec}s` : `${Math.floor(ageSec / 60)}min`;
      heartbeatBadge = `<span class="badge badge--${cls}" title="Último output del bot">⏱ ${label}</span>`;
    } else {
      heartbeatBadge = `<span class="badge badge--muted" title="Sin heartbeat registrado">⏱ —</span>`;
    }
  }

  const shortBadge = lastEvt?.type === 'hedge_opened' && p.running
    ? `<span class="badge badge--yellow">SHORT ACTIVO</span>` : '';

  // Recent events mini-preview (last 3)
  const recentEventsHtml = (p.recent_events || []).slice(0, 3).map(e => `
    <div class="mini-evt mini-evt--${evtColor(e.type)}">
      <span>${evtLabel(e.type)}</span>
      ${e.price ? `<span class="mono">$${fmtNum(e.price)}</span>` : ''}
      ${e.pnl   != null ? `<span class="mono pnl-${e.pnl >= 0 ? 'pos' : 'neg'}">${e.pnl >= 0 ? '+' : ''}${e.pnl.toFixed(2)}%</span>` : ''}
      <span class="muted">${e.ts ? relTime(e.ts) : ''}</span>
    </div>`).join('');

  return `
<div class="pool-card pool-card--${h.level}${isHistorical ? ' pool-card--historical' : ''}" id="card-${p.config_id}">
  <div class="pool-card-header">
    <div class="health-dot health-dot--${h.level}"></div>
    <span class="pool-pair">${p.pair}</span>
    <span class="pool-nft">NFT #${p.nft_token_id}</span>
  </div>

  <div class="pool-row">
    <span class="pool-label">Rango</span>
    <span class="pool-val">$${fmtNum(p.lower_bound)} — $${fmtNum(p.upper_bound)}</span>
  </div>
  <div class="pool-row">
    <span class="pool-label">Precio actual</span>
    <span class="pool-val pool-val--${h.level}">${priceStr}</span>
  </div>
  ${(() => {
    const poolVal = estimatePoolValue(p, ethPrice);
    if (!poolVal) return '';
    const hedgeNotional = poolVal * (p.hedge_ratio / 100);
    return `<div class="pool-row">
      <span class="pool-label">Pool Value ~</span>
      <span class="pool-val" style="font-weight:600;color:#e2e8f0">$${fmtNum(poolVal)}
        <span style="font-size:.68rem;color:var(--muted);margin-left:4px">hedge $${fmtNum(hedgeNotional)}</span>
      </span>
    </div>`;
  })()}

  <div class="range-bar-wrap">
    <div class="range-bar-bg">
      <div class="range-bar-fill" style="width:${barPct}%"></div>
      <div class="range-bar-cursor" style="left:${cursorPct}%"></div>
    </div>
  </div>

  <div class="pool-row">
    <span class="pool-label">Salud</span>
    <span class="pool-val pool-val--${h.level}">${h.reason}</span>
  </div>
  <div class="pool-row">
    <span class="pool-label">Último evento</span>
    <span class="pool-val">${lastEvtStr} <span style="color:var(--muted)">${lastTimeStr}</span></span>
  </div>
  ${pnlStr ? `
  <div class="pool-row">
    <span class="pool-label">PnL estimado</span>
    <span class="pool-val pool-val--${parseFloat(pnlStr) >= 0 ? 'green' : 'red'}">${pnlStr}</span>
  </div>` : ''}
  <div class="pool-row">
    <span class="pool-label">Volumen generado</span>
    <span class="pool-val pool-val--green">$${fmtNum(p.volume_usd)}</span>
  </div>

  ${recentEventsHtml ? `<div class="mini-events">${recentEventsHtml}</div>` : ''}

  <div class="pool-row pool-row--params">
    <span class="pool-label">Params</span>
    <span class="pool-val" style="font-size:.68rem;display:flex;gap:.5rem;flex-wrap:wrap">
      <span title="Target leverage">${p.leverage ?? 10}x</span>
      <span title="Stop Loss">SL ${p.sl_pct ?? 0.1}%</span>
      ${p.tp_pct ? `<span title="Take Profit">TP ${p.tp_pct}%</span>` : ''}
      <span title="Trailing Stop" style="color:${p.trailing_stop ? 'var(--green)' : 'var(--muted)'}">Trail ${p.trailing_stop ? '✓' : '✗'}</span>
      <span title="Auto-rearm" style="color:${p.auto_rearm ? 'var(--green)' : 'var(--muted)'}">Rearm ${p.auto_rearm ? '✓' : '✗'}</span>
    </span>
  </div>

  <div class="pool-footer">
    <div style="display:flex;gap:.4rem;align-items:center;flex-wrap:wrap">
      ${botStatus}${heartbeatBadge}${shortBadge}
      <span class="badge badge--muted">${
        p.mode === 'aragan' ? 'Defensor Bajista' :
        p.mode === 'avaro'  ? 'Defensor Alcista' :
        p.mode === 'fury'   ? '⚡ FURY RSI' :
        p.mode === 'whale'  ? '🐋 WHALE' :
        p.mode.toUpperCase()
      }</span>
      <span class="badge badge--muted">${chainName(p.chain_id)}</span>
    </div>
    <span style="color:var(--muted);font-size:.7rem">${p.user_plan.toUpperCase()}</span>
  </div>
  <div class="pool-wallet">${p.user_address}</div>

  <button class="detail-toggle" onclick="toggleDetail(${p.config_id})">
    ${isExpanded ? '▲ Ocultar detalle' : '▼ Ver detalle HL + historial'}
  </button>

  <div class="detail-drawer ${isExpanded ? '' : 'hidden'}" id="drawer-${p.config_id}">
    <div class="detail-loading" id="hl-loading-${p.config_id}">Cargando datos HL...</div>
    <div class="detail-content hidden" id="hl-content-${p.config_id}"></div>
  </div>
</div>`;
}

// ── Detail drawer toggle ───────────────────────────────────────────────────
function toggleDetail(configId) {
  const drawer = document.getElementById(`drawer-${configId}`);
  const btn    = drawer?.previousElementSibling;
  if (!drawer) return;

  if (state.expanded.has(configId)) {
    state.expanded.delete(configId);
    drawer.classList.add('hidden');
    if (btn) btn.textContent = '▼ Ver detalle HL + historial';
  } else {
    state.expanded.add(configId);
    drawer.classList.remove('hidden');
    if (btn) btn.textContent = '▲ Ocultar detalle';
    loadHlDetail(configId);
  }
}

async function loadHlDetail(configId) {
  if (state.hlLoading.has(configId)) return;
  state.hlLoading.add(configId);

  const loadEl    = document.getElementById(`hl-loading-${configId}`);
  const contentEl = document.getElementById(`hl-content-${configId}`);
  if (!loadEl || !contentEl) { state.hlLoading.delete(configId); return; }

  loadEl.classList.remove('hidden');
  contentEl.classList.add('hidden');

  try {
    const d = await apiGet(`/admin/pool/${configId}/hl`);
    contentEl.innerHTML = renderHlDetail(d, state.ethPrice);
    loadEl.classList.add('hidden');
    contentEl.classList.remove('hidden');
  } catch (e) {
    loadEl.textContent = `Error: ${e.message}`;
  } finally {
    state.hlLoading.delete(configId);
  }
}

// ── HL detail content ──────────────────────────────────────────────────────
function renderHlDetail(d, ethPrice = null) {
  const sections = [];

  // ── Active HL Position ──
  if (d.hl_error) {
    sections.push(`<div class="detail-section">
      <div class="detail-section-title">Posición Hyperliquid</div>
      <div class="detail-error">⚠ ${d.hl_error}</div>
    </div>`);
  } else if (d.hl_position) {
    const pos = d.hl_position;
    const pnlClass = pos.unrealized_pnl >= 0 ? 'green' : 'red';
    const roePct   = (pos.return_on_equity * 100).toFixed(2);

    // Trail status: events are desc order, find if breakeven comes after last hedge_opened
    const events      = d.events || [];
    const openIdx     = events.findIndex(e => e.type === 'hedge_opened');
    const trailActive = openIdx > 0 && events.slice(0, openIdx).some(e => e.type === 'breakeven');
    const trailBadge  = `<span class="badge badge--${trailActive ? 'green' : 'muted'}">${trailActive ? '🛡️ Trail ACTIVO' : 'Trail inactivo'}</span>`;

    // SL distance from native order trigger price
    const slPx = d.hl_sl_order?.trigger_px || null;
    let slDistHtml = '';
    if (slPx && ethPrice) {
      const distPct = ((slPx - ethPrice) / ethPrice * 100).toFixed(2);
      const distUsd = (slPx - ethPrice).toFixed(2);
      const distClass = Math.abs(distPct) < 1 ? 'red' : Math.abs(distPct) < 2 ? 'yellow' : 'green';
      slDistHtml = `
    <div class="hl-pos-item">
      <span class="hl-pos-label">Distancia al SL</span>
      <span class="hl-pos-val mono pool-val--${distClass}">+${distPct}% ($${distUsd})</span>
    </div>`;
    }

    sections.push(`
<div class="detail-section">
  <div class="detail-section-title">Posición Activa — Hyperliquid ${trailBadge}</div>
  <div class="hl-pos-grid">
    <div class="hl-pos-item">
      <span class="hl-pos-label">Par</span>
      <span class="hl-pos-val">${pos.coin}-PERP</span>
    </div>
    <div class="hl-pos-item">
      <span class="hl-pos-label">Lado</span>
      <span class="hl-pos-val hl-pos-val--${pos.side === 'SHORT' ? 'red' : 'green'}">${pos.side}</span>
    </div>
    <div class="hl-pos-item">
      <span class="hl-pos-label">Tamaño</span>
      <span class="hl-pos-val mono">${Math.abs(pos.size).toFixed(4)} ${pos.coin}</span>
    </div>
    <div class="hl-pos-item">
      <span class="hl-pos-label">Precio entrada</span>
      <span class="hl-pos-val mono">$${fmtNum(pos.entry_price)}</span>
    </div>
    <div class="hl-pos-item">
      <span class="hl-pos-label">PnL no realizado</span>
      <span class="hl-pos-val mono pool-val--${pnlClass}">${pos.unrealized_pnl >= 0 ? '+' : ''}$${fmtNum(pos.unrealized_pnl)} (${roePct}%)</span>
    </div>
    <div class="hl-pos-item">
      <span class="hl-pos-label">Apalancamiento</span>
      <span class="hl-pos-val mono">${pos.leverage}x ${pos.leverage_type}</span>
    </div>
    ${pos.liquidation_px ? `
    <div class="hl-pos-item">
      <span class="hl-pos-label">Precio liquidación</span>
      <span class="hl-pos-val mono pool-val--red">$${fmtNum(pos.liquidation_px)}</span>
    </div>` : ''}
    <div class="hl-pos-item">
      <span class="hl-pos-label">Margen usado</span>
      <span class="hl-pos-val mono">$${fmtNum(pos.margin_used)}</span>
    </div>
    <div class="hl-pos-item">
      <span class="hl-pos-label">Valor posición</span>
      <span class="hl-pos-val mono">$${fmtNum(pos.position_value)}</span>
    </div>
    ${slDistHtml}
  </div>
  ${d.hl_margin?.account_value ? `
  <div class="hl-margin-bar">
    <span>Cuenta: <b>$${fmtNum(d.hl_margin.account_value)}</b></span>
    <span>Margen total: <b>$${fmtNum(d.hl_margin.total_margin_used)}</b></span>
    <span>Exposición: <b>$${fmtNum(d.hl_margin.total_ntl_pos)}</b></span>
  </div>` : ''}
</div>`);

    // ── Native SL order status ──
    const sl = d.hl_sl_order;
    if (sl) {
      sections.push(`
<div class="detail-section">
  <div class="detail-section-title">Stop-Loss Nativo — Hyperliquid</div>
  <div class="hl-sl-row">
    <span class="badge badge--green">✓ PROTEGIDO</span>
    <span class="mono">Trigger: $${fmtNum(sl.trigger_px)}</span>
    <span class="muted">·</span>
    <span class="mono">${Math.abs(sl.size).toFixed(4)} ETH</span>
    <span class="muted">·</span>
    <span class="muted">condición: ${sl.trigger_cond || '—'}</span>
    <span class="muted">·</span>
    <span class="muted">oid: ${sl.oid}</span>
  </div>
</div>`);
    } else {
      sections.push(`
<div class="detail-section">
  <div class="detail-section-title">Stop-Loss Nativo — Hyperliquid</div>
  <div class="hl-sl-row">
    <span class="badge badge--red">⚠ SIN SL NATIVO</span>
    <span class="muted">Solo protección por software (polling cada 30s). Implementar Opción A para cobertura nativa.</span>
  </div>
</div>`);
    }
  } else if (!d.hl_error) {
    sections.push(`<div class="detail-section">
      <div class="detail-section-title">Posición Hyperliquid</div>
      <div class="detail-empty">Sin posición activa en HL para ${d.pair?.split('/')[0] || 'ETH'}-PERP</div>
      ${d.hl_margin?.account_value ? `
      <div class="hl-margin-bar">
        <span>Cuenta: <b>$${fmtNum(d.hl_margin.account_value)}</b></span>
        <span>Margen libre: <b>$${fmtNum(d.hl_margin.account_value - d.hl_margin.total_margin_used)}</b></span>
      </div>` : ''}
    </div>`);
  }

  // ── Event History ──
  if (d.events?.length) {
    const rows = d.events.map(e => {
      const det = e.details || {};
      const detStr = [
        det.trigger   ? `trigger: ${det.trigger}` : '',
        det.size      ? `size: ${det.size} ETH` : '',
        det.notional  ? `notional: $${fmtNum(det.notional)}` : '',
        det.leverage  ? `lev: ${det.leverage}x` : '',
        det.sl_price  ? `SL: $${fmtNum(det.sl_price)}` : '',
        det.reason    ? `${det.reason}` : '',
        det.error     ? `err: ${det.error}` : '',
      ].filter(Boolean).join(' · ');

      return `<tr>
        <td class="mono muted">${e.ts ? relTime(e.ts) : '—'}</td>
        <td><span class="badge badge--${evtColor(e.type)}">${evtLabel(e.type)}</span></td>
        <td class="mono">${e.price ? '$'+fmtNum(e.price) : '—'}</td>
        <td class="mono ${e.pnl != null ? (e.pnl >= 0 ? 'pnl-pos' : 'pnl-neg') : ''}">${e.pnl != null ? (e.pnl >= 0 ? '+' : '')+e.pnl.toFixed(2)+'%' : '—'}</td>
        <td class="muted detail-notes">${detStr}</td>
      </tr>`;
    }).join('');

    sections.push(`
<div class="detail-section">
  <div class="detail-section-title">Historial de Eventos (últimos ${d.events.length})</div>
  <div class="detail-table-wrap">
    <table class="detail-table">
      <thead><tr><th>Tiempo</th><th>Evento</th><th>Precio</th><th>PnL</th><th>Detalles</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  </div>
</div>`);
  }

  // ── HL Fills ──
  if (d.hl_fills?.length) {
    const fillRows = d.hl_fills.map(f => `<tr>
      <td class="mono muted">${f.ts ? relTime(new Date(f.ts).toISOString()) : '—'}</td>
      <td>${f.coin}-PERP</td>
      <td><span class="badge badge--${f.side.startsWith('SELL') ? 'red' : 'green'}">${f.side}</span></td>
      <td class="mono">$${fmtNum(f.price)}</td>
      <td class="mono">${Math.abs(f.size).toFixed(4)}</td>
      <td class="mono muted">$${fmtNum(f.fee)}</td>
    </tr>`).join('');

    sections.push(`
<div class="detail-section">
  <div class="detail-section-title">Fills Recientes — Hyperliquid (últimos ${d.hl_fills.length})</div>
  <div class="detail-table-wrap">
    <table class="detail-table">
      <thead><tr><th>Tiempo</th><th>Par</th><th>Lado</th><th>Precio</th><th>Tamaño</th><th>Fee</th></tr></thead>
      <tbody>${fillRows}</tbody>
    </table>
  </div>
</div>`);
  } else if (!d.hl_error) {
    sections.push(`<div class="detail-section">
      <div class="detail-section-title">Fills Recientes — Hyperliquid</div>
      <div class="detail-empty">Sin fills recientes en esta wallet.</div>
    </div>`);
  }

  return sections.join('');
}

// ── Users registry ────────────────────────────────────────────────────────
let _usersTableOpen = false;

async function toggleUsersTable() {
  const wrap    = document.getElementById('users-table-wrap');
  const label   = document.getElementById('users-toggle-label');
  _usersTableOpen = !_usersTableOpen;
  if (_usersTableOpen) {
    wrap.classList.remove('hidden');
    label.textContent = '▲ Ocultar';
    await loadUsersTable();
  } else {
    wrap.classList.add('hidden');
    label.textContent = '▼ Ver todas';
  }
}

async function loadUsersTable() {
  const loadEl   = document.getElementById('users-loading');
  const contentEl = document.getElementById('users-table-content');
  loadEl.classList.remove('hidden');
  contentEl.innerHTML = '';
  try {
    const d = await apiGet('/admin/users');
    loadEl.classList.add('hidden');
    contentEl.innerHTML = renderUsersTable(d.users);
  } catch (e) {
    loadEl.textContent = `Error: ${e.message}`;
  }
}

function renderUsersTable(users) {
  if (!users.length) return '<div class="loading-msg">Sin usuarios registrados.</div>';

  const funnelLabel = {
    bot_running:    { text: 'Bot corriendo',   cls: 'green'  },
    bot_configured: { text: 'Bot configurado', cls: 'yellow' },
    pool_added:     { text: 'Pool añadido',    cls: 'muted'  },
    signed_up:      { text: 'Solo registrado', cls: 'muted'  },
  };

  const rows = users.map(u => {
    const f = funnelLabel[u.funnel] || { text: u.funnel, cls: 'muted' };
    const inactiveWarn = u.days_inactive != null && u.days_inactive > 7
      ? ' users-row--cold' : '';
    return `<tr class="${inactiveWarn}">
      <td class="mono users-addr" title="${u.address}">${shortAddr(u.address)}</td>
      <td><span class="badge badge--${planColor(u.plan)}">${u.plan.toUpperCase()}</span></td>
      <td><span class="badge badge--${f.cls}">${f.text}</span></td>
      <td class="mono center">${u.pool_count}</td>
      <td class="mono center">${u.running_bots > 0
        ? `<span class="pool-val--green">${u.running_bots}</span>` : '—'}</td>
      <td class="mono muted">${u.created_at ? relTime(u.created_at) : '—'}</td>
      <td class="mono ${u.days_inactive != null && u.days_inactive > 7 ? 'pool-val--red' : 'muted'}">${
        u.last_seen ? relTime(u.last_seen) : '—'}</td>
    </tr>`;
  }).join('');

  return `
<div class="detail-table-wrap">
  <table class="detail-table users-table">
    <thead>
      <tr>
        <th>Wallet</th>
        <th>Plan</th>
        <th>Funnel</th>
        <th class="center">Pools</th>
        <th class="center">Bots</th>
        <th>Registrado</th>
        <th>Última actividad</th>
      </tr>
    </thead>
    <tbody>${rows}</tbody>
  </table>
</div>`;
}

function planColor(plan) {
  return { pro: 'yellow', starter: 'green', free: 'muted' }[plan] || 'muted';
}

// ── Nuclear stop ───────────────────────────────────────────────────────────
// ── Maintenance mode toggle ────────────────────────────────────────────────

let _maintenanceActive = false;

async function syncMaintenanceBtn() {
  try {
    const res  = await fetch(`${API_BASE}/status/maintenance`, { cache: 'no-store' });
    const data = await res.json();
    _maintenanceActive = data.maintenance;
    _updateMaintenanceBtn();
  } catch (_) {}
}

function _updateMaintenanceBtn() {
  const btn = document.getElementById('btn-maintenance');
  if (!btn) return;
  if (_maintenanceActive) {
    btn.textContent = '🔧 Maintenance: ON';
    btn.classList.add('btn-maintenance--active');
  } else {
    btn.textContent = '🔧 Maintenance: OFF';
    btn.classList.remove('btn-maintenance--active');
  }
}

async function toggleMaintenance() {
  const enable  = !_maintenanceActive;
  const message = enable
    ? prompt(
        'Maintenance message (shown to users):',
        'Protection bots temporarily suspended for a scheduled upgrade. Re-enable your protection after the update.'
      )
    : '';
  if (enable && message === null) return; // user cancelled prompt

  try {
    const d = await apiPost('/admin/maintenance', { active: enable, message: message || '' });
    _maintenanceActive = d.maintenance;
    _updateMaintenanceBtn();
    alert(enable
      ? `✅ Maintenance mode ON. Users will see the amber banner.`
      : `✅ Maintenance mode OFF. Banner hidden.`
    );
  } catch (e) {
    if (e.message !== 'Session expired') alert('Error: ' + e.message);
  }
}

async function nuclearStop() {
  if (!confirm('¿Detener TODOS los bots? Esta acción es irreversible hasta reinicio manual.')) return;
  try {
    const d = await apiPost('/admin/stop-all');
    alert(`✅ Detenidos: ${d.stopped_count} bots.`);
    doRefresh();
  } catch (e) {
    if (e.message !== 'Session expired') alert('Error: ' + e.message);
  }
}

// ── Helpers ────────────────────────────────────────────────────────────────
function shortAddr(addr) {
  if (!addr || addr.length < 10) return addr;
  return addr.slice(0, 6) + '…' + addr.slice(-4);
}

function fmtNum(n) {
  if (n == null || isNaN(n)) return '0';
  return Number(n).toLocaleString('en-US', { maximumFractionDigits: 2 });
}

function chainName(id) {
  return { 42161: 'Arbitrum', 1: 'Ethereum', 8453: 'Base' }[id] || `Chain ${id}`;
}

function evtLabel(type) {
  return {
    started:               '🚀 Iniciado',
    hedge_opened:          '🚨 Short abierto',
    breakeven:             '🛡️ Breakeven',
    tp_hit:                '🎯 TP alcanzado',
    sl_hit:                '🛑 SL activado',
    trailing_stop:         '🛑 Trailing stop',
    bounds_refreshed:      '🔄 Rango actualizado',
    reentry_guard_cleared: '🔓 Re-entry guard limpiado',
    stopped:               '⏹ Detenido',
    error:                 '❌ Error',
  }[type] || type;
}

function evtColor(type) {
  return {
    started:               'muted',
    hedge_opened:          'yellow',
    breakeven:             'green',
    tp_hit:                'green',
    sl_hit:                'red',
    trailing_stop:         'red',
    bounds_refreshed:      'muted',
    reentry_guard_cleared: 'muted',
    stopped:               'muted',
    error:                 'red',
  }[type] || 'muted';
}

function relTime(isoStr) {
  // Ensure UTC interpretation — DB timestamps have no 'Z' suffix so browsers
  // would otherwise parse them as local time, producing negative diffs.
  const normalized = isoStr && !isoStr.endsWith('Z') && !isoStr.includes('+')
    ? isoStr.replace(' ', 'T') + 'Z'
    : isoStr;
  const diff = Math.floor((Date.now() - new Date(normalized).getTime()) / 1000);
  if (diff < 0)     return 'ahora';
  if (diff < 60)    return `hace ${diff}s`;
  if (diff < 3600)  return `hace ${Math.floor(diff/60)}min`;
  if (diff < 86400) return `hace ${Math.floor(diff/3600)}h`;
  return `hace ${Math.floor(diff/86400)}d`;
}

// ── Pool value estimate (no blockchain — uses x_max_eth from started event) ─
// x_max_eth is the max ETH the position holds at lower_bound (from bot startup).
// We use this to estimate current value based on price position within range.
function estimatePoolValue(p, ethPrice) {
  const xMax = p.x_max_eth;
  if (!xMax || !ethPrice || !p.lower_bound || !p.upper_bound) return null;
  const lower = p.lower_bound;
  const upper = p.upper_bound;

  if (ethPrice >= upper) {
    // Out of range high — all USDC. Value ≈ x_max * upper_bound
    return xMax * upper;
  }
  if (ethPrice <= lower) {
    // Out of range low — all ETH. Value ≈ x_max * current_price
    return xMax * ethPrice;
  }
  // In range — approximate using geometric mean of ETH and USDC components
  const sqrtP = Math.sqrt(ethPrice);
  const sqrtA = Math.sqrt(lower);
  const sqrtB = Math.sqrt(upper);
  const ethAmt  = xMax * (sqrtB - sqrtP) / (sqrtP * sqrtB) * sqrtP * sqrtP; // simplified
  const usdcAmt = xMax * (sqrtP - sqrtA) * sqrtP;
  return ethAmt * ethPrice + usdcAmt;
}
