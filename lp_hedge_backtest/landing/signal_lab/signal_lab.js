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
let _activeSignalId = null;   // signal being executed

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
  await Promise.all([fetchLpRange(), fetchSignals()]);
  _setTimestamp("Actualizado " + new Date().toLocaleTimeString("es-VE", { hour: "2-digit", minute: "2-digit" }));
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

    const active  = _signals.filter(s => s.status === "pending");
    const closed  = _signals.filter(s => s.status !== "pending");

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
      content.innerHTML += `<div class="sl-signal-list" style="margin-top:8px">${closed.slice(0,3).map(s => _renderSignalCard(s, true)).join("")}</div>`;
    }
    content.classList.remove("hidden");

    _buildHistorySummary(closed);
    histTgl.classList.remove("hidden");

  } catch {
    loading.classList.add("hidden");
    empty.classList.remove("hidden");
  }
}

function _renderSignalCard(sig, forceExpired = false) {
  const expired  = forceExpired || sig.status !== "pending";
  const dir      = (sig.direction || "short").toLowerCase();
  const lev      = sig.leverage ? `${sig.leverage}x` : "";
  const entry    = sig.entry    ? `$${_fmt(sig.entry)}`    : "—";
  const sl       = sig.stoploss ? `$${_fmt(sig.stoploss)}` : "—";
  const tps      = (sig.targets || []).map(t => `$${_fmt(t)}`).join(" / ");
  const age      = _ageLabel(sig.age_seconds);
  const statusLabel = _statusLabel(sig.status);

  const dirHtml = `<span class="sl-dir-pill ${dir}">${dir.toUpperCase()}</span>`;
  const btnHtml = expired
    ? `<span style="font-size:0.65rem;color:var(--color-text-muted)">${statusLabel}</span>`
    : `<button class="btn btn-primary btn-sm" onclick="openExecuteModal(${sig.id})">Ejecutar →</button>`;

  return `
    <div class="sl-signal-card${expired ? " sl-signal-card--expired" : ""}">
      ${dirHtml}
      <div class="sl-signal-info">
        <div class="sl-signal-pair">${sig.pair || "—"} ${lev}</div>
        <div class="sl-signal-prices">E ${entry} · SL ${sl}${tps ? " · TP " + tps : ""}</div>
      </div>
      <div class="sl-signal-age">${age}</div>
      ${btnHtml}
    </div>
  `;
}

function _buildHistorySummary(closed) {
  const tpCount  = closed.filter(s => s.status === "tp_hit").length;
  const slCount  = closed.filter(s => s.status === "stopped").length;
  const expCount = closed.filter(s => s.status === "expired" || s.status === "cancelled").length;

  const parts = [];
  if (tpCount)  parts.push(`TP ✅ ${tpCount}`);
  if (slCount)  parts.push(`SL ❌ ${slCount}`);
  if (expCount) parts.push(`Expiradas ${expCount}`);

  const summary = document.getElementById("history-summary");
  summary.textContent = `▸ Ver historial (${parts.join(" · ")})`;
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
    if (history.length === 0) {
      el.innerHTML = '<p style="font-size:0.72rem;color:var(--color-text-muted);padding-top:8px">Sin historial aún.</p>';
      return;
    }
    el.innerHTML = `<div class="sl-history-list">${history.map(_renderHistoryRow).join("")}</div>`;
    _historyLoaded = true;
  } catch {
    el.innerHTML = '<p style="font-size:0.72rem;color:#f87171;padding-top:8px">Error al cargar historial.</p>';
  }
}

function _renderHistoryRow(sig) {
  const dir   = (sig.direction || "").toUpperCase();
  const entry = sig.entry ? `$${_fmt(sig.entry)}` : "—";
  const age   = sig.received_at ? new Date(sig.received_at).toLocaleDateString("es-VE",{month:"short",day:"numeric"}) : "—";
  return `
    <div class="sl-history-row">
      <span class="sl-outcome-pill ${sig.status}">${_statusLabel(sig.status)}</span>
      <span>${sig.pair || "—"} ${dir}</span>
      <span>E ${entry}</span>
      <span style="margin-left:auto">${age}</span>
    </div>
  `;
}

// ── Execute Modal ──────────────────────────────────────────

async function openExecuteModal(signalId) {
  _activeSignalId = signalId;
  _selectedWallet = null;

  const sig = _signals.find(s => s.id === signalId);
  if (!sig) return;

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
  await _loadModalWallets();

  document.getElementById("modal-confirm-btn").disabled = true;
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
    const res = await fetch(`${API_BASE}/bots`, {
      headers: { "Content-Type": "application/json", ..._authHeader() },
    });
    if (!res.ok) throw new Error(res.status);
    const data = await res.json();
    const configs = data.configs || data || [];

    // Build wallet map: address → has_active_bot
    const walletMap = {};
    for (const cfg of configs) {
      const addr = cfg.hl_wallet_addr;
      if (!addr) continue;
      if (!walletMap[addr]) walletMap[addr] = { active: false, bot_id: null };
      if (cfg.active) { walletMap[addr].active = true; walletMap[addr].bot_id = cfg.id; }
    }

    if (Object.keys(walletMap).length === 0) {
      listEl.innerHTML = '<p style="font-size:0.72rem;color:var(--color-text-muted)">No hay wallets registradas. Configura un bot primero.</p>';
      return;
    }

    listEl.innerHTML = Object.entries(walletMap).map(([addr, info]) => {
      const short  = addr.slice(0,6) + "..." + addr.slice(-4);
      const locked = info.active;
      return `
        <label class="sl-wallet-option${locked ? " sl-wallet-option--locked" : ""}">
          <input type="radio" name="exec-wallet" value="${addr}" ${locked ? "disabled" : ""}
            onchange="onWalletSelected('${addr}')">
          <span class="sl-wallet-addr">${short}</span>
          ${locked ? `<span class="sl-wallet-lock">🔒 Bot #${info.bot_id} activo</span>` : ""}
        </label>
      `;
    }).join("");

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
  document.getElementById("modal-size-row").classList.remove("hidden");
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
  btn.textContent = "Registrando...";

  try {
    const res = await fetch(`${API_BASE}/signal-lab/execute`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ..._authHeader() },
      body: JSON.stringify({ signal_id: _activeSignalId, hl_wallet_addr: _selectedWallet }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.status);

    closeExecuteModal();
    _showOrderDetails(data.order);
  } catch (e) {
    btn.disabled = false;
    btn.textContent = "Confirmar →";
    alert(`Error: ${e.message}`);
  }
}

function _showOrderDetails(order) {
  if (!order) return;
  const dir    = (order.direction || "short").toUpperCase();
  const entry  = order.entry    ? `$${_fmt(order.entry)}`    : "—";
  const sl     = order.stoploss ? `$${_fmt(order.stoploss)}` : "—";
  const tps    = (order.targets || []).map(t => `$${_fmt(t)}`).join(" / ");
  const sizePct = order.size_pct || 2;

  document.getElementById("order-detail-content").innerHTML = `
    <div><span class="od-label">Par:       </span><span class="od-value">${order.symbol || "—"}/USDC</span></div>
    <div><span class="od-label">Dirección: </span><span class="od-value">${dir}</span></div>
    <div><span class="od-label">Leverage:  </span><span class="od-value">${order.leverage || "—"}x</span></div>
    <div><span class="od-label">Entrada:   </span><span class="od-value">${entry}</span></div>
    <div><span class="od-label">Stop Loss: </span><span class="od-value">${sl}</span></div>
    ${tps ? `<div><span class="od-label">Targets:   </span><span class="od-value">${tps}</span></div>` : ""}
    <div><span class="od-label">Tamaño:    </span><span class="od-value">${sizePct}% de tu balance</span></div>
  `;
  document.getElementById("order-detail-modal").classList.remove("hidden");
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
