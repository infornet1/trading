'use strict';

// ── Config ─────────────────────────────────────────────────────────────────
const API_BASE      = '/trading/lp-hedge/api';
const REFRESH_SECS  = 30;
const NEAR_EDGE_PCT = 0.05;   // 5% from boundary = yellow warning

// ── State ──────────────────────────────────────────────────────────────────
const state = {
  jwt:      localStorage.getItem('vf_jwt') || null,
  provider: null,
  address:  null,
  ethPrice: null,
  timer:    null,
  countdown: REFRESH_SECS,
};

// ── Boot ───────────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  if (state.jwt && jwtIsAdmin(state.jwt) && !jwtExpired(state.jwt)) {
    showContent();
    doRefresh();
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

    // Get nonce
    const nonceRes = await fetch(`${API_BASE}/auth/nonce?address=${state.address}`);
    if (!nonceRes.ok) throw new Error('Error al obtener nonce.');
    const { nonce } = await nonceRes.json();

    // Sign
    const sig = await signer.signMessage(`Sign in to VIZNAGO FURY\nNonce: ${nonce}`);

    // Verify
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
  } catch (e) {
    errEl.textContent = e.message || 'Error desconocido.';
    errEl.classList.remove('hidden');
  }
}

// ── API call ───────────────────────────────────────────────────────────────
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
  clearInterval(state.timer);
  setStatus('Actualizando...');
  try {
    await Promise.all([fetchEthPrice(), renderOverview()]);
    state.countdown = REFRESH_SECS;
    state.timer = setInterval(() => {
      state.countdown--;
      setStatus(`Actualizado · próximo en ${state.countdown}s`);
      if (state.countdown <= 0) doRefresh();
    }, 1000);
  } catch (e) {
    setStatus(`Error: ${e.message}`);
  }
}

function setStatus(msg) {
  document.getElementById('refresh-status').textContent = msg;
}

// ── Overview render ────────────────────────────────────────────────────────
async function renderOverview() {
  const data = await apiGet('/admin/overview');
  renderStats(data.stats);
  renderPools(data.pools);
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

  // Bot crashed: config active but process not running
  if (p.active && !p.running) return { level: 'red', reason: 'Bot caído (proceso detenido)' };

  // Active short open
  if (lastType === 'hedge_opened' && p.running) {
    return { level: 'yellow', reason: 'Short activo — cobertura en curso' };
  }

  // Price out of range (if we have current price for this pair)
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

  // Bot not running and not active — just idle/stopped by user
  if (!p.running && !p.active) {
    return { level: 'yellow', reason: 'Bot detenido manualmente' };
  }

  return { level: 'green', reason: 'En rango — fees activos' };
}

// ── Pool card HTML ─────────────────────────────────────────────────────────
function poolCard(p, ethPrice) {
  const h = poolHealth(p, ethPrice);

  // Range bar position (ETH pools only)
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

  return `
<div class="pool-card pool-card--${h.level}">
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

  <div class="pool-footer">
    <div style="display:flex;gap:.4rem;align-items:center">
      ${botStatus}${shortBadge}
      <span class="badge badge--muted">${p.mode.toUpperCase()}</span>
      <span class="badge badge--muted">${chainName(p.chain_id)}</span>
    </div>
    <span style="color:var(--muted);font-size:.7rem">${p.user_plan.toUpperCase()}</span>
  </div>
  <div class="pool-wallet">${p.user_address}</div>
</div>`;
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

function relTime(isoStr) {
  const diff = Math.floor((Date.now() - new Date(isoStr).getTime()) / 1000);
  if (diff < 60)   return `hace ${diff}s`;
  if (diff < 3600) return `hace ${Math.floor(diff/60)}min`;
  if (diff < 86400) return `hace ${Math.floor(diff/3600)}h`;
  return `hace ${Math.floor(diff/86400)}d`;
}
