"""Search channel history for a keyword."""

import os
import sys
import asyncio
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.types import PeerChannel

load_dotenv()

API_ID   = int(os.getenv("TG_API_ID"))
API_HASH = os.getenv("TG_API_HASH")
SESSION  = os.getenv("TG_SESSION", "viznago_listener")

KEYWORD = sys.argv[1] if len(sys.argv) > 1 else "BCH"

async def main():
    async with TelegramClient(SESSION, API_ID, API_HASH) as client:
        entity = await client.get_entity(PeerChannel(1951769926))
        print(f"Searching '{KEYWORD}' in: {entity.title}\n")

        async for msg in client.iter_messages(entity, search=KEYWORD, limit=10):
            print(f"[MSG ID: {msg.id} | {msg.date}]")
            print(msg.text or "(no text)")
            print("-" * 60)

asyncio.run(main())
