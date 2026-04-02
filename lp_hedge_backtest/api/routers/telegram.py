"""
Telegram webhook router — handles incoming updates from @vizniago_bot.

Commands:
  /start <wallet_address>   Link wallet to receive bot alerts
  /status                   Show all bots for the linked wallet
  /help                     List available commands

Auth model: wallet address (trust-based for alpha).
Step 8 will add NFT key on-chain verification.
"""

from datetime import datetime

from fastapi import APIRouter, Request
from sqlalchemy import select

from api.database import AsyncSessionLocal
from api.models import BotConfig, TelegramLink
from api.telegram_alerts import send_message

router = APIRouter(prefix="/telegram", tags=["telegram"])

_MODE_LABELS = {
    "aragan": "Defensor Bajista",
    "avaro":  "Defensor Alcista",
    "fury":   "FURY",
    "whale":  "WHALE",
}

_HELP_TEXT = (
    "*VIZNAGO Bot Commands*\n\n"
    "/start `0xYourWallet` — Link wallet to receive alerts\n"
    "/status — Show your active bots\n"
    "/help — Show this message\n\n"
    "_Visit the dashboard to manage your bots._"
)


@router.post("/webhook")
async def telegram_webhook(request: Request):
    """Receive incoming Telegram updates (registered via setWebhook)."""
    try:
        body = await request.json()
    except Exception:
        return {"ok": True}

    message = body.get("message") or body.get("edited_message")
    if not message:
        return {"ok": True}

    chat_id = message["chat"]["id"]
    text    = (message.get("text") or "").strip()

    if not text.startswith("/"):
        return {"ok": True}

    parts   = text.split(maxsplit=1)
    command = parts[0].lower().split("@")[0]  # strip @botname suffix if present
    arg     = parts[1].strip() if len(parts) > 1 else ""

    if command == "/start":
        await _handle_start(chat_id, arg)
    elif command == "/status":
        await _handle_status(chat_id)
    elif command == "/help":
        await send_message(chat_id, _HELP_TEXT)
    else:
        await send_message(chat_id, "Unknown command. Use /help to see available commands.")

    return {"ok": True}


async def _handle_start(chat_id: int, wallet: str):
    wallet = wallet.lower().strip()
    if not wallet.startswith("0x") or len(wallet) != 42:
        await send_message(
            chat_id,
            "❌ *Invalid wallet address.*\n\n"
            "Usage: `/start 0xYourWalletAddress`\n\n"
            "Connect your wallet on the dashboard first, then copy the address here.",
        )
        return

    async with AsyncSessionLocal() as db:
        existing = await db.execute(
            select(TelegramLink).where(TelegramLink.telegram_chat_id == chat_id)
        )
        link = existing.scalar_one_or_none()

        if link:
            if link.user_address == wallet:
                await send_message(chat_id, f"✅ Already linked to `{wallet[:6]}...{wallet[-4:]}`")
                return
            link.user_address = wallet
            link.linked_at    = datetime.utcnow()
            await db.commit()
            await send_message(
                chat_id,
                f"🔄 *Wallet updated*\n`{wallet[:6]}...{wallet[-4:]}`\n\nAlerts will now follow this wallet's bots.",
            )
            return

        db.add(TelegramLink(user_address=wallet, telegram_chat_id=chat_id))
        await db.commit()

    await send_message(
        chat_id,
        f"✅ *Wallet linked!*\n\n"
        f"`{wallet[:6]}...{wallet[-4:]}`\n\n"
        f"You'll receive alerts for:\n"
        f"• Hedge entries & exits\n"
        f"• Stop losses & take profits\n"
        f"• Circuit breakers & errors\n"
        f"• LP events\n\n"
        f"Use /status to see your bots.",
    )


async def _handle_status(chat_id: int):
    async with AsyncSessionLocal() as db:
        link_res = await db.execute(
            select(TelegramLink).where(TelegramLink.telegram_chat_id == chat_id)
        )
        link = link_res.scalar_one_or_none()

        if not link:
            await send_message(
                chat_id,
                "⚠️ No wallet linked yet.\n\nUse `/start 0xYourWallet` to link your wallet.",
            )
            return

        bots_res = await db.execute(
            select(BotConfig).where(BotConfig.user_address == link.user_address)
        )
        bots = bots_res.scalars().all()

    if not bots:
        await send_message(chat_id, "No bots found for your wallet.")
        return

    short_wallet = f"{link.user_address[:6]}...{link.user_address[-4:]}"
    lines = [f"*VIZNAGO Bots* — `{short_wallet}`\n"]
    for bot in bots:
        status = "🟢 RUNNING" if bot.active else "⚫ STOPPED"
        label  = _MODE_LABELS.get(bot.mode, bot.mode.upper())
        nft    = str(bot.nft_token_id)
        lines.append(f"{status} *{label}* — {bot.pair} #{nft}")

    await send_message(chat_id, "\n".join(lines))
