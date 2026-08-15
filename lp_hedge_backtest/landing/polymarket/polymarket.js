'use strict';

// ── Config ─────────────────────────────────────────────────────────────────
const API_BASE = '/trading/lp-hedge/api';
const FEED_MAX = 50;
const LANG_KEY = 'vf_lang';   // same storage key as landing/i18n.js

// ── Page-local i18n ────────────────────────────────────────────────────────
// NOTE: page-local translation map (polymarket page only). Uses the same
// data-i18n attribute convention and the same localStorage key ('vf_lang')
// as landing/i18n.js, so merging these keys into i18n.js later is mechanical.
const I18N = {
  es: {
    'poly.connect':           '🟢  Conectar Wallet',
    'poly.connecting':        '⏳ Conectando…',
    'poly.hero.sub':          'Compra shares de un mercado de Polymarket y sal automáticamente: take-profit y stop-loss sintético vigilados cada pocos segundos.',
    'poly.auth.banner':       '🔒 Conecta tu wallet para gestionar tus bots. Los bots en ejecución siguen corriendo aunque tu sesión expire.',
    'poly.auth.connect':      'Conectar',
    'poly.feed.title':        '📡 Actividad en Vivo',
    'poly.feed.updated':      'Actualizado',
    'poly.feed.empty':        'Sin actividad aún — lanza un bot abajo.',
    'poly.bots.title':        '⚙️ Mis Bots',
    'poly.bots.hint':         'Conecta wallet para gestionar',
    'poly.bots.none':         'No tienes bots aún. Lanza uno abajo.',
    'poly.launch.title':      '🚀 Nuevo Bot',
    'poly.launch.overlay':    '🔒 Conecta tu wallet para lanzar un bot',
    'poly.form.token':        'Token ID del mercado',
    'poly.form.size':         'Tamaño (USDC)',
    'poly.form.entry':        'Precio de entrada (opcional)',
    'poly.form.entry_ph':     'vacío = mercado',
    'poly.form.tp':           'Take-profit',
    'poly.form.sl':           'Stop-loss',
    'poly.form.funder':       'Polygon funder address',
    'poly.form.privkey':      'Polygon private key',
    'poly.form.paper':        '📋 Paper mode (sin órdenes reales)',
    'poly.launch.btn':        '🎯  Launch Polymarket Bot',
    'poly.launch.launching':  '⏳ Lanzando…',
    'poly.status.active':     'ACTIVO',
    'poly.status.stopped':    'DETENIDO',
    'poly.btn.stop':          '■ Stop',
    'poly.btn.restart':       '▶ Restart',
    'poly.busy.stopping':     '⏳ Deteniendo…',
    'poly.busy.restarting':   '⏳ Reiniciando…',
    'poly.busy.deleting':     '⏳ …',
    'poly.confirm.stop':      '⚠️ ¿Detener este bot?\n\nLa posición queda ABIERTA en Polymarket — al detenerse, el bot solo deja de monitorearla y NUNCA vende. Para salir, hazlo manualmente en Polymarket o reinicia el bot.',
    'poly.confirm.delete':    '¿Eliminar este bot? Esta acción no puede deshacerse.',
    'poly.card.paper':        '📋 paper',
    'poly.card.entry':        'entrada',
    'poly.card.entry.market': 'mercado',
    'poly.card.entry.limit':  'límite',
    'poly.error.load_bots':   'Error cargando bots',
    'poly.error.launch':      'Launch failed',
    'poly.error.stop':        'Stop failed',
    'poly.error.restart':     'Restart failed',
    'poly.error.delete':      'Delete failed',
    'poly.error.no_wallet':   'No se detectó wallet. Instala Rabby o MetaMask.',
    'poly.error.connect':     'Wallet connect failed',
    'poly.err.token_required':'Token ID es requerido',
    'poly.err.size':          'Tamaño debe ser > 0',
    'poly.err.tp_range':      'Take-profit debe estar entre 0 y 1',
    'poly.err.sl_range':      'Stop-loss debe estar entre 0 y 1',
    'poly.err.tp_gt_sl':      'Take-profit debe ser mayor que stop-loss',
    'poly.err.keys_required': 'Funder address y private key son requeridos en modo live',
    'poly.ws.live':           'En vivo',
    'poly.ws.reconnecting':   'Reconectando…',
    'poly.ws.offline':        'Sin conexión',
  },
  en: {
    'poly.connect':           '🟢  Connect Wallet',
    'poly.connecting':        '⏳ Connecting…',
    'poly.hero.sub':          'Buy shares in a Polymarket market and exit automatically: take-profit and synthetic stop-loss watched every few seconds.',
    'poly.auth.banner':       '🔒 Connect your wallet to manage your bots. Bots that are already running keep running even if your session expires.',
    'poly.auth.connect':      'Connect',
    'poly.feed.title':        '📡 Live Activity',
    'poly.feed.updated':      'Updated',
    'poly.feed.empty':        'No activity yet — launch a bot below.',
    'poly.bots.title':        '⚙️ My Bots',
    'poly.bots.hint':         'Connect wallet to manage',
    'poly.bots.none':         'No bots yet. Launch one below.',
    'poly.launch.title':      '🚀 New Bot',
    'poly.launch.overlay':    '🔒 Connect your wallet to launch a bot',
    'poly.form.token':        'Market token ID',
    'poly.form.size':         'Size (USDC)',
    'poly.form.entry':        'Entry price (optional)',
    'poly.form.entry_ph':     'empty = market',
    'poly.form.tp':           'Take-profit',
    'poly.form.sl':           'Stop-loss',
    'poly.form.funder':       'Polygon funder address',
    'poly.form.privkey':      'Polygon private key',
    'poly.form.paper':        '📋 Paper mode (no real orders)',
    'poly.launch.btn':        '🎯  Launch Polymarket Bot',
    'poly.launch.launching':  '⏳ Launching…',
    'poly.status.active':     'ACTIVE',
    'poly.status.stopped':    'STOPPED',
    'poly.btn.stop':          '■ Stop',
    'poly.btn.restart':       '▶ Restart',
    'poly.busy.stopping':     '⏳ Stopping…',
    'poly.busy.restarting':   '⏳ Restarting…',
    'poly.busy.deleting':     '⏳ …',
    'poly.confirm.stop':      '⚠️ Stop this bot?\n\nThe position stays OPEN on Polymarket — on stop the bot only stops monitoring it and NEVER sells. To exit, do it manually on Polymarket or restart the bot.',
    'poly.confirm.delete':    'Delete this bot? This action cannot be undone.',
    'poly.card.paper':        '📋 paper',
    'poly.card.entry':        'entry',
    'poly.card.entry.market': 'market',
    'poly.card.entry.limit':  'limit',
    'poly.error.load_bots':   'Error loading bots',
    'poly.error.launch':      'Launch failed',
    'poly.error.stop':        'Stop failed',
    'poly.error.restart':     'Restart failed',
    'poly.error.delete':      'Delete failed',
    'poly.error.no_wallet':   'No wallet detected. Install Rabby or MetaMask.',
    'poly.error.connect':     'Wallet connect failed',
    'poly.err.token_required':'Token ID is required',
    'poly.err.size':          'Size must be > 0',
    'poly.err.tp_range':      'Take-profit must be between 0 and 1',
    'poly.err.sl_range':      'Stop-loss must be between 0 and 1',
    'poly.err.tp_gt_sl':      'Take-profit must be greater than stop-loss',
    'poly.err.keys_required': 'Funder address and private key are required in live mode',
    'poly.ws.live':           'Live',
    'poly.ws.reconnecting':   'Reconnecting…',
    'poly.ws.offline':        'Offline',
  },
};

let pageLang = localStorage.getItem(LANG_KEY) || 'es';

function t(key) {
  return I18N[pageLang]?.[key] ?? I18N.en[key] ?? key;
}

function applyLang() {
  document.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => { el.placeholder = t(el.dataset.i18nPlaceholder); });
  document.documentElement.lang = pageLang;
  document.getElementById('lang-es')?.classList.toggle('active', pageLang === 'es');
  document.getElementById('lang-en')?.classList.toggle('active', pageLang === 'en');
}

window.setLang = function (lang) {
  if (!I18N[lang] || lang === pageLang) return;
  pageLang = lang;
  localStorage.setItem(LANG_KEY, lang);
  applyLang();
  // Re-render JS-built strings so they follow the new language
  updateWalletUI();
  renderMyBots();
  refreshWsIndicator();
};

// ── State ──────────────────────────────────────────────────────────────────
const poly = {
  jwt:     localStorage.getItem('vf_jwt') || null,
  address: null,
  provider: null,
  bots:    {},      // config_id → BotConfigOut
  sockets: {},      // config_id → WebSocket
  wsState: {},      // config_id → 'connecting' | 'live' | 'reconnecting'
  feedKeys: new Set(),     // dedupe between history backfill and WS pushes
  historyLoaded: new Set(), // config_ids whose event history was backfilled
};

let _initComplete = false;

// ── Boot ───────────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', async () => {
  applyLang();
  registerWalletListeners();
  updateWalletUI();
  if (poly.jwt) {
    // Silently pick up the already-connected account so the chip shows and
    // later accountsChanged events compare against the right address.
    if (window.ethereum) {
      try {
        const accts = await window.ethereum.request({ method: 'eth_accounts' });
        if (accts.length) { poly.address = accts[0]; updateWalletUI(); }
      } catch (_) {}
    }
    await loadBots();
  } else {
    document.getElementById('auth-banner').classList.remove('hidden');
    renderMyBots();
    updateLaunchOverlay();
  }
  refreshWsIndicator();
  _initComplete = true;
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
    const err = new Error('Session expired — please sign in again.');
    err.sessionExpired = true;
    throw err;
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
    showError(t('poly.error.no_wallet'));
    return;
  }
  try {
    const btn = document.getElementById('wallet-btn');
    if (btn) { btn.disabled = true; btn.textContent = t('poly.connecting'); }

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
    else showError(t('poly.error.connect') + ': ' + (err.message || err));
    const btn = document.getElementById('wallet-btn');
    if (btn) { btn.disabled = false; btn.textContent = t('poly.connect'); }
  }
};

// ── Wallet account / chain change handling ────────────────────────────────
function closeAllSockets() {
  for (const ws of Object.values(poly.sockets)) { try { ws.close(); } catch (_) {} }
  poly.sockets = {};
  poly.wsState = {};
  refreshWsIndicator();
}

function handleSignedOut() {
  poly.jwt     = null;
  poly.address = null;
  poly.bots    = {};
  localStorage.removeItem('vf_jwt');
  closeAllSockets();
  updateWalletUI();
  renderMyBots();
  updateLaunchOverlay();
  document.getElementById('auth-banner').classList.remove('hidden');
}

function handleAccountsChanged(accounts) {
  if (!accounts.length) {
    // Rabby and MetaMask briefly fire accountsChanged([]) mid-switch before
    // resolving to the new account. Debounce 300 ms — if an account arrives
    // within that window it was a transient switch, not a real disconnect.
    // Also: never fire during page init — wait until _initComplete.
    setTimeout(() => {
      if (!window._pendingAccount && _initComplete) handleSignedOut();
      window._pendingAccount = false;
    }, 300);
    return;
  }
  window._pendingAccount = true;
  const incoming = accounts[0].toLowerCase();
  const current  = poly.address ? poly.address.toLowerCase() : null;

  // Account actually changed → the old JWT belongs to the previous wallet;
  // clear it so the new account re-authenticates.
  if (current && incoming !== current) {
    poly.jwt = null;
    localStorage.removeItem('vf_jwt');
    poly.bots = {};
    closeAllSockets();
    document.getElementById('auth-banner').classList.remove('hidden');
  }

  poly.address = accounts[0];
  updateWalletUI();
  if (poly.jwt) loadBots();
  else { renderMyBots(); updateLaunchOverlay(); }
}

function handleChainChanged() {
  // Brief delay — some wallets are still finalising the chain switch when
  // this event fires; recreating the provider immediately can hit the old chain.
  setTimeout(() => {
    if (window.ethereum) poly.provider = new ethers.BrowserProvider(window.ethereum);
    if (poly.jwt) loadBots();
  }, 150);
}

function registerWalletListeners() {
  if (!window.ethereum) return;
  window.ethereum.removeListener('accountsChanged', handleAccountsChanged);
  window.ethereum.removeListener('chainChanged', handleChainChanged);
  window.ethereum.on('accountsChanged', handleAccountsChanged);
  window.ethereum.on('chainChanged', handleChainChanged);
}

function updateWalletUI() {
  const btn  = document.getElementById('wallet-btn');
  const chip = document.getElementById('wallet-chip');
  if (!poly.address || !poly.jwt) {
    if (btn)  { btn.classList.remove('hidden'); btn.disabled = false; btn.textContent = t('poly.connect'); }
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
    // Prune WS state for bots that stopped or disappeared
    for (const id of Object.keys(poly.wsState)) {
      if (!poly.bots[id]?.active) delete poly.wsState[id];
    }
    renderMyBots();
    refreshWsIndicator();
    backfillHistory();
  } catch (e) {
    // On 401 the auth banner is already shown — don't double-report.
    if (e?.sessionExpired) return;
    showError(t('poly.error.load_bots') + ': ' + (e.message || e));
  }
}

// ── Event history backfill ─────────────────────────────────────────────────
// WS pushes only show events emitted while the page is open. Backfill the
// last 50 persisted events per active bot so the feed survives a reload.
async function backfillHistory() {
  const ids = Object.values(poly.bots)
    .filter(b => b.active && !poly.historyLoaded.has(b.id))
    .map(b => b.id);
  if (!ids.length) return;
  for (const id of ids) poly.historyLoaded.add(id);

  const results = await Promise.all(ids.map(async id => {
    try {
      const res = await apiCall('GET', `/bots/${id}/events?limit=50`);
      // Endpoint returns a plain array today; tolerate a future
      // { events, total } envelope shape.
      const rows = Array.isArray(res) ? res : (res.events || res.items || []);
      return rows.map(ev => ({
        event:    ev.event_type,
        price:    ev.price_at_event,
        pnl:      ev.pnl,
        details:  ev.details || {},
        ts:       ev.ts,
        configId: id,
      }));
    } catch (_) { return []; }
  }));

  // Newest first; appended below any live WS rows already in the feed
  const rows = results.flat().sort((a, b) => (a.ts < b.ts ? 1 : -1));
  for (const row of rows) appendFeedRow(row);
}

// ── WebSocket (live logs + events) ─────────────────────────────────────────
function connectBotWS(configId) {
  if (poly.sockets[configId]) return;
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const url   = `${proto}://${location.host}/trading/lp-hedge/api/ws/${configId}?token=${poly.jwt}`;
  const ws    = new WebSocket(url);
  poly.sockets[configId] = ws;
  poly.wsState[configId] = 'connecting';
  refreshWsIndicator();

  ws.onopen = () => {
    poly.wsState[configId] = 'live';
    refreshWsIndicator();
  };

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
    const bot = poly.bots[configId];
    if (bot?.active && poly.jwt) {
      poly.wsState[configId] = 'reconnecting';
      refreshWsIndicator();
      setTimeout(() => {
        const b = poly.bots[configId];
        if (b?.active && poly.jwt) {
          connectBotWS(configId);
        } else {
          delete poly.wsState[configId];
          refreshWsIndicator();
        }
      }, 10_000);
    } else {
      delete poly.wsState[configId];
      refreshWsIndicator();
    }
  };

  ws.onerror = () => ws.close();
}

// ── WS connection status indicator ─────────────────────────────────────────
function refreshWsIndicator() {
  const el = document.getElementById('ws-status');
  if (!el) return;
  const states = Object.values(poly.wsState);
  let cls, key;
  if (states.includes('live')) {
    cls = 'ws-status--live';      key = 'poly.ws.live';
  } else if (states.length) {
    cls = 'ws-status--reconnect'; key = 'poly.ws.reconnecting';
  } else {
    cls = 'ws-status--off';       key = 'poly.ws.offline';
  }
  el.className = 'ws-status ' + cls;
  const txt = el.querySelector('.ws-status-text');
  if (txt) txt.textContent = t(key);
}

// ── Activity Feed ──────────────────────────────────────────────────────────
function feedKey(data) {
  return `${data.ts}|${data.event || data.event_type || ''}|${data.msg || ''}`;
}

function buildFeedRowHTML(data) {
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
                    started: '#9ca3af', stopped: '#9ca3af', error: '#f87171' }[evt] || '#9ca3af';
    const pnl = data.pnl != null
      ? ` <span style="color:${data.pnl >= 0 ? '#34d399' : '#f87171'}">PnL $${Number(data.pnl).toFixed(4)}</span>` : '';
    const price = data.price != null ? ` @ $${Number(data.price).toFixed(4)}` : '';
    // Human-readable detail persisted/broadcast with the event (errors etc.)
    const det = data.details || {};
    const detailMsg = det.msg || det.event_label || '';
    const msgHtml = detailMsg ? `<span class="sig-msg">${escapeHtml(detailMsg)}</span>` : '';
    body = `<span class="sig-evt" style="color:${color}">${evt.toUpperCase()}</span>
            <span class="sig-asset">#${data.configId}${price}</span>${pnl}${msgHtml}`;
  }

  return `<div class="signal-row">
    <span class="sig-time">${ts}</span>${body}
  </div>`;
}

function renderFeedRow(data, { prepend }) {
  const feed = document.getElementById('activity-feed');
  if (!feed) return;

  const key = feedKey(data);
  if (poly.feedKeys.has(key)) return;
  poly.feedKeys.add(key);

  const empty = feed.querySelector('.wt-empty');
  if (empty) empty.remove();

  const div = document.createElement('div');
  div.innerHTML = buildFeedRowHTML(data);
  const row = div.firstElementChild;
  if (prepend) {
    row.classList.add('signal-row--new');
    feed.insertBefore(row, feed.firstChild);
    setTimeout(() => row.classList.remove('signal-row--new'), 800);
  } else {
    feed.appendChild(row);
  }

  while (feed.children.length > FEED_MAX) feed.removeChild(feed.lastChild);

  const updated = document.getElementById('feed-updated');
  if (updated) updated.textContent = t('poly.feed.updated') + ' ' + new Date().toLocaleTimeString();
}

function prependFeedRow(data) { renderFeedRow(data, { prepend: true }); }
function appendFeedRow(data)  { renderFeedRow(data, { prepend: false }); }

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
    container.innerHTML = `<p class="wt-muted">${t('poly.bots.none')}</p>`;
    return;
  }

  container.innerHTML = bots.map(bot => {
    const isActive = bot.active;
    const statusDot = isActive
      ? `<span class="tracker-dot tracker-dot--on"></span>`
      : `<span class="tracker-dot tracker-dot--off"></span>`;
    const label = isActive ? t('poly.status.active') : t('poly.status.stopped');
    const labelColor = isActive ? '#34d399' : '#9ca3af';
    const token = bot.polymarket_token_id || '';
    const sizeUsd = Number(bot.polymarket_size_usd || 0);
    // Share prices (0–1) read naturally as outcome percentages
    const tpPct = bot.polymarket_tp_price != null ? Math.round(bot.polymarket_tp_price * 100) : null;
    const slPct = bot.polymarket_sl_price != null ? Math.round(bot.polymarket_sl_price * 100) : null;
    const paper = bot.paper_trade ? t('poly.card.paper') + ' · ' : '';
    const entry = bot.polymarket_entry_price
      ? `${t('poly.card.entry.limit')} $${bot.polymarket_entry_price}`
      : t('poly.card.entry.market');
    const created = (() => {
      try { return new Date(bot.created_at).toLocaleDateString(); }
      catch (_) { return ''; }
    })();

    return `<div class="tracker-card">
      <div class="tracker-card-left">
        ${statusDot}
        <div>
          <div class="tracker-card-title" title="${token}">
            ${paper}$${sizeUsd.toLocaleString()} · TP ${tpPct ?? '?'}% / SL ${slPct ?? '?'}% · ${token.slice(0, 10)}…
          </div>
          <div class="tracker-card-sub" style="color:${labelColor}">
            ${label} · ${t('poly.card.entry')} ${entry} · ID ${bot.id}${created ? ' · ' + created : ''}
          </div>
        </div>
      </div>
      <div class="tracker-card-actions">
        ${isActive
          ? `<button class="btn btn-sm wt-btn-stop" onclick="stopPolyBot(${bot.id}, this)">${t('poly.btn.stop')}</button>`
          : `<button class="btn btn-sm wt-btn-start" onclick="restartPolyBot(${bot.id}, this)">${t('poly.btn.restart')}</button>`
        }
        <button class="btn btn-sm wt-btn-delete" onclick="deletePolyBot(${bot.id}, this)">🗑</button>
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
  if (btn) { btn.disabled = true; btn.textContent = t('poly.launch.launching'); }
  if (err) err.textContent = '';

  try {
    const tokenId    = document.getElementById('poly-token-id')?.value.trim() || '';
    const sizeUsd    = parseFloat(document.getElementById('poly-size-usd')?.value || '0');
    const entryRaw   = document.getElementById('poly-entry-price')?.value.trim() || '';
    const tpPrice    = parseFloat(document.getElementById('poly-tp-price')?.value || '0');
    const slPrice    = parseFloat(document.getElementById('poly-sl-price')?.value || '0');
    const paperTrade = document.getElementById('poly-paper-trade')?.checked ?? true;

    if (!tokenId) throw new Error(t('poly.err.token_required'));
    if (!(sizeUsd > 0)) throw new Error(t('poly.err.size'));
    if (!(tpPrice > 0 && tpPrice < 1)) throw new Error(t('poly.err.tp_range'));
    if (!(slPrice > 0 && slPrice < 1)) throw new Error(t('poly.err.sl_range'));
    if (tpPrice <= slPrice) throw new Error(t('poly.err.tp_gt_sl'));

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
      if (!funder || !privKey) throw new Error(t('poly.err.keys_required'));
      payload.hl_wallet_addr = funder;
      payload.hl_api_key     = privKey;
    }

    const res = await apiCall('POST', '/bots', payload);
    await apiCall('POST', `/bots/${res.id}/start`);
    await loadBots();
    connectBotWS(res.id);

    if (btn) { btn.disabled = false; btn.textContent = t('poly.launch.btn'); }
  } catch (e) {
    if (err) err.textContent = t('poly.error.launch') + ': ' + (e.message || e);
    if (btn) { btn.disabled = false; btn.textContent = t('poly.launch.btn'); }
  }
};

window.restartPolyBot = async function (configId, btn) {
  if (btn) { btn.disabled = true; btn.textContent = t('poly.busy.restarting'); }
  try {
    await apiCall('POST', `/bots/${configId}/start`);
    await loadBots();
    connectBotWS(configId);
  } catch (e) {
    if (!e?.sessionExpired) showError(t('poly.error.restart') + ': ' + (e.message || e));
    if (btn) { btn.disabled = false; btn.textContent = t('poly.btn.restart'); }
  }
};

window.stopPolyBot = async function (configId, btn) {
  if (!confirm(t('poly.confirm.stop'))) return;
  if (btn) { btn.disabled = true; btn.textContent = t('poly.busy.stopping'); }
  try {
    await apiCall('POST', `/bots/${configId}/stop`);
    await loadBots();
  } catch (e) {
    if (!e?.sessionExpired) showError(t('poly.error.stop') + ': ' + (e.message || e));
    if (btn) { btn.disabled = false; btn.textContent = t('poly.btn.stop'); }
  }
};

window.deletePolyBot = async function (configId, btn) {
  if (!confirm(t('poly.confirm.delete'))) return;
  if (btn) { btn.disabled = true; btn.textContent = t('poly.busy.deleting'); }
  try {
    await apiCall('DELETE', `/bots/${configId}`);
    delete poly.bots[configId];
    renderMyBots();
  } catch (e) {
    if (!e?.sessionExpired) showError(t('poly.error.delete') + ': ' + (e.message || e));
    if (btn) { btn.disabled = false; btn.textContent = '🗑'; }
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
