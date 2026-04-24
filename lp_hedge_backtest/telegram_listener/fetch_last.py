"""
One-shot script: fetch last 5 messages from a private Telegram channel.
First run will ask for phone number + OTP to create the session file.
"""

import os
import asyncio
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.types import PeerChannel

load_dotenv()

API_ID   = int(os.getenv("TG_API_ID"))
API_HASH = os.getenv("TG_API_HASH")
SESSION  = os.getenv("TG_SESSION", "viznago_listener")

# Private channel ID from https://t.me/c/1951769926/7
CHANNEL_ID = -1001951769926


async def main():
    async with TelegramClient(SESSION, API_ID, API_HASH) as client:
        me = await client.get_me()
        print(f"Logged in as: {me.first_name} (@{me.username})\n")

        entity = await client.get_entity(PeerChannel(1951769926))
        print(f"Channel: {entity.title}\n")

        messages = await client.get_messages(entity, limit=5)
        for msg in reversed(messages):
            print(f"[{msg.date}]")
            print(msg.text or "(no text — media/sticker)")
            print("-" * 60)


if __name__ == "__main__":
    asyncio.run(main())
