"""
Telegram alert dispatcher for VIZNAGO bots.

Sends formatted push notifications to users who have linked their wallet
via @vizniago_bot. Fires as a background task — never blocks event handling.
"""

import asyncio
import os

import httpx

_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN", "")
_API_BASE = f"https://api.telegram.org/bot{_TOKEN}"

# Only these event types trigger a Telegram push (high-priority set)
_ALERT_EVENTS = {
    "hedge_opened", "sl_hit", "tp_hit", "trailing_stop",
    "fury_entry", "fury_sl", "fury_tp", "fury_circuit_breaker",
    "error", "lp_removed", "lp_burned",
}

_MODE_LABELS = {
    "aragan": "Defensor Bajista",
    "avaro":  "Defensor Alcista",
    "fury":   "FURY",
    "whale":  "WHALE",
}


def _fmt_price(price) -> str:
    if price is None:
        return "—"
    return f"${float(price):,.2f}"


def _fmt_pnl(pnl) -> str:
    if pnl is None:
        return ""
    v    = float(pnl)
    sign = "+" if v >= 0 else ""
    return f"{sign}${v:.2f}"


def _build_message(event_type: str, pair: str, mode: str, price, pnl, details) -> str:
    d          = details or {}
    mode_label = _MODE_LABELS.get(mode, mode.upper())
    p          = _fmt_price(price)
    lines: list[str] = []

    if event_type == "hedge_opened":
        side = d.get("side", "SHORT")
        size = d.get("size", "")
        lev  = d.get("leverage", "")
        lines = [f"🛡 *VIZNAGO {mode_label}*", f"{side} opened @ {p}"]
        if size: lines.append(f"Size: {size}")
        if lev:  lines.append(f"Leverage: {lev}x")
        lines.append(f"Pair: {pair}")

    elif event_type == "sl_hit":
        lines = [f"🛑 *Stop Loss Hit* — {mode_label}", f"Closed @ {p}"]
        if pnl: lines.append(f"PnL: {_fmt_pnl(pnl)}")

    elif event_type == "tp_hit":
        lines = [f"✅ *Take Profit Hit* — {mode_label}", f"Closed @ {p}"]
        if pnl: lines.append(f"PnL: {_fmt_pnl(pnl)}")

    elif event_type == "trailing_stop":
        lines = [f"🔒 *Trailing Stop* — {mode_label}", f"Closed @ {p}"]
        if pnl: lines.append(f"PnL: {_fmt_pnl(pnl)}")

    elif event_type == "fury_entry":
        side  = d.get("side", "")
        gates = d.get("gates", "")
        lev   = d.get("leverage", "")
        lines = [f"⚡ *VIZNAGO FURY Entry*"]
        if side:  lines.append(f"{side} @ {p}")
        if lev:   lines.append(f"Leverage: {lev}x")
        if gates: lines.append(f"Gates: {gates}/6")

    elif event_type == "fury_sl":
        lines = [f"🛑 *FURY Stop Loss*", f"Closed @ {p}"]
        if pnl: lines.append(f"PnL: {_fmt_pnl(pnl)}")

    elif event_type == "fury_tp":
        lines = [f"✅ *FURY Take Profit*", f"Closed @ {p}"]
        if pnl: lines.append(f"PnL: {_fmt_pnl(pnl)}")

    elif event_type == "fury_circuit_breaker":
        reason = d.get("reason", "")
        lines  = [f"⚠️ *FURY Circuit Breaker*",
                  f"Bot paused — {reason}" if reason else "Bot paused"]

    elif event_type == "lp_removed":
        lines = [f"⚠️ *LP Position Removed* — {pair}"]

    elif event_type == "lp_burned":
        lines = [f"🔥 *LP Position Burned* — {pair}"]

    elif event_type == "error":
        msg   = d.get("msg", "")
        lines = [f"❌ *Bot Error* — {mode_label}",
                 msg if msg else "Check dashboard for details"]

    else:
        lines = [f"ℹ️ *{event_type}* — {mode_label}"]

    lines.append("\n_VIZNAGO_")
    return "\n".join(lines)


async def send_message(chat_id: int, text: str) -> bool:
    """Send a Telegram message. Returns True on success."""
    if not _TOKEN:
        return False
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.post(
                f"{_API_BASE}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            )
            return r.status_code == 200
    except Exception as e:
        print(f"[Telegram] Send error to {chat_id}: {e}", flush=True)
        return False


async def send_alert(config_id: int, event_type: str, price, pnl, details):
    """
    Look up the Telegram chat_id for this config's owner and send an alert.
    Only fires for events in _ALERT_EVENTS — silent for all others.
    """
    if event_type not in _ALERT_EVENTS:
        return
    if not _TOKEN:
        return

    try:
        from sqlalchemy import select
        from api.database import AsyncSessionLocal
        from api.models import BotConfig, TelegramLink

        async with AsyncSessionLocal() as db:
            bot_res = await db.execute(
                select(BotConfig).where(BotConfig.id == config_id)
            )
            bot = bot_res.scalar_one_or_none()
            if not bot:
                return

            links_res = await db.execute(
                select(TelegramLink).where(TelegramLink.user_address == bot.user_address)
            )
            links = links_res.scalars().all()
            if not links:
                return

            msg = _build_message(event_type, bot.pair, bot.mode, price, pnl, details)
            for link in links:
                asyncio.create_task(send_message(link.telegram_chat_id, msg))

    except Exception as e:
        print(f"[Telegram] Alert error for config {config_id}: {e}", flush=True)
