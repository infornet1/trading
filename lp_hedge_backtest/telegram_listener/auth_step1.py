"""Step 1: Send OTP to phone. Saves phone_hash for step 2."""

import os
import json
import asyncio
from dotenv import load_dotenv
from telethon import TelegramClient

load_dotenv()

API_ID   = int(os.getenv("TG_API_ID"))
API_HASH = os.getenv("TG_API_HASH")
SESSION  = os.getenv("TG_SESSION", "viznago_listener")
PHONE    = "+584142337463"

async def main():
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.connect()
    result = await client.send_code_request(PHONE)
    with open(".phone_hash", "w") as f:
        json.dump({"phone": PHONE, "hash": result.phone_code_hash}, f)
    print("OTP sent to your Telegram app. Now run:")
    print("  python auth_step2.py <otp_code>")
    await client.disconnect()

asyncio.run(main())
