"""
Phase 0 POC — read raw messages from a Telegram signal channel.
Run once interactively to authenticate (phone + OTP), then stays connected.
"""

import os
import asyncio
from dotenv import load_dotenv
from telethon import TelegramClient, events

load_dotenv()

API_ID   = int(os.getenv("TG_API_ID"))
API_HASH = os.getenv("TG_API_HASH")
CHANNEL  = os.getenv("TG_CHANNEL")
SESSION  = os.getenv("TG_SESSION", "viznago_listener")

if not CHANNEL:
    raise ValueError("Set TG_CHANNEL in .env before running (e.g. @mycryptosignals)")

client = TelegramClient(SESSION, API_ID, API_HASH)


@client.on(events.NewMessage(chats=CHANNEL))
async def on_signal(event):
    msg = event.message
    print(f"\n[NEW SIGNAL] {msg.date}")
    print(f"{'=' * 60}")
    print(msg.text)
    print(f"{'=' * 60}")


async def main():
    await client.start()
    me = await client.get_me()
    print(f"Logged in as: {me.first_name} (@{me.username})")
    print(f"Listening to: {CHANNEL}")
    print("Waiting for new messages... (Ctrl+C to stop)\n")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
