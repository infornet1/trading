"""
Signal position reconciler (M2-8) — orphan close scanner.

Runs every 5 minutes. For each filled execution with no close_price:
  1. Queries HL to check whether the position is still open
  2. If closed: matches fills to sl/tp order IDs to determine reason
  3. Writes close_price + updates signal status + sends email

Handles thread 22 (Bitcoin Daily) signals and any other case where the
Telegram channel doesn't post a close update.
"""

import asyncio
import calendar
from datetime import datetime

from sqlalchemy import select, update

from api.database import AsyncSessionLocal
from api.models import SignalEvent, SignalExecution, SignalWallet

SCAN_INTERVAL = 300   # every 5 minutes
STARTUP_DELAY =  90   # stagger from other background tasks


def _hl_check_closed(
    wallet_addr:  str,
    symbol:       str,
    is_short:     bool,
    entry_oid:    str | None,
    executed_at:  datetime,
    sl_oid:       str | None,
    tp1_oid:      str | None,
    tp2_oid:      str | None,
) -> dict:
    """
    Synchronous HL query — run via asyncio.to_thread.

    Returns dict with keys:
      still_open  bool
      close_price float | None   (weighted avg of close fills)
      reason      "sl" | "tp1" | "tp2" | "unknown"
      error       str | None
    """
    try:
        from hyperliquid.info import Info
        from hyperliquid.utils import constants
        info = Info(constants.MAINNET_API_URL, skip_ws=True)

        # ── 1. Is position still open? ────────────────────────────────────────
        state = info.user_state(wallet_addr)
        for ap in state.get("assetPositions", []):
            pos = ap["position"]
            if pos["coin"] == symbol and abs(float(pos.get("szi", 0))) > 0:
                return {"still_open": True}

        # ── 2. Position closed — find close fills ─────────────────────────────
        # calendar.timegm always treats struct_time as UTC (safe for naive datetimes)
        entry_ts_ms = calendar.timegm(executed_at.timetuple()) * 1000

        fills = info.user_fills(wallet_addr)

        # Fills for this coin since entry, excluding the entry fill itself
        close_side = "B" if is_short else "A"  # buying back SHORT, or selling LONG
        close_fills = [
            f for f in fills
            if (
                f.get("coin") == symbol
                and int(f.get("time", 0)) >= entry_ts_ms
                and f.get("side") == close_side
                and str(f.get("oid", "")) != str(entry_oid)
            )
        ]

        if not close_fills:
            # Position gone but no matching fills — manual close or data gap
            return {"still_open": False, "close_price": None, "reason": "unknown", "error": None}

        # ── 3. Match order IDs to determine close reason ──────────────────────
        # Build OID → reason map (tp2 checked before tp1 so split-TP final close wins)
        oid_reason: dict[str, str] = {}
        if sl_oid:  oid_reason[str(sl_oid)]  = "sl"
        if tp1_oid: oid_reason[str(tp1_oid)] = "tp1"
        if tp2_oid: oid_reason[str(tp2_oid)] = "tp2"

        reason = "unknown"
        # Scan fills from oldest to newest; last match wins (tp2 > tp1 if both present)
        for f in reversed(close_fills):
            r = oid_reason.get(str(f.get("oid", "")))
            if r:
                reason = r

        # ── 4. Weighted-average close price across all close fills ─────────────
        total_sz = sum(abs(float(f.get("sz", 0))) for f in close_fills)
        close_price = None
        if total_sz > 0:
            close_price = round(
                sum(float(f["px"]) * abs(float(f.get("sz", 0))) for f in close_fills) / total_sz,
                6,
            )

        return {
            "still_open":  False,
            "close_price": close_price,
            "reason":      reason,
            "error":       None,
        }

    except Exception as exc:
        # Treat errors as "still open" — never false-close a position
        return {"still_open": True, "error": str(exc)}


async def _reconcile_once() -> None:
    """One reconciliation pass over all open executions."""
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(SignalExecution, SignalEvent, SignalWallet)
            .join(SignalEvent,  SignalExecution.signal_id      == SignalEvent.id)
            .join(SignalWallet, SignalExecution.hl_wallet_addr == SignalWallet.hl_wallet_addr)
            .where(
                SignalExecution.outcome     == "filled",
                SignalExecution.close_price.is_(None),
                SignalWallet.active         == True,
            )
        )
        rows = res.all()

    if not rows:
        return

    print(f"[Reconciler] Scanning {len(rows)} open execution(s)…", flush=True)

    for execution, signal, wallet in rows:
        symbol   = (signal.pair or "").split("/")[0].upper()
        is_short = (signal.direction or "short").lower() == "short"

        result = await asyncio.to_thread(
            _hl_check_closed,
            wallet.hl_wallet_addr,
            symbol,
            is_short,
            execution.hl_order_id,
            execution.executed_at,
            execution.sl_order_id,
            execution.tp1_order_id,
            execution.tp2_order_id,
        )

        if result.get("error"):
            print(f"[Reconciler] HL error for exec#{execution.id} ({symbol}): {result['error']}", flush=True)
            continue

        if result.get("still_open"):
            continue

        close_price = result.get("close_price")
        reason      = result.get("reason", "unknown")

        if close_price is None:
            print(
                f"[Reconciler] {symbol} exec#{execution.id}: closed but no fill data — skipping",
                flush=True,
            )
            continue

        new_status = "stopped" if reason == "sl" else "tp_hit"
        icon       = "🛑" if reason == "sl" else "🎯"

        async with AsyncSessionLocal() as db:
            await db.execute(
                update(SignalExecution)
                .where(SignalExecution.id == execution.id)
                .values(close_price=close_price)
            )
            # Only update signal status if it isn't already a terminal state
            await db.execute(
                update(SignalEvent)
                .where(
                    SignalEvent.id     == signal.id,
                    SignalEvent.status.notin_(["stopped", "tp_hit", "cancelled"]),
                )
                .values(status=new_status)
            )
            await db.commit()

        fp      = float(execution.fill_price) if execution.fill_price else None
        pnl_pct = None
        if fp:
            raw     = ((fp - close_price) / fp) if is_short else ((close_price - fp) / fp)
            pnl_pct = round(raw * (signal.leverage or 1) * 100, 2)

        sign = "+" if (pnl_pct or 0) >= 0 else ""
        print(
            f"[Reconciler] {icon} {signal.pair} exec#{execution.id} "
            f"{reason} @ ${close_price:,.4f}"
            + (f" ({sign}{pnl_pct:.1f}%)" if pnl_pct is not None else "")
            + f" wallet …{wallet.hl_wallet_addr[-4:]}",
            flush=True,
        )

        # Email notification
        body = (
            f"Posición cerrada detectada por el reconciliador HL.\n\n"
            f"Par:       {signal.pair}\n"
            f"Dirección: {(signal.direction or '').upper()}\n"
            f"Entrada:   ${fp:,.4f}\n"
            f"Cierre:    ${close_price:,.4f} ({reason.upper()})\n"
            f"Leverage:  {signal.leverage}×\n"
            + (f"P&L:       {sign}{pnl_pct:.2f}%\n" if pnl_pct is not None else "")
            + f"Wallet:    {wallet.hl_wallet_addr}\n\n"
            f"Detectado automáticamente por el escáner de posiciones huérfanas."
        )
        try:
            from api.signal_email import send_signal_email
            await asyncio.to_thread(
                send_signal_email,
                f"{icon} Cierre reconciliado: {signal.pair}",
                body,
            )
        except Exception as exc:
            print(f"[Reconciler] Email error: {exc}", flush=True)


async def run_signal_reconciler() -> None:
    """Background loop: scan for orphaned closed positions every 5 minutes."""
    await asyncio.sleep(STARTUP_DELAY)
    while True:
        try:
            await _reconcile_once()
        except Exception as exc:
            print(f"[Reconciler] Unhandled error: {exc}", flush=True)
        await asyncio.sleep(SCAN_INTERVAL)
