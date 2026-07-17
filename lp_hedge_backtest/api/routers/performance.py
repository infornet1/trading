"""Profitability dashboard endpoints.

All endpoints are user-scoped (filtered by JWT address) and read-only.
They aggregate data from bot_trades, wallet_snapshots, and signal_executions.
"""

import csv
import io
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_address
from api.database import AsyncSessionLocal
from api.models import BotTrade, SignalExecution, WalletSnapshot
from api.rate_limiter import performance_limiter

router = APIRouter(
    prefix="/performance",
    tags=["performance"],
    dependencies=[Depends(performance_limiter)],
)


async def _get_db() -> AsyncSession:
    async with AsyncSessionLocal() as db:
        yield db


def _to_float(value) -> Optional[float]:
    return float(value) if value is not None else None


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")


@router.get("/summary")
async def performance_summary(
    address: str = Depends(get_current_address),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
):
    """High-level profitability KPIs for the authenticated user."""
    from_dt = _parse_date(from_date)
    to_dt = _parse_date(to_date)
    if to_dt:
        to_dt = to_dt + timedelta(days=1)

    async with AsyncSessionLocal() as db:
        stmt = (
            select(BotTrade)
            .where(BotTrade.user_address == address)
            .where(BotTrade.is_estimate.is_(False))
        )
        if from_dt:
            stmt = stmt.where(BotTrade.closed_at >= from_dt)
        if to_dt:
            stmt = stmt.where(BotTrade.closed_at < to_dt)
        result = await db.execute(stmt)
        trades = result.scalars().all()

        signal_stmt = select(SignalExecution).where(SignalExecution.user_address == address)
        if from_dt:
            signal_stmt = signal_stmt.where(SignalExecution.closed_at >= from_dt)
        if to_dt:
            signal_stmt = signal_stmt.where(SignalExecution.closed_at < to_dt)
        signal_result = await db.execute(signal_stmt)
        signal_execs = signal_result.scalars().all()

        realized = sum((t.realized_pnl_usd or Decimal("0") for t in trades), Decimal("0"))
        fees = sum((t.fees_usd or Decimal("0") for t in trades), Decimal("0"))
        funding = sum((t.funding_usd or Decimal("0") for t in trades), Decimal("0"))
        signal_pnl = sum((e.realized_pnl_usd or Decimal("0") for e in signal_execs), Decimal("0"))
        signal_fees = sum((e.fees_usd or Decimal("0") for e in signal_execs), Decimal("0"))

        net = realized - fees - funding + signal_pnl - signal_fees
        closed_trades = [t for t in trades if t.closed_at is not None]
        wins = sum(1 for t in closed_trades if (t.realized_pnl_usd or Decimal("0")) > 0)
        losses = sum(1 for t in closed_trades if (t.realized_pnl_usd or Decimal("0")) < 0)
        total = wins + losses

        win_rate = (wins / total * 100) if total else 0.0
        gross_profit = sum((t.realized_pnl_usd or Decimal("0")) for t in closed_trades if (t.realized_pnl_usd or Decimal("0")) > 0)
        gross_loss = abs(sum((t.realized_pnl_usd or Decimal("0")) for t in closed_trades if (t.realized_pnl_usd or Decimal("0")) < 0))
        profit_factor = (gross_profit / gross_loss) if gross_loss else None

        return {
            "net_realized_pnl_usd": _to_float(net),
            "bot_realized_pnl_usd": _to_float(realized),
            "bot_fees_usd": _to_float(fees),
            "bot_funding_usd": _to_float(funding),
            "signal_realized_pnl_usd": _to_float(signal_pnl),
            "signal_fees_usd": _to_float(signal_fees),
            "total_trades": total,
            "winning_trades": wins,
            "losing_trades": losses,
            "win_rate_pct": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2) if profit_factor is not None else None,
        }


@router.get("/equity-curve")
async def equity_curve(
    address: str = Depends(get_current_address),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    granularity: str = Query("day", pattern="^(day|hour)$"),
):
    """Time-series wallet balance snapshots for equity-curve charting."""
    from_dt = _parse_date(from_date)
    to_dt = _parse_date(to_date)
    if to_dt:
        to_dt = to_dt + timedelta(days=1)

    async with AsyncSessionLocal() as db:
        stmt = select(WalletSnapshot).where(WalletSnapshot.user_address == address)
        if from_dt:
            stmt = stmt.where(WalletSnapshot.snapshot_at >= from_dt)
        if to_dt:
            stmt = stmt.where(WalletSnapshot.snapshot_at < to_dt)
        stmt = stmt.order_by(WalletSnapshot.snapshot_at)
        result = await db.execute(stmt)
        snapshots = result.scalars().all()

        points = []
        max_equity = Decimal("0")
        for s in snapshots:
            equity = Decimal(str(s.balance_usdc or 0))
            if equity > max_equity:
                max_equity = equity
            drawdown = ((max_equity - equity) / max_equity * 100) if max_equity else Decimal("0")
            points.append({
                "ts": s.snapshot_at.isoformat() if s.snapshot_at else None,
                "equity": _to_float(equity),
                "drawdown_pct": _to_float(drawdown),
            })
        return points


@router.get("/trades")
async def trade_journal(
    address: str = Depends(get_current_address),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """Paginated trade journal combining LP bot trades and Signal Lab executions."""
    from_dt = _parse_date(from_date)
    to_dt = _parse_date(to_date)
    if to_dt:
        to_dt = to_dt + timedelta(days=1)

    async with AsyncSessionLocal() as db:
        stmt = (
            select(BotTrade)
            .where(BotTrade.user_address == address)
            .where(BotTrade.is_estimate.is_(False))
        )
        if from_dt:
            stmt = stmt.where(BotTrade.closed_at >= from_dt)
        if to_dt:
            stmt = stmt.where(BotTrade.closed_at < to_dt)
        stmt = stmt.order_by(BotTrade.closed_at.desc()).limit(limit).offset(offset)
        result = await db.execute(stmt)
        trades = result.scalars().all()

        rows = []
        for t in trades:
            rows.append({
                "id": t.id,
                "source": "bot",
                "config_id": t.config_id,
                "mode": t.mode,
                "pair": t.pair,
                "side": t.side,
                "entry_price": _to_float(t.entry_price),
                "exit_price": _to_float(t.exit_price),
                "size_usd": _to_float(t.size_usd),
                "realized_pnl_usd": _to_float(t.realized_pnl_usd),
                "fees_usd": _to_float(t.fees_usd),
                "funding_usd": _to_float(t.funding_usd),
                "net_pnl_usd": _to_float(t.net_pnl_usd),
                "exit_reason": t.exit_reason,
                "is_estimate": t.is_estimate,
                "opened_at": t.opened_at.isoformat() if t.opened_at else None,
                "closed_at": t.closed_at.isoformat() if t.closed_at else None,
            })
        return {"rows": rows, "limit": limit, "offset": offset}


@router.get("/breakdown")
async def breakdown(
    address: str = Depends(get_current_address),
    by: str = Query("pair", pattern="^(pair|mode|month)$"),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
):
    """Aggregated P&L grouped by pair, mode, or month."""
    from_dt = _parse_date(from_date)
    to_dt = _parse_date(to_date)
    if to_dt:
        to_dt = to_dt + timedelta(days=1)

    async with AsyncSessionLocal() as db:
        stmt = (
            select(BotTrade)
            .where(BotTrade.user_address == address)
            .where(BotTrade.is_estimate.is_(False))
        )
        if from_dt:
            stmt = stmt.where(BotTrade.closed_at >= from_dt)
        if to_dt:
            stmt = stmt.where(BotTrade.closed_at < to_dt)
        result = await db.execute(stmt)
        trades = result.scalars().all()

        groups = {}
        for t in trades:
            if by == "pair":
                key = t.pair or "unknown"
            elif by == "mode":
                key = t.mode or "unknown"
            else:  # month
                key = t.closed_at.strftime("%Y-%m") if t.closed_at else "unknown"

            if key not in groups:
                groups[key] = {"trades": 0, "realized_pnl_usd": Decimal("0"),
                               "fees_usd": Decimal("0"), "funding_usd": Decimal("0"),
                               "net_pnl_usd": Decimal("0"), "wins": 0, "losses": 0}

            g = groups[key]
            g["trades"] += 1
            g["realized_pnl_usd"] += t.realized_pnl_usd or Decimal("0")
            g["fees_usd"] += t.fees_usd or Decimal("0")
            g["funding_usd"] += t.funding_usd or Decimal("0")
            g["net_pnl_usd"] += t.net_pnl_usd or Decimal("0")
            pnl = t.realized_pnl_usd or Decimal("0")
            if pnl > 0:
                g["wins"] += 1
            elif pnl < 0:
                g["losses"] += 1

        return {
            "by": by,
            "rows": [
                {
                    "key": key,
                    "trades": g["trades"],
                    "realized_pnl_usd": _to_float(g["realized_pnl_usd"]),
                    "fees_usd": _to_float(g["fees_usd"]),
                    "funding_usd": _to_float(g["funding_usd"]),
                    "net_pnl_usd": _to_float(g["net_pnl_usd"]),
                    "wins": g["wins"],
                    "losses": g["losses"],
                }
                for key, g in sorted(groups.items())
            ],
        }


@router.get("/export")
async def export_csv(
    address: str = Depends(get_current_address),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
):
    """Export the trade journal as CSV."""
    from_dt = _parse_date(from_date)
    to_dt = _parse_date(to_date)
    if to_dt:
        to_dt = to_dt + timedelta(days=1)

    async with AsyncSessionLocal() as db:
        stmt = (
            select(BotTrade)
            .where(BotTrade.user_address == address)
            .where(BotTrade.is_estimate.is_(False))
        )
        if from_dt:
            stmt = stmt.where(BotTrade.closed_at >= from_dt)
        if to_dt:
            stmt = stmt.where(BotTrade.closed_at < to_dt)
        stmt = stmt.order_by(BotTrade.closed_at.desc())
        result = await db.execute(stmt)
        trades = result.scalars().all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "id", "mode", "pair", "side", "entry_price", "exit_price", "size_usd",
            "realized_pnl_usd", "fees_usd", "funding_usd", "net_pnl_usd",
            "exit_reason", "is_estimate", "opened_at", "closed_at",
        ])
        for t in trades:
            writer.writerow([
                t.id, t.mode, t.pair, t.side,
                _to_float(t.entry_price), _to_float(t.exit_price), _to_float(t.size_usd),
                _to_float(t.realized_pnl_usd), _to_float(t.fees_usd),
                _to_float(t.funding_usd), _to_float(t.net_pnl_usd),
                t.exit_reason, t.is_estimate,
                t.opened_at.isoformat() if t.opened_at else "",
                t.closed_at.isoformat() if t.closed_at else "",
            ])

        output.seek(0)
        filename = f"viznago_trades_{address[:8]}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode("utf-8")),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
