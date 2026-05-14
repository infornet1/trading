"use strict";
/* ============================================================
   LP Signal Lab — Frontend Logic
============================================================ */

const API_BASE = '/trading/lp-hedge/api';

let _token          = localStorage.getItem("vf_jwt") || null;
let _address        = null;
let _wallets        = [];     // [{address, active_bot_id}]
let _signals        = [];     // current signal list
let _historyLoaded  = false;
let _historyOpen    = false;
let _selectedWallet = null;   // wallet address chosen in modal
let _signalWalletAddr = null; // registered signal wallet addr (for warning text)
let _activeSignalId = null;   // signal being executed
let _overrideSig    = null;   // signal data saved for modal reset
let _autoStatus     = { armed: false, wallets: [] }; // auto-execute armed state

// Per-pair defaults (loaded once, updated on save/delete)
let _userDefaults     = null;   // {COIN: {leverage, size_usdt}} — null until loaded
let _hlAssets         = null;   // [{coin, max_leverage, sz_decimals}] — null until loaded
let _configPanelOpen  = false;
let _configPanelReady = false;

// ── Auth ───────────────────────────────────────────────────

async function connectWallet() {
  if (!window.ethereum) {
    alert("No se detectó wallet. Instala Rabby o MetaMask.");
    return;
  }
  const btn = document.getElementById("wallet-btn");
  try {
    if (btn) { btn.disabled = true; btn.textContent = "⏳ Conectando…"; }

    const provider = new ethers.BrowserProvider(window.ethereum);
    await provider.send("eth_requestAccounts", []);
    const signer = await provider.getSigner();
    _address = await signer.getAddress();

    const nonceRes = await fetch(`${API_BASE}/auth/nonce?address=${_address}`);
    if (!nonceRes.ok) throw new Error("No se pudo obtener nonce");
    const { nonce } = await nonceRes.json();

    const signature = await signer.signMessage(`Sign in to VIZNIAGO FURY\nNonce: ${nonce}`);

    const verRes = await fetch(`${API_BASE}/auth/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ address: _address, signature }),
    });
    if (!verRes.ok) throw new Error("Verificación fallida");
    const { access_token } = await verRes.json();

    _token = access_token;
    localStorage.setItem("vf_jwt", _token);

    if (btn) {
      btn.disabled = false;
      btn.textContent = `🟢 ${_address.slice(0,6)}…${_address.slice(-4)}`;
    }
    refreshAll();
  } catch (err) {
    if (err.code !== 4001) alert("Error: " + (err.message || err));
    if (btn) { btn.disabled = false; btn.textContent = "🟢  Conectar Billetera"; }
  }
}

function _authHeader() {
  return _token ? { "Authorization": `Bearer ${_token}` } : {};
}

// ── Boot ───────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  refreshAll();
});

async function refreshAll() {
  _setTimestamp("Actualizando...");
  await Promise.all([fetchLpRange(), fetchAutoStatus(), fetchSignals(), fetchHlPositions(), _loadUserDefaults()]);
  _setTimestamp("Actualizado " + new Date().toLocaleTimeString("es-VE", { hour: "2-digit", minute: "2-digit" }));
}

async function _loadUserDefaults() {
  if (!_token) { _userDefaults = {}; return; }
  try {
    const res = await fetch(`${API_BASE}/signal-lab/user-defaults`, { headers: _authHeader() });
    if (res.ok) {
      const data = await res.json();
      _userDefaults = data.defaults || {};
    } else {
      _userDefaults = {};
    }
  } catch {
    _userDefaults = {};
  }
}

async function fetchAutoStatus() {
  if (!_token) return;
  try {
    const res = await fetch(`${API_BASE}/signal-lab/auto-status`, {
      headers: { ..._authHeader() },
    });
    if (!res.ok) return;
    _autoStatus = await res.json();
    _renderAutoStatusBanner();
  } catch {
    // non-fatal — page works without it
  }
}

function _renderAutoStatusBanner() {
  const el = document.getElementById("auto-status-banner");
  if (!el) return;

  if (!_autoStatus.armed || _autoStatus.wallets.length === 0) {
    el.innerHTML = "";
    el.classList.add("hidden");
    return;
  }

  const walletTags = _autoStatus.wallets.map(w => {
    const bal = w.balance_usdc != null ? ` · $${Number(w.balance_usdc).toFixed(2)} USDC` : "";
    return `<span class="sl-auto-wallet">${w.label} <code>${w.addr_short}</code>${bal}</span>`;
  }).join("");

  el.innerHTML = `
    <span class="sl-auto-dot"></span>
    <span class="sl-auto-label">🤖 Auto-execute activo</span>
    <span style="font-size:0.68rem;color:var(--color-text-muted);margin:0 6px">·</span>
    <span style="font-size:0.68rem;color:var(--color-text-muted)">señales se ejecutan automáticamente · Ejecutar → como respaldo</span>
    ${walletTags}
  `;
  el.classList.remove("hidden");
}

// ── LP Range Advisor ───────────────────────────────────────

async function fetchLpRange() {
  const loading = document.getElementById("lp-range-loading");
  const content = document.getElementById("lp-range-content");
  const empty   = document.getElementById("lp-range-empty");

  loading.classList.remove("hidden");
  content.classList.add("hidden");
  empty.classList.add("hidden");

  try {
    const res = await fetch(`${API_BASE}/signal-lab/lp-range`, {
      headers: { "Content-Type": "application/json", ..._authHeader() },
    });
    if (!res.ok) throw new Error(res.status);
    const data = await res.json();

    loading.classList.add("hidden");
    if (!data.available) {
      empty.classList.remove("hidden");
      return;
    }
    content.innerHTML = _renderLpRange(data);
    content.classList.remove("hidden");
  } catch {
    loading.classList.add("hidden");
    empty.classList.remove("hidden");
  }
}

function _renderLpRange(data) {
  const analysis = data.analysis || {};
  const ranges   = data.ranges   || {};
  const opts     = ranges.options || {};
  const cp       = ranges.current_price || 0;
  const msgDate  = data.msg_date ? new Date(data.msg_date) : null;

  const trend     = (analysis.trend || "").toLowerCase();
  const bias      = (analysis.analyst_bias || "").toLowerCase();
  const vol       = (analysis.volatility || "").toLowerCase();
  const notes     = analysis.notes || "";
  const stdOpt    = opts["A_standard"] || {};
  const tightOpt  = opts["B_tight"]    || {};
  const consOpt   = opts["C_conservative"] || {};

  // BTC context — look for btc in notes or use a generic macro hint
  const btcLevels = (analysis.btc_context) || null;

  // Bar width as % of the full range vs a 30% price window around current price
  const viewLow  = cp * 0.85;
  const viewHigh = cp * 1.15;
  const viewRange = viewHigh - viewLow;
  function barStyle(lo, hi) {
    const left  = Math.max(0, (lo - viewLow) / viewRange * 100);
    const right = Math.min(100, (hi - viewLow) / viewRange * 100);
    return `left:${left.toFixed(1)}%;width:${(right-left).toFixed(1)}%`;
  }

  const dateLabel = msgDate
    ? `gráfico del ${msgDate.toLocaleDateString("es-VE", {day:"numeric", month:"short"})} · Bitcoin Daily`
    : "Bitcoin Daily";

  return `
    <div class="sl-range-meta">
      <span class="sl-price">ETH $${cp.toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2})}</span>
      <span class="sl-trend-pill ${trend}">${_trendLabel(trend)}</span>
      <span class="sl-vol">Vol: ${vol || "—"}</span>
    </div>

    ${notes ? `<p style="font-size:0.72rem;color:var(--color-text-muted);margin-bottom:12px;">${notes}</p>` : ""}

    <div class="sl-range-card">
      <div class="sl-range-label">⭐ Rango Estándar</div>
      <div class="sl-range-bar-wrap">
        <div class="sl-range-bar" style="${barStyle(stdOpt.lower||cp*0.97, stdOpt.upper||cp*1.03)}"></div>
      </div>
      <div class="sl-range-prices">
        <span>$${_fmt(stdOpt.lower)}</span>
        <span>$${_fmt(stdOpt.upper)}</span>
      </div>
      <div class="sl-range-params">
        <div class="sl-param">
          <span class="sl-param-label">Ancho</span>
          <span class="sl-param-value">${stdOpt.width_pct||"—"}%</span>
        </div>
        <div class="sl-param">
          <span class="sl-param-label">Leverage</span>
          <span class="sl-param-value">${stdOpt.leverage||"—"}</span>
        </div>
        <div class="sl-param">
          <span class="sl-param-label">Stop Loss</span>
          <span class="sl-param-value">${stdOpt.sl_pct||"—"}</span>
        </div>
        <div class="sl-param">
          <span class="sl-param-label">Modo</span>
          <span class="sl-param-value">Defensor Bajista</span>
        </div>
      </div>
      <div class="sl-range-cta">
        <button class="btn btn-primary btn-sm" onclick="goToConfigurator(${stdOpt.lower||0},${stdOpt.upper||0})">
          Usar este rango →
        </button>
        <button class="sl-alt-toggle" onclick="toggleAltRanges(this)">▸ Ver alternativas</button>
      </div>
    </div>

    <div class="sl-alt-options hidden">
      <div class="sl-alt-card">
        <div>
          <div class="sl-alt-name">B — Ajustado</div>
          <div class="sl-alt-range">$${_fmt(tightOpt.lower)} – $${_fmt(tightOpt.upper)}</div>
        </div>
        <div class="sl-alt-meta">${tightOpt.width_pct||"—"}% · ${tightOpt.leverage||"—"} · SL ${tightOpt.sl_pct||"—"}</div>
      </div>
      <div class="sl-alt-card">
        <div>
          <div class="sl-alt-name">C — Conservador</div>
          <div class="sl-alt-range">$${_fmt(consOpt.lower)} – $${_fmt(consOpt.upper)}</div>
        </div>
        <div class="sl-alt-meta">${consOpt.width_pct||"—"}% · ${consOpt.leverage||"—"} · SL ${consOpt.sl_pct||"—"}</div>
      </div>
    </div>

    <div class="sl-btc-context" id="btc-context-row">
      🔶 BTC · ${_trendLabel(bias)} (sesgo analista) — contexto macro para ETH
    </div>

    <div class="sl-chart-source">📷 Basado en: ${dateLabel}</div>
  `;
}

function toggleAltRanges(btn) {
  const altDiv = btn.closest(".sl-range-card").nextElementSibling;
  if (!altDiv) return;
  const open = !altDiv.classList.contains("hidden");
  altDiv.classList.toggle("hidden", open);
  btn.textContent = open ? "▸ Ver alternativas" : "▴ Ocultar alternativas";
}

function goToConfigurator(lower, upper) {
  // Navigate to LP Defensor with pre-filled range params
  sessionStorage.setItem("sl_prefill_lower", lower);
  sessionStorage.setItem("sl_prefill_upper", upper);
  window.location.href = "../dashboard/index.html#new-bot";
}

// ── Signal Feed ────────────────────────────────────────────

async function fetchSignals() {
  const loading = document.getElementById("signals-loading");
  const content = document.getElementById("signal-feed-content");
  const empty   = document.getElementById("signals-empty");
  const badge   = document.getElementById("signal-count-badge");
  const histTgl = document.getElementById("signal-history-toggle");

  loading.classList.remove("hidden");
  content.classList.add("hidden");
  empty.classList.add("hidden");
  badge.classList.add("hidden");
  histTgl.classList.add("hidden");

  try {
    const res = await fetch(`${API_BASE}/signal-lab/signals?limit=20`, {
      headers: { "Content-Type": "application/json", ..._authHeader() },
    });
    if (!res.ok) throw new Error(res.status);
    const data = await res.json();
    _signals = data.signals || [];

    loading.classList.add("hidden");

    const CLOSED_STATUSES = ["stopped", "tp_hit", "cancelled"];
    const ACTIVE_MAX_AGE  = 7 * 3600;
    const active  = _signals.filter(s => !CLOSED_STATUSES.includes(s.status) && s.age_seconds < ACTIVE_MAX_AGE);
    const closed  = _signals.filter(s =>  CLOSED_STATUSES.includes(s.status) || s.age_seconds >= ACTIVE_MAX_AGE);

    if (active.length === 0 && closed.length === 0) {
      empty.classList.remove("hidden");
      return;
    }

    if (active.length > 0) {
      badge.textContent = active.length;
      badge.classList.remove("hidden");
    }

    content.innerHTML = `<div class="sl-signal-list">${active.map(_renderSignalCard).join("")}</div>`;
    if (closed.length > 0) {
      content.innerHTML += `<div class="sl-signal-list" style="margin-top:8px">${closed.slice(0,3).map(_renderSignalCard).join("")}</div>`;
    }
    content.classList.remove("hidden");

    // Build a basic summary from what's visible; will be replaced with accurate stats on history open
    _buildHistorySummary({
      tp:       closed.filter(s => s.status === "tp_hit").length,
      sl:       closed.filter(s => s.status === "stopped").length,
      expired:  closed.filter(s => s.status === "expired" || s.status === "cancelled").length,
      win_rate: null,
      decided:  0,
    });
    histTgl.classList.remove("hidden");

  } catch {
    loading.classList.add("hidden");
    empty.classList.remove("hidden");
  }
}

function _renderSignalCard(sig) {
  const dir      = (sig.direction || "short").toLowerCase();
  const lev      = sig.leverage ? `${sig.leverage}x` : "";
  const entry    = sig.entry    ? `$${_fmt(sig.entry)}`    : "—";
  const sl       = sig.stoploss ? `$${_fmt(sig.stoploss)}` : "—";
  const tps      = (sig.targets || []).map(t => `$${_fmt(t)}`).join(" / ");
  const age      = _ageLabel(sig.age_seconds);
  const statusLabel = _statusLabel(sig.status);

  const dirHtml = `<span class="sl-dir-pill ${dir}">${dir.toUpperCase()}</span>`;
  const srcBadge = sig.source_id === 2
    ? `<span class="sl-source-badge">📊 BTC Daily</span>`
    : "";

  // Signals that are closed/invalid — trade is over, no re-entry
  const isClosed = ["stopped", "tp_hit", "cancelled"].includes(sig.status);

  let btnHtml;
  if (isClosed) {
    btnHtml = `<span style="font-size:0.65rem;color:var(--color-text-muted)">${statusLabel}</span>`;
  } else if (sig.is_running) {
    // Already live on HL for this wallet — show status, no execute button
    const autoTag = _autoStatus.armed ? `<span class="sl-auto-armed-tag">🤖</span>` : "";
    btnHtml = `
      <div class="sl-btn-group">
        ${autoTag}
        <span class="sl-running-badge">🟢 En curso</span>
      </div>
    `;
  } else {
    // Not running yet — show Execute button (auto fires automatically, this is the fallback)
    const autoTag = _autoStatus.armed
      ? `<span class="sl-auto-armed-tag" title="Auto-execute armado — se ejecutará automáticamente">🤖</span>`
      : "";
    btnHtml = `
      <div class="sl-btn-group">
        ${autoTag}
        <button class="btn btn-primary btn-sm" onclick="openExecuteModal(${sig.id})">Ejecutar →</button>
      </div>
    `;
  }

  return `
    <div class="sl-signal-card${isClosed ? " sl-signal-card--expired" : ""}">
      ${dirHtml}
      <div class="sl-signal-info">
        <div class="sl-signal-pair">${srcBadge}${sig.pair || "—"} ${lev}</div>
        <div class="sl-signal-prices">E ${entry} · SL ${sl}${tps ? " · TP " + tps : ""}</div>
      </div>
      <div class="sl-signal-age">${age}</div>
      ${btnHtml}
    </div>
  `;
}

function _buildHistorySummary(stats) {
  const parts = [];
  if (stats.tp)      parts.push(`TP ✅ ${stats.tp}`);
  if (stats.sl)      parts.push(`SL ❌ ${stats.sl}`);
  if (stats.expired) parts.push(`Expiradas ${stats.expired}`);
  if (stats.win_rate != null) parts.push(`Win rate ${stats.win_rate}%`);

  const summary = document.getElementById("history-summary");
  const arrow   = _historyOpen ? "▴" : "▸";
  summary.textContent = `${arrow} Ver historial (${parts.join(" · ") || "vacío"})`;
}

function toggleHistory() {
  if (_historyOpen) {
    document.getElementById("signal-history-content").classList.add("hidden");
    document.getElementById("history-summary").textContent =
      document.getElementById("history-summary").textContent.replace("▴", "▸");
    _historyOpen = false;
    return;
  }
  _historyOpen = true;
  document.getElementById("history-summary").textContent =
    document.getElementById("history-summary").textContent.replace("▸", "▴");

  if (_historyLoaded) {
    document.getElementById("signal-history-content").classList.remove("hidden");
    return;
  }
  _loadHistory();
}

async function _loadHistory() {
  const el = document.getElementById("signal-history-content");
  el.innerHTML = '<p style="font-size:0.72rem;color:var(--color-text-muted);padding-top:8px">Cargando...</p>';
  el.classList.remove("hidden");

  try {
    const res = await fetch(`${API_BASE}/signal-lab/history?limit=30`, {
      headers: { "Content-Type": "application/json", ..._authHeader() },
    });
    const data = await res.json();
    const history = data.history || [];
    const stats   = data.stats   || {};

    // Refresh summary bar with real stats from API
    _buildHistorySummary(stats);

    if (history.length === 0) {
      el.innerHTML = '<p style="font-size:0.72rem;color:var(--color-text-muted);padding-top:8px">Sin historial aún.</p>';
      _historyLoaded = true;
      return;
    }

    // Win rate stats bar (only if there are decided trades)
    let statsBar = "";
    if (stats.decided > 0) {
      const wrColor = stats.win_rate >= 50 ? "var(--color-neon-green)" : "#f87171";
      statsBar = `
        <div class="sl-history-stats">
          <span>Ejecutadas: <strong>${stats.decided}</strong></span>
          <span>✅ TP: <strong>${stats.tp}</strong></span>
          <span>❌ SL: <strong>${stats.sl}</strong></span>
          <span>Win rate: <strong style="color:${wrColor}">${stats.win_rate}%</strong></span>
        </div>`;
    }

    el.innerHTML = statsBar + `<div class="sl-history-list">${history.map(_renderHistoryRow).join("")}</div>`;
    _historyLoaded = true;
  } catch {
    el.innerHTML = '<p style="font-size:0.72rem;color:#f87171;padding-top:8px">Error al cargar historial.</p>';
  }
}

function _renderHistoryRow(sig) {
  const dir  = (sig.direction || "").toUpperCase();
  const age  = sig.received_at
    ? new Date(sig.received_at).toLocaleDateString("es-VE", { month: "short", day: "numeric" })
    : "—";

  // Price columns — only show when executed
  let priceBlock = "";
  if (sig.fill_price) {
    const fillStr  = `E $${_fmt(sig.fill_price)}`;
    const closeStr = sig.close_price ? ` → $${_fmt(sig.close_price)}` : "";
    priceBlock = `<span class="sl-history-prices">${fillStr}${closeStr}</span>`;
  }

  // P&L badge
  let pnlBadge = "";
  if (sig.pnl_pct != null) {
    const pos     = sig.pnl_pct >= 0;
    const sign    = pos ? "+" : "";
    const est     = sig.estimated_pnl ? " ~" : "";
    pnlBadge = `<span class="sl-pnl-badge ${pos ? "sl-pnl-pos" : "sl-pnl-neg"}">${est}${sign}${sig.pnl_pct.toFixed(1)}%</span>`;
  }

  return `
    <div class="sl-history-row">
      <span class="sl-outcome-pill ${sig.status}">${_statusLabel(sig.status)}</span>
      <span class="sl-history-pair">${sig.pair || "—"} ${dir} ${sig.leverage || ""}x</span>
      ${priceBlock}
      ${pnlBadge}
      <span class="sl-history-date">${age}</span>
    </div>
  `;
}

// ── HL Open Positions ──────────────────────────────────────

async function fetchHlPositions() {
  const loading    = document.getElementById("hl-positions-loading");
  const content    = document.getElementById("hl-positions-content");
  const empty      = document.getElementById("hl-positions-empty");
  const countBadge = document.getElementById("hl-positions-count");

  loading.classList.remove("hidden");
  content.classList.add("hidden");
  empty.classList.add("hidden");
  countBadge.classList.add("hidden");

  if (!_token) {
    loading.classList.add("hidden");
    empty.textContent = "Conecta tu wallet para ver posiciones abiertas en Hyperliquid.";
    empty.classList.remove("hidden");
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/signal-lab/hl-positions`, {
      headers: { ..._authHeader() },
    });
    if (!res.ok) throw new Error(res.status);
    const data      = await res.json();
    const positions = data.positions || [];

    loading.classList.add("hidden");

    if (positions.length === 0) {
      empty.textContent = "No hay posiciones abiertas en Hyperliquid.";
      empty.classList.remove("hidden");
      return;
    }

    countBadge.textContent = positions.length;
    countBadge.classList.remove("hidden");

    const totalPnl  = data.total_pnl || 0;
    const totalSign = totalPnl >= 0 ? "+" : "";
    const totalCls  = totalPnl >= 0 ? "sl-pnl-pos" : "sl-pnl-neg";

    content.innerHTML = `
      <div class="sl-pos-total">
        P&L no realizado: <span class="sl-pnl-badge ${totalCls}">${totalSign}$${Math.abs(totalPnl).toFixed(2)}</span>
      </div>
      <div class="sl-pos-list">${positions.map(_renderPositionCard).join("")}</div>
    `;
    content.classList.remove("hidden");
  } catch {
    loading.classList.add("hidden");
    empty.textContent = "Error al cargar posiciones.";
    empty.classList.remove("hidden");
  }
}

function _renderPositionCard(p) {
  const dir      = (p.side || "short").toLowerCase();
  const levType  = p.leverage_type === "isolated" ? "iso" : "cross";
  const entry    = `$${_fmt(p.entry_px)}`;
  const val      = `$${_fmt(p.pos_value)}`;
  const margin   = `$${_fmt(p.margin_used)}`;
  const walletShort = p.wallet_addr
    ? p.wallet_addr.slice(0, 6) + "…" + p.wallet_addr.slice(-4)
    : "";

  const slStr = p.sl_price  ? `SL $${_fmt(p.sl_price)}`                                : "";
  const tpStr = (p.tp_prices || []).length > 0
    ? `TP ${p.tp_prices.map(t => `$${_fmt(t)}`).join(" / ")}`
    : "";
  const levelsStr = [slStr, tpStr].filter(Boolean).join(" · ");

  const pnl     = p.unrealized_pnl || 0;
  const roe     = p.roe_pct || 0;
  const pnlPos  = pnl >= 0;
  const pnlSign = pnlPos ? "+" : "";
  const pnlCls  = pnlPos ? "sl-pnl-pos" : "sl-pnl-neg";

  return `
    <div class="sl-pos-card">
      <span class="sl-dir-pill ${dir}">${dir.toUpperCase()}</span>
      <div class="sl-pos-info">
        <div class="sl-pos-pair">${p.coin}/USDT <span class="sl-pos-lev">${p.leverage}× ${levType}</span></div>
        <div class="sl-pos-meta">E ${entry} · ${p.size} ${p.coin} (${val}) · Margin ${margin}</div>
        ${levelsStr ? `<div class="sl-pos-levels">${levelsStr}</div>` : ""}
        <div class="sl-pos-wallet">${p.wallet_label} · <code>${walletShort}</code></div>
      </div>
      <span class="sl-pnl-badge sl-pos-pnl ${pnlCls}">${pnlSign}$${Math.abs(pnl).toFixed(2)} · ${pnlSign}${roe.toFixed(1)}%</span>
    </div>
  `;
}

// ── Execute Modal ──────────────────────────────────────────

async function openExecuteModal(signalId) {
  _activeSignalId   = signalId;
  _selectedWallet   = null;
  _overrideSig      = null;
  _signalWalletAddr = null;

  const sig = _signals.find(s => s.id === signalId);
  if (!sig) return;
  _overrideSig = sig;

  // Signal summary
  const dir   = (sig.direction || "short").toUpperCase();
  const entry = sig.entry    ? `$${_fmt(sig.entry)}`    : "—";
  const sl    = sig.stoploss ? `$${_fmt(sig.stoploss)}` : "—";
  const tps   = (sig.targets || []).map(t => `$${_fmt(t)}`).join(" & ");
  document.getElementById("modal-signal-summary").innerHTML = `
    <strong>${sig.pair || "—"} ${dir} ${sig.leverage||""}x</strong><br>
    Entrada ${entry} · SL ${sl}${tps ? " · TP " + tps : ""}
  `;

  // Freshness check — price drift + SL buffer
  await _loadSignalFreshness(sig);

  // Load wallets (active bots list from /bots endpoint)
  document.getElementById("modal-confirm-btn").disabled = true;
  document.getElementById("modal-override-wrap").classList.add("hidden");
  document.getElementById("modal-override-body").classList.add("hidden");
  document.getElementById("modal-override-chevron").textContent = "▸";
  // Ensure user defaults are loaded (no-op if already done)
  if (_userDefaults === null) await _loadUserDefaults();
  await _loadModalWallets();

  document.getElementById("execute-modal").classList.remove("hidden");
}

async function _loadSignalFreshness(sig) {
  const el = document.getElementById("modal-freshness");
  if (!el || !sig.entry || !sig.stoploss) { el && el.classList.add("hidden"); return; }

  const base = (sig.pair || "").split("/")[0].toUpperCase();
  el.innerHTML = '<div class="sl-freshness sl-freshness-loading">Verificando precio actual…</div>';
  el.classList.remove("hidden");

  try {
    const res  = await fetch(`${API_BASE}/signal-lab/price/${base}`, { headers: _authHeader() });
    const data = await res.json();

    if (!data.available || !data.price) {
      el.classList.add("hidden");
      return;
    }

    const current = data.price;
    const entry   = parseFloat(sig.entry);
    const sl      = parseFloat(sig.stoploss);
    const isShort = sig.direction === "short";

    // Drift: positive = price above entry
    const drift    = (current - entry) / entry * 100;
    const driftBad = isShort ? drift > 0 : drift < 0;
    const driftAbs = Math.abs(drift);

    // SL buffer remaining (% of original)
    const origBuffer = Math.abs(sl - entry);
    const curBuffer  = isShort ? sl - current : current - sl;
    const bufferPct  = Math.max(0, (curBuffer / origBuffer) * 100);

    let cls = "sl-freshness-ok";
    if (driftBad && driftAbs >= 1.0) cls = "sl-freshness-danger";
    else if (driftBad && driftAbs >= 0.3) cls = "sl-freshness-warn";

    const driftSign  = drift > 0 ? "+" : "";
    const driftLabel = driftBad
      ? `<span class="sl-drift-bad">${driftSign}${driftAbs.toFixed(2)}% contra la señal</span>`
      : `<span class="sl-drift-ok">${driftSign}${driftAbs.toFixed(2)}% a favor</span>`;

    const bufferWarn = bufferPct < 30 ? " — ⚠️ buffer bajo" : "";

    el.innerHTML = `
      <div class="sl-freshness ${cls}">
        <div class="sl-freshness-row">
          <span>Precio actual: <strong>$${_fmt(current)}</strong></span>
          <span>Drift: ${driftLabel}</span>
        </div>
        <div class="sl-freshness-buffer">
          Margen a SL restante: <strong>${bufferPct.toFixed(0)}%</strong>${bufferWarn}
        </div>
      </div>
    `;
  } catch {
    el.classList.add("hidden");
  }
}

async function _loadModalWallets() {
  const listEl = document.getElementById("modal-wallet-list");
  listEl.innerHTML = '<p style="font-size:0.72rem;color:var(--color-text-muted)">Cargando wallets...</p>';

  try {
    // Fetch LP bot wallets + the current user's own copy-trading wallet in parallel
    const [botsRes, swRes] = await Promise.allSettled([
      fetch(`${API_BASE}/bots`, { headers: { ..._authHeader() } }),
      fetch(`${API_BASE}/signal-lab/my-wallet`, { headers: { ..._authHeader() } }),
    ]);

    // Build LP bot wallet map: address → {active, bot_id}
    const lpMap = {};
    if (botsRes.status === "fulfilled" && botsRes.value.ok) {
      const data = await botsRes.value.json();
      for (const cfg of (data.configs || data || [])) {
        const addr = (cfg.hl_wallet_addr || "").toLowerCase();
        if (!addr) continue;
        if (!lpMap[addr]) lpMap[addr] = { active: false, bot_id: null };
        if (cfg.active) { lpMap[addr].active = true; lpMap[addr].bot_id = cfg.id; }
      }
    }

    // Signal wallet: only the wallet registered to the connected user
    const signalWallets = [];
    if (swRes.status === "fulfilled" && swRes.value.ok) {
      const swData = await swRes.value.json();
      if (swData.registered && swData.hl_wallet_addr) {
        signalWallets.push({ ...swData, active: true });
        _signalWalletAddr = swData.hl_wallet_addr.toLowerCase();
      }
    }

    const items = [];

    // Signal wallets first (they can execute directly)
    for (const w of signalWallets) {
      const addr   = w.hl_wallet_addr.toLowerCase();
      const short  = addr.slice(0,6) + "…" + addr.slice(-4);
      const bal    = w.balance_usdc != null ? `$${Number(w.balance_usdc).toFixed(2)}` : "";
      const autoTag = w.auto_execute
        ? `<span class="sl-wallet-auto">🤖 Auto</span>`
        : `<span class="sl-wallet-auto sl-wallet-auto--off">Manual</span>`;
      items.push(`
        <label class="sl-wallet-option sl-wallet-option--signal">
          <input type="radio" name="exec-wallet" value="${addr}"
            onchange="onWalletSelected('${addr}')">
          <span class="sl-wallet-addr">${short}</span>
          <span class="sl-wallet-label">${w.label}</span>
          ${autoTag}
          ${bal ? `<span class="sl-wallet-bal">${bal}</span>` : ""}
        </label>
      `);
    }

    // LP bot wallets (may be locked)
    for (const [addr, info] of Object.entries(lpMap)) {
      // Skip if already shown as signal wallet
      if (signalWallets.some(w => w.hl_wallet_addr.toLowerCase() === addr)) continue;
      const short  = addr.slice(0,6) + "…" + addr.slice(-4);
      const locked = info.active;
      items.push(`
        <label class="sl-wallet-option${locked ? " sl-wallet-option--locked" : ""}">
          <input type="radio" name="exec-wallet" value="${addr}" ${locked ? "disabled" : ""}
            onchange="onWalletSelected('${addr}')">
          <span class="sl-wallet-addr">${short}</span>
          ${locked ? `<span class="sl-wallet-lock">🔒 Bot #${info.bot_id} activo</span>` : ""}
        </label>
      `);
    }

    if (items.length === 0) {
      listEl.innerHTML = '<p style="font-size:0.72rem;color:var(--color-text-muted)">No hay wallets disponibles.</p>';
      return;
    }
    listEl.innerHTML = items.join("");

    // Auto-select if only one wallet is available (not locked)
    const selectableWallets = [
      ...signalWallets.map(w => w.hl_wallet_addr.toLowerCase()),
      ...Object.entries(lpMap)
        .filter(([addr, info]) => !info.active && !signalWallets.some(w => w.hl_wallet_addr.toLowerCase() === addr))
        .map(([addr]) => addr),
    ];
    if (selectableWallets.length === 1) {
      const radio = listEl.querySelector(`input[name="exec-wallet"][value="${selectableWallets[0]}"]`);
      if (radio) { radio.checked = true; onWalletSelected(selectableWallets[0]); }
    }

  } catch {
    listEl.innerHTML = '<p style="font-size:0.72rem;color:#f87171">Error al cargar wallets. ¿Estás conectado?</p>';
  }
}

function onWalletSelected(addr) {
  _selectedWallet = addr;
  // Update visual selection
  document.querySelectorAll(".sl-wallet-option").forEach(el => el.classList.remove("sl-wallet-option--selected"));
  const radio = document.querySelector(`input[name="exec-wallet"][value="${addr}"]`);
  if (radio) radio.closest(".sl-wallet-option").classList.add("sl-wallet-option--selected");
  document.getElementById("modal-confirm-btn").disabled = false;

  // Show and pre-fill override section
  _fillOverrideFields(_overrideSig);
  document.getElementById("modal-override-wrap").classList.remove("hidden");

  // Update warning based on whether this is a registered signal wallet
  const warnEl = document.getElementById("modal-warn-text");
  if (warnEl) {
    const isSignalWallet = _signalWalletAddr && addr === _signalWalletAddr;
    warnEl.textContent = isSignalWallet
      ? "⚠️ Se colocará una orden real en Hyperliquid con estos parámetros."
      : "⚠️ Esta acción registra tu intención. Coloca la orden manualmente en Hyperliquid con los parámetros mostrados.";
  }
}

function _fillOverrideFields(sig) {
  if (!sig) return;
  const coin  = (sig.pair || "").split("/")[0].toUpperCase();
  const saved = _userDefaults && _userDefaults[coin];

  document.getElementById("ovr-leverage").value = saved?.leverage  || sig.leverage || "";
  document.getElementById("ovr-size").value      = saved?.size_usdt || "";
  document.getElementById("ovr-sl").value        = sig.stoploss    || "";
  document.getElementById("ovr-tp1").value       = sig.targets?.[0] || "";
  document.getElementById("ovr-tp2").value       = sig.targets?.[1] || "";

  const myDefaultsBtn = document.getElementById("modal-reset-mydefaults-btn");
  if (myDefaultsBtn) myDefaultsBtn.style.display = saved ? "inline-flex" : "none";

  _updateNotional();
}

function toggleOverrides() {
  const body    = document.getElementById("modal-override-body");
  const chevron = document.getElementById("modal-override-chevron");
  const open    = !body.classList.contains("hidden");
  body.classList.toggle("hidden", open);
  if (chevron) chevron.textContent = open ? "▸" : "▾";
}

function _updateNotional() {
  const el = document.getElementById("modal-notional");
  if (!el || !_overrideSig) return;
  const entry = parseFloat(_overrideSig.entry);
  const coin  = (_overrideSig.pair || "").split("/")[0].toUpperCase();
  const lev   = parseFloat(document.getElementById("ovr-leverage")?.value) || 0;
  const usdt  = parseFloat(document.getElementById("ovr-size")?.value)     || 0;
  if (!entry || !lev || !usdt) { el.textContent = ""; return; }
  const coins  = usdt / entry;
  const margin = usdt / lev;
  el.innerHTML = `≈ <strong>${coins.toFixed(4)} ${coin}</strong> · $${usdt.toFixed(2)} notional · Margin <strong>$${margin.toFixed(2)}</strong>`;
}

function _resetToSignalDefaults() {
  if (!_overrideSig) return;
  document.getElementById("ovr-leverage").value = _overrideSig.leverage   || "";
  document.getElementById("ovr-size").value      = "";
  document.getElementById("ovr-sl").value        = _overrideSig.stoploss  || "";
  document.getElementById("ovr-tp1").value       = _overrideSig.targets?.[0] || "";
  document.getElementById("ovr-tp2").value       = _overrideSig.targets?.[1] || "";
  _updateNotional();
}

function _resetToMyDefaults() {
  if (!_overrideSig) return;
  const coin  = (_overrideSig.pair || "").split("/")[0].toUpperCase();
  const saved = _userDefaults && _userDefaults[coin];
  if (!saved) return;
  document.getElementById("ovr-leverage").value = saved.leverage  || "";
  document.getElementById("ovr-size").value      = saved.size_usdt || "";
  // Keep signal's SL/TP
  document.getElementById("ovr-sl").value  = _overrideSig.stoploss     || "";
  document.getElementById("ovr-tp1").value = _overrideSig.targets?.[0] || "";
  document.getElementById("ovr-tp2").value = _overrideSig.targets?.[1] || "";
  _updateNotional();
}

function closeExecuteModal() {
  document.getElementById("execute-modal").classList.add("hidden");
  _activeSignalId = null;
  _selectedWallet = null;
}

function closeModalOnOverlay(event) {
  if (event.target === event.currentTarget) {
    event.currentTarget.classList.add("hidden");
  }
}

async function confirmExecute() {
  if (!_activeSignalId || !_selectedWallet) return;

  const btn = document.getElementById("modal-confirm-btn");
  btn.disabled = true;
  btn.textContent = "Ejecutando...";

  // Collect override fields (only include non-empty values)
  const ovrLev  = parseInt(document.getElementById("ovr-leverage")?.value);
  const ovrSize = parseFloat(document.getElementById("ovr-size")?.value);
  const ovrSl   = parseFloat(document.getElementById("ovr-sl")?.value);
  const ovrTp1  = parseFloat(document.getElementById("ovr-tp1")?.value);
  const ovrTp2  = parseFloat(document.getElementById("ovr-tp2")?.value);

  const body = {
    signal_id:     _activeSignalId,
    hl_wallet_addr: _selectedWallet,
    ...(ovrLev  && !isNaN(ovrLev)  ? { override_leverage:  ovrLev  } : {}),
    ...(ovrSize && !isNaN(ovrSize) ? { override_size_usdt: ovrSize } : {}),
    ...(ovrSl   && !isNaN(ovrSl)  ? { override_sl:        ovrSl   } : {}),
    ...(ovrTp1  && !isNaN(ovrTp1) ? { override_tp1:       ovrTp1  } : {}),
    ...(ovrTp2  && !isNaN(ovrTp2) ? { override_tp2:       ovrTp2  } : {}),
  };

  try {
    const res = await fetch(`${API_BASE}/signal-lab/execute`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ..._authHeader() },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.status);

    closeExecuteModal();
    _showOrderDetails(data.order, data.fill, data.auto_executed);
  } catch (e) {
    btn.disabled = false;
    btn.textContent = "Confirmar →";
    alert(`Error: ${e.message}`);
  }
}

function _showOrderDetails(order, fill, autoExecuted) {
  if (!order) return;
  const dir      = (order.direction || "short").toUpperCase();
  const entry    = order.entry    ? `$${_fmt(order.entry)}`    : "—";
  const sl       = order.stoploss ? `$${_fmt(order.stoploss)}` : "—";
  const tps      = (order.targets || []).map(t => `$${_fmt(t)}`).join(" / ");
  const sizePct  = order.size_pct || 2;

  let fillHtml = "";
  if (fill) {
    fillHtml = `
      <hr style="border-color:var(--color-border);margin:8px 0">
      <div style="font-size:0.7rem;color:var(--color-accent);font-weight:600;margin-bottom:4px">
        ✅ Orden ejecutada en Hyperliquid
      </div>
      <div><span class="od-label">Fill price: </span><span class="od-value">$${_fmt(fill.fill_price)}</span></div>
      <div><span class="od-label">Size:       </span><span class="od-value">${fill.size} ${order.symbol}</span></div>
      <div><span class="od-label">Margen:     </span><span class="od-value">$${fill.margin_used} USDC</span></div>
      <div><span class="od-label">Order ID:   </span><span class="od-value" style="font-size:0.65rem">${fill.hl_order_id || "—"}</span></div>
    `;
  } else {
    fillHtml = `
      <div style="font-size:0.7rem;color:var(--color-text-muted);margin-top:8px">
        ⚠️ Coloca esta orden manualmente en Hyperliquid.
      </div>
    `;
  }

  document.getElementById("order-detail-content").innerHTML = `
    <div><span class="od-label">Par:       </span><span class="od-value">${order.symbol || "—"}/USDC</span></div>
    <div><span class="od-label">Dirección: </span><span class="od-value">${dir}</span></div>
    <div><span class="od-label">Leverage:  </span><span class="od-value">${order.leverage || "—"}x</span></div>
    <div><span class="od-label">Entrada:   </span><span class="od-value">${entry}</span></div>
    <div><span class="od-label">Stop Loss: </span><span class="od-value">${sl}</span></div>
    ${tps ? `<div><span class="od-label">Targets:   </span><span class="od-value">${tps}</span></div>` : ""}
    <div><span class="od-label">Tamaño:    </span><span class="od-value">${sizePct}% de balance</span></div>
    ${fillHtml}
  `;
  document.getElementById("order-detail-modal").classList.remove("hidden");
}

// ── Mi Config Panel ────────────────────────────────────────

async function toggleConfigPanel() {
  const body    = document.getElementById("config-panel-body");
  const chevron = document.getElementById("config-panel-chevron");
  _configPanelOpen = !_configPanelOpen;
  body.classList.toggle("hidden", !_configPanelOpen);
  if (chevron) chevron.textContent = _configPanelOpen
    ? "▾ Configurar defaults por par"
    : "▸ Configurar defaults por par";

  if (_configPanelOpen && !_configPanelReady) {
    await _loadConfigPanel();
  }
}

async function _loadConfigPanel() {
  const loadingEl = document.getElementById("config-loading");
  if (loadingEl) loadingEl.style.display = "block";

  await Promise.all([
    _fetchHlAssets(),
    _userDefaults === null ? _loadUserDefaults() : Promise.resolve(),
  ]);
  _configPanelReady = true;

  if (loadingEl) loadingEl.style.display = "none";
  _renderConfigSaved();
  _updateConfigBadge();
}

async function _fetchHlAssets() {
  if (_hlAssets !== null) return;
  if (!_token) { _hlAssets = []; return; }
  try {
    const res = await fetch(`${API_BASE}/signal-lab/hl-assets`, { headers: _authHeader() });
    if (res.ok) {
      const data = await res.json();
      _hlAssets = data.assets || [];
    } else {
      _hlAssets = [];
    }
  } catch {
    _hlAssets = [];
  }
}

function _renderConfigSaved() {
  const section = document.getElementById("config-saved-section");
  const list    = document.getElementById("config-saved-list");
  if (!section || !list) return;

  const entries = Object.entries(_userDefaults || {});
  if (entries.length === 0) {
    section.classList.add("hidden");
    return;
  }
  section.classList.remove("hidden");
  list.innerHTML = entries.map(([coin, def]) => {
    const asset  = (_hlAssets || []).find(a => a.coin === coin);
    return _renderConfigRow(coin, asset?.max_leverage || "—", def);
  }).join("");
}

function _updateConfigBadge() {
  const badge   = document.getElementById("config-panel-badge");
  const count   = Object.keys(_userDefaults || {}).length;
  if (!badge) return;
  if (count > 0) {
    badge.textContent = count;
    badge.classList.remove("hidden");
  } else {
    badge.classList.add("hidden");
  }
}

function _filterConfigAssets(query) {
  const resultsEl = document.getElementById("config-asset-results");
  if (!resultsEl) return;
  const q = (query || "").trim().toUpperCase();
  if (!q) { resultsEl.classList.add("hidden"); return; }

  const filtered = (_hlAssets || []).filter(a => a.coin.startsWith(q) || a.coin.includes(q)).slice(0, 12);
  if (filtered.length === 0) {
    resultsEl.innerHTML = `<div class="sl-config-empty">Sin resultados para "${query}"</div>`;
  } else {
    resultsEl.innerHTML = filtered.map(a => {
      const saved = _userDefaults && _userDefaults[a.coin];
      return _renderConfigRow(a.coin, a.max_leverage, saved);
    }).join("");
  }
  resultsEl.classList.remove("hidden");
}

function _renderConfigRow(coin, maxLev, saved) {
  const savedLev  = saved?.leverage  || "";
  const savedSize = saved?.size_usdt || "";
  const hasSaved  = !!saved;
  return `
    <div class="sl-config-row${hasSaved ? " sl-config-row--saved" : ""}" id="cfg-row-${coin}">
      <span class="sl-config-coin">${coin}</span>
      <span class="sl-config-maxlev">Max ${maxLev}×</span>
      <input type="number" class="sl-config-input" id="cfg-lev-${coin}"
             value="${savedLev}" min="1" max="${maxLev}" step="1" placeholder="Lev×" title="Leverage">
      <span class="sl-config-sep">×  $</span>
      <input type="number" class="sl-config-input" id="cfg-size-${coin}"
             value="${savedSize}" min="10" step="1" placeholder="USDT" title="Tamaño USDT">
      <button class="sl-config-save-btn" onclick="saveDefault('${coin}')" title="Guardar">💾</button>
      ${hasSaved
        ? `<button class="sl-config-del-btn" onclick="deleteDefault('${coin}')" title="Eliminar">✕</button>`
        : `<span class="sl-config-del-placeholder"></span>`}
    </div>
  `;
}

async function saveDefault(coin) {
  if (!_token) { alert("Conecta tu wallet primero."); return; }
  const levEl  = document.getElementById(`cfg-lev-${coin}`);
  const sizeEl = document.getElementById(`cfg-size-${coin}`);
  const lev    = parseInt(levEl?.value);
  const size   = parseFloat(sizeEl?.value);
  if (!lev || !size || lev < 1 || size < 10) {
    alert("Leverage ≥ 1× y tamaño ≥ $10 USDT requeridos."); return;
  }
  try {
    const res = await fetch(`${API_BASE}/signal-lab/user-defaults/${coin}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ..._authHeader() },
      body: JSON.stringify({ leverage: lev, size_usdt: size }),
    });
    if (!res.ok) throw new Error(await res.text());

    if (!_userDefaults) _userDefaults = {};
    _userDefaults[coin] = { leverage: lev, size_usdt: size };

    _renderConfigSaved();
    _updateConfigBadge();
    const q = document.getElementById("config-search")?.value || "";
    if (q) _filterConfigAssets(q);

    // Flash row green briefly
    const row = document.getElementById(`cfg-row-${coin}`);
    if (row) {
      row.style.borderColor = "var(--color-neon-green)";
      setTimeout(() => { const r = document.getElementById(`cfg-row-${coin}`); if (r) r.style.borderColor = ""; }, 1500);
    }
  } catch (e) { alert(`Error: ${e.message}`); }
}

async function deleteDefault(coin) {
  if (!_token) return;
  try {
    await fetch(`${API_BASE}/signal-lab/user-defaults/${coin}`, {
      method: "DELETE", headers: _authHeader(),
    });
    if (_userDefaults) delete _userDefaults[coin];
    _renderConfigSaved();
    _updateConfigBadge();
    const q = document.getElementById("config-search")?.value || "";
    if (q) _filterConfigAssets(q);
  } catch (e) { console.error("deleteDefault failed:", e); }
}

// ── Utils ──────────────────────────────────────────────────

function _fmt(n) {
  if (n === null || n === undefined) return "—";
  const num = parseFloat(n);
  if (num >= 1000) return num.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (num >= 1)    return num.toFixed(3);
  return num.toFixed(5);
}

function _ageLabel(seconds) {
  if (!seconds && seconds !== 0) return "—";
  if (seconds < 60)   return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds/60)}m`;
  const h = Math.floor(seconds/3600);
  const m = Math.floor((seconds % 3600) / 60);
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

function _statusLabel(status) {
  const labels = {
    pending:   "Activa",
    executed:  "Ejecutada",
    expired:   "⏱ Expirada",
    stopped:   "🚫 SL",
    tp_hit:    "✅ TP",
    cancelled: "Cancelada",
  };
  return labels[status] || status;
}

function _trendLabel(trend) {
  if (trend === "bearish") return "↘ Bajista";
  if (trend === "bullish") return "↗ Alcista";
  return "↔ Lateral";
}

function _setTimestamp(text) {
  const el = document.getElementById("sl-last-update");
  if (el) el.textContent = text;
}

// ── Mobile nav ─────────────────────────────────────────────

function toggleMobileNav() {
  const links = document.getElementById("navbar-links");
  if (links) links.classList.toggle("open");
}
