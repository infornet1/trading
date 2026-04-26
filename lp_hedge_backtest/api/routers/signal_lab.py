"""
Signal Lab API router.

Endpoints:
  GET  /signal-lab/signals          List recent signals (paginated, filterable by status)
  GET  /signal-lab/lp-range         Latest ETH/BTC LP range analysis (from cache file)
  POST /signal-lab/execute          Record signal execution intent + wallet conflict check
"""

import json
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_address
from api.database import get_db
from api.models import BotConfig, SignalEvent, SignalExecution, SignalSource

router = APIRouter(prefix="/signal-lab", tags=["signal-lab"])

_LP_RANGE_CACHE = os.path.join(
    os.path.dirname(__file__), "..", "..", "data_cache", "lp_range_latest.json"
)


# ── Schemas ────────────────────────────────────────────────────────────────

class ExecuteRequest(BaseModel):
    signal_id:     int
    hl_wallet_addr: str   # wallet the user wants to trade from


# ── Helpers ───────────────────────────────────────────────────────────────

def _signal_to_dict(ev: SignalEvent) -> dict:
    age_seconds = int((datetime.utcnow() - ev.received_at).total_seconds())
    return {
        "id":          ev.id,
        "source_id":   ev.source_id,
        "pair":        ev.pair,
        "direction":   ev.direction,
        "leverage":    ev.leverage,
        "entry":       float(ev.entry)    if ev.entry    else None,
        "stoploss":    float(ev.stoploss) if ev.stoploss else None,
        "targets":     ev.targets or [],
        "size_pct":    float(ev.size_pct) if ev.size_pct else None,
        "status":      ev.status,
        "msg_id":      ev.msg_id,
        "received_at": ev.received_at.isoformat() + "Z",
        "updated_at":  ev.updated_at.isoformat() + "Z",
        "age_seconds": age_seconds,
    }


# ── Routes ─────────────────────────────────────────────────────────────────

@router.get("/signals")
async def list_signals(
    status:   Optional[str] = Query(None, description="Filter by status: pending|expired|stopped|tp_hit|cancelled"),
    limit:    int           = Query(20, ge=1, le=100),
    db: AsyncSession        = Depends(get_db),
    address:  str           = Depends(get_current_address),
):
    """Return recent signals from all active sources, newest first."""
    q = select(SignalEvent).order_by(desc(SignalEvent.received_at)).limit(limit)
    if status:
        q = q.where(SignalEvent.status == status)
    result = await db.execute(q)
    events = result.scalars().all()
    return {"signals": [_signal_to_dict(e) for e in events]}


@router.get("/lp-range")
async def get_lp_range(address: str = Depends(get_current_address)):
    """Return the latest cached ETH/BTC LP range analysis."""
    cache_path = os.path.abspath(_LP_RANGE_CACHE)
    if not os.path.exists(cache_path):
        return {"available": False, "message": "No analysis available yet. Run eth_lp_range.py --save to populate."}
    try:
        with open(cache_path) as f:
            data = json.load(f)
        return {"available": True, **data}
    except Exception as e:
        return {"available": False, "message": f"Cache read error: {e}"}


@router.post("/execute")
async def execute_signal(
    body:    ExecuteRequest,
    address: str            = Depends(get_current_address),
    db:      AsyncSession   = Depends(get_db),
):
    """
    Record signal execution intent.
    V1: validates wallet conflict + records intent. User places order manually on HL.
    """
    wallet = body.hl_wallet_addr.lower().strip()

    # 1. Signal must exist and be pending
    ev_res = await db.execute(select(SignalEvent).where(SignalEvent.id == body.signal_id))
    signal = ev_res.scalar_one_or_none()
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")
    if signal.status != "pending":
        raise HTTPException(status_code=409, detail=f"Signal is already {signal.status}")

    # 2. Wallet conflict guard — hard block if active LP bot exists on this wallet
    conflict_res = await db.execute(
        select(BotConfig).where(
            BotConfig.hl_wallet_addr == wallet,
            BotConfig.active == True,
        )
    )
    active_bot = conflict_res.scalar_one_or_none()
    if active_bot:
        raise HTTPException(
            status_code=409,
            detail=f"LP Bot #{active_bot.id} is active on this wallet. Pause it first.",
        )

    # 3. Record execution intent
    execution = SignalExecution(
        signal_id      = signal.id,
        user_address   = address.lower(),
        hl_wallet_addr = wallet,
        outcome        = "pending",
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)

    # 4. Return order details for manual execution
    base = (signal.pair or "").split("/")[0].upper()
    return {
        "execution_id": execution.id,
        "order": {
            "symbol":    base,
            "direction": signal.direction,
            "leverage":  signal.leverage,
            "entry":     float(signal.entry)    if signal.entry    else None,
            "stoploss":  float(signal.stoploss) if signal.stoploss else None,
            "targets":   signal.targets or [],
            "size_pct":  float(signal.size_pct) if signal.size_pct else 2.0,
        },
        "message": "Intent recorded. Place this order manually on Hyperliquid.",
    }


@router.get("/sources")
async def list_sources(
    db:      AsyncSession = Depends(get_db),
    address: str          = Depends(get_current_address),
):
    """List all configured signal sources."""
    result = await db.execute(select(SignalSource).where(SignalSource.active == True))
    sources = result.scalars().all()
    return {
        "sources": [
            {
                "id": s.id, "name": s.name,
                "channel_id": s.channel_id, "thread_id": s.thread_id,
                "purpose": s.purpose,
            }
            for s in sources
        ]
    }


@router.get("/history")
async def signal_history(
    limit:   int         = Query(50, ge=1, le=200),
    db:      AsyncSession = Depends(get_db),
    address: str          = Depends(get_current_address),
):
    """Return closed signals (stopped, tp_hit, expired, cancelled) for history panel."""
    q = (
        select(SignalEvent)
        .where(SignalEvent.status.in_(["stopped", "tp_hit", "expired", "cancelled"]))
        .order_by(desc(SignalEvent.received_at))
        .limit(limit)
    )
    result = await db.execute(q)
    events = result.scalars().all()
    return {"history": [_signal_to_dict(e) for e in events]}
