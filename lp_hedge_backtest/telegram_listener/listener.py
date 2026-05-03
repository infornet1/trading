"""
LP Signal Lab — Telegram listener daemon.

Listens to thread 7 (Short-Term signals) of channel 1951769926.
Parses signals + standalone update messages, persists to signal_events DB table.

Run:
    cd /var/www/dev/trading/lp_hedge_backtest
    source venv/bin/activate
    python -m telegram_listener.listener
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

# Allow importing api.* from project root and signal_parser from telegram_listener/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.tl.types import PeerChannel

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
load_dotenv(os.path.join(os.path.dirname(__file__), "../api/.env"), override=False)

from signal_parser import parse_signal, parse_update

from sqlalchemy import select, update as sql_update
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from eth_account import Account
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants as hlc

from api.models import SignalEvent, SignalExecution, SignalWallet
from api.crypto import decrypt
from api.signal_executor import place_hl_order
from api.signal_email import send_signal_email

API_ID   = int(os.getenv("TG_API_ID"))
API_HASH = os.getenv("TG_API_HASH")
SESSION  = os.getenv("TG_SESSION", "viznago_listener")
DB_URL   = os.getenv("DB_URL", "mysql+aiomysql://viznago:90GSxYu0GdSe6fzGowBA4hNOlsBK@localhost/viznago_dev")

CHANNEL_ID        = 1951769926
SHORT_TERM_THREAD = 7    # signals thread

engine       = create_async_engine(DB_URL, pool_pre_ping=True, pool_recycle=3600, echo=False)
AsyncSession_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

SOURCE_ID = 1   # signal_sources.id for Short-Term thread


def _thread_id(msg) -> int | None:
    """Return the topic thread ID a message belongs to, or None if top-level."""
    if not msg.reply_to:
        return None
    rt = msg.reply_to
    return getattr(rt, "reply_to_top_id", None) or getattr(rt, "reply_to_msg_id", None)


def _is_short_term(msg) -> bool:
    tid = _thread_id(msg)
    # Topic creation message has id == thread_id; subsequent replies have top_id == thread_id
    return tid == SHORT_TERM_THREAD or msg.id == SHORT_TERM_THREAD


async def save_signal(msg, sig) -> int | None:
    async with AsyncSession_() as db:
        ev = SignalEvent(
            source_id   = SOURCE_ID,
            pair        = sig.pair,
            direction   = sig.direction,
            leverage    = sig.leverage,
            entry       = sig.entry,
            stoploss    = sig.stoploss,
            targets     = sig.targets,
            size_pct    = sig.size_pct,
            raw_text    = msg.text or "",
            status      = "pending",
            msg_id      = msg.id,
            received_at = msg.date.replace(tzinfo=timezone.utc) if msg.date.tzinfo is None else msg.date,
        )
        db.add(ev)
        await db.commit()
        await db.refresh(ev)
        ev_id = ev.id

    # Email: new signal received
    entry_str = f"${sig.entry:,.4f}" if sig.entry else "market"
    sl_str    = f"${sig.stoploss:,.4f}" if sig.stoploss else "—"
    tps_str   = " / ".join(f"${t:,.4f}" for t in (sig.targets or [])) or "—"
    await asyncio.to_thread(
        send_signal_email,
        f"📡 Nueva señal: {sig.pair} {sig.direction.upper()} {sig.leverage}x",
        f"Señal recibida de Swallow Trade\n\n"
        f"Par:       {sig.pair}\n"
        f"Dirección: {sig.direction.upper()}\n"
        f"Leverage:  {sig.leverage}x\n"
        f"Entrada:   {entry_str}\n"
        f"Stop Loss: {sl_str}\n"
        f"Targets:   {tps_str}\n"
        f"Tamaño:    {sig.size_pct or 2}% del balance\n\n"
        f"Signal ID: {ev_id}",
    )

    # Auto-execute for any registered wallets with auto_execute=True
    asyncio.create_task(_auto_execute_signal(ev_id, sig))
    return ev_id


async def _auto_execute_signal(signal_id: int, sig):
    """Fire real HL orders for all active auto-execute wallets."""
    async with AsyncSession_() as db:
        res = await db.execute(
            select(SignalWallet).where(
                SignalWallet.auto_execute == True,
                SignalWallet.active       == True,
            )
        )
        wallets = res.scalars().all()

        if not wallets:
            return

        # Re-fetch signal to get SQLAlchemy model (place_hl_order reads .pair etc.)
        sig_res = await db.execute(select(SignalEvent).where(SignalEvent.id == signal_id))
        signal  = sig_res.scalar_one_or_none()
        if not signal:
            return

        for wallet in wallets:
            print(
                f"[Auto-Execute] Wallet {wallet.hl_wallet_addr[:10]}… → "
                f"{sig.pair} {sig.direction.upper()} {sig.leverage}x",
                flush=True,
            )
            result = await asyncio.to_thread(
                place_hl_order,
                wallet.hl_wallet_addr,
                wallet.hl_secret_key,
                signal,
            )

            outcome = "filled" if result["success"] else "failed"
            execution = SignalExecution(
                signal_id      = signal_id,
                user_address   = wallet.hl_wallet_addr,  # auto-exec: wallet is the "user"
                hl_wallet_addr = wallet.hl_wallet_addr,
                hl_order_id    = result.get("hl_order_id"),
                fill_price     = result.get("fill_price"),
                outcome        = outcome,
            )
            db.add(execution)

            if result["success"]:
                signal.status = "executed"
                print(
                    f"[Auto-Execute] ✅ {sig.pair} filled @ ${result['fill_price']} "
                    f"| order {result['hl_order_id']}",
                    flush=True,
                )
                sym = sig.pair.split('/')[0]
                lev_line = (
                    f"Leverage:   {result['leverage']}x  "
                    f"⚠️ ajustado desde {result['leverage_requested']}x (máx HL para {sym})\n"
                    if result.get("leverage_adjusted") else
                    f"Leverage:   {result['leverage']}x\n"
                )
                if result.get("split_tps"):
                    tp_lines = (
                        f"TP1:        ${result['tp1_price']:,.4f}  ({result['tp1_size']} {sym} — 50%)\n"
                        f"TP2:        ${result['tp2_price']:,.4f}  ({result['tp2_size']} {sym} — 50%)\n"
                        f"SL:         ${result.get('sl_price', float(sig.stoploss)):,.4f}  (full size, reduce_only — cubre runner)\n"
                    )
                else:
                    tp1 = result.get("tp1_price")
                    tp_lines = (
                        f"TP:         ${tp1:,.4f}  (full size)\n" if tp1 else ""
                        f"SL:         ${float(sig.stoploss):,.4f}\n"
                    )
                await asyncio.to_thread(
                    send_signal_email,
                    f"✅ Orden ejecutada: {sig.pair} {sig.direction.upper()} {sig.leverage}x",
                    f"Copy trade ejecutado automáticamente en Hyperliquid\n\n"
                    f"Par:        {sig.pair}\n"
                    f"Dirección:  {sig.direction.upper()}\n"
                    f"{lev_line}"
                    f"Fill price: ${result['fill_price']:,.4f}\n"
                    f"Size:       {result['size']} {sym}\n"
                    f"Margen:     ${result['margin_used']:.2f} USDC\n"
                    f"Balance:    ${result['balance']:.2f} USDC\n"
                    f"Order ID:   {result['hl_order_id']}\n\n"
                    f"{tp_lines}",
                )
            else:
                print(
                    f"[Auto-Execute] ❌ {sig.pair} failed: {result['error']}",
                    flush=True,
                )
                await asyncio.to_thread(
                    send_signal_email,
                    f"❌ Auto-execute FALLIDO: {sig.pair} {sig.direction.upper()}",
                    f"La orden NO fue ejecutada en Hyperliquid\n\n"
                    f"Par:    {sig.pair}\n"
                    f"Error:  {result['error']}\n\n"
                    f"Acción requerida: revisa el balance y la configuración de la wallet.",
                )

        await db.commit()


async def apply_update_to_db(msg, update_status: str):
    """Find the most recent open signal before this msg and update its status."""
    async with AsyncSession_() as db:
        # Check if it's a formal reply to a known signal
        parent_id = None
        if msg.reply_to:
            parent_id = getattr(msg.reply_to, "reply_to_msg_id", None)

        if parent_id:
            res = await db.execute(
                select(SignalEvent).where(
                    SignalEvent.source_id == SOURCE_ID,
                    SignalEvent.msg_id    == parent_id,
                    SignalEvent.status    == "pending",
                )
            )
            target = res.scalar_one_or_none()
            if target:
                target.status = update_status
                await db.commit()
                return target.id

        # Standalone update — apply to most recent open signal before this msg timestamp
        res = await db.execute(
            select(SignalEvent)
            .where(
                SignalEvent.source_id   == SOURCE_ID,
                SignalEvent.status      == "pending",
                SignalEvent.received_at <= msg.date,
            )
            .order_by(SignalEvent.received_at.desc())
            .limit(1)
        )
        target = res.scalar_one_or_none()
        if target:
            target.status = update_status
            await db.commit()
            return target.id

    return None


# ── Startup orphan reconciliation ────────────────────────────────────────────

def _fetch_orphan_report(hl_wallet_addr: str) -> list[dict]:
    """Synchronous: return open HL positions with their native SL/TP order status."""
    info   = Info(hlc.MAINNET_API_URL, skip_ws=True)
    state  = info.user_state(hl_wallet_addr)
    if not state:
        return []

    try:
        open_orders = info.open_orders(hl_wallet_addr)
    except Exception:
        open_orders = []

    result = []
    for p in state.get("assetPositions", []):
        pos = p["position"]
        szi = float(pos.get("szi", 0))
        if szi == 0:
            continue

        symbol   = pos["coin"]
        entry_px = float(pos.get("entryPx", 0))
        is_long  = szi > 0

        coin_triggers = [
            o for o in open_orders
            if o.get("coin") == symbol and o.get("triggerPx") is not None
        ]
        existing_sl  = next(
            (o for o in coin_triggers if "stop" in o.get("orderType", "").lower()), None
        )
        existing_tps = [
            o for o in coin_triggers if "take profit" in o.get("orderType", "").lower()
        ]
        result.append({
            "symbol":       symbol,
            "size":         abs(szi),
            "entry_px":     entry_px,
            "is_long":      is_long,
            "existing_sl":  existing_sl,
            "existing_tps": existing_tps,
        })
    return result


def _place_emergency_sl(wallet, symbol: str, is_long: bool, size: float, entry_px: float) -> float:
    """Synchronous: place a 3% adverse SL when no native SL exists on a recovered position."""
    secret_key   = decrypt(wallet.hl_secret_key)
    account      = Account.from_key(secret_key)
    exchange     = Exchange(account, hlc.MAINNET_API_URL, account_address=wallet.hl_wallet_addr)
    sl_price     = round(entry_px * (1.03 if not is_long else 0.97), 6)
    close_is_buy = not is_long
    exchange.order(
        symbol, close_is_buy, size, sl_price,
        {"trigger": {"triggerPx": sl_price, "isMarket": True, "tpsl": "sl"}},
        reduce_only=True,
    )
    return sl_price


async def _reconcile_orphans():
    """
    Called once at listener startup. For each active signal_wallet, check HL for open
    positions. Any position with no signal_executions record in the last 8h is an orphan:
    ensure a native SL exists (place emergency SL if missing) and send an admin alert.
    """
    print("[Signal Lab] Startup reconciliation — checking for orphan positions…", flush=True)
    async with AsyncSession_() as db:
        res     = await db.execute(select(SignalWallet).where(SignalWallet.active == True))
        wallets = res.scalars().all()

    if not wallets:
        print("[Signal Lab] Reconcile: no active wallets.", flush=True)
        return

    cutoff = datetime.utcnow() - timedelta(hours=8)

    for wallet in wallets:
        try:
            positions = await asyncio.to_thread(_fetch_orphan_report, wallet.hl_wallet_addr)
        except Exception as e:
            print(f"[Signal Lab] Reconcile: could not fetch {wallet.hl_wallet_addr[:10]}…: {e}", flush=True)
            continue

        if not positions:
            print(f"[Signal Lab] Reconcile: {wallet.hl_wallet_addr[:10]}… — no open positions ✅", flush=True)
            continue

        for pos in positions:
            symbol    = pos["symbol"]
            is_long   = pos["is_long"]
            size      = pos["size"]
            entry_px  = pos["entry_px"]
            direction = "LONG" if is_long else "SHORT"

            # Check if we have a known execution for this wallet+symbol in the last 8h
            async with AsyncSession_() as db:
                chk = await db.execute(
                    select(SignalExecution)
                    .join(SignalEvent)
                    .where(
                        SignalExecution.hl_wallet_addr == wallet.hl_wallet_addr,
                        SignalEvent.pair.like(f"{symbol}/%"),
                        SignalExecution.executed_at    >= cutoff,
                    )
                    .limit(1)
                )
                known = chk.scalar_one_or_none()

            if known:
                print(
                    f"[Signal Lab] Reconcile: {wallet.hl_wallet_addr[:10]}… "
                    f"{symbol} {direction} — known execution (id={known.id}), skipping ✅",
                    flush=True,
                )
                continue

            # Orphan confirmed
            print(
                f"⚠️  [Signal Lab] Orphan: {wallet.hl_wallet_addr[:10]}… "
                f"{symbol} {direction} | size={size} | entry=${entry_px:.4f}",
                flush=True,
            )

            sl_note = ""
            if pos["existing_sl"]:
                sl_oid = pos["existing_sl"]["oid"]
                sl_px  = pos["existing_sl"].get("triggerPx", "?")
                sl_note = f"✅ SL nativo encontrado | OID {sl_oid} | trigger ${sl_px}"
                print(f"   {sl_note}", flush=True)
            else:
                try:
                    sl_price = await asyncio.to_thread(
                        _place_emergency_sl, wallet, symbol, is_long, size, entry_px
                    )
                    sl_note = f"⚠️ Sin SL — se colocó SL de emergencia @ ${sl_price:.4f} (3% adverso)"
                    print(f"   {sl_note}", flush=True)
                except Exception as e:
                    sl_note = f"❌ SL de emergencia FALLÓ: {e}"
                    print(f"   {sl_note}", flush=True)

            tp_count = len(pos["existing_tps"])
            tp_note  = f"{tp_count} TP order(s) encontrados" if tp_count else "Sin TP orders"

            await asyncio.to_thread(
                send_signal_email,
                f"⚠️ Posición huérfana detectada al reiniciar listener",
                f"El listener se reinició y encontró una posición sin registro en VIZNAGO.\n\n"
                f"Wallet:    {wallet.hl_wallet_addr}\n"
                f"Par:       {symbol}\n"
                f"Dirección: {direction}\n"
                f"Entrada:   ${entry_px:,.4f}\n"
                f"Tamaño:    {size}\n\n"
                f"SL:  {sl_note}\n"
                f"TP:  {tp_note}\n\n"
                f"Acción recomendada: verifica la posición en HL y ciérrala manualmente si es necesario.",
            )

    print("[Signal Lab] Startup reconciliation complete.", flush=True)


async def main():
    session_path = os.path.join(os.path.dirname(__file__), SESSION)

    await _reconcile_orphans()

    async with TelegramClient(session_path, API_ID, API_HASH) as client:
        me = await client.get_me()
        print(f"[Signal Lab Listener] Logged in as @{me.username}", flush=True)
        print(f"[Signal Lab Listener] Listening on channel {CHANNEL_ID} thread {SHORT_TERM_THREAD}", flush=True)

        entity = await client.get_entity(PeerChannel(CHANNEL_ID))

        @client.on(events.NewMessage(chats=entity))
        async def on_message(event):
            msg = event.message
            if not _is_short_term(msg):
                return  # ignore messages from other threads

            text = msg.text or ""
            if not text.strip():
                return

            sig = parse_signal(text)
            if sig:
                ev_id = await save_signal(msg, sig)
                print(
                    f"[{msg.date:%H:%M:%S}] NEW SIGNAL saved (id={ev_id}): "
                    f"{sig.pair} {sig.direction.upper()} {sig.leverage}x @ ${sig.entry}",
                    flush=True,
                )
                return

            update = parse_update(text)
            if update:
                ev_id = await apply_update_to_db(msg, update)
                label = ev_id or "no match"
                print(
                    f"[{msg.date:%H:%M:%S}] UPDATE ({update}) → signal id={label}",
                    flush=True,
                )

        print("[Signal Lab Listener] Ready. Waiting for messages...", flush=True)
        await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
