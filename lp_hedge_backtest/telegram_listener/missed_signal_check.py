"""
Missed-signal detector — independent daily audit of the Telegram listener.

Catches the 2026-08-02 failure mode: the channel posted a parseable signal
but signal_events has no row for it (listener alive but silently deaf).

How it works:
  1. Copies the live Telethon session file to a temp dir (NEVER opens the
     live one — the listener holds it open; concurrent SQLite access risks
     corruption) and connects with the copy.
  2. Fetches the last 72h of messages from each monitored forum thread
     (default 7,22,29,7901,27,1438 — override via argv, e.g. "7,22").
  3. Runs the REAL parser (telegram_listener/signal_parser.parse_signal —
     imported, not reimplemented) and mirrors the listener's HL-asset skip.
  4. Compares (msg_id, source_id) against signal_events; anything parsed
     but absent is MISSED.

Exit codes: 0 = OK (one-line summary) · 1 = missed signals (alert email sent)
            2 = infrastructure failure (Telegram/DB unreachable) — cron mail
            still carries the printed error.

Run as root (same user as the listener):
    cd /var/www/dev/trading/lp_hedge_backtest
    ./venv/bin/python telegram_listener/missed_signal_check.py [threads]
"""

import asyncio
import os
import shutil
import smtplib
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(_HERE, "..")
sys.path.insert(0, _HERE)
sys.path.insert(0, _ROOT)

from dotenv import load_dotenv

load_dotenv(os.path.join(_HERE, ".env"))
load_dotenv(os.path.join(_HERE, "../api/.env"), override=False)
load_dotenv(os.path.join(_HERE, "../api/.env.email"), override=False)

from signal_parser import parse_signal  # noqa: E402 — real parser, import-only reuse

from sqlalchemy import create_engine, text  # noqa: E402
from telethon import TelegramClient  # noqa: E402
from telethon.tl.types import PeerChannel  # noqa: E402

from api.email_config import load_email_config  # noqa: E402

API_ID   = int(os.getenv("TG_API_ID"))
API_HASH = os.getenv("TG_API_HASH")
SESSION  = os.getenv("TG_SESSION", "viznago_listener")
DB_URL   = os.getenv("DB_URL")
if not DB_URL:
    print("ERROR: DB_URL environment variable is required", flush=True)
    sys.exit(2)

CHANNEL_ID = 1951769926
LOOKBACK_H = 72
TOTAL_TIMEOUT_S = 60

# thread_id → signal_sources.id (must match listener.py SOURCE_ID_MAP)
SOURCE_ID_MAP = {7: 1, 22: 2, 29: 3, 7901: 4, 27: 5, 1438: 6}
SOURCE_NAMES = {1: "Short-Term", 2: "Bitcoin Daily Signals", 3: "Mid Term", 4: "Gold Signals", 5: "Long-Term", 6: "Coin Ideas"}

# Ops recipient convention used across the repo (api/signal_email.py,
# api/lp_reconciler.py, api/bot_manager.py): EMAIL_RECIPIENTS, comma-separated.
RECIPIENTS = [
    r.strip()
    for r in os.getenv("EMAIL_RECIPIENTS", "perdomo.gustavo@gmail.com").split(",")
    if r.strip()
]


def _copy_session(tmpdir: str) -> str:
    """Copy the live session (and any SQLite journal sidecar) to tmpdir.

    Returns the session path (without .session suffix) for TelegramClient.
    """
    live = os.path.join(_HERE, SESSION)
    copied = os.path.join(tmpdir, SESSION)
    for suffix in (".session", ".session-journal", "-journal"):
        src = live + suffix
        if os.path.exists(src):
            shutil.copy(src, copied + suffix)
    if not os.path.exists(copied + ".session"):
        raise FileNotFoundError(f"session file not found: {live}.session")
    return copied


def _fetch_hl_assets() -> set[str] | None:
    """HL perp whitelist — the listener skips signals for unlisted assets,
    so the detector must too or it would false-alert on every such skip.
    None = could not fetch; caller treats every asset as listed (fail open
    toward alerting, never toward silence)."""
    try:
        from hyperliquid.info import Info
        from hyperliquid.utils import constants as hlc
        meta = Info(hlc.MAINNET_API_URL, skip_ws=True).meta()
        return {a["name"].upper() for a in meta.get("universe", [])}
    except Exception as e:
        print(f"WARN: HL asset list unavailable ({e}) — not filtering by asset", flush=True)
        return None


def _db_known_msg_ids(sync_url: str, cutoff: datetime) -> set[tuple[int, int]]:
    engine = create_engine(sync_url, pool_pre_ping=True)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT msg_id, source_id FROM signal_events WHERE received_at >= :cutoff"),
            {"cutoff": cutoff.replace(tzinfo=None)},
        ).fetchall()
    engine.dispose()
    return {(int(r[0]), int(r[1])) for r in rows}


def _send_alert(missed: list[dict]) -> None:
    cfg = load_email_config()
    if not cfg:
        print("ERROR: no email config — cannot send missed-signal alert", flush=True)
        return
    lines = [
        "El canal publicó señales parseables que NO están en signal_events.",
        "El listener probablemente está vivo pero sordo (incidente 2026-08-02).",
        "",
    ]
    for m in missed:
        lines.append(
            f"• {m['date']:%Y-%m-%d %H:%M UTC} | thread {m['thread']} "
            f"({SOURCE_NAMES.get(m['source_id'], '?')}) | {m['pair']} "
            f"{m['direction'].upper()} | msg_id={m['msg_id']}"
        )
        lines.append(f"  {m['first_line']}")
    lines += [
        "",
        "Acción: revisar telegram_listener/logs/listener.log (¿HEARTBEAT ok reciente?),",
        "verificar la conexión Telegram y recuperar manualmente estas señales del canal.",
    ]
    msg = MIMEMultipart()
    msg["From"]    = cfg["sender_email"]
    msg["To"]      = ", ".join(RECIPIENTS)
    msg["Subject"] = f"🚨 [Signal Lab] {len(missed)} señal(es) PERDIDA(S) — listener no las registró"
    msg.attach(MIMEText("\n".join(lines), "plain"))
    s = smtplib.SMTP(cfg["smtp_server"], cfg["smtp_port"], timeout=15)
    s.starttls()
    s.login(cfg["smtp_username"], cfg["smtp_password"])
    s.send_message(msg)
    s.quit()
    print(f"Alert email sent to {msg['To']}", flush=True)


async def _run(threads: list[int]) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_H)

    hl_assets = await asyncio.to_thread(_fetch_hl_assets)

    tmpdir = tempfile.mkdtemp(prefix="missed_sig_check_")
    client = None
    try:
        session_copy = _copy_session(tmpdir)
        client = TelegramClient(session_copy, API_ID, API_HASH)
        await asyncio.wait_for(client.connect(), timeout=30)
        if not await client.is_user_authorized():
            print("ERROR: copied session is not authorized — cannot audit", flush=True)
            return 2

        entity = await client.get_entity(PeerChannel(CHANNEL_ID))

        scanned = 0
        parsed: list[dict] = []
        for tid in threads:
            source_id = SOURCE_ID_MAP.get(tid)
            if source_id is None:
                print(f"WARN: thread {tid} has no source mapping — skipped", flush=True)
                continue

            # Messages inside the topic, newest first, down to the 72h cutoff.
            msgs = []
            async for m in client.iter_messages(entity, reply_to=tid):
                if m.date and m.date.replace(tzinfo=timezone.utc) < cutoff:
                    break
                msgs.append(m)
            # The topic root message itself (listener treats msg.id == thread
            # id as belonging to the source too).
            root = await client.get_messages(entity, ids=tid)
            if (root and getattr(root, "text", None) and root.date
                    and root.date.replace(tzinfo=timezone.utc) >= cutoff):
                msgs.append(root)

            for m in msgs:
                txt = (m.text or "").strip()
                if not txt:
                    continue
                scanned += 1
                sig = parse_signal(txt)
                if not sig:
                    continue
                if hl_assets is not None and sig.pair.split("/")[0].upper() not in hl_assets:
                    continue  # listener skips these too — not a miss
                parsed.append({
                    "msg_id":     m.id,
                    "source_id":  source_id,
                    "thread":     tid,
                    "pair":       sig.pair,
                    "direction":  sig.direction,
                    "date":       m.date.replace(tzinfo=timezone.utc),
                    "first_line": txt.splitlines()[0][:120],
                })
    finally:
        if client is not None:
            try:
                await client.disconnect()
            except Exception as e:
                print(f"WARN: disconnect failed: {e}", flush=True)
        shutil.rmtree(tmpdir, ignore_errors=True)

    sync_url = DB_URL.replace("mysql+aiomysql", "mysql+pymysql")
    known = await asyncio.to_thread(_db_known_msg_ids, sync_url, cutoff)

    missed = [p for p in parsed if (p["msg_id"], p["source_id"]) not in known]

    if missed:
        print(f"MISSED: {len(missed)} of {len(parsed)} parsed signals absent from signal_events "
              f"({scanned} messages scanned, last {LOOKBACK_H}h)", flush=True)
        for m in missed:
            print(f"  {m['date']:%Y-%m-%d %H:%M} thread {m['thread']} {m['pair']} "
                  f"msg_id={m['msg_id']}: {m['first_line']}", flush=True)
        try:
            await asyncio.to_thread(_send_alert, missed)
        except Exception as e:
            print(f"ERROR: alert email failed: {e}", flush=True)
        return 1

    print(f"OK: 0 missed of {len(parsed)} parsed signals "
          f"({scanned} messages scanned, threads {threads}, last {LOOKBACK_H}h, "
          f"{len(known)} signal_events rows compared)", flush=True)
    return 0


def main() -> int:
    threads = [int(t) for t in (sys.argv[1] if len(sys.argv) > 1 else "7,22,29,7901,27,1438").split(",")]
    try:
        return asyncio.run(asyncio.wait_for(_run(threads), timeout=TOTAL_TIMEOUT_S))
    except (asyncio.TimeoutError, TimeoutError):
        print(f"ERROR: check timed out after {TOTAL_TIMEOUT_S}s", flush=True)
        return 2
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", flush=True)
        return 2


if __name__ == "__main__":
    sys.exit(main())
