"""
Scan last 48h of channel messages:
  1. Parse all signals (Format A + B)
  2. Detect status updates — both formal replies AND standalone update messages
     (Swallow Trade posts updates as standalone msgs, not Telegram replies)
  3. Validate pairs against live HL supported assets
  4. Classify: TRADABLE / CLOSED / EXPIRED / UNSUPPORTED
"""

import os
import asyncio
import httpx
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.types import PeerChannel

load_dotenv()
from signal_parser import parse_signal, parse_update

API_ID   = int(os.getenv("TG_API_ID"))
API_HASH = os.getenv("TG_API_HASH")
SESSION  = os.getenv("TG_SESSION", "viznago_listener")

CHANNEL_ID        = 1951769926
SHORT_TERM_THREAD = 7     # Short-Term signals thread
NOW               = datetime.now(timezone.utc)
SINCE             = NOW - timedelta(hours=48)
EXPIRY_H          = 4    # short-term signals: expire after 4h if no update


async def fetch_hl_assets() -> set:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            "https://api.hyperliquid.xyz/info",
            json={"type": "meta"},
            headers={"Content-Type": "application/json"},
        )
        return {a["name"].upper() for a in r.json().get("universe", [])}


async def main():
    hl_assets = await fetch_hl_assets()

    async with TelegramClient(SESSION, API_ID, API_HASH) as client:
        entity = await client.get_entity(PeerChannel(CHANNEL_ID))

        # collect msgs from Short-Term thread only, newest→oldest, stop at SINCE
        all_msgs = []
        async for msg in client.iter_messages(entity, offset_date=NOW, reply_to=SHORT_TERM_THREAD):
            if msg.date < SINCE:
                break
            all_msgs.append(msg)

        # reverse to chronological order for easier processing
        all_msgs.sort(key=lambda m: m.date)

        # --- separate signals from updates ---
        signals = []   # list of {signal, msg, status, update_text}
        sig_ids = set()

        for msg in all_msgs:
            text = msg.text or ""
            sig  = parse_signal(text)
            if sig:
                signals.append({
                    "signal": sig, "msg": msg,
                    "status": "open", "update_text": None
                })
                sig_ids.add(msg.id)

        # --- apply updates: formal replies first ---
        for msg in all_msgs:
            text = msg.text or ""
            if msg.id in sig_ids:
                continue
            update = parse_update(text)
            if not update:
                continue

            # check if it's a formal Telegram reply to a known signal
            parent_id = getattr(msg.reply_to, "reply_to_msg_id", None) if msg.reply_to else None
            if parent_id:
                for entry in signals:
                    if entry["msg"].id == parent_id and entry["status"] == "open":
                        entry["status"]      = update
                        entry["update_text"] = text.strip()
                        break
            else:
                # standalone update — apply to the most recent still-open signal
                # posted after that signal (Swallow Trade's style)
                for entry in reversed(signals):
                    if entry["msg"].date < msg.date and entry["status"] == "open":
                        entry["status"]      = update
                        entry["update_text"] = text.strip()
                        break

        # --- classify + HL filter ---
        tradable     = []
        not_tradable = []

        for entry in signals:
            sig    = entry["signal"]
            msg    = entry["msg"]
            status = entry["status"]
            age_h  = (NOW - msg.date).total_seconds() / 3600
            base   = sig.pair.split("/")[0].upper()
            on_hl  = base in hl_assets

            if status in ("stopped", "target_hit", "cancelled"):
                reason = status.replace("_", " ").upper()
                flag   = False
            elif not on_hl:
                reason = f"NOT ON HL"
                flag   = False
            elif age_h > EXPIRY_H and status == "open":
                reason = f"EXPIRED ({age_h:.1f}h old)"
                flag   = False
            else:
                reason = f"OPEN  {age_h:.1f}h ago"
                flag   = True

            rec = {**entry, "age_h": age_h, "on_hl": on_hl, "reason": reason, "tradable": flag}
            (tradable if flag else not_tradable).append(rec)

        # --- display ---
        total = len(signals)
        print(f"\n{'='*62}")
        print(f"  Swallow Trade - Premium  |  48h scan")
        print(f"  {SINCE.strftime('%Y-%m-%d %H:%M')} → {NOW.strftime('%Y-%m-%d %H:%M')} UTC")
        print(f"  {total} signals  |  {len(hl_assets)} HL assets loaded")
        print(f"{'='*62}\n")

        print(f"✅ TRADABLE ({len(tradable)})")
        print(f"{'─'*62}")
        if tradable:
            for r in tradable:
                s   = r["signal"]
                lev = f"{s.leverage}x" if s.leverage else "?"
                tgts = " | ".join(f"${t:,.5g}" for t in s.targets)
                print(f"  [#{r['msg']['id'] if isinstance(r['msg'], dict) else r['msg'].id}]"
                      f"  {r['msg'].date.strftime('%m-%d %H:%M UTC')}")
                print(f"  {s.pair}  {s.direction.upper()}  {lev}")
                print(f"  Entry ${s.entry:,.5g}  SL ${s.stoploss:,.5g}  TP {tgts}")
                print(f"  ⏱ {r['reason']}")
                print()
        else:
            print("  None\n")

        print(f"🔴 NOT TRADABLE ({len(not_tradable)})")
        print(f"{'─'*62}")
        for r in not_tradable:
            s   = r["signal"]
            lev = f"{s.leverage}x" if s.leverage else "?"
            mid = r["msg"].id
            dt  = r["msg"].date.strftime("%m-%d %H:%M")
            print(f"  [#{mid}] {dt} UTC  {s.pair} {s.direction.upper()} {lev}  → {r['reason']}")
            if r["update_text"]:
                print(f"    ↳ \"{r['update_text'][:80]}\"")
        print()

asyncio.run(main())
