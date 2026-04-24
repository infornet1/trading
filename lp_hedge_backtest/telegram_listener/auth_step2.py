"""Step 2: Sign in with OTP + optional 2FA password, then fetch last 5 messages."""

import os
import sys
import json
import asyncio
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.types import PeerChannel
from telethon.errors import SessionPasswordNeededError

load_dotenv()

API_ID   = int(os.getenv("TG_API_ID"))
API_HASH = os.getenv("TG_API_HASH")
SESSION  = os.getenv("TG_SESSION", "viznago_listener")

if len(sys.argv) < 2:
    print("Usage: python auth_step2.py <otp_code> [2fa_password]")
    sys.exit(1)

OTP_CODE = sys.argv[1].strip()
PASSWORD = sys.argv[2] if len(sys.argv) > 2 else None

async def main():
    with open(".phone_hash") as f:
        data = json.load(f)

    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.connect()

    try:
        await client.sign_in(data["phone"], OTP_CODE, phone_code_hash=data["hash"])
    except SessionPasswordNeededError:
        if not PASSWORD:
            print("2FA required. Run: python auth_step2.py <otp> <2fa_password>")
            await client.disconnect()
            return
        await client.sign_in(password=PASSWORD)

    me = await client.get_me()
    print(f"Logged in as: {me.first_name} (@{me.username})\n")

    entity = await client.get_entity(PeerChannel(1951769926))
    print(f"Channel: {entity.title}\n")

    messages = await client.get_messages(entity, limit=5)
    for msg in reversed(messages):
        print(f"[{msg.date}]")
        print(msg.text or "(no text — media/sticker)")
        print("-" * 60)

    await client.disconnect()
    if os.path.exists(".phone_hash"):
        os.remove(".phone_hash")

asyncio.run(main())
