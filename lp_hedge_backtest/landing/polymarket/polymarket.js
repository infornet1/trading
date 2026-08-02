'use strict';

// ── Config ─────────────────────────────────────────────────────────────────
const API_BASE = '/trading/lp-hedge/api';
const FEED_MAX = 50;

// ── State ──────────────────────────────────────────────────────────────────
const poly = {
  jwt:     localStorage.getItem('vf_jwt') || null,
  address: null,
  provider: null,
  bots:    {},   // config_id → BotConfigOut
  sockets: {},   // config_id → WebSocket
};

// ── Boot ───────────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  updateWalletUI();
  if (poly.jwt) {
    loadBots();
  } else {
    document.getElementById('auth-banner').classList.remove('hidden');
    renderMyBots();
    updateLaunchOverlay();
  }
});

// ── API Helper ─────────────────────────────────────────────────────────────
async function apiCall(method, path, body) {
  const opts = {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(poly.jwt ? { Authorization: `Bearer ${poly.jwt}` } : {}),
    },
  };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(API_BASE + path, opts);
  if (res.status === 401) {
    poly.jwt = null;
    localStorage.removeItem('vf_jwt');
    updateWalletUI();
    renderMyBots();
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

    poly.provider = new ethers.BrowserProvider(window.ethereum);
    await poly.provider.send('eth_requestAccounts', []);
    const signer = await poly.provider.getSigner();
    poly.address = await signer.getAddress();

    const nonceRes = await fetch(`${API_BASE}/auth/nonce?address=${poly.address}`);
    if (!nonceRes.ok) throw new Error('No se pudo obtener nonce del servidor');
    const { nonce } = await nonceRes.json();

    const message   = `Sign in to VIZNIAGO FURY\nNonce: ${nonce}`;
    const signature = await signer.signMessage(message);

    const verRes = await fetch(`${API_BASE}/auth/verify`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ address: poly.address, signature }),
    });
    if (!verRes.ok) throw new Error('Verificación de firma fallida');
    const { access_token } = await verRes.json();

    poly.jwt = access_token;
    localStorage.setItem('vf_jwt', access_token);
    document.getElementById('auth-banner').classList.add('hidden');

    updateWalletUI();
    await loadBots();
  } catch (err) {
    if (err.code === 4001) { /* user rejected */ }
    else showError('Wallet connect failed: ' + (err.message || err));
    const btn = document.getElementById('wallet-btn');
    if (btn) { btn.disabled = false; btn.textContent = '🟢  Conectar Wallet'; }
  }
};

function updateWalletUI() {
  const btn  = document.getElementById('wallet-btn');
  const chip = document.getElementById('wallet-chip');
  if (!poly.address || !poly.jwt) {
    if (btn)  { btn.classList.remove('hidden'); btn.disabled = false; btn.textContent = '🟢  Conectar Wallet'; }
    if (chip) chip.classList.add('hidden');
  } else {
    if (btn)  btn.classList.add('hidden');
    if (chip) {
      chip.classList.remove('hidden');
      chip.textContent = poly.address.slice(0,6) + '…' + poly.address.slice(-4);
    }
  }
  updateLaunchOverlay();
}

function updateLaunchOverlay() {
  const overlay = document.getElementById('launch-overlay');
  if (!overlay) return;
  overlay.style.display = poly.jwt ? 'none' : 'flex';
}

// ── Load Bots ─────────────────────────────────────────────────────────────
async function loadBots() {
  try {
    const bots = await apiCall('GET', '/bots');
    poly.bots = {};
    for (const b of bots) {
      if (b.mode === 'polymarket') {
        poly.bots[b.id] = b;
        if (b.active) connectBotWS(b.id);
      }
    }
    renderMyBots();
  } catch (e) {
    showError('Error cargando bots: ' + (e.message || e));
  }
}

// ── WebSocket (live logs + events) ─────────────────────────────────────────
function connectBotWS(configId) {
  if (poly.sockets[configId]) return;
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const url   = `${proto}://${location.host}/trading/lp-hedge/api/ws/${configId}?token=${poly.jwt}`;
  const ws    = new WebSocket(url);
  poly.sockets[configId] = ws;

  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      if (data.event === 'ping') return;
      if (data.type === 'log') {
        prependFeedRow({ ts: data.ts, msg: data.msg, configId });
      } else if (data.event || data.event_type) {
        prependFeedRow({ ...data, configId });
      }
    } catch (_) {}
  };

  ws.onclose = () => {
    delete poly.sockets[configId];
    setTimeout(() => {
      const bot = poly.bots[configId];
      if (bot?.active && poly.jwt) connectBotWS(configId);
    }, 10_000);
  };

  ws.onerror = () => ws.close();
}

// ── Activity Feed ──────────────────────────────────────────────────────────
function prependFeedRow(data) {
  const feed = document.getElementById('activity-feed');
  if (!feed) return;

  const empty = feed.querySelector('.wt-empty');
  if (empty) empty.remove();

  const ts = (() => {
    try { return new Date(data.ts).toLocaleTimeString(); }
    catch (_) { return ''; }
  })();

  const evt = data.event || data.event_type || '';
  let body;
  if (data.msg) {
    body = `<span class="sig-asset">${escapeHtml(data.msg)}</span>`;
  } else {
    const color = { poly_entry: '#00d4ff', poly_tp: '#34d399', poly_sl: '#f87171',
                    started: '#9ca3af', error: '#f87171' }[evt] || '#9ca3af';
    const pnl = data.pnl != null
      ? ` <span style="color:${data.pnl >= 0 ? '#34d399' : '#f87171'}">PnL $${Number(data.pnl).toFixed(4)}</span>` : '';
    const price = data.price != null ? ` @ $${Number(data.price).toFixed(4)}` : '';
    body = `<span class="sig-evt" style="color:${color}">${evt.toUpperCase()}</span>
            <span class="sig-asset">#${data.configId}${price}</span>${pnl}`;
  }

  const div = document.createElement('div');
  div.innerHTML = `<div class="signal-row signal-row--new">
    <span class="sig-time">${ts}</span>${body}
  </div>`;
  const row = div.firstElementChild;
  feed.insertBefore(row, feed.firstChild);
  setTimeout(() => row.classList.remove('signal-row--new'), 800);

  while (feed.children.length > FEED_MAX) feed.removeChild(feed.lastChild);

  const updated = document.getElementById('feed-updated');
  if (updated) updated.textContent = 'Actualizado ' + new Date().toLocaleTimeString();
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// ── My Bots ────────────────────────────────────────────────────────────────
function renderMyBots() {
  const container = document.getElementById('my-bots-list');
  const hint      = document.getElementById('my-bots-auth-hint');
  if (!container) return;

  if (!poly.jwt) {
    if (hint) hint.style.display = 'inline';
    container.innerHTML = '';
    return;
  }
  if (hint) hint.style.display = 'none';

  const bots = Object.values(poly.bots);
  if (!bots.length) {
    container.innerHTML = `<p class="wt-muted">No tienes bots aún. Lanza uno abajo.</p>`;
    return;
  }

  container.innerHTML = bots.map(bot => {
    const isActive = bot.active;
    const statusDot = isActive
      ? `<span class="tracker-dot tracker-dot--on"></span>`
      : `<span class="tracker-dot tracker-dot--off"></span>`;
    const label = isActive ? 'ACTIVO' : 'DETENIDO';
    const labelColor = isActive ? '#34d399' : '#9ca3af';
    const token = bot.polymarket_token_id || '';
    const paper = bot.paper_trade ? '📋 paper · ' : '';
    const entry = bot.polymarket_entry_price ? `límite $${bot.polymarket_entry_price}` : 'mercado';

    return `<div class="tracker-card">
      <div class="tracker-card-left">
        ${statusDot}
        <div>
          <div class="tracker-card-title" title="${token}">
            ${paper}$${Number(bot.polymarket_size_usd || 0).toLocaleString()} · ${token.slice(0, 10)}…
          </div>
          <div class="tracker-card-sub" style="color:${labelColor}">
            ${label} · entrada ${entry} · TP $${bot.polymarket_tp_price} / SL $${bot.polymarket_sl_price} · ID ${bot.id}
          </div>
        </div>
      </div>
      <div class="tracker-card-actions">
        ${isActive
          ? `<button class="btn btn-sm wt-btn-stop" onclick="stopPolyBot(${bot.id})">■ Stop</button>`
          : `<button class="btn btn-sm wt-btn-start" onclick="restartPolyBot(${bot.id})">▶ Restart</button>`
        }
        <button class="btn btn-sm wt-btn-delete" onclick="deletePolyBot(${bot.id})">🗑</button>
      </div>
    </div>`;
  }).join('');
}

// ── Bot Controls ───────────────────────────────────────────────────────────
window.toggleLiveKeys = function () {
  const paper  = document.getElementById('poly-paper-trade')?.checked ?? true;
  const keysEl = document.getElementById('poly-live-keys');
  if (keysEl) keysEl.style.display = paper ? 'none' : 'block';
};

window.launchPolyBot = async function () {
  const btn = document.getElementById('poly-launch-btn');
  const err = document.getElementById('poly-launch-error');
  if (btn) { btn.disabled = true; btn.textContent = 'Launching…'; }
  if (err) err.textContent = '';

  try {
    const tokenId    = document.getElementById('poly-token-id')?.value.trim() || '';
    const sizeUsd    = parseFloat(document.getElementById('poly-size-usd')?.value || '0');
    const entryRaw   = document.getElementById('poly-entry-price')?.value.trim() || '';
    const tpPrice    = parseFloat(document.getElementById('poly-tp-price')?.value || '0');
    const slPrice    = parseFloat(document.getElementById('poly-sl-price')?.value || '0');
    const paperTrade = document.getElementById('poly-paper-trade')?.checked ?? true;

    if (!tokenId) throw new Error('Token ID es requerido');
    if (!(sizeUsd > 0)) throw new Error('Tamaño debe ser > 0');
    if (!(tpPrice > 0 && tpPrice < 1)) throw new Error('Take-profit debe estar entre 0 y 1');
    if (!(slPrice > 0 && slPrice < 1)) throw new Error('Stop-loss debe estar entre 0 y 1');
    if (tpPrice <= slPrice) throw new Error('Take-profit debe ser mayor que stop-loss');

    const payload = {
      mode:                 'polymarket',
      chain_id:             137,
      nft_token_id:         `poly-${Date.now()}`,
      pair:                 'POLY',
      lower_bound:          0,
      upper_bound:          0,
      polymarket_token_id:  tokenId,
      polymarket_side:      'buy',
      polymarket_size_usd:  sizeUsd,
      polymarket_tp_price:  tpPrice,
      polymarket_sl_price:  slPrice,
      paper_trade:          paperTrade,
    };
    if (entryRaw) payload.polymarket_entry_price = parseFloat(entryRaw);

    if (!paperTrade) {
      const funder = document.getElementById('poly-funder')?.value.trim() || '';
      const privKey = document.getElementById('poly-private-key')?.value.trim() || '';
      if (!funder || !privKey) throw new Error('Funder address y private key son requeridos en modo live');
      payload.hl_wallet_addr = funder;
      payload.hl_api_key     = privKey;
    }

    const res = await apiCall('POST', '/bots', payload);
    await apiCall('POST', `/bots/${res.id}/start`);
    await loadBots();
    connectBotWS(res.id);

    if (btn) { btn.disabled = false; btn.textContent = '🎯  Launch Polymarket Bot'; }
  } catch (e) {
    if (err) err.textContent = 'Launch failed: ' + (e.message || e);
    if (btn) { btn.disabled = false; btn.textContent = '🎯  Launch Polymarket Bot'; }
  }
};

window.restartPolyBot = async function (configId) {
  try {
    await apiCall('POST', `/bots/${configId}/start`);
    await loadBots();
    connectBotWS(configId);
  } catch (e) {
    showError('Restart failed: ' + (e.message || e));
  }
};

window.stopPolyBot = async function (configId) {
  try {
    await apiCall('POST', `/bots/${configId}/stop`);
    await loadBots();
  } catch (e) {
    showError('Stop failed: ' + (e.message || e));
  }
};

window.deletePolyBot = async function (configId) {
  if (!confirm('¿Eliminar este bot? Esta acción no puede deshacerse.')) return;
  try {
    await apiCall('DELETE', `/bots/${configId}`);
    delete poly.bots[configId];
    renderMyBots();
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
