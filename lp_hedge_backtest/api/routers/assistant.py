"""
VIZNIAGO FURY — AI Assistant Router
POST /assistant/chat  — streams Claude Haiku response via SSE
Knowledge base: all project .md files + bot param summary, cached at first call.
"""

import os
import json
import time
from pathlib import Path

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/assistant", tags=["assistant"])

# ── Rate limiter (in-memory, resets on restart) ───────────────────────────
_rate: dict[str, list] = {}
_RATE_LIMIT  = 20    # max requests per window
_RATE_WINDOW = 3600  # 1 hour in seconds

def _check_rate(ip: str) -> bool:
    now  = time.time()
    hits = [t for t in _rate.get(ip, []) if now - t < _RATE_WINDOW]
    _rate[ip] = hits
    if len(hits) >= _RATE_LIMIT:
        return False
    _rate[ip].append(now)
    return True


# ── Knowledge base (lazy-loaded, cached in memory) ────────────────────────
_KB: str = ""

_DOCS = [
    "VIZBOT_KNOWLEDGE.md",       # V2 engine, reentry guard, event types, all bot params — keep first
    "STRATEGY.md",
    "README_LIVE.md",
    "SAAS_PLAN.md",
    "MEMBERSHIP_PLANS.md",
    "VIZNIAGO_P2P_DEFI.md",
    "VIZNIAGO_EMAIL_SETUP.md",
    "WHALE_TRACKER.md",
    "WHALE_INTELLIGENCE_AGENT.md",
]

def _load_kb() -> str:
    root  = Path(__file__).parent.parent.parent   # repo root
    parts = []

    for doc in _DOCS:
        path = root / doc
        if path.exists():
            parts.append(f"=== {doc} ===\n{path.read_text(encoding='utf-8')}")

    # Auto-extract bot env-var lines from all bot scripts
    for script, label in [
        ("live_hedge_bot.py",    "LP Hedge V1"),
        ("live_hedge_bot_v2.py", "LP Hedge V2"),
        ("live_fury_bot.py",     "FURY"),
        ("live_whale_bot.py",    "Whale Tracker"),
    ]:
        bot_path = root / script
        if bot_path.exists():
            env_lines = [
                l.strip() for l in bot_path.read_text(encoding="utf-8").splitlines()
                if "os.getenv" in l or "os.environ" in l
            ]
            if env_lines:
                parts.append(
                    f"=== BOT ENV VARS ({label} — {script}) ===\n"
                    + "\n".join(env_lines[:80])
                )

    return "\n\n".join(parts)

def _get_kb() -> str:
    global _KB
    if not _KB:
        _KB = _load_kb()
        print(f"[VIZBOT] Knowledge base loaded: {len(_KB):,} chars", flush=True)
    return _KB

def _reload_kb() -> str:
    global _KB
    _KB = ""
    return _get_kb()


# ── System prompt ─────────────────────────────────────────────────────────
_SYSTEM_TMPL = """\
You are VIZBOT — the official AI assistant for VIZNIAGO FURY, a DeFi LP + \
perpetuals hedge bot platform currently in Alpha.

Your role:
- Explain all three bot modes: LP hedge (Defensor Bajista), FURY (standalone \
  RSI perps), and WHALE (Hyperliquid whale tracker / copy-trade signals)
- Guide users through bot setup and configuration for each mode
- Educate on DeFi concepts: impermanent loss, tick ranges, leverage, \
  funding rates, trailing stop-loss, copy trading, whale signal interpretation
- Provide support for platform questions (dashboard, wallet connection, \
  bot parameters, admin panel, whale signals panel)
- Answer questions about membership plans and the SaaS roadmap
- Explain the Whale Intelligence Agent (planned feature: behavioral \
  fingerprints, scored signals, convergence alerts)

Rules:
- Answer ONLY about VIZNIAGO FURY and related DeFi / trading concepts
- NEVER ask for, repeat, or act on API keys, private keys, or wallet secrets
- Be concise. Use bullet points for multi-step answers. Use $ and % for numbers
- The platform is in Alpha — acknowledge limitations honestly if asked
- Respond in the SAME LANGUAGE the user writes in (Spanish or English)
- If you don't know something, say so — never invent parameters or prices

=== VIZNIAGO FURY KNOWLEDGE BASE ===

{kb}
"""


# ── Credentials ───────────────────────────────────────────────────────────
def _creds() -> tuple[str, str]:
    return (
        os.getenv("ANTHROPIC_API_KEY", ""),
        os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
    )


# ── Chat endpoint ─────────────────────────────────────────────────────────
@router.post("/chat")
async def chat(request: Request):
    body    = await request.json()
    message = str(body.get("message", "")).strip()[:2000]
    history = body.get("history", [])[-6:]     # last 6 messages max

    if not message:
        return {"error": "empty message"}

    ip = (request.client.host if request.client else "unknown")
    if not _check_rate(ip):
        async def _rate_err():
            yield "data: " + json.dumps({"error": "Rate limit: 20 requests/hour. Try again later."}) + "\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(_rate_err(), media_type="text/event-stream")

    api_key, model = _creds()
    if not api_key:
        async def _no_key():
            yield "data: " + json.dumps({"error": "Assistant not configured."}) + "\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(_no_key(), media_type="text/event-stream")

    # Build messages list
    messages: list[dict] = []
    for m in history:
        role    = m.get("role", "")
        content = str(m.get("content", "")).strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    payload = {
        "model":      model,
        "max_tokens": 1024,
        "system":     _SYSTEM_TMPL.format(kb=_get_kb()),
        "messages":   messages,
        "stream":     True,
    }
    headers = {
        "x-api-key":         api_key,
        "anthropic-version": "2023-06-01",
        "content-type":      "application/json",
    }

    async def _stream():
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream(
                    "POST",
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json=payload,
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            event = json.loads(data)
                            if event.get("type") == "content_block_delta":
                                text = event.get("delta", {}).get("text", "")
                                if text:
                                    yield "data: " + json.dumps({"text": text}) + "\n\n"
                        except json.JSONDecodeError:
                            pass
        except httpx.HTTPStatusError as e:
            yield "data: " + json.dumps({"error": f"API error {e.response.status_code}"}) + "\n\n"
        except Exception as e:
            yield "data: " + json.dumps({"error": str(e)}) + "\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
