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
};

// ── Boot ───────────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  if (state.jwt && jwtIsAdmin(state.jwt) && !jwtExpired(state.jwt)) {
    showContent();
    doRefresh();
    applyRefreshInterval();
  } else {
    state.jwt = null;
    localStorage.removeItem('vf_jwt');
    showGate();
  }

  document.getElementById('btn-signin').addEventListener('click', signIn);
});

// ── Auth helpers ───────────────────────────────────────────────────────────
function jwtPayload(token) {
  try { return JSON.parse(atob(token.split('.')[1])); } catch { return {}; }
}
function jwtIsAdmin(token)  { return jwtPayload(token).is_admin === true; }
function jwtExpired(token)  { return (jwtPayload(token).exp || 0) * 1000 < Date.now(); }

function showGate()    {
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
async function apiGet(path) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { Authorization: `Bearer ${state.jwt}` },
  });
  if (res.status === 401 || res.status === 403) {
    state.jwt = null;
    localStorage.removeItem('vf_jwt');
    showGate();
    throw new Error('Session expired');
  }
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

// ── Price fetch (CoinGecko free) ───────────────────────────────────────────
async function fetchEthPrice() {
  try {
    const r = await fetch(
      'https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd'
    );
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
  renderStats(data.stats);
  renderPools(data.pools);
  // Re-load HL detail for any currently expanded cards
  for (const configId of state.expanded) {
    loadHlDetail(configId);
  }
}

function renderStats(s) {
  document.getElementById('stat-wallets').textContent = s.total_wallets;
  document.getElementById('stat-pools').textContent   = s.total_pools;
  document.getElementById('stat-bots').textContent    = s.active_bots;
  document.getElementById('stat-shorts').textContent  = s.active_shorts;
  document.getElementById('stat-volume').textContent  =
    '$' + fmtNum(s.total_volume_usd);
}

function renderPools(pools) {
  const grid = document.getElementById('pools-grid');
  if (!pools.length) {
    grid.innerHTML = '<div class="loading-msg">No hay pools registrados aún.</div>';
    return;
  }
  const price = state.ethPrice;
  grid.innerHTML = pools.map(p => poolCard(p, price)).join('');
}

// ── Health logic ───────────────────────────────────────────────────────────
function poolHealth(p, currentPrice) {
  const lastType = p.last_event?.type;

  if (p.active && !p.running) return { level: 'red', reason: 'Bot caído (proceso detenido)' };

  if (lastType === 'hedge_opened' && p.running) {
    return { level: 'yellow', reason: 'Short activo — cobertura en curso' };
  }

  if (currentPrice && p.pair.startsWith('ETH')) {
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

// ── Pool card HTML ─────────────────────────────────────────────────────────
function poolCard(p, ethPrice) {
  const h = poolHealth(p, ethPrice);
  const isExpanded = state.expanded.has(p.config_id);

  let barPct = 50, cursorPct = 50, priceStr = '—';
  if (ethPrice && p.pair.startsWith('ETH')) {
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
<div class="pool-card pool-card--${h.level}" id="card-${p.config_id}">
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

  <div class="pool-footer">
    <div style="display:flex;gap:.4rem;align-items:center">
      ${botStatus}${shortBadge}
      <span class="badge badge--muted">${p.mode.toUpperCase()}</span>
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
    contentEl.innerHTML = renderHlDetail(d);
    loadEl.classList.add('hidden');
    contentEl.classList.remove('hidden');
  } catch (e) {
    loadEl.textContent = `Error: ${e.message}`;
  } finally {
    state.hlLoading.delete(configId);
  }
}

// ── HL detail content ──────────────────────────────────────────────────────
function renderHlDetail(d) {
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
    sections.push(`
<div class="detail-section">
  <div class="detail-section-title">Posición Activa — Hyperliquid</div>
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
  </div>
  ${d.hl_margin?.account_value ? `
  <div class="hl-margin-bar">
    <span>Cuenta: <b>$${fmtNum(d.hl_margin.account_value)}</b></span>
    <span>Margen total: <b>$${fmtNum(d.hl_margin.total_margin_used)}</b></span>
    <span>Exposición: <b>$${fmtNum(d.hl_margin.total_ntl_pos)}</b></span>
  </div>` : ''}
</div>`);
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

// ── Nuclear stop ───────────────────────────────────────────────────────────
async function nuclearStop() {
  if (!confirm('¿Detener TODOS los bots? Esta acción es irreversible hasta reinicio manual.')) return;
  try {
    const res = await fetch(`${API_BASE}/admin/stop-all`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${state.jwt}` },
    });
    const d = await res.json();
    alert(`✅ Detenidos: ${d.stopped_count} bots.`);
    doRefresh();
  } catch (e) {
    alert('Error: ' + e.message);
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
    started:       '🚀 Iniciado',
    hedge_opened:  '🚨 Short abierto',
    breakeven:     '🛡️ Breakeven',
    tp_hit:        '🎯 TP alcanzado',
    sl_hit:        '🛑 SL activado',
    trailing_stop: '🛑 Trailing stop',
    stopped:       '⏹ Detenido',
    error:         '❌ Error',
  }[type] || type;
}

function evtColor(type) {
  return {
    started:       'muted',
    hedge_opened:  'yellow',
    breakeven:     'green',
    tp_hit:        'green',
    sl_hit:        'red',
    trailing_stop: 'red',
    stopped:       'muted',
    error:         'red',
  }[type] || 'muted';
}

function relTime(isoStr) {
  const diff = Math.floor((Date.now() - new Date(isoStr).getTime()) / 1000);
  if (diff < 60)    return `hace ${diff}s`;
  if (diff < 3600)  return `hace ${Math.floor(diff/60)}min`;
  if (diff < 86400) return `hace ${Math.floor(diff/3600)}h`;
  return `hace ${Math.floor(diff/86400)}d`;
}
