'use strict';

// ── Config ─────────────────────────────────────────────────────────────────
const API_BASE         = '/trading/lp-hedge/api';
const WHALE_SIGNAL_MAX = 50;
const LOG_MAX          = 50;

// ── i18n (central module: ../i18n.js, loaded before this script) ──────────
// Translations live in landing/i18n.js (keys prefixed 'whale.*'); it exposes
// window.t / window.setLanguage / window.currentLang and persists to the
// 'vf_lang' localStorage key. These thin wrappers only add the page-specific
// pieces the central module doesn't know about: the #lang-es/#lang-en toggle
// classes and re-rendering JS-built strings on language switch.
function t(key) { return window.t(key); }

function applyLang() {
  window.applyTranslations();
  document.getElementById('lang-es')?.classList.toggle('active', window.currentLang === 'es');
  document.getElementById('lang-en')?.classList.toggle('active', window.currentLang === 'en');
}

window.setLang = function (lang) {
  if (lang === window.currentLang) return;
  window.setLanguage(lang);   // persists vf_lang + applies data-i18n strings
  applyLang();                // toggle the page's lang buttons
  // Re-render JS-built strings so they follow the new language
  updateWalletUI();
  renderMyTrackers();
  renderSignalsFeed();
  updateStats();
  refreshWsIndicator();
};

// ── State ──────────────────────────────────────────────────────────────────
const whale = {
  jwt:          localStorage.getItem('vf_jwt') || null,
  address:      null,
  provider:     null,
  bots:         {},          // config_id → BotConfigOut
  sockets:      {},          // config_id → WebSocket
  wsState:      {},          // config_id → 'connecting' | 'live' | 'reconnecting'
  signals:      {},          // config_id → array (live via WS)
  publicSignals: [],         // from public endpoint (no auth)
};

let _initComplete = false;

// ── Boot ───────────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', async () => {
  applyLang();
  registerWalletListeners();
  updateWalletUI();
  loadPublicWhaleSignals();
  setInterval(loadPublicWhaleSignals, 30_000);

  if (whale.jwt) {
    // Silently pick up the already-connected account so the chip shows and
    // later accountsChanged events compare against the right address.
    if (window.ethereum) {
      try {
        const accts = await window.ethereum.request({ method: 'eth_accounts' });
        if (accts.length) { whale.address = accts[0]; updateWalletUI(); }
      } catch (_) {}
    }
    await loadBots();
  } else {
    document.getElementById('auth-banner').classList.remove('hidden');
    renderMyTrackers();
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
    showError(t('whale.error.no_wallet'));
    return;
  }
  try {
    const btn = document.getElementById('wallet-btn');
    if (btn) { btn.disabled = true; btn.textContent = t('whale.connecting'); }

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
    else showError(t('whale.error.connect') + ': ' + (err.message || err));
    const btn = document.getElementById('wallet-btn');
    if (btn) { btn.disabled = false; btn.textContent = t('whale.connect'); }
  }
};

// ── Wallet account / chain change handling ────────────────────────────────
function closeAllSockets() {
  for (const ws of Object.values(whale.sockets)) { try { ws.close(); } catch (_) {} }
  whale.sockets = {};
  whale.wsState = {};
  refreshWsIndicator();
}

function handleSignedOut() {
  whale.jwt     = null;
  whale.address = null;
  whale.bots    = {};
  localStorage.removeItem('vf_jwt');
  closeAllSockets();
  updateWalletUI();
  renderMyTrackers();
  updateLaunchOverlay();
  updateStats();
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
  const current  = whale.address ? whale.address.toLowerCase() : null;

  // Account actually changed → the old JWT belongs to the previous wallet;
  // clear it so the new account re-authenticates.
  if (current && incoming !== current) {
    whale.jwt = null;
    localStorage.removeItem('vf_jwt');
    whale.bots = {};
    closeAllSockets();
    document.getElementById('auth-banner').classList.remove('hidden');
  }

  whale.address = accounts[0];
  updateWalletUI();
  if (whale.jwt) loadBots();
  else { renderMyTrackers(); updateLaunchOverlay(); }
}

function handleChainChanged() {
  // Brief delay — some wallets are still finalising the chain switch when
  // this event fires; recreating the provider immediately can hit the old chain.
  setTimeout(() => {
    if (window.ethereum) whale.provider = new ethers.BrowserProvider(window.ethereum);
    if (whale.jwt) loadBots();
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
  if (!whale.address || !whale.jwt) {
    if (btn)  { btn.classList.remove('hidden'); btn.disabled = false; btn.textContent = t('whale.connect'); }
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
    // Prune WS state for bots that stopped or disappeared
    for (const id of Object.keys(whale.wsState)) {
      if (!whale.bots[id]?.active) delete whale.wsState[id];
    }
    renderMyTrackers();
    updateStats();
    refreshWsIndicator();
  } catch (e) {
    // On 401 the auth banner is already shown — don't double-report.
    if (e?.sessionExpired) return;
    showError(t('whale.error.load_bots') + ': ' + (e.message || e));
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
  whale.wsState[configId] = 'connecting';
  refreshWsIndicator();

  ws.onopen = () => {
    whale.wsState[configId] = 'live';
    refreshWsIndicator();
  };

  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      if (data.event === 'ping') return;
      const evt = data.event || data.event_type || '';
      // Broadcast payloads nest the bot's payload under `details` — merge it
      // so live rows have the same shape as the public history endpoint.
      const row = { ...(data.details || {}), ...data };
      if (evt.startsWith('whale_') && evt !== 'whale_snapshot') {
        if (!whale.signals[configId]) whale.signals[configId] = [];
        whale.signals[configId].unshift(row);
        if (whale.signals[configId].length > WHALE_SIGNAL_MAX)
          whale.signals[configId].pop();
        prependSignalRow(row, configId);
        updateStats();
      } else if (evt === 'error') {
        // Surface bot errors in the feed — details.msg carries the message.
        if (!whale.signals[configId]) whale.signals[configId] = [];
        whale.signals[configId].unshift(row);
        prependSignalRow(row, configId);
      }
    } catch (_) {}
  };

  ws.onclose = () => {
    delete whale.sockets[configId];
    const bot = whale.bots[configId];
    if (bot?.active && whale.jwt) {
      whale.wsState[configId] = 'reconnecting';
      refreshWsIndicator();
      setTimeout(() => {
        const b = whale.bots[configId];
        if (b?.active && whale.jwt) {
          connectBotWS(configId);
        } else {
          delete whale.wsState[configId];
          refreshWsIndicator();
        }
      }, 10_000);
    } else {
      delete whale.wsState[configId];
      refreshWsIndicator();
    }
  };

  ws.onerror = () => ws.close();
}

// ── WS connection status indicator ─────────────────────────────────────────
function refreshWsIndicator() {
  const el = document.getElementById('ws-status');
  if (!el) return;
  const states = Object.values(whale.wsState);
  let cls, key;
  if (states.includes('live')) {
    cls = 'ws-status--live';      key = 'whale.ws.live';
  } else if (states.length) {
    cls = 'ws-status--reconnect'; key = 'whale.ws.reconnecting';
  } else {
    cls = 'ws-status--off';       key = 'whale.ws.offline';
  }
  el.className = 'ws-status ' + cls;
  const txt = el.querySelector('.ws-status-text');
  if (txt) txt.textContent = t(key);
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
    feed.innerHTML = `<div class="wt-empty"><div class="wt-empty-icon">🌊</div><p>${t('whale.feed.empty')}</p></div>`;
    return;
  }

  feed.innerHTML = allSignals.map(s => buildSignalRowHTML(s)).join('');

  const updated = document.getElementById('signals-updated');
  if (updated) updated.textContent = t('whale.feed.updated') + ' ' + new Date().toLocaleTimeString();
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
  if (updated) updated.textContent = t('whale.feed.updated') + ' ' + new Date().toLocaleTimeString();
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function buildSignalRowHTML(s) {
  const evtRaw   = s.event_type || s.event || '';
  const det      = s.details || {};
  const evt      = evtRaw.replace('whale_','').replace(/_/g,' ').toUpperCase();
  const side     = (s.side || '').toUpperCase();
  const asset    = s.asset || '—';
  const sizeUsd  = Number(s.size_usd || 0);
  const deltaUsd = s.delta_usd != null ? Number(s.delta_usd) : null;
  const addr     = s.address || '';
  const ts       = (() => {
    try { return new Date(String(s.ts).replace(/[+-]\d{2}:\d{2}$/, '')).toLocaleTimeString(); }
    catch(_) { return s.ts || ''; }
  })();
  // Human-readable detail for error / unmapped events
  const msg = s.msg || det.msg || det.event_label || '';

  const evtColor = { whale_new_position:'#00d4ff', whale_closed:'#9ca3af',
    whale_flip:'#f59e0b', whale_size_increase:'#34d399', whale_size_decrease:'#f87171',
    error:'#f87171' }[evtRaw] || '#9ca3af';
  const sideColor = side === 'LONG' ? '#34d399' : side === 'SHORT' ? '#f87171' : '#9ca3af';
  const sideArrow = side === 'LONG' ? '▲' : side === 'SHORT' ? '▼' : '';
  const sz   = sizeUsd ? `$${sizeUsd.toLocaleString('en-US',{maximumFractionDigits:0})}` : '—';
  const delta = deltaUsd != null
    ? `<span style="color:${deltaUsd>=0?'#34d399':'#f87171'}">${deltaUsd>=0?'▲':'▼'}$${Math.abs(deltaUsd).toLocaleString('en-US',{maximumFractionDigits:0})}</span>` : '';
  const addrHtml = addr
    ? `<span class="sig-addr" title="${addr}" onclick="navigator.clipboard?.writeText('${addr}')">${addr.slice(0,6)}…${addr.slice(-4)}</span>` : '';
  const msgHtml = msg ? `<span class="sig-msg">${escapeHtml(msg)}</span>` : '';

  return `<div class="signal-row">
    <span class="sig-time">${ts}</span>
    <span class="sig-evt" style="color:${evtColor}">${evt}</span>
    <span class="sig-asset">${asset}</span>
    <span class="sig-side" style="color:${sideColor}">${sideArrow} ${side||'—'}</span>
    <span class="sig-size">${sz}</span>
    ${delta ? `<span class="sig-delta">${delta}</span>` : '<span></span>'}
    ${addrHtml}
    ${msgHtml}
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
    container.innerHTML = `<p class="wt-muted">${t('whale.trackers.none')}</p>`;
    return;
  }

  container.innerHTML = bots.map(bot => {
    const isActive = bot.active;
    const statusDot = isActive
      ? `<span class="tracker-dot tracker-dot--on"></span>`
      : `<span class="tracker-dot tracker-dot--off"></span>`;
    const label = isActive ? t('whale.status.active') : t('whale.status.stopped');
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
          ? `<button class="btn btn-sm wt-btn-stop" onclick="stopWhaleBot(${bot.id}, this)">${t('whale.btn.stop')}</button>`
          : `<button class="btn btn-sm wt-btn-start" onclick="restartWhaleBot(${bot.id}, this)">${t('whale.btn.restart')}</button>`
        }
        <button class="btn btn-sm wt-btn-delete" onclick="deleteWhaleBot(${bot.id}, this)">🗑</button>
      </div>
    </div>`;
  }).join('');
}

// ── Stats Bar ──────────────────────────────────────────────────────────────
function updateStats() {
  // Only actual whale signals count — error rows are excluded
  const isSignal = s => (s.event_type || s.event || '') !== 'error';
  const allSignals = [
    ...Object.values(whale.signals).flat(),
    ...whale.publicSignals,
  ].filter(isSignal);

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
  if (btn) { btn.disabled = true; btn.textContent = t('whale.launch.launching'); }
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

    if (btn) { btn.disabled = false; btn.textContent = t('whale.launch.btn'); }
  } catch (e) {
    if (err) err.textContent = t('whale.error.launch') + ': ' + (e.message || e);
    if (btn) { btn.disabled = false; btn.textContent = t('whale.launch.btn'); }
  }
};

window.restartWhaleBot = async function (configId, btn) {
  if (btn) { btn.disabled = true; btn.textContent = t('whale.busy.restarting'); }
  try {
    await apiCall('POST', `/bots/${configId}/start`);
    await loadBots();
    connectBotWS(configId);
  } catch (e) {
    if (!e?.sessionExpired) showError(t('whale.error.restart') + ': ' + (e.message || e));
    if (btn) { btn.disabled = false; btn.textContent = t('whale.btn.restart'); }
  }
};

window.stopWhaleBot = async function (configId, btn) {
  if (!confirm(t('whale.confirm.stop'))) return;
  if (btn) { btn.disabled = true; btn.textContent = t('whale.busy.stopping'); }
  try {
    await apiCall('POST', `/bots/${configId}/stop`);
    await loadBots();
  } catch (e) {
    if (!e?.sessionExpired) showError(t('whale.error.stop') + ': ' + (e.message || e));
    if (btn) { btn.disabled = false; btn.textContent = t('whale.btn.stop'); }
  }
};

window.deleteWhaleBot = async function (configId, btn) {
  if (!confirm(t('whale.confirm.delete'))) return;
  if (btn) { btn.disabled = true; btn.textContent = t('whale.busy.deleting'); }
  try {
    await apiCall('DELETE', `/bots/${configId}`);
    delete whale.bots[configId];
    renderMyTrackers();
    updateStats();
  } catch (e) {
    if (!e?.sessionExpired) showError(t('whale.error.delete') + ': ' + (e.message || e));
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
