"""
Telegram long-polling task — alternative to webhook for environments where
Telegram's servers can't resolve the local domain (e.g. .ve TLD DNS issues).

Runs as an asyncio background task inside the FastAPI lifespan.
Polls getUpdates every 30 s (Telegram-side long poll), processes commands,
marks updates as consumed via offset. No external URL registration needed.
"""

import asyncio
import os

import httpx

from api.routers.telegram import _handle_start, _handle_status, _handle_unlink, _HELP_TEXT
from api.telegram_alerts import send_message

_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN", "")
_API_BASE = f"https://api.telegram.org/bot{_TOKEN}"
_POLL_TIMEOUT = 30   # seconds — long-poll window held open by Telegram


async def _process_update(update: dict):
    message = update.get("message") or update.get("edited_message")
    if not message:
        return

    chat_id = message["chat"]["id"]
    text    = (message.get("text") or "").strip()

    if not text.startswith("/"):
        return

    parts   = text.split(maxsplit=1)
    command = parts[0].lower().split("@")[0]
    arg     = parts[1].strip() if len(parts) > 1 else ""

    if command == "/start":
        await _handle_start(chat_id, arg)
    elif command == "/status":
        await _handle_status(chat_id)
    elif command == "/unlink":
        await _handle_unlink(chat_id)
    elif command == "/help":
        await send_message(chat_id, _HELP_TEXT)
    else:
        await send_message(chat_id, "Unknown command. Use /help to see available commands.")


async def run_poller():
    """
    Long-polling loop. Runs indefinitely — cancel the task to stop.
    Automatically resumes after errors with a short back-off.
    """
    if not _TOKEN:
        print("[TelegramPoller] TELEGRAM_BOT_TOKEN not set — poller disabled", flush=True)
        return

    # Make sure no stale webhook is registered (would block getUpdates)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(f"{_API_BASE}/deleteWebhook", json={"drop_pending_updates": False})
    except Exception as e:
        print(f"[TelegramPoller] Could not delete webhook: {e}", flush=True)

    print("[TelegramPoller] Started — polling @vizniago_bot for updates", flush=True)
    offset = 0
    backoff = 5

    while True:
        try:
            async with httpx.AsyncClient(timeout=_POLL_TIMEOUT + 5) as client:
                r = await client.post(
                    f"{_API_BASE}/getUpdates",
                    json={"offset": offset, "timeout": _POLL_TIMEOUT, "allowed_updates": ["message"]},
                )
            if r.status_code != 200:
                print(f"[TelegramPoller] HTTP {r.status_code} — retrying in {backoff}s", flush=True)
                await asyncio.sleep(backoff)
                continue

            data = r.json()
            if not data.get("ok"):
                print(f"[TelegramPoller] API error: {data} — retrying in {backoff}s", flush=True)
                await asyncio.sleep(backoff)
                continue

            backoff = 5  # reset back-off on success
            updates = data.get("result", [])
            for update in updates:
                offset = update["update_id"] + 1
                try:
                    await _process_update(update)
                except Exception as e:
                    print(f"[TelegramPoller] Error processing update {update.get('update_id')}: {e}", flush=True)

        except asyncio.CancelledError:
            print("[TelegramPoller] Stopped", flush=True)
            return
        except Exception as e:
            print(f"[TelegramPoller] Connection error: {e} — retrying in {backoff}s", flush=True)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)  # exponential back-off, cap at 60 s
