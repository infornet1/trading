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

  // Enter key on wallet search input
  const wsInput = document.getElementById('wallet-search-input');
  if (wsInput) wsInput.addEventListener('keydown', e => { if (e.key === 'Enter') searchWallet(); });
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

    const sig = await signer.signMessage(`Sign in to VIZNIAGO FURY\nNonce: ${nonce}`);

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

// ── M2-12: API health tracking ─────────────────────────────────────────────
let _apiFails = 0;
const _API_FAIL_THRESHOLD = 2;

function _showReconnectOverlay(show) {
  let overlay = document.getElementById('reconnect-overlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'reconnect-overlay';
    overlay.className = 'reconnect-overlay';
    overlay.innerHTML = `
      <div class="reconnect-box">
        <div class="reconnect-spinner"></div>
        <div class="reconnect-msg">Reconectando con el servidor…</div>
        <div class="reconnect-sub">El panel se actualizará automáticamente al restablecer la conexión.</div>
      </div>`;
    document.body.appendChild(overlay);
  }
  overlay.classList.toggle('hidden', !show);
  // Disable all interactive elements while disconnected
  document.querySelectorAll('button, input, select, textarea').forEach(el => {
    if (show) el.setAttribute('data-m12-disabled', '1'), el.disabled = true;
    else if (el.getAttribute('data-m12-disabled')) el.removeAttribute('data-m12-disabled'), el.disabled = false;
  });
}

// ── Refresh cycle ──────────────────────────────────────────────────────────
async function doRefresh() {
  setStatus('Actualizando...');
  try {
    await Promise.all([fetchEthPrice(), renderOverview()]);
    _apiFails = 0;
    _showReconnectOverlay(false);
    const now = new Date().toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    setStatus(state.refreshInterval > 0
      ? `Actualizado ${now} · Auto ${msToLabel(state.refreshInterval)}`
      : `Actualizado ${now}`);
  } catch (e) {
    _apiFails++;
    if (_apiFails >= _API_FAIL_THRESHOLD) _showReconnectOverlay(true);
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
  renderCaidoBanner(data.pools);
  renderPools(data.pools);
  // Re-load HL detail for any currently expanded cards
  for (const configId of state.expanded) {
    loadHlDetail(configId);
  }
}

// M2-32: CAÍDO bots banner — shown when any LP bot is active=true but running=false
function renderCaidoBanner(pools) {
  const LP_MODES = new Set(['aragan', 'avaro', 'fury']);
  const caidos = pools.filter(p => LP_MODES.has(p.mode) && p.active && !p.running);
  let banner = document.getElementById('caido-banner');
  if (!banner) {
    banner = document.createElement('div');
    banner.id = 'caido-banner';
    banner.className = 'caido-banner';
    const content = document.getElementById('admin-content');
    content.insertBefore(banner, content.firstChild);
  }
  if (caidos.length) {
    const nftList = caidos.map(p => `NFT #${p.nft_token_id}`).join(', ');
    banner.innerHTML = `⚠️ <strong>${caidos.length} bot${caidos.length > 1 ? 's' : ''} caído${caidos.length > 1 ? 's' : ''}</strong> — atención requerida: ${nftList}`;
    banner.classList.remove('hidden');
  } else {
    banner.classList.add('hidden');
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

  // M2-31: V2 bot count — derived from pools already in memory
  const v2El = document.getElementById('stat-v2-bots');
  if (v2El && state.lastPools) {
    const v2Count = state.lastPools.filter(p => {
      const started = (p.recent_events || []).find(e => e.event_type === 'started');
      return started?.details?.engine === 'v2';
    }).length;
    v2El.textContent = v2Count;
  }
}

function renderPools(pools) {
  const grid = document.getElementById('pools-grid');
  if (!pools.length) {
    grid.innerHTML = '<div class="loading-msg">No hay pools registrados aún.</div>';
    return;
  }

  const price = state.ethPrice;

  // Classify pools by bot family
  const LP_MODES    = new Set(['aragan', 'avaro', 'fury']);
  const lpPools     = pools.filter(p => LP_MODES.has(p.mode));
  const whalePools  = pools.filter(p => p.mode === 'whale');
  const otherPools  = pools.filter(p => !LP_MODES.has(p.mode) && p.mode !== 'whale');

  let html = '';

  // ── LP Hedge section ────────────────────────────────────────────────
  if (lpPools.length) {
    const lpRunning = lpPools.filter(p => p.running);
    const lpStopped = lpPools.filter(p => !p.running);
    html += renderBotSection({
      title:      '🛡️ LP Hedge',
      running:    lpRunning,
      stopped:    lpStopped,
      price,
      toggleKey:  'lp',
    });
  }

  // ── Whale Tracker section ───────────────────────────────────────────
  if (whalePools.length) {
    const whaleRunning = whalePools.filter(p => p.running);
    const whaleStopped = whalePools.filter(p => !p.running);
    const whaleAllRunning = whaleRunning.length === whalePools.length;
    const whaleToggleBtn = whaleAllRunning
      ? `<button class="btn-outline-sm btn-danger-sm" onclick="toggleWhaleBots(false)" title="Libera ~6.6% CPU y ~261 MB RAM">⏸ Pausar Whales</button>`
      : `<button class="btn-outline-sm btn-success-sm" onclick="toggleWhaleBots(true)" title="Reiniciar todos los whale bots">▶ Activar Whales</button>`;
    html += renderBotSection({
      title:       '🐋 Whale Tracker',
      running:     whaleRunning,
      stopped:     whaleStopped,
      price,
      toggleKey:   'whale',
      extraHeader: whaleToggleBtn,
    });
  }

  // ── Other / unknown modes ───────────────────────────────────────────
  if (otherPools.length) {
    const otherRunning = otherPools.filter(p => p.running);
    const otherStopped = otherPools.filter(p => !p.running);
    html += renderBotSection({
      title:      '⚙️ Otros',
      running:    otherRunning,
      stopped:    otherStopped,
      price,
      toggleKey:  'other',
    });
  }

  grid.innerHTML = html;
  renderRiskStrip(pools);
}

function renderBotSection({ title, running, stopped, price, toggleKey, extraHeader = '' }) {
  const stoppedKey  = `historicalOpen_${toggleKey}`;
  const isOpen      = state[stoppedKey] !== false; // default open
  let html = '';

  // Running subsection
  html += `<div class="pools-section">
  <div class="pools-section-header">
    <span>${title} <span class="pools-count">${running.length} running</span></span>
    ${extraHeader}
  </div>
  <div class="pools-cards-grid">
    ${running.length
      ? running.map(p => poolCard(p, price)).join('')
      : `<div class="loading-msg">Sin bots ${title} corriendo ahora.</div>`}
  </div>
</div>`;

  // Stopped subsection (collapsible)
  if (stopped.length) {
    html += `<div class="pools-section">
  <div class="pools-section-header pools-section-header--muted"
       onclick="toggleSectionStopped('${toggleKey}')">
    <span>Configured / Stopped <span class="pools-count">${stopped.length}</span></span>
    <button class="btn-outline-sm" style="pointer-events:none">${isOpen ? '▲ Hide' : '▼ Show'}</button>
  </div>
  <div class="pools-cards-grid ${isOpen ? '' : 'hidden'}" id="stopped-${toggleKey}">
    ${stopped.map(p => poolCard(p, price, true)).join('')}
  </div>
</div>`;
  }

  return html;
}

function toggleSectionStopped(key) {
  const stateKey = `historicalOpen_${key}`;
  state[stateKey] = state[stateKey] === false ? true : false;
  if (state.lastPools) renderPools(state.lastPools);
}

// Legacy toggle kept for any external references
function toggleHistorical() {
  toggleSectionStopped('lp');
}

async function toggleWhaleBots(start) {
  const action = start ? 'start-whale-bots' : 'stop-whale-bots';
  const label  = start ? 'Activar' : 'Pausar';
  if (!confirm(`¿${label} todos los Whale bots?`)) return;
  try {
    const data = await apiPost(`/admin/${action}`);
    const n    = start ? data.started_count : data.stopped_count;
    alert(`✅ ${label}: ${n} whale bot(s)`);
    await renderOverview();
  } catch (e) {
    if (e.message !== 'Session expired') alert('Error: ' + e.message);
  }
}

// ── Health logic ───────────────────────────────────────────────────────────
function poolHealth(p, currentPrice) {
  const lastType = p.last_event?.type;

  if (p.active && !p.running) return { level: 'red', reason: 'Bot caído (proceso detenido)' };

  if (lastType === 'hedge_opened' && p.running) {
    return { level: 'yellow', reason: 'Short activo — cobertura en curso' };
  }

  if (currentPrice && (p.pair.startsWith('ETH') || p.pair.startsWith('WETH'))) {
    // Use actual trigger prices (not raw bounds) — trigger_pct is stored negative e.g. -0.5
    const trigPct       = p.trigger_pct ?? -0.5;
    const lowerTrigPx   = p.lower_bound * (1 + trigPct / 100);
    const upperTrigPx   = p.upper_bound * (1 - trigPct / 100);
    const pct_to_lower  = (currentPrice - lowerTrigPx) / currentPrice;
    const pct_to_upper  = (upperTrigPx  - currentPrice) / currentPrice;

    if (currentPrice <= lowerTrigPx) {
      return lastType === 'hedge_opened'
        ? { level: 'yellow', reason: 'Trigger bajista alcanzado — short activo' }
        : { level: 'red',    reason: 'Trigger bajista alcanzado — SIN cobertura activa' };
    }
    if (currentPrice >= upperTrigPx) {
      return lastType === 'hedge_opened'
        ? { level: 'yellow', reason: 'Trigger alcista alcanzado — short activo' }
        : { level: 'yellow', reason: 'Trigger alcista — SHORT pendiente de abrir' };
    }
    if (pct_to_lower < NEAR_EDGE_PCT) {
      return { level: 'yellow', reason: `Cerca del trigger bajista (${(pct_to_lower*100).toFixed(1)}%)` };
    }
    if (pct_to_upper < NEAR_EDGE_PCT) {
      return { level: 'yellow', reason: `Cerca del trigger alcista (${(pct_to_upper*100).toFixed(1)}%)` };
    }
  }

  if (!p.running && !p.active) {
    return { level: 'yellow', reason: 'Bot detenido manualmente' };
  }

  return { level: 'green', reason: 'En rango — fees activos' };
}

// Helper: infer reentry guard state from recent_events without extra API call.
// Guard is active if the most recent close event (sl_hit / trailing_stop) comes
// AFTER the most recent reentry_guard_cleared or started event.
function poolGuardPill(p) {
  if (p.mode === 'whale') return '';
  const events = p.recent_events || [];
  const CLOSE_TYPES   = new Set(['sl_hit', 'trailing_stop', 'tp_hit']);
  const RESET_TYPES   = new Set(['reentry_guard_cleared', 'started']);
  const lastClose  = events.find(e => CLOSE_TYPES.has(e.type));
  const lastReset  = events.find(e => RESET_TYPES.has(e.type));
  if (!lastClose) return '';
  // events are DESC order — if lastClose appears before lastReset, guard is active
  const closeIdx = events.indexOf(lastClose);
  const resetIdx = lastReset ? events.indexOf(lastReset) : Infinity;
  if (closeIdx >= resetIdx) return ''; // reset happened after close → guard cleared
  const guardPx = lastClose.details?.reentry_guard;
  if (!guardPx) return '';
  return `<span class="badge badge--yellow" title="Reentry guard activo — precio debe superar este nivel">🔒 $${fmtNum(guardPx)}</span>`;
}

// Helper: derive engine version from started event details (no extra API call)
function poolEngineTag(p) {
  const events = p.recent_events || [];
  const started = events.find(e => e.type === 'started');
  const isV2 = started?.details?.engine === 'v2';
  return isV2
    ? `<span class="badge badge--green" title="Motor V2 — SL nativo + recuperación de crash">V2</span>`
    : `<span class="badge badge--muted" title="Motor V1 — protección por software">V1</span>`;
}

// Helper: compute both trigger prices for a pool config
function poolTriggers(p) {
  const trigPct = p.trigger_pct ?? -0.5;
  return {
    lower: p.lower_bound * (1 + trigPct / 100),
    upper: p.upper_bound * (1 - trigPct / 100),
  };
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
  ${p.hl_wallet_addr ? `<div class="pool-wallet" style="color:var(--amber);font-size:.62rem" title="HL protection wallet">HL: ${p.hl_wallet_addr}</div>` : ''}

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

  ${(() => {
    const { lower: lTrig, upper: uTrig } = poolTriggers(p);
    const trigRow = `
  <div class="pool-row">
    <span class="pool-label">Triggers ↓↑</span>
    <span class="pool-val" style="font-size:.72rem">
      <span style="color:#f87171">$${fmtNum(lTrig)}</span>
      <span style="color:var(--muted)"> · </span>
      <span style="color:#fbbf24">$${fmtNum(uTrig)}</span>
    </span>
  </div>`;
    if (!ethPrice || !(p.pair.startsWith('ETH') || p.pair.startsWith('WETH'))) return trigRow;
    const distL   = ((ethPrice - lTrig) / ethPrice) * 100;
    const distU   = ((uTrig - ethPrice)  / ethPrice) * 100;
    const nearest = Math.abs(distL) <= Math.abs(distU) ? distL : distU;
    const dir     = Math.abs(distL) <= Math.abs(distU) ? '↓' : '↑';
    const cls     = Math.abs(nearest) < 2 ? 'red' : Math.abs(nearest) < 5 ? 'yellow' : 'green';
    return trigRow + `
  <div class="pool-row">
    <span class="pool-label">Distancia trigger</span>
    <span class="pool-val pool-val--${cls}">${dir} ${Math.abs(nearest).toFixed(1)}%</span>
  </div>`;
  })()}

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
      ${botStatus}${heartbeatBadge}${shortBadge}${poolGuardPill(p)}
      <span class="badge badge--muted">${
        p.mode === 'aragan' ? 'Defensor Bajista' :
        p.mode === 'avaro'  ? 'Defensor Alcista' :
        p.mode === 'fury'   ? '⚡ FURY RSI' :
        p.mode === 'whale'  ? '🐋 WHALE' :
        p.mode.toUpperCase()
      }</span>
      <span class="badge badge--muted">${chainName(p.chain_id)}</span>
      ${poolEngineTag(p)}
    </div>
    <span style="color:var(--muted);font-size:.7rem">${p.user_plan.toUpperCase()}</span>
  </div>
  <div class="pool-wallet">${p.user_address}</div>
  ${p.hl_wallet_addr ? `<div class="pool-wallet" style="color:var(--amber);font-size:.62rem" title="HL protection wallet">HL: ${p.hl_wallet_addr}</div>` : ''}
  ${p.hl_wallet_addr ? `<div class="pool-row" style="margin-top:.25rem">
    <span class="pool-label">HL Balance</span>
    <span class="pool-val ${p.hl_account_value == null ? '' : p.hl_account_value <= 0 ? 'pool-val--red' : p.hl_account_value < 20 ? 'pool-val--yellow' : 'pool-val--green'}">${
      p.hl_account_value == null ? '—' : '$' + p.hl_account_value.toFixed(2)
    }</span>
  </div>` : ''}

  <div class="card-action-row">
    <button class="detail-toggle" onclick="toggleDetail(${p.config_id})">
      ${isExpanded ? '▲ Ocultar detalle' : '▼ Ver detalle HL + historial'}
    </button>
    <button class="btn-restart" id="restart-btn-${p.config_id}" onclick="restartBot(${p.config_id})" title="Detener y relanzar este bot desde la config actual en DB">
      ↺ Reiniciar
    </button>
  </div>

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
    <span class="muted">Protección solo por software (polling cada 30s). Si el bot se cae con posición abierta, no hay SL activo en HL hasta que reinicie.</span>
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

// ── Active Risk Strip ──────────────────────────────────────────────────────

function renderRiskStrip(pools) {
  const strip = document.getElementById('risk-strip');
  if (!strip) return;

  const activeShorts = pools.filter(p =>
    p.running && p.last_event?.type === 'hedge_opened'
  );

  if (!activeShorts.length) {
    strip.classList.add('hidden');
    return;
  }

  const items = activeShorts.map(p => {
    const health  = poolHealth(p, state.ethPrice);
    const dotCls  = `risk-dot--${health.level}`;
    const price   = p.last_event?.price != null ? `$${fmtNum(p.last_event.price)}` : '—';
    const pnlVal  = p.last_event?.pnl;
    const pnlHtml = pnlVal != null
      ? `<span class="${pnlVal >= 0 ? 'risk-pnl-pos' : 'risk-pnl-neg'}">${pnlVal >= 0 ? '+' : ''}$${fmtNum(Math.abs(pnlVal))}</span>`
      : '';
    const hbHtml  = p.last_heartbeat ? heartbeatBadgeHtml(p.last_heartbeat) : '';
    // Distance to nearest trigger in risk strip
    let distHtml = '';
    if (state.ethPrice && (p.pair.startsWith('ETH') || p.pair.startsWith('WETH'))) {
      const { lower: lTrig, upper: uTrig } = poolTriggers(p);
      const distL   = ((state.ethPrice - lTrig) / state.ethPrice) * 100;
      const distU   = ((uTrig - state.ethPrice)  / state.ethPrice) * 100;
      const nearest = Math.abs(distL) <= Math.abs(distU) ? distL : distU;
      const dir     = Math.abs(distL) <= Math.abs(distU) ? '↓' : '↑';
      const cls     = Math.abs(nearest) < 2 ? 'risk-pnl-neg' : Math.abs(nearest) < 5 ? '' : '';
      distHtml = `<span class="risk-sep">·</span><span class="${cls}" title="Distancia al trigger">${dir}${Math.abs(nearest).toFixed(1)}%</span>`;
    }
    return `
      <div class="risk-item" onclick="searchWalletDirect('${p.user_address}')" title="Click para ver detalle">
        <span class="risk-dot ${dotCls}"></span>
        <span class="risk-wallet">${shortAddr(p.user_address)}</span>
        <span class="risk-sep">·</span>
        <span class="risk-pair">${p.pair} NFT #${p.nft_token_id}</span>
        <span class="risk-sep">·</span>
        <span class="risk-entry">Entry ${price}</span>
        ${pnlHtml ? `<span class="risk-sep">·</span>${pnlHtml}` : ''}
        ${distHtml}
        ${hbHtml}
      </div>`;
  }).join('');

  strip.innerHTML = `
    <div class="risk-strip-inner">
      <span class="risk-strip-title">⚡ POSICIONES ABIERTAS</span>
      <span class="risk-strip-count">${activeShorts.length}</span>
      <div class="risk-items">${items}</div>
    </div>`;
  strip.classList.remove('hidden');
}

function heartbeatBadgeHtml(ts) {
  if (!ts) return '';
  const normalized = !ts.endsWith('Z') && !ts.includes('+') ? ts.replace(' ', 'T') + 'Z' : ts;
  const ageSec = Math.floor((Date.now() - new Date(normalized).getTime()) / 1000);
  const cls    = ageSec < 120 ? 'green' : ageSec < 300 ? 'yellow' : 'red';
  const label  = ageSec < 60  ? `${ageSec}s` : `${Math.floor(ageSec / 60)}min`;
  return `<span class="badge badge--${cls} risk-hb">⏱ ${label}</span>`;
}

// ── Wallet Search / User Lookup ────────────────────────────────────────────

async function searchWallet() {
  const input = document.getElementById('wallet-search-input');
  const query = (input?.value || '').trim().toLowerCase();
  if (query.length < 4) return;

  const panel = document.getElementById('wallet-panel');
  panel.innerHTML = '<div class="loading-msg">Buscando…</div>';
  panel.classList.remove('hidden');
  document.getElementById('wallet-search-clear').classList.remove('hidden');

  // Match from already-loaded pools
  const pools = (state.lastPools || []).filter(p =>
    p.user_address?.toLowerCase().includes(query)
  );

  // Get user profile from users endpoint
  let userProfile = null;
  try {
    const d = await apiGet('/admin/users');
    userProfile = (d.users || []).find(u => u.address?.toLowerCase().includes(query));
  } catch (_) {}

  if (!pools.length && !userProfile) {
    panel.innerHTML = `<div class="wp-not-found">Sin resultados para <strong>${query}</strong></div>`;
    return;
  }

  panel.innerHTML = buildWalletPanel(userProfile, pools);
}

function searchWalletDirect(address) {
  const input = document.getElementById('wallet-search-input');
  if (input) input.value = address;
  searchWallet();
  setTimeout(() => {
    document.getElementById('wallet-panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, 300);
}

function clearWalletSearch() {
  const input = document.getElementById('wallet-search-input');
  if (input) input.value = '';
  document.getElementById('wallet-panel')?.classList.add('hidden');
  document.getElementById('wallet-search-clear')?.classList.add('hidden');
}

function buildWalletPanel(user, pools) {
  const address  = user?.address || pools[0]?.user_address || '—';
  const plan     = user?.plan    || 'free';
  const funnel   = user?.funnel  || '—';
  const running  = user?.running_bots || 0;

  const funnelMap = {
    bot_running:    'Bot corriendo',
    bot_configured: 'Bot configurado',
    pool_added:     'Pool añadido',
    signed_up:      'Registrado',
  };

  // ── Header ───────────────────────────────────────────────────────────
  let html = `
    <div class="wp-header">
      <div class="wp-address-row">
        <span class="wp-address">${address}</span>
        <button class="btn-outline-sm" onclick="navigator.clipboard.writeText('${address}');this.textContent='✓ Copiado';setTimeout(()=>this.textContent='⎘ Copiar',1500)">⎘ Copiar</button>
      </div>
      <div class="wp-badges">
        <span class="badge badge--${planColor(plan)}">${plan.toUpperCase()}</span>
        <span class="badge badge--muted">${funnelMap[funnel] || funnel}</span>
        ${running > 0 ? `<span class="badge badge--green">● ${running} bot(s) activos</span>` : ''}
        ${user?.last_seen ? `<span class="wp-last-seen">Última actividad: ${relTime(user.last_seen)}</span>` : ''}
      </div>
      <div class="wp-actions">
        <button class="btn-outline-sm wp-btn" onclick="alert('Disponible en Step 8 (billing)')">✏️ Override Plan</button>
        <button class="btn-outline-sm wp-btn" onclick="alert('Disponible en Step 8 (billing)')">📅 Extender</button>
        <button class="btn-outline-sm wp-btn wp-btn--danger" onclick="alert('Disponible en Step 8 (billing)')">⛔ Suspender</button>
        <button class="btn-outline-sm wp-btn" onclick="alert('Disponible en Step 8 (billing)')">💰 Reembolsar</button>
        <button class="btn-outline-sm wp-btn" onclick="alert('Disponible en Step 8 (billing)')">📝 Nota</button>
      </div>
      <div class="wp-step8-note">⚙️ Las acciones de gestión estarán activas en Step 8 — Subscriptions</div>
    </div>`;

  // ── Pools / Bots ─────────────────────────────────────────────────────
  if (pools.length) {
    html += `<div class="wp-section-title">POOLS / BOTS (${pools.length})</div>`;
    html += pools.map(p => {
      const health  = poolHealth(p, state.ethPrice);
      const lastEvt = p.last_event;
      const evtHtml = lastEvt
        ? `<span class="wp-pool-evt">${evtLabel(lastEvt.type)}${lastEvt.price != null ? ` @ $${fmtNum(lastEvt.price)}` : ''}${lastEvt.pnl != null ? ` · PnL $${fmtNum(lastEvt.pnl)}` : ''} <span class="muted">${relTime(lastEvt.ts)}</span></span>`
        : '';

      return `
        <div class="wp-pool-row">
          <div class="health-dot health-dot--${health.level}" style="flex-shrink:0;margin-top:3px"></div>
          <div class="wp-pool-body">
            <div class="wp-pool-top">
              <span class="pool-pair">${p.pair}</span>
              <span class="pool-nft">NFT #${p.nft_token_id}</span>
              ${p.running ? '<span class="badge badge--green">RUNNING</span>' : p.active ? '<span class="badge badge--red">CAÍDO</span>' : '<span class="badge badge--muted">STOPPED</span>'}
              ${p.paper_trade ? '<span class="badge badge--yellow">PAPER</span>' : ''}
            </div>
            <div class="wp-pool-meta">Mode: ${p.mode} · ${p.leverage}x leverage · SL ${p.sl_pct}%${p.tp_pct ? ` · TP ${p.tp_pct}%` : ''}</div>
            ${evtHtml}
          </div>
          <button class="btn-outline-sm" style="flex-shrink:0" onclick="toggleDetail(${p.config_id})">Ver HL ▾</button>
        </div>
        <div id="detail-${p.config_id}" class="pool-detail hidden"></div>`;
    }).join('');
  } else {
    html += `<div class="wp-no-pools">Sin pools configurados para esta wallet.</div>`;
  }

  return html;
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

// ── M2-28: Per-bot restart ─────────────────────────────────────────────────
async function restartBot(configId) {
  const btn = document.getElementById(`restart-btn-${configId}`);
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Reiniciando…'; }
  try {
    const d = await apiPost(`/admin/restart/${configId}`);
    doRefresh();
  } catch (e) {
    if (e.message !== 'Session expired') alert('Error al reiniciar: ' + e.message);
    if (btn) { btn.disabled = false; btn.textContent = '↺ Reiniciar'; }
  }
}

// ── M2-30: Force LP reconciler scan ────────────────────────────────────────
async function reconcileNow() {
  const btn = document.getElementById('btn-reconcile');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Escaneando…'; }
  try {
    const d = await apiPost('/admin/reconcile-now');
    alert('✅ ' + (d.message || 'Reconciler scan complete'));
    doRefresh();
  } catch (e) {
    if (e.message !== 'Session expired') alert('Error: ' + e.message);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '🔍 Reconcile LP'; }
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
    reentry_guard_cleared: '🔓 Re-entrada lista',
    lp_removed:            '💧 LP retirado',
    lp_burned:             '🔥 NFT quemado',
    orphan_recovered:      '♻️ Posición recuperada',
    stopped:               '⏹ Detenido',
    error:                 '❌ Error',
    fury_entry:            '⚡ FURY entrada',
    fury_sl:               '⚡ FURY SL',
    fury_tp:               '⚡ FURY TP',
    fury_circuit_breaker:  '⚡ FURY circuit breaker',
    whale_new_position:    '🐋 Nueva posición',
    whale_closed:          '🐋 Posición cerrada',
    whale_size_increase:   '🐋 Tamaño aumentado',
    whale_size_decrease:   '🐋 Tamaño reducido',
    whale_flip:            '🐋 Cambio de lado',
    whale_snapshot:        '🐋 Snapshot',
    whale_event:           '🐋 Evento',
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
    lp_removed:            'yellow',
    lp_burned:             'red',
    orphan_recovered:      'green',
    stopped:               'muted',
    error:                 'red',
    fury_entry:            'yellow',
    fury_sl:               'red',
    fury_tp:               'green',
    fury_circuit_breaker:  'red',
    whale_new_position:    'yellow',
    whale_closed:          'muted',
    whale_size_increase:   'yellow',
    whale_size_decrease:   'muted',
    whale_flip:            'yellow',
    whale_snapshot:        'muted',
    whale_event:           'muted',
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
