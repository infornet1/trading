"""
Telegram webhook router — handles incoming updates from @vizniago_bot.

Commands:
  /start <wallet_address>      Add a wallet to your alert list
  /status                      Show bots across all linked wallets
  /unlink <0xWallet|all>       Remove one wallet or all links
  /help                        List available commands

Multi-wallet: one Telegram user can link many wallets.
Auth model: wallet address (trust-based for alpha).
Step 8 will add NFT key on-chain verification.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import delete, select

from api.auth import get_current_address
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
    "/start `0xWallet` — Add a wallet to your alert list\n"
    "/status — Show bots across all linked wallets\n"
    "/unlink `0xWallet` — Remove a specific wallet\n"
    "/unlink all — Remove all linked wallets\n"
    "/help — Show this message\n\n"
    "_You can link multiple wallets. Each fires alerts independently._"
)


@router.get("/link-status")
async def telegram_link_status(address: str = Depends(get_current_address)):
    """Return how many Telegram chats are linked to this wallet."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(TelegramLink).where(TelegramLink.user_address == address.lower())
        )
        links = result.scalars().all()
    if links:
        return {"linked": True, "count": len(links)}
    return {"linked": False, "count": 0}


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
    elif command == "/unlink":
        await _handle_unlink(chat_id, arg)
    elif command == "/help":
        await send_message(chat_id, _HELP_TEXT)
    else:
        await send_message(chat_id, "Unknown command. Use /help to see available commands.")

    return {"ok": True}


_WELCOME_TEXT = (
    "VIZNAGO Bot 🛡 — Alertas DeFi en tiempo real\n\n"
    "Monitorea tus bots LP de cobertura desde Telegram.\n"
    "Soporta múltiples wallets. Sin datos personales.\n\n"
    "Comandos:\n"
    "/start `0xWallet` — vincular wallet\n"
    "/status         — ver bots activos\n"
    "/unlink         — desactivar alertas\n"
    "/help           — ayuda"
)


async def _handle_start(chat_id: int, wallet: str):
    wallet = wallet.lower().strip()

    # /start with no argument → show welcome + onboarding prompt
    if not wallet:
        await send_message(chat_id, _WELCOME_TEXT)
        return

    if not wallet.startswith("0x") or len(wallet) != 42:
        await send_message(
            chat_id,
            "❌ *Dirección inválida.*\n\n"
            "Uso: `/start 0xTuWallet`\n\n"
            "Puedes vincular múltiples wallets.",
        )
        return

    async with AsyncSessionLocal() as db:
        existing = await db.execute(
            select(TelegramLink).where(
                TelegramLink.telegram_chat_id == chat_id,
                TelegramLink.user_address == wallet,
            )
        )
        if existing.scalar_one_or_none():
            await send_message(chat_id, f"✅ Already linked: `{wallet[:6]}...{wallet[-4:]}`")
            return

        db.add(TelegramLink(user_address=wallet, telegram_chat_id=chat_id))
        await db.commit()

        # Count total wallets linked to this chat
        count_res = await db.execute(
            select(TelegramLink).where(TelegramLink.telegram_chat_id == chat_id)
        )
        total = len(count_res.scalars().all())

    await send_message(
        chat_id,
        f"✅ *Wallet added!*\n\n"
        f"`{wallet[:6]}...{wallet[-4:]}`\n\n"
        f"You now have *{total}* wallet(s) linked.\n"
        f"Use /status to see all bots, /unlink `0xWallet` to remove one.",
    )


async def _handle_unlink(chat_id: int, arg: str = ""):
    arg = arg.lower().strip()

    async with AsyncSessionLocal() as db:
        all_res = await db.execute(
            select(TelegramLink).where(TelegramLink.telegram_chat_id == chat_id)
        )
        links = all_res.scalars().all()

        if not links:
            await send_message(chat_id, "⚠️ No wallets linked — nothing to unlink.")
            return

        # /unlink all
        if arg == "all":
            await db.execute(
                delete(TelegramLink).where(TelegramLink.telegram_chat_id == chat_id)
            )
            await db.commit()
            await send_message(
                chat_id,
                f"🔕 *All wallets unlinked* ({len(links)} removed)\n\n"
                f"Use /start `0xWallet` to re-link at any time.",
            )
            return

        # /unlink 0xWallet
        if arg.startswith("0x") and len(arg) == 42:
            match = next((l for l in links if l.user_address == arg), None)
            if not match:
                await send_message(chat_id, f"⚠️ `{arg[:6]}...{arg[-4:]}` is not in your linked wallets.")
                return
            await db.execute(
                delete(TelegramLink).where(
                    TelegramLink.telegram_chat_id == chat_id,
                    TelegramLink.user_address == arg,
                )
            )
            await db.commit()
            remaining = len(links) - 1
            msg = (
                f"🔕 *Unlinked* `{arg[:6]}...{arg[-4:]}`\n\n"
                f"{remaining} wallet(s) still active."
                if remaining else
                f"🔕 *Unlinked* `{arg[:6]}...{arg[-4:]}`\n\nNo wallets remaining. Use /start to re-link."
            )
            await send_message(chat_id, msg)
            return

        # No arg — show list if multiple, unlink directly if only one
        if len(links) == 1:
            wallet = links[0].user_address
            await db.execute(
                delete(TelegramLink).where(TelegramLink.telegram_chat_id == chat_id)
            )
            await db.commit()
            await send_message(
                chat_id,
                f"🔕 *Unlinked* `{wallet[:6]}...{wallet[-4:]}`\n\nUse /start to re-link at any time.",
            )
            return

        # Multiple wallets — ask user to specify
        lines = ["⚠️ *You have multiple wallets linked. Specify which to remove:*\n"]
        for l in links:
            lines.append(f"• `/unlink {l.user_address}`")
        lines.append("\nOr use `/unlink all` to remove everything.")
        await send_message(chat_id, "\n".join(lines))


async def _handle_status(chat_id: int):
    async with AsyncSessionLocal() as db:
        links_res = await db.execute(
            select(TelegramLink).where(TelegramLink.telegram_chat_id == chat_id)
        )
        links = links_res.scalars().all()

        if not links:
            await send_message(
                chat_id,
                "⚠️ No wallets linked yet.\n\nUse `/start 0xYourWallet` to add a wallet.",
            )
            return

        wallets = [l.user_address for l in links]
        bots_res = await db.execute(
            select(BotConfig).where(BotConfig.user_address.in_(wallets))
        )
        bots = bots_res.scalars().all()

    lines = [f"*VIZNAGO Status* — {len(wallets)} wallet(s)\n"]
    for wallet in wallets:
        short = f"{wallet[:6]}...{wallet[-4:]}"
        wallet_bots = [b for b in bots if b.user_address == wallet]
        lines.append(f"👛 `{short}`")
        if not wallet_bots:
            lines.append("  _No bots configured_")
        else:
            for bot in wallet_bots:
                status = "🟢" if bot.active else "⚫"
                label  = _MODE_LABELS.get(bot.mode, bot.mode.upper())
                lines.append(f"  {status} *{label}* — {bot.pair} #{bot.nft_token_id}")
        lines.append("")

    await send_message(chat_id, "\n".join(lines).rstrip())
