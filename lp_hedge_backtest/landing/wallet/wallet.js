/* ============================================================
   VIZNIAGO — Wallet Manager v2  (Stage 1)
   ============================================================ */

'use strict';

const API_BASE = '/trading/lp-hedge/api';

const CHAIN_LABELS = {
  42161: 'ARB',
  1:     'ETH',
  8453:  'BASE',
};

// ── State ──────────────────────────────────────────────────
let _jwt      = localStorage.getItem('vf_jwt') || null;
let _address  = null;   // connected wallet address (checksummed)
let _bots     = [];     // BotConfigOut[]
let _balances = {};     // tokenId → { value, error }
let _statuses = {};     // botId → { running: bool }  (only fetched for active bots)
let _editOpen = {};     // tokenId → 'edit' | 'link' | 'remove' | null

// ── API helper ─────────────────────────────────────────────
async function apiFetch(path, opts = {}) {
  const res = await fetch(API_BASE + path, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(_jwt ? { Authorization: `Bearer ${_jwt}` } : {}),
      ...(opts.headers || {}),
    },
  });
  if (res.status === 401) {
    _clearSession();
    renderPage();
    throw new Error('Session expired — please sign in again');
  }
  return res;
}

// ── Auth ───────────────────────────────────────────────────
function _clearSession() {
  _jwt      = null;
  _address  = null;
  _bots     = [];
  _balances = {};
  _statuses = {};
  _editOpen = {};
  localStorage.removeItem('vf_jwt');
}

window.wmConnect = async function () {
  if (!window.ethereum) {
    _showError('No wallet detected. Install MetaMask or a compatible browser wallet.');
    return;
  }
  try {
    const btn = document.getElementById('wm-signin-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Connecting…'; }

    const provider = new ethers.BrowserProvider(window.ethereum);
    const accounts = await provider.send('eth_requestAccounts', []);
    if (!accounts.length) throw new Error('No accounts returned');

    _address = ethers.getAddress(accounts[0]);

    // Nonce → sign → JWT
    const nonceRes = await fetch(`${API_BASE}/auth/nonce?address=${_address}`);
    if (!nonceRes.ok) throw new Error('Could not get sign-in nonce');
    const { nonce } = await nonceRes.json();

    const signer    = await provider.getSigner();
    const message   = `Sign in to VIZNIAGO FURY\nNonce: ${nonce}`;
    const signature = await signer.signMessage(message);

    const verRes = await fetch(`${API_BASE}/auth/verify`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ address: _address, signature }),
    });
    if (!verRes.ok) throw new Error('Signature verification failed');
    const { access_token } = await verRes.json();

    _jwt = access_token;
    localStorage.setItem('vf_jwt', access_token);

    await _loadBots();
    renderPage();
  } catch (err) {
    if (err.code === 4001) { /* user rejected */ }
    else _showError('Sign-in failed: ' + (err.message || err));
    const btn = document.getElementById('wm-signin-btn');
    if (btn) { btn.disabled = false; btn.textContent = '🔐 Sign in with Wallet'; }
  }
};

window.wmDisconnect = function () {
  _clearSession();
  renderPage();
};

// ── Load bots ──────────────────────────────────────────────
async function _loadBots() {
  const res = await apiFetch('/bots');
  if (!res.ok) throw new Error('Failed to load bots');
  _bots = await res.json();

  // Extract address from JWT payload if not already set
  if (!_address && _jwt) {
    try {
      const payload = JSON.parse(atob(_jwt.split('.')[1]));
      _address = payload.sub || payload.address || null;
    } catch (_) {}
  }

  // Fetch HL balances + statuses in parallel
  const wallets    = [...new Set(_bots.map(b => b.hl_wallet_addr).filter(Boolean))];
  const activeBots = _bots.filter(b => b.active);

  await Promise.all([
    ...wallets.map(w => _fetchHLBalance(w)),
    ...activeBots.map(b => _fetchBotStatus(b.id)),
  ]);
}

async function _fetchHLBalance(wallet) {
  try {
    const res = await apiFetch(`/bots/hl-balance?wallet=${encodeURIComponent(wallet)}`);
    const data = await res.json();
    // Store under each tokenId that uses this wallet
    _bots.forEach(b => {
      if (b.hl_wallet_addr === wallet) {
        _balances[b.nft_token_id] = data;
      }
    });
  } catch (err) {
    _bots.forEach(b => {
      if (b.hl_wallet_addr === wallet) {
        _balances[b.nft_token_id] = { error: err.message };
      }
    });
  }
}

async function _fetchBotStatus(botId) {
  try {
    const res  = await apiFetch(`/bots/${botId}/status`);
    const data = await res.json();
    _statuses[botId] = { running: data.running === true };
  } catch (_) {
    // On error, assume running (safe default — keeps lock in place)
    _statuses[botId] = { running: true };
  }
}

// ── Per-card refresh ───────────────────────────────────────
window.wmRefreshCard = async function (tokenId) {
  const bot = _bots.find(b => b.nft_token_id === tokenId);
  if (!bot?.hl_wallet_addr) return;
  const btn = document.querySelector(`[data-refresh="${tokenId}"]`);
  if (btn) { btn.disabled = true; btn.textContent = '⟳'; }

  // Re-fetch bot list first (active state may have changed)
  try {
    await _loadBots();
    renderPage();
  } catch (err) {
    _showCardError(tokenId, 'Refresh failed: ' + err.message);
    if (btn) { btn.disabled = false; btn.textContent = '⟳'; }
  }
};

// ── Render ─────────────────────────────────────────────────
function renderPage() {
  const root = document.getElementById('wm-root');
  if (!root) return;

  if (!_jwt) {
    root.innerHTML = _renderAuthGate();
    return;
  }

  if (!_bots.length) {
    root.innerHTML = _renderNoBots();
    return;
  }

  root.innerHTML = `
    <div class="wm2-toolbar">
      <span class="wm2-signed-in-as">
        <span class="wm2-dot"></span>
        ${_shortAddr(_address)}
      </span>
      <button class="wm2-btn wm2-btn--ghost" onclick="wmDisconnect()">Disconnect</button>
    </div>
    <div class="wm2-cards-grid" id="wm2-cards-grid">
      ${_bots.map(b => _buildCard(b)).join('')}
    </div>
  `;

  // Re-attach inline form handlers (they live in the DOM)
}

function _renderAuthGate() {
  return `
    <div class="wm2-auth-gate">
      <div class="wm2-auth-icon">🔐</div>
      <p class="wm2-auth-msg">Connect your wallet to manage your protection wallets</p>
      <button class="wm2-btn wm2-btn--primary" id="wm-signin-btn" onclick="wmConnect()">
        🔐 Sign in with Wallet
      </button>
    </div>
  `;
}

function _renderNoBots() {
  return `
    <div class="wm2-toolbar">
      <span class="wm2-signed-in-as">
        <span class="wm2-dot"></span>
        ${_shortAddr(_address)}
      </span>
      <button class="wm2-btn wm2-btn--ghost" onclick="wmDisconnect()">Disconnect</button>
    </div>
    <div class="wm2-empty">
      <div class="wm2-empty-icon">🛡️</div>
      <p class="wm2-empty-msg">No bot configurations found.</p>
      <p class="wm2-empty-sub">Create a bot in <a href="../dashboard/index.html">LP Defensor</a> first.</p>
    </div>
  `;
}

function _buildCard(bot) {
  const tokenId    = bot.nft_token_id;
  const chainLabel = CHAIN_LABELS[bot.chain_id] || `chain:${bot.chain_id}`;
  const hasHL      = !!bot.hl_wallet_addr;
  const isActive   = bot.active;
  const editState  = _editOpen[tokenId] || null;

  // HL Balance display
  let balHtml = '';
  if (hasHL) {
    const bal = _balances[tokenId];
    balHtml = _renderBalanceLine(bal);
  }

  // Determine actual running state for active bots
  const statusData = isActive ? (_statuses[bot.id] ?? null) : null;
  const isCrashed  = isActive && statusData !== null && statusData.running === false;
  const isRunning  = isActive && !isCrashed;

  // Card top strip color
  const stripClass = isCrashed ? 'wm2-card--crashed'
                   : isActive  ? 'wm2-card--active'
                   :             'wm2-card--idle';

  // Status badge
  let statusBadge = '';
  if (isCrashed) {
    statusBadge = `<span class="wm2-badge wm2-badge--crashed">🔴 BOT CAÍDO</span>`;
  } else if (isRunning) {
    statusBadge = `<span class="wm2-badge wm2-badge--running">🟢 RUNNING</span>`;
  }

  // LP wallet — user's own wallet address
  const lpAddrDisplay = _address
    ? `<span class="wm2-mono">${_shortAddr(_address)}</span>
       <span class="wm2-copy-icon" onclick="wmCopyAddr('${_address}', this)" title="Copy">📋</span>`
    : '<span class="wm2-mono wm2-muted">—</span>';

  // HL wallet row
  let hlSection = '';
  if (hasHL) {
    const hlAddr = bot.hl_wallet_addr;
    hlSection = `
      <div class="wm2-arrow-row">⬇ protected by</div>
      <div class="wm2-detail-row">
        <span class="wm2-detail-label">HL Wallet</span>
        <span class="wm2-detail-val">
          <span class="wm2-mono">${_shortAddr(hlAddr)}</span>
          <span class="wm2-copy-icon" onclick="wmCopyAddr('${hlAddr}', this)" title="Copy">📋</span>
        </span>
      </div>
      <div class="wm2-detail-row">
        <span class="wm2-detail-label">HL Balance</span>
        <span class="wm2-detail-val">${balHtml}</span>
      </div>
      <div class="wm2-detail-row">
        <span class="wm2-detail-label">API Key</span>
        <span class="wm2-detail-val wm2-muted">•••••••••• (set)</span>
      </div>
    `;
  } else {
    hlSection = `
      <div class="wm2-no-hl">
        <span class="wm2-no-hl-icon">⚠</span>
        No HL protection linked
      </div>
    `;
  }

  // Inline form
  let inlineForm = '';
  if (editState === 'edit' || editState === 'link') {
    inlineForm = _buildEditForm(bot, editState);
  } else if (editState === 'remove') {
    inlineForm = _buildRemoveConfirm(bot);
  }

  // Footer actions
  let footer = '';
  if (isActive) {
    const lockMsg = isCrashed
      ? '🔒 Bot is flagged active but not running — stop it in LP Defensor to edit'
      : '🔒 Stop the bot in LP Defensor to edit';
    footer = `<div class="wm2-lock-hint">${lockMsg}</div>`;
  } else if (editState) {
    footer = ''; // form handles its own buttons
  } else if (hasHL) {
    footer = `
      <div class="wm2-card-actions">
        <button class="wm2-btn wm2-btn--outline" onclick="wmStartEdit('${tokenId}')">✏ Edit</button>
        <button class="wm2-btn wm2-btn--danger"  onclick="wmStartRemove('${tokenId}')">🗑 Remove</button>
        <button class="wm2-btn wm2-btn--ghost" data-refresh="${tokenId}"
                onclick="wmRefreshCard('${tokenId}')">⟳</button>
      </div>
    `;
  } else {
    footer = `
      <div class="wm2-card-actions">
        <button class="wm2-btn wm2-btn--primary" onclick="wmStartLink('${tokenId}')">➕ Link HL Wallet</button>
      </div>
    `;
  }

  return `
    <div class="wm2-card ${stripClass}" id="card-${tokenId}">
      <div class="wm2-card-header">
        <span class="wm2-card-title">NFT #${_esc(tokenId)} · ${_esc(bot.pair)} · ${_esc(chainLabel)}</span>
        ${statusBadge}
      </div>
      <div class="wm2-detail-row">
        <span class="wm2-detail-label">LP Wallet</span>
        <span class="wm2-detail-val">${lpAddrDisplay}</span>
      </div>
      ${hlSection}
      ${inlineForm}
      ${footer}
      <div class="wm2-card-error hidden" id="card-err-${tokenId}"></div>
    </div>
  `;
}

function _buildEditForm(bot, mode) {
  const tokenId = bot.nft_token_id;
  const preAddr  = mode === 'edit' ? (bot.hl_wallet_addr || '') : '';
  const isLink   = mode === 'link';
  const saveLabel = isLink ? 'Link Wallet' : 'Save';
  const addrPlaceholder = isLink ? '0x…' : (bot.hl_wallet_addr || '0x…');

  return `
    <div class="wm2-inline-form" id="form-${tokenId}">
      <div class="wm2-form-row">
        <label class="wm2-form-label">HL Wallet Address</label>
        <input class="wm2-input" id="inp-addr-${tokenId}"
               type="text" autocomplete="off" spellcheck="false"
               value="${preAddr}"
               placeholder="${addrPlaceholder}" />
      </div>
      <div class="wm2-form-row">
        <label class="wm2-form-label">API Private Key</label>
        <div class="wm2-input-wrap">
          <input class="wm2-input" id="inp-key-${tokenId}"
                 type="password" autocomplete="new-password"
                 placeholder="${isLink ? 'Enter API private key' : 'Leave blank to keep current'}" />
          <span class="wm2-eye" onclick="wmToggleKey('inp-key-${tokenId}', this)" title="Show/hide">👁</span>
        </div>
        ${!isLink ? '<div class="wm2-form-hint">Leave blank to keep the current key</div>' : ''}
      </div>
      <div class="wm2-form-actions">
        <button class="wm2-btn wm2-btn--primary" onclick="wmSaveEdit('${tokenId}', ${isLink})">${saveLabel}</button>
        <button class="wm2-btn wm2-btn--ghost" onclick="wmCancelEdit('${tokenId}')">Cancel</button>
      </div>
    </div>
  `;
}

function _buildRemoveConfirm(bot) {
  const tokenId = bot.nft_token_id;
  const shortHL = _shortAddr(bot.hl_wallet_addr);
  return `
    <div class="wm2-remove-confirm" id="remove-confirm-${tokenId}">
      <span class="wm2-remove-msg">Remove HL wallet <strong>${shortHL}</strong> from this position?</span>
      <div class="wm2-form-actions">
        <button class="wm2-btn wm2-btn--danger" onclick="wmConfirmRemove('${tokenId}')">Yes, remove</button>
        <button class="wm2-btn wm2-btn--ghost" onclick="wmCancelEdit('${tokenId}')">Cancel</button>
      </div>
    </div>
  `;
}

// ── Balance display ────────────────────────────────────────
function _renderBalanceLine(bal) {
  if (!bal) return '<span class="wm2-muted">—</span>';
  if (bal.error === 'no_hl_wallet') return '<span class="wm2-muted">—</span>';
  if (bal.error) return `<span class="wm2-bal-red">Error</span>`;

  const val = parseFloat(bal.account_value);
  if (isNaN(val)) return '<span class="wm2-muted">—</span>';

  let cls = 'wm2-bal-green';
  if (val <= 0)   cls = 'wm2-bal-red';
  else if (val < 20) cls = 'wm2-bal-amber';

  return `<span class="${cls}">$${val.toFixed(2)}</span>`;
}

// ── Edit / Link / Remove actions (called from DOM) ─────────
window.wmStartEdit = function (tokenId) {
  _editOpen[tokenId] = 'edit';
  _rerenderCard(tokenId);
};

window.wmStartLink = function (tokenId) {
  _editOpen[tokenId] = 'link';
  _rerenderCard(tokenId);
};

window.wmStartRemove = function (tokenId) {
  _editOpen[tokenId] = 'remove';
  _rerenderCard(tokenId);
};

window.wmCancelEdit = function (tokenId) {
  delete _editOpen[tokenId];
  _rerenderCard(tokenId);
};

window.wmToggleKey = function (inputId, eyeEl) {
  const inp = document.getElementById(inputId);
  if (!inp) return;
  inp.type = inp.type === 'password' ? 'text' : 'password';
  eyeEl.style.opacity = inp.type === 'text' ? '1' : '0.5';
};

window.wmSaveEdit = async function (tokenId, isLink) {
  const bot = _bots.find(b => b.nft_token_id === tokenId);
  if (!bot) return;

  const addrEl = document.getElementById(`inp-addr-${tokenId}`);
  const keyEl  = document.getElementById(`inp-key-${tokenId}`);
  if (!addrEl || !keyEl) return;

  const newAddr = addrEl.value.trim();
  const newKey  = keyEl.value.trim();

  // Validation
  if (!newAddr) { _showCardError(tokenId, 'HL Wallet Address is required'); return; }
  if (isLink && !newKey) { _showCardError(tokenId, 'API Private Key is required'); return; }

  // Build payload — only include changed / provided fields
  const payload = {};
  if (newAddr !== (bot.hl_wallet_addr || '')) payload.hl_wallet_addr = newAddr;
  if (newKey)                                  payload.hl_api_key     = newKey;

  if (!Object.keys(payload).length) {
    // Nothing changed
    delete _editOpen[tokenId];
    _rerenderCard(tokenId);
    return;
  }

  const saveBtn = document.querySelector(`#form-${tokenId} .wm2-btn--primary`);
  if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = '⏳ Saving…'; }

  try {
    const res = await apiFetch(`/bots/${bot.id}`, {
      method: 'PUT',
      body:   JSON.stringify(payload),
    });

    if (res.status === 409) {
      _showCardError(tokenId, 'Bot is now running — stop it in LP Defensor first');
      if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = 'Save'; }
      return;
    }
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || `Save failed (${res.status})`);
    }

    // Update local bot data
    const updated = await res.json();
    const idx = _bots.findIndex(b => b.id === bot.id);
    if (idx !== -1) _bots[idx] = updated;

    delete _editOpen[tokenId];

    // Re-fetch HL balance for new wallet
    if (updated.hl_wallet_addr) {
      await _fetchHLBalance(updated.hl_wallet_addr);
    }

    _rerenderCard(tokenId);
  } catch (err) {
    _showCardError(tokenId, err.message);
    if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = isLink ? 'Link Wallet' : 'Save'; }
  }
};

window.wmConfirmRemove = async function (tokenId) {
  const bot = _bots.find(b => b.nft_token_id === tokenId);
  if (!bot?.hl_wallet_addr) return;

  const btn = document.querySelector(`#remove-confirm-${tokenId} .wm2-btn--danger`);
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Removing…'; }

  try {
    const wallet = bot.hl_wallet_addr;
    const res = await apiFetch(
      `/bots/hl-wallet?wallet=${encodeURIComponent(wallet)}`,
      { method: 'DELETE' }
    );

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || `Remove failed (${res.status})`);
    }

    // Clear wallet from ALL bots that shared it (backend clears all non-running)
    _bots.forEach(b => {
      if (b.hl_wallet_addr === wallet) {
        delete _balances[b.nft_token_id];
        delete _editOpen[b.nft_token_id];
        b.hl_wallet_addr = null;
      }
    });

    renderPage(); // full re-render — multiple cards may have changed
  } catch (err) {
    _showCardError(tokenId, err.message);
    if (btn) { btn.disabled = false; btn.textContent = 'Yes, remove'; }
  }
};

// ── Copy address ───────────────────────────────────────────
window.wmCopyAddr = function (addr, el) {
  navigator.clipboard.writeText(addr).then(() => {
    const orig = el.textContent;
    el.textContent = '✓';
    el.style.color = '#00ffb3';
    setTimeout(() => {
      el.textContent = orig;
      el.style.color = '';
    }, 1500);
  }).catch(() => {});
};

// ── Helpers ────────────────────────────────────────────────
function _shortAddr(addr) {
  if (!addr) return '—';
  return `${addr.slice(0, 6)}…${addr.slice(-4)}`;
}

function _esc(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function _rerenderCard(tokenId) {
  const bot  = _bots.find(b => b.nft_token_id === tokenId);
  const card = document.getElementById(`card-${tokenId}`);
  if (!bot || !card) { renderPage(); return; }
  const tmp = document.createElement('div');
  tmp.innerHTML = _buildCard(bot);
  card.replaceWith(tmp.firstElementChild);
}

function _showCardError(tokenId, msg) {
  const el = document.getElementById(`card-err-${tokenId}`);
  if (!el) return;
  el.textContent = '⚠ ' + msg;
  el.classList.remove('hidden');
  setTimeout(() => el.classList.add('hidden'), 6000);
}

function _showError(msg) {
  const el = document.getElementById('wm-global-error');
  if (!el) return;
  el.textContent = msg;
  el.classList.remove('hidden');
  setTimeout(() => el.classList.add('hidden'), 8000);
}

// ── Bootstrap ──────────────────────────────────────────────
async function wmInit() {
  if (_jwt) {
    // Try to restore session — extract address from JWT
    try {
      const payload = JSON.parse(atob(_jwt.split('.')[1]));
      _address = payload.sub || payload.address || null;
      await _loadBots();
    } catch (err) {
      // JWT expired or invalid
      _clearSession();
    }
  }
  renderPage();
}

// Wait for ethers.js to be ready
if (typeof ethers !== 'undefined') {
  wmInit();
} else {
  window.addEventListener('load', () => {
    const check = setInterval(() => {
      if (typeof ethers !== 'undefined') {
        clearInterval(check);
        wmInit();
      }
    }, 100);
  });
}
