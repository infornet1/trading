'use strict';

// ── Config ─────────────────────────────────────────────────────────────────
const API_BASE         = '/trading/lp-hedge/api';
const WHALE_SIGNAL_MAX = 50;
const LOG_MAX          = 50;

// ── State ──────────────────────────────────────────────────────────────────
const whale = {
  jwt:          localStorage.getItem('vf_jwt') || null,
  address:      null,
  provider:     null,
  bots:         {},          // config_id → BotConfigOut
  sockets:      {},          // config_id → WebSocket
  signals:      {},          // config_id → array (live via WS)
  publicSignals: [],         // from public endpoint (no auth)
};

// ── Boot ───────────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  updateWalletUI();
  loadPublicWhaleSignals();
  setInterval(loadPublicWhaleSignals, 30_000);

  if (whale.jwt) {
    loadBots();
  } else {
    document.getElementById('auth-banner').classList.remove('hidden');
    renderMyTrackers();
    updateLaunchOverlay();
  }
});

// ── API Helper ─────────────────────────────────────────────────────────────
async function apiCall(method, path, body) {
  const opts = {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(whale.jwt ? { Authorization: `Bearer ${whale.jwt}` } : {}),
    },
  };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(API_BASE + path, opts);
  if (res.status === 401) {
    whale.jwt = null;
    localStorage.removeItem('vf_jwt');
    updateWalletUI();
    renderMyTrackers();
    updateLaunchOverlay();
    document.getElementById('auth-banner').classList.remove('hidden');
    throw new Error('Session expired — please sign in again.');
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  if (res.status === 204) return null;
  return res.json();
}

// ── Wallet Connect + SIWE ─────────────────────────────────────────────────
window.connectWallet = async function () {
  if (!window.ethereum) {
    showError('No se detectó wallet. Instala Rabby o MetaMask.');
    return;
  }
  try {
    const btn = document.getElementById('wallet-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Conectando…'; }

    whale.provider = new ethers.BrowserProvider(window.ethereum);
    await whale.provider.send('eth_requestAccounts', []);
    const signer = await whale.provider.getSigner();
    whale.address = await signer.getAddress();

    // SIWE sign-in
    const nonceRes = await fetch(`${API_BASE}/auth/nonce?address=${whale.address}`);
    if (!nonceRes.ok) throw new Error('No se pudo obtener nonce del servidor');
    const { nonce } = await nonceRes.json();

    const message   = `Sign in to VIZNIAGO FURY\nNonce: ${nonce}`;
    const signature = await signer.signMessage(message);

    const verRes = await fetch(`${API_BASE}/auth/verify`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ address: whale.address, signature }),
    });
    if (!verRes.ok) throw new Error('Verificación de firma fallida');
    const { access_token } = await verRes.json();

    whale.jwt = access_token;
    localStorage.setItem('vf_jwt', access_token);
    document.getElementById('auth-banner').classList.add('hidden');

    updateWalletUI();
    await loadBots();
  } catch (err) {
    if (err.code === 4001) { /* user rejected */ }
    else showError('Wallet connect failed: ' + (err.message || err));
    const btn = document.getElementById('wallet-btn');
    if (btn) { btn.disabled = false; btn.textContent = '🟢\u00a0 Conectar Wallet'; }
  }
};

function updateWalletUI() {
  const btn  = document.getElementById('wallet-btn');
  const chip = document.getElementById('wallet-chip');
  if (!whale.address || !whale.jwt) {
    if (btn)  { btn.classList.remove('hidden'); btn.disabled = false; btn.textContent = '🟢\u00a0 Conectar Wallet'; }
    if (chip) chip.classList.add('hidden');
  } else {
    if (btn)  btn.classList.add('hidden');
    if (chip) {
      chip.classList.remove('hidden');
      chip.textContent = whale.address.slice(0,6) + '…' + whale.address.slice(-4);
    }
  }
  updateLaunchOverlay();
}

function updateLaunchOverlay() {
  const overlay = document.getElementById('launch-overlay');
  if (!overlay) return;
  if (whale.jwt) {
    overlay.style.display = 'none';
  } else {
    overlay.style.display = 'flex';
  }
}

// ── Load Bots ─────────────────────────────────────────────────────────────
async function loadBots() {
  try {
    const bots = await apiCall('GET', '/bots');
    whale.bots = {};
    for (const b of bots) {
      if (b.mode === 'whale') {
        whale.bots[b.id] = b;
        if (b.active) connectBotWS(b.id);
      }
    }
    renderMyTrackers();
    updateStats();
  } catch (e) {
    showError('Error cargando bots: ' + (e.message || e));
  }
}

// ── Public Whale Signals ───────────────────────────────────────────────────
async function loadPublicWhaleSignals() {
  try {
    const signals = await fetch(API_BASE + '/bots/public-whale-signals?limit=50')
      .then(r => r.ok ? r.json() : []);
    if (!Array.isArray(signals)) return;
    whale.publicSignals = signals;
    renderSignalsFeed();
    updateStats();
  } catch (_) {}
}

// ── WebSocket ─────────────────────────────────────────────────────────────
function connectBotWS(configId) {
  if (whale.sockets[configId]) return;
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const url   = `${proto}://${location.host}/trading/lp-hedge/api/ws/${configId}?token=${whale.jwt}`;
  const ws    = new WebSocket(url);
  whale.sockets[configId] = ws;

  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      if (data.event === 'ping') return;
      const evt = data.event || data.event_type || '';
      if (evt.startsWith('whale_') && evt !== 'whale_snapshot') {
        if (!whale.signals[configId]) whale.signals[configId] = [];
        whale.signals[configId].unshift(data);
        if (whale.signals[configId].length > WHALE_SIGNAL_MAX)
          whale.signals[configId].pop();
        prependSignalRow(data, configId);
        updateStats();
      }
    } catch (_) {}
  };

  ws.onclose = () => {
    delete whale.sockets[configId];
    setTimeout(() => {
      const bot = whale.bots[configId];
      if (bot?.active && whale.jwt) connectBotWS(configId);
    }, 10_000);
  };

  ws.onerror = () => ws.close();
}

// ── Signals Feed Rendering ─────────────────────────────────────────────────
function renderSignalsFeed() {
  const feed = document.getElementById('signals-feed');
  if (!feed) return;

  // Merge live WS signals + public endpoint signals, deduplicate, sort
  const allSignals = [
    ...Object.values(whale.signals).flat(),
    ...whale.publicSignals,
  ].filter((s, i, arr) => {
    const key = `${s.ts}|${s.asset}|${s.event_type || s.event}`;
    return arr.findIndex(x => `${x.ts}|${x.asset}|${x.event_type || x.event}` === key) === i;
  }).sort((a, b) => (b.ts > a.ts ? 1 : -1)).slice(0, 30);

  if (!allSignals.length) {
    feed.innerHTML = `<div class="wt-empty"><div class="wt-empty-icon">🌊</div><p>Sin señales aún — el tracker está sondeando…</p></div>`;
    return;
  }

  feed.innerHTML = allSignals.map(s => buildSignalRowHTML(s)).join('');

  const updated = document.getElementById('signals-updated');
  if (updated) updated.textContent = 'Actualizado ' + new Date().toLocaleTimeString();
}

function prependSignalRow(data, configId) {
  const feed = document.getElementById('signals-feed');
  if (!feed) return;

  // Remove empty state if present
  const empty = feed.querySelector('.wt-empty');
  if (empty) empty.remove();

  const div = document.createElement('div');
  div.innerHTML = buildSignalRowHTML(data, configId);
  const row = div.firstElementChild;
  row.classList.add('signal-row--new');
  feed.insertBefore(row, feed.firstChild);
  setTimeout(() => row.classList.remove('signal-row--new'), 800);

  // Trim to max 30
  while (feed.children.length > 30) feed.removeChild(feed.lastChild);

  const updated = document.getElementById('signals-updated');
  if (updated) updated.textContent = 'Actualizado ' + new Date().toLocaleTimeString();
}

function buildSignalRowHTML(s) {
  const evtRaw   = s.event_type || s.event || '';
  const evt      = evtRaw.replace('whale_','').replace(/_/g,' ').toUpperCase();
  const side     = (s.side || '').toUpperCase();
  const asset    = s.asset || '—';
  const sizeUsd  = Number(s.size_usd || 0);
  const deltaUsd = s.delta_usd != null ? Number(s.delta_usd) : null;
  const addr     = s.address || '';
  const ts       = (() => {
    try { return new Date(s.ts.replace(/[+-]\d{2}:\d{2}$/, '')).toLocaleTimeString(); }
    catch(_) { return s.ts || ''; }
  })();

  const evtColor = { whale_new_position:'#00d4ff', whale_closed:'#9ca3af',
    whale_flip:'#f59e0b', whale_size_increase:'#34d399', whale_size_decrease:'#f87171' }[evtRaw] || '#9ca3af';
  const sideColor = side === 'LONG' ? '#34d399' : side === 'SHORT' ? '#f87171' : '#9ca3af';
  const sideArrow = side === 'LONG' ? '▲' : side === 'SHORT' ? '▼' : '';
  const sz   = sizeUsd ? `$${sizeUsd.toLocaleString('en-US',{maximumFractionDigits:0})}` : '—';
  const delta = deltaUsd != null
    ? `<span style="color:${deltaUsd>=0?'#34d399':'#f87171'}">${deltaUsd>=0?'▲':'▼'}$${Math.abs(deltaUsd).toLocaleString('en-US',{maximumFractionDigits:0})}</span>` : '';
  const addrHtml = addr
    ? `<span class="sig-addr" title="${addr}" onclick="navigator.clipboard?.writeText('${addr}')">${addr.slice(0,6)}…${addr.slice(-4)}</span>` : '';

  return `<div class="signal-row">
    <span class="sig-time">${ts}</span>
    <span class="sig-evt" style="color:${evtColor}">${evt}</span>
    <span class="sig-asset">${asset}</span>
    <span class="sig-side" style="color:${sideColor}">${sideArrow} ${side||'—'}</span>
    <span class="sig-size">${sz}</span>
    ${delta ? `<span class="sig-delta">${delta}</span>` : '<span></span>'}
    ${addrHtml}
  </div>`;
}

// ── My Trackers ────────────────────────────────────────────────────────────
function renderMyTrackers() {
  const container = document.getElementById('my-trackers-list');
  const hint      = document.getElementById('my-trackers-auth-hint');
  if (!container) return;

  if (!whale.jwt) {
    if (hint) hint.style.display = 'inline';
    container.innerHTML = '';
    return;
  }
  if (hint) hint.style.display = 'none';

  const bots = Object.values(whale.bots);
  if (!bots.length) {
    container.innerHTML = `<p class="wt-muted">No tienes trackers aún. Lanza uno abajo.</p>`;
    return;
  }

  container.innerHTML = bots.map(bot => {
    const isActive = bot.active;
    const statusDot = isActive
      ? `<span class="tracker-dot tracker-dot--on"></span>`
      : `<span class="tracker-dot tracker-dot--off"></span>`;
    const label = isActive ? 'ACTIVO' : 'DETENIDO';
    const labelColor = isActive ? '#34d399' : '#9ca3af';

    return `<div class="tracker-card">
      <div class="tracker-card-left">
        ${statusDot}
        <div>
          <div class="tracker-card-title">Top-${bot.whale_top_n||50} · $${Number(bot.whale_min_notional||50000).toLocaleString()} min</div>
          <div class="tracker-card-sub" style="color:${labelColor}">${label} · ID ${bot.id}</div>
        </div>
      </div>
      <div class="tracker-card-actions">
        ${isActive
          ? `<button class="btn btn-sm wt-btn-stop" onclick="stopWhaleBot(${bot.id})">■ Stop</button>`
          : `<button class="btn btn-sm wt-btn-start" onclick="restartWhaleBot(${bot.id})">▶ Restart</button>`
        }
        <button class="btn btn-sm wt-btn-delete" onclick="deleteWhaleBot(${bot.id})">🗑</button>
      </div>
    </div>`;
  }).join('');
}

// ── Stats Bar ──────────────────────────────────────────────────────────────
function updateStats() {
  const allSignals = [
    ...Object.values(whale.signals).flat(),
    ...whale.publicSignals,
  ];

  const todayStr = new Date().toDateString();
  const today = allSignals.filter(s => {
    try { return new Date(s.ts).toDateString() === todayStr; }
    catch(_) { return false; }
  });

  const last = allSignals.sort((a, b) => (b.ts > a.ts ? 1 : -1))[0];
  const lastTs = last ? (() => {
    try { return new Date(last.ts).toLocaleTimeString(); }
    catch(_) { return '—'; }
  })() : '—';

  const activeBots  = Object.values(whale.bots).filter(b => b.active);
  const totalTopN   = activeBots.reduce((s, b) => s + (b.whale_top_n || 0), 0);

  const el = id => document.getElementById(id);
  if (el('stat-signals-today'))   el('stat-signals-today').textContent   = today.length;
  if (el('stat-active-trackers')) el('stat-active-trackers').textContent = activeBots.length;
  if (el('stat-whales-watched'))  el('stat-whales-watched').textContent  = totalTopN || '—';
  if (el('stat-last-signal'))     el('stat-last-signal').textContent     = lastTs;
}

// ── Bot Controls ───────────────────────────────────────────────────────────
window.launchWhaleBot = async function () {
  const btn = document.getElementById('whale-launch-btn');
  const err = document.getElementById('whale-launch-error');
  if (btn) { btn.disabled = true; btn.textContent = 'Launching…'; }
  if (err) err.textContent = '';

  try {
    const topN        = parseInt(document.getElementById('whale-top-n')?.value || '30', 10);
    const minNotional = parseFloat(document.getElementById('whale-min-notional')?.value || '100000');
    const pollInt     = parseInt(document.getElementById('whale-poll-interval')?.value || '30', 10);
    const watchAssets = document.getElementById('whale-watch-assets')?.value.trim() || '';
    const customAddrs = document.getElementById('whale-custom-addresses')?.value.trim() || '';
    const useWs       = document.getElementById('whale-use-ws')?.checked ?? false;
    const paperTrade  = document.getElementById('whale-paper-trade')?.checked ?? true;

    const tokenId = `whale-${Date.now()}`;

    const res = await apiCall('POST', '/bots', {
      mode:                    'whale',
      chain_id:                42161,
      nft_token_id:            tokenId,
      pair:                    'WHALE',
      lower_bound:             0,
      upper_bound:             0,
      whale_top_n:             topN,
      whale_min_notional:      minNotional,
      whale_poll_interval:     pollInt,
      whale_watch_assets:      watchAssets,
      whale_custom_addresses:  customAddrs,
      whale_use_websocket:     useWs,
      whale_oi_spike_threshold: 0.03,
      paper_trade:             paperTrade,
    });

    await apiCall('POST', `/bots/${res.id}/start`);
    await loadBots();
    connectBotWS(res.id);

    if (btn) { btn.disabled = false; btn.textContent = '🐋\u00a0 Launch Whale Tracker'; }
  } catch (e) {
    if (err) err.textContent = 'Launch failed: ' + (e.message || e);
    if (btn) { btn.disabled = false; btn.textContent = '🐋\u00a0 Launch Whale Tracker'; }
  }
};

window.restartWhaleBot = async function (configId) {
  try {
    await apiCall('POST', `/bots/${configId}/start`);
    await loadBots();
    connectBotWS(configId);
  } catch (e) {
    showError('Restart failed: ' + (e.message || e));
  }
};

window.stopWhaleBot = async function (configId) {
  try {
    await apiCall('POST', `/bots/${configId}/stop`);
    await loadBots();
  } catch (e) {
    showError('Stop failed: ' + (e.message || e));
  }
};

window.deleteWhaleBot = async function (configId) {
  if (!confirm('¿Eliminar este tracker? Esta acción no puede deshacerse.')) return;
  try {
    await apiCall('DELETE', `/bots/${configId}`);
    delete whale.bots[configId];
    renderMyTrackers();
    updateStats();
  } catch (e) {
    showError('Delete failed: ' + (e.message || e));
  }
};

// ── Error Display ─────────────────────────────────────────────────────────
function showError(msg) {
  const banner = document.getElementById('error-banner');
  if (!banner) return;
  banner.textContent = msg;
  banner.classList.remove('hidden');
  setTimeout(() => banner.classList.add('hidden'), 8000);
}
