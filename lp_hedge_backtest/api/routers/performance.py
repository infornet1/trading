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
from sqlalchemy import case, func, select
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
    include_estimates: bool = Query(False),
):
    """High-level profitability KPIs for the authenticated user."""
    from_dt = _parse_date(from_date)
    to_dt = _parse_date(to_date)
    if to_dt:
        to_dt = to_dt + timedelta(days=1)

    async with AsyncSessionLocal() as db:
        # Win/loss conditions: closed trades (closed_at IS NOT NULL) with pnl > 0 / < 0
        win_cond = BotTrade.closed_at.isnot(None) & (func.coalesce(BotTrade.realized_pnl_usd, 0) > 0)
        loss_cond = BotTrade.closed_at.isnot(None) & (func.coalesce(BotTrade.realized_pnl_usd, 0) < 0)
        stmt = select(
            func.coalesce(func.sum(BotTrade.realized_pnl_usd), 0).label("realized"),
            func.coalesce(func.sum(BotTrade.fees_usd), 0).label("fees"),
            func.coalesce(func.sum(BotTrade.funding_usd), 0).label("funding"),
            func.coalesce(func.sum(case((win_cond, 1), else_=0)), 0).label("wins"),
            func.coalesce(func.sum(case((loss_cond, 1), else_=0)), 0).label("losses"),
            func.coalesce(func.sum(case((win_cond, BotTrade.realized_pnl_usd), else_=0)), 0).label("gross_profit"),
            func.coalesce(func.sum(case((loss_cond, BotTrade.realized_pnl_usd), else_=0)), 0).label("gross_loss"),
        ).where(BotTrade.user_address == address)
        if not include_estimates:
            stmt = stmt.where(BotTrade.is_estimate.is_(False))
        if from_dt:
            stmt = stmt.where(BotTrade.closed_at >= from_dt)
        if to_dt:
            stmt = stmt.where(BotTrade.closed_at < to_dt)
        row = (await db.execute(stmt)).one()

        signal_stmt = select(
            func.coalesce(func.sum(SignalExecution.realized_pnl_usd), 0).label("pnl"),
            func.coalesce(func.sum(SignalExecution.fees_usd), 0).label("fees"),
        ).where(SignalExecution.user_address == address)
        if from_dt:
            signal_stmt = signal_stmt.where(SignalExecution.closed_at >= from_dt)
        if to_dt:
            signal_stmt = signal_stmt.where(SignalExecution.closed_at < to_dt)
        srow = (await db.execute(signal_stmt)).one()

        realized = Decimal(str(row.realized))
        fees = Decimal(str(row.fees))
        funding = Decimal(str(row.funding))
        signal_pnl = Decimal(str(srow.pnl))
        signal_fees = Decimal(str(srow.fees))

        net = realized - fees - funding + signal_pnl - signal_fees
        wins = int(row.wins)
        losses = int(row.losses)
        total = wins + losses

        win_rate = (wins / total * 100) if total else 0.0
        gross_profit = Decimal(str(row.gross_profit))
        gross_loss = abs(Decimal(str(row.gross_loss)))
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
    include_estimates: bool = Query(False),
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
        )
        if not include_estimates:
            stmt = stmt.where(BotTrade.is_estimate.is_(False))
        if from_dt:
            stmt = stmt.where(BotTrade.closed_at >= from_dt)
        if to_dt:
            stmt = stmt.where(BotTrade.closed_at < to_dt)
        # Total matching rows for client-side pagination
        total = (await db.execute(
            select(func.count()).select_from(stmt.subquery())
        )).scalar_one()

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
        return {"rows": rows, "limit": limit, "offset": offset, "total": total}


@router.get("/breakdown")
async def breakdown(
    address: str = Depends(get_current_address),
    by: str = Query("pair", pattern="^(pair|mode|month)$"),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    include_estimates: bool = Query(False),
):
    """Aggregated P&L grouped by pair, mode, or month."""
    from_dt = _parse_date(from_date)
    to_dt = _parse_date(to_date)
    if to_dt:
        to_dt = to_dt + timedelta(days=1)

    async with AsyncSessionLocal() as db:
        if by == "pair":
            key_col = func.coalesce(BotTrade.pair, "unknown")
        elif by == "mode":
            key_col = func.coalesce(BotTrade.mode, "unknown")
        else:  # month — DATE_FORMAT produces the same "%Y-%m" buckets as strftime
            key_col = func.coalesce(func.date_format(BotTrade.closed_at, "%Y-%m"), "unknown")

        win_cond = func.coalesce(BotTrade.realized_pnl_usd, 0) > 0
        loss_cond = func.coalesce(BotTrade.realized_pnl_usd, 0) < 0
        stmt = (
            select(
                key_col.label("key"),
                func.count().label("trades"),
                func.coalesce(func.sum(BotTrade.realized_pnl_usd), 0).label("realized_pnl_usd"),
                func.coalesce(func.sum(BotTrade.fees_usd), 0).label("fees_usd"),
                func.coalesce(func.sum(BotTrade.funding_usd), 0).label("funding_usd"),
                func.coalesce(func.sum(BotTrade.net_pnl_usd), 0).label("net_pnl_usd"),
                func.coalesce(func.sum(case((win_cond, 1), else_=0)), 0).label("wins"),
                func.coalesce(func.sum(case((loss_cond, 1), else_=0)), 0).label("losses"),
            )
            .where(BotTrade.user_address == address)
        )
        if not include_estimates:
            stmt = stmt.where(BotTrade.is_estimate.is_(False))
        if from_dt:
            stmt = stmt.where(BotTrade.closed_at >= from_dt)
        if to_dt:
            stmt = stmt.where(BotTrade.closed_at < to_dt)
        stmt = stmt.group_by(key_col)
        rows = (await db.execute(stmt)).all()

        return {
            "by": by,
            "rows": [
                {
                    "key": r.key,
                    "trades": int(r.trades),
                    "realized_pnl_usd": _to_float(r.realized_pnl_usd),
                    "fees_usd": _to_float(r.fees_usd),
                    "funding_usd": _to_float(r.funding_usd),
                    "net_pnl_usd": _to_float(r.net_pnl_usd),
                    "wins": int(r.wins),
                    "losses": int(r.losses),
                }
                for r in sorted(rows, key=lambda r: r.key)
            ],
        }


@router.get("/export")
async def export_csv(
    address: str = Depends(get_current_address),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    include_estimates: bool = Query(False),
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
        )
        if not include_estimates:
            stmt = stmt.where(BotTrade.is_estimate.is_(False))
        if from_dt:
            stmt = stmt.where(BotTrade.closed_at >= from_dt)
        if to_dt:
            stmt = stmt.where(BotTrade.closed_at < to_dt)
        # Real row count so the client can tell a capped CSV from a complete one
        total = (await db.execute(
            select(func.count()).select_from(stmt.subquery())
        )).scalar_one()
        # Hard cap to bound memory on large journals
        stmt = stmt.order_by(BotTrade.closed_at.desc()).limit(10000)
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
        headers = {
            "Content-Disposition": f"attachment; filename={filename}",
            "X-Total-Rows": str(total),
        }
        if total > len(trades):
            headers["X-Truncated"] = "true"
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode("utf-8")),
            media_type="text/csv",
            headers=headers,
        )
