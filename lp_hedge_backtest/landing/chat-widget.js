/**
 * VIZBOT — VIZNAGO FURY AI Chat Widget
 * Self-contained: injects its own CSS, works on landing + dashboard.
 * Requires no external dependencies.
 */
(function () {
  'use strict';

  const API_BASE  = '/trading/lp-hedge/api';
  const HIST_KEY  = 'vizbot_history';
  const LANG_KEY  = 'vf_lang';
  const MAX_HIST  = 20;   // messages kept in sessionStorage
  const MAX_SEND  = 6;    // messages sent to API per call

  // ── Language ─────────────────────────────────────────────────────────────
  function getLang() {
    return localStorage.getItem(LANG_KEY) || 'es';
  }

  const L = {
    es: {
      title:       'VIZBOT',
      subtitle:    'Asistente VIZNAGO FURY',
      placeholder: 'Pregunta sobre estrategia, configuración, soporte...',
      greeting:    '¡Hola! Soy VIZBOT, tu asistente de VIZNAGO FURY 🛡\n\nPuedo ayudarte con:\n• Cómo funciona el bot de cobertura LP\n• Configuración de parámetros (leverage, SL, rango)\n• Estrategia LP + perps y pérdida impermanente\n• Planes de membresía y roadmap\n• Dudas de soporte\n\n¿En qué puedo ayudarte?',
      errConn:     'Error al conectar con el asistente. Intenta de nuevo.',
      errRate:     'Límite alcanzado (20 mensajes/hora). Espera un momento.',
      sending:     'Enviando...',
      clearBtn:    'Limpiar chat',
    },
    en: {
      title:       'VIZBOT',
      subtitle:    'VIZNAGO FURY Assistant',
      placeholder: 'Ask about strategy, configuration, support...',
      greeting:    'Hi! I\'m VIZBOT, your VIZNAGO FURY assistant 🛡\n\nI can help you with:\n• How the LP hedge bot works\n• Parameter configuration (leverage, SL, range)\n• LP + perps strategy and impermanent loss\n• Membership plans and roadmap\n• Support questions\n\nWhat can I help you with?',
      errConn:     'Error connecting to assistant. Please try again.',
      errRate:     'Rate limit reached (20 msgs/hour). Please wait.',
      sending:     'Sending...',
      clearBtn:    'Clear chat',
    },
  };

  function t(key) { return (L[getLang()] || L.es)[key] || key; }

  // ── State ─────────────────────────────────────────────────────────────────
  let isOpen      = false;
  let isStreaming = false;
  let history     = [];

  function loadHistory() {
    try { history = JSON.parse(sessionStorage.getItem(HIST_KEY) || '[]'); }
    catch { history = []; }
  }
  function saveHistory() {
    if (history.length > MAX_HIST) history = history.slice(-MAX_HIST);
    sessionStorage.setItem(HIST_KEY, JSON.stringify(history));
  }

  // ── CSS injection ─────────────────────────────────────────────────────────
  function injectStyles() {
    if (document.getElementById('vizbot-styles')) return;
    const s = document.createElement('style');
    s.id = 'vizbot-styles';
    s.textContent = `
/* ── VIZBOT widget container ── */
#vizbot-widget {
  position: fixed; bottom: 24px; right: 24px; z-index: 9990;
  font-family: 'Inter', system-ui, sans-serif;
}

/* ── FAB button ── */
#vizbot-fab {
  width: 54px; height: 54px; border-radius: 50%;
  background: linear-gradient(135deg, #c9a84c 0%, #a8832e 100%);
  border: none; cursor: pointer; font-size: 1.25rem;
  box-shadow: 0 4px 20px rgba(201,168,76,0.45);
  display: flex; align-items: center; justify-content: center;
  position: relative; transition: transform .2s, box-shadow .2s;
}
#vizbot-fab:hover { transform: scale(1.08); box-shadow: 0 6px 28px rgba(201,168,76,0.6); }
#vizbot-fab-icon { line-height: 1; }
#vizbot-fab-dot {
  position: absolute; top: 4px; right: 4px;
  width: 10px; height: 10px; border-radius: 50%;
  background: #00e676; border: 2px solid #0d0d0d;
  animation: vizbot-pulse 2.2s ease-in-out infinite;
}
@keyframes vizbot-pulse {
  0%,100% { opacity:1; transform:scale(1); }
  50%      { opacity:.55; transform:scale(1.25); }
}

/* ── Chat panel ── */
#vizbot-panel {
  position: absolute; bottom: 64px; right: 0; width: 348px;
  background: #0d0d0d; border: 1px solid rgba(201,168,76,.32);
  border-radius: 14px; overflow: hidden;
  box-shadow: 0 12px 48px rgba(0,0,0,.7), 0 0 32px rgba(201,168,76,.07);
  display: flex; flex-direction: column;
  transform: translateY(12px) scale(.96); opacity: 0; pointer-events: none;
  transition: transform .22s ease, opacity .22s ease;
  max-height: 520px;
}
#vizbot-panel.vizbot-open {
  transform: translateY(0) scale(1); opacity: 1; pointer-events: all;
}

/* ── Header ── */
#vizbot-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 11px 14px; background: #111;
  border-bottom: 1px solid rgba(201,168,76,.18); flex-shrink: 0;
}
#vizbot-header-left { display: flex; align-items: center; gap: 9px; }
#vizbot-live-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: #00e676; box-shadow: 0 0 6px #00e676; flex-shrink: 0;
}
#vizbot-title-text {
  font-family: 'Orbitron', monospace; font-size: .72rem; font-weight: 700;
  color: #c9a84c; letter-spacing: .1em;
}
#vizbot-subtitle-text { font-size: .6rem; color: #555; margin-top: 1px; }
#vizbot-header-actions { display: flex; align-items: center; gap: 4px; }
.vizbot-hdr-btn {
  background: transparent; border: none; cursor: pointer;
  color: #555; font-size: .72rem; padding: 3px 7px; border-radius: 4px;
  transition: color .2s, background .2s;
}
.vizbot-hdr-btn:hover { color: #c9a84c; background: rgba(201,168,76,.08); }

/* ── Messages ── */
#vizbot-messages {
  flex: 1; overflow-y: auto; padding: 14px 12px;
  display: flex; flex-direction: column; gap: 10px;
  scrollbar-width: thin; scrollbar-color: #222 transparent;
  min-height: 0;
}
#vizbot-messages::-webkit-scrollbar { width: 4px; }
#vizbot-messages::-webkit-scrollbar-thumb { background: #2a2a2a; border-radius: 2px; }

.vizbot-bubble {
  max-width: 88%; padding: 9px 13px; border-radius: 10px;
  font-size: .79rem; line-height: 1.55; white-space: pre-wrap; word-break: break-word;
  animation: vizbot-fadein .18s ease;
}
@keyframes vizbot-fadein { from { opacity:0; transform:translateY(4px); } to { opacity:1; transform:none; } }

.vizbot-bubble-user {
  align-self: flex-end; background: #132033; color: #dce8f0;
  border: 1px solid rgba(0,212,255,.18); border-radius: 10px 10px 3px 10px;
}
.vizbot-bubble-assistant {
  align-self: flex-start; background: #141414; color: #e0e0e0;
  border: 1px solid #222; border-radius: 10px 10px 10px 3px;
}
.vizbot-bubble-assistant.vizbot-error { color: #ff6b6b; border-color: rgba(255,61,0,.3); }
.vizbot-bubble-typing {
  align-self: flex-start; background: #141414; color: #555;
  border: 1px solid #222; border-radius: 10px; font-style: italic;
}
.vizbot-typing-dot {
  display: inline-block; animation: vizbot-dots 1.2s infinite;
}
.vizbot-typing-dot:nth-child(2) { animation-delay: .2s; }
.vizbot-typing-dot:nth-child(3) { animation-delay: .4s; }
@keyframes vizbot-dots { 0%,80%,100%{opacity:.2} 40%{opacity:1} }

/* ── Input row ── */
#vizbot-input-row {
  display: flex; gap: 7px; padding: 10px 11px;
  border-top: 1px solid #1a1a1a; background: #0d0d0d; flex-shrink: 0;
}
#vizbot-input {
  flex: 1; background: #141414; border: 1px solid #252525;
  border-radius: 7px; padding: 8px 11px; color: #e0e0e0;
  font-size: .78rem; font-family: inherit; outline: none;
  transition: border-color .2s;
}
#vizbot-input:focus { border-color: rgba(201,168,76,.45); }
#vizbot-input::placeholder { color: #444; }
#vizbot-send {
  background: linear-gradient(135deg,#c9a84c,#a8832e);
  border: none; border-radius: 7px; color: #000;
  font-size: .85rem; padding: 8px 13px; cursor: pointer;
  transition: opacity .2s; font-weight: 700;
}
#vizbot-send:hover { opacity: .88; }
#vizbot-send:disabled { opacity: .35; cursor: not-allowed; }

@media (max-width: 420px) {
  #vizbot-widget { bottom: 16px; right: 12px; }
  #vizbot-panel  { width: calc(100vw - 24px); right: -12px; }
}
    `;
    document.head.appendChild(s);
  }

  // ── DOM helpers ───────────────────────────────────────────────────────────
  function el(id) { return document.getElementById(id); }

  function scrollBottom() {
    const m = el('vizbot-messages');
    if (m) m.scrollTop = m.scrollHeight;
  }

  function appendBubble(type, text, save) {
    const m = el('vizbot-messages');
    if (!m) return null;
    const div = document.createElement('div');
    div.className = 'vizbot-bubble vizbot-bubble-' + type;
    if (type === 'typing') {
      div.innerHTML = '<span class="vizbot-typing-dot">●</span><span class="vizbot-typing-dot">●</span><span class="vizbot-typing-dot">●</span>';
    } else {
      div.textContent = text;
    }
    m.appendChild(div);
    scrollBottom();
    if (save && text) {
      history.push({ role: type === 'user' ? 'user' : 'assistant', content: text });
      saveHistory();
    }
    return div;
  }

  function removeTyping() {
    el('vizbot-messages')?.querySelector('.vizbot-bubble-typing')?.remove();
  }

  // ── Build widget DOM ──────────────────────────────────────────────────────
  function buildWidget() {
    if (el('vizbot-widget')) return;   // already built
    injectStyles();
    loadHistory();

    const wrap = document.createElement('div');
    wrap.id = 'vizbot-widget';
    wrap.innerHTML = `
      <button id="vizbot-fab" onclick="vizbotToggle()" aria-label="VIZBOT assistant">
        <span id="vizbot-fab-icon">💬</span>
        <span id="vizbot-fab-dot"></span>
      </button>
      <div id="vizbot-panel" role="dialog" aria-label="VIZBOT chat">
        <div id="vizbot-header">
          <div id="vizbot-header-left">
            <div id="vizbot-live-dot"></div>
            <div>
              <div id="vizbot-title-text">VIZBOT</div>
              <div id="vizbot-subtitle-text"></div>
            </div>
          </div>
          <div id="vizbot-header-actions">
            <button class="vizbot-hdr-btn" id="vizbot-clear-btn" onclick="vizbotClear()" title="Clear"></button>
            <button class="vizbot-hdr-btn" onclick="vizbotToggle()" title="Close">✕</button>
          </div>
        </div>
        <div id="vizbot-messages"></div>
        <div id="vizbot-input-row">
          <input id="vizbot-input" type="text" autocomplete="off"
                 onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();vizbotSend();}" />
          <button id="vizbot-send" onclick="vizbotSend()">➤</button>
        </div>
      </div>
    `;
    document.body.appendChild(wrap);

    // Set language labels
    el('vizbot-subtitle-text').textContent = t('subtitle');
    el('vizbot-input').placeholder         = t('placeholder');
    el('vizbot-clear-btn').textContent     = t('clearBtn');

    // Render history or greeting
    if (history.length === 0) {
      appendBubble('assistant', t('greeting'), false);
    } else {
      history.forEach(m => {
        const div = document.createElement('div');
        div.className = 'vizbot-bubble vizbot-bubble-' + (m.role === 'user' ? 'user' : 'assistant');
        div.textContent = m.content;
        el('vizbot-messages').appendChild(div);
      });
      scrollBottom();
    }

    // Close on Escape
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && isOpen) vizbotToggle(); });
  }

  // ── Public API ────────────────────────────────────────────────────────────
  window.vizbotToggle = function () {
    isOpen = !isOpen;
    el('vizbot-panel')?.classList.toggle('vizbot-open', isOpen);
    el('vizbot-fab-icon').textContent = isOpen ? '✕' : '💬';
    if (isOpen) { el('vizbot-input')?.focus(); scrollBottom(); }
  };

  window.vizbotClear = function () {
    history = [];
    sessionStorage.removeItem(HIST_KEY);
    const m = el('vizbot-messages');
    if (m) { m.innerHTML = ''; appendBubble('assistant', t('greeting'), false); }
  };

  window.vizbotSend = async function () {
    if (isStreaming) return;
    const input = el('vizbot-input');
    if (!input) return;
    const message = input.value.trim();
    if (!message) return;
    input.value = '';

    appendBubble('user', message, true);
    const typing = appendBubble('typing', '', false);
    isStreaming = true;
    el('vizbot-send').disabled = true;

    try {
      const resp = await fetch(API_BASE + '/assistant/chat', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          message,
          history: history.slice(-MAX_SEND).slice(0, -1),   // exclude the just-saved user msg
        }),
      });

      typing.remove();

      const bubble = appendBubble('assistant', '', false);
      let fullText = '';

      const reader  = resp.body.getReader();
      const decoder = new TextDecoder();
      let   buf     = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop();   // keep partial line

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6);
          if (raw === '[DONE]') break;
          try {
            const ev = JSON.parse(raw);
            if (ev.text) {
              fullText += ev.text;
              bubble.textContent = fullText;
              scrollBottom();
            }
            if (ev.error) {
              bubble.textContent = ev.error.includes('Rate') ? t('errRate') : t('errConn');
              bubble.classList.add('vizbot-error');
            }
          } catch { /* partial JSON — skip */ }
        }
      }

      if (fullText) {
        history.push({ role: 'assistant', content: fullText });
        saveHistory();
      }
    } catch {
      typing.remove();
      appendBubble('assistant', t('errConn'), false).classList.add('vizbot-error');
    } finally {
      isStreaming = false;
      el('vizbot-send').disabled = false;
      el('vizbot-input')?.focus();
    }
  };

  // ── Init ──────────────────────────────────────────────────────────────────
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', buildWidget);
  } else {
    buildWidget();
  }
})();
