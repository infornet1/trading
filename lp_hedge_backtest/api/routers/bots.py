"""
Bot config CRUD + start/stop/status/events endpoints.

All routes require a valid JWT (Authorization: Bearer <token>).
Users can only access their own bot configs.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_address
from api.crypto import decrypt, encrypt
from api.database import get_db
from api.models import BotConfig, BotEvent, User

router = APIRouter(prefix="/bots", tags=["bots"])


# ── Schemas ────────────────────────────────────────────────────────────────

class BotConfigCreate(BaseModel):
    chain_id:       int
    nft_token_id:   str
    pair:           str
    lower_bound:    float
    upper_bound:    float
    trigger_pct:    float = -0.50
    hedge_ratio:    float = 50.00
    hedge_exchange: str = "hyperliquid"
    hl_api_key:     Optional[str] = None   # plaintext — encrypted before storage
    hl_wallet_addr: Optional[str] = None
    mode:           str = "aragan"

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        if v not in ("aragan", "avaro"):
            raise ValueError("mode must be 'aragan' or 'avaro'")
        return v

    @field_validator("pair")
    @classmethod
    def no_btc_short(cls, v: str) -> str:
        # Golden rule: BTC pairs can only use aragan (hedge only = short) — enforced below
        return v


class BotConfigUpdate(BaseModel):
    lower_bound:    Optional[float] = None
    upper_bound:    Optional[float] = None
    trigger_pct:    Optional[float] = None
    hedge_ratio:    Optional[float] = None
    hl_api_key:     Optional[str]   = None
    hl_wallet_addr: Optional[str]   = None
    mode:           Optional[str]   = None

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v):
        if v is not None and v not in ("aragan", "avaro"):
            raise ValueError("mode must be 'aragan' or 'avaro'")
        return v


class BotConfigOut(BaseModel):
    id:             int
    chain_id:       int
    nft_token_id:   str
    pair:           str
    lower_bound:    float
    upper_bound:    float
    trigger_pct:    float
    hedge_ratio:    float
    hedge_exchange: str
    hl_wallet_addr: Optional[str]
    mode:           str
    active:         bool
    created_at:     datetime
    updated_at:     datetime

    class Config:
        from_attributes = True


class BotEventOut(BaseModel):
    id:             int
    event_type:     str
    price_at_event: Optional[float]
    pnl:            Optional[float]
    details:        Optional[dict]
    ts:             datetime

    class Config:
        from_attributes = True


# ── Helpers ────────────────────────────────────────────────────────────────

async def _get_own_config(config_id: int, address: str, db: AsyncSession) -> BotConfig:
    result = await db.execute(select(BotConfig).where(BotConfig.id == config_id))
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=404, detail="Bot config not found")
    if cfg.user_address != address:
        raise HTTPException(status_code=403, detail="Not your bot config")
    return cfg


def _enforce_golden_rules(pair: str, mode: str):
    """BTC: NEVER short. Avaro mode opens longs on breakout, not shorts for BTC."""
    pair_upper = pair.upper()
    if "BTC" in pair_upper and mode == "avaro":
        raise HTTPException(
            status_code=400,
            detail="BTC pairs cannot use Avaro mode (golden rule: BTC long only). Use Aragan.",
        )


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get("", response_model=list[BotConfigOut])
async def list_bots(
    address: str = Depends(get_current_address),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BotConfig).where(BotConfig.user_address == address)
    )
    return result.scalars().all()


@router.post("", response_model=BotConfigOut, status_code=status.HTTP_201_CREATED)
async def create_bot(
    body: BotConfigCreate,
    address: str = Depends(get_current_address),
    db: AsyncSession = Depends(get_db),
):
    _enforce_golden_rules(body.pair, body.mode)

    # Ensure user row exists
    result = await db.execute(select(User).where(User.address == address))
    if not result.scalar_one_or_none():
        db.add(User(address=address))

    encrypted_key = encrypt(body.hl_api_key) if body.hl_api_key else None

    cfg = BotConfig(
        user_address   = address,
        chain_id       = body.chain_id,
        nft_token_id   = body.nft_token_id,
        pair           = body.pair,
        lower_bound    = body.lower_bound,
        upper_bound    = body.upper_bound,
        trigger_pct    = body.trigger_pct,
        hedge_ratio    = body.hedge_ratio,
        hedge_exchange = body.hedge_exchange,
        hl_api_key     = encrypted_key,
        hl_wallet_addr = body.hl_wallet_addr,
        mode           = body.mode,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return cfg


@router.put("/{config_id}", response_model=BotConfigOut)
async def update_bot(
    config_id: int,
    body: BotConfigUpdate,
    address: str = Depends(get_current_address),
    db: AsyncSession = Depends(get_db),
):
    cfg = await _get_own_config(config_id, address, db)
    if cfg.active:
        raise HTTPException(status_code=409, detail="Stop the bot before editing its config")

    if body.lower_bound  is not None: cfg.lower_bound    = body.lower_bound
    if body.upper_bound  is not None: cfg.upper_bound    = body.upper_bound
    if body.trigger_pct  is not None: cfg.trigger_pct    = body.trigger_pct
    if body.hedge_ratio  is not None: cfg.hedge_ratio    = body.hedge_ratio
    if body.hl_wallet_addr is not None: cfg.hl_wallet_addr = body.hl_wallet_addr
    if body.hl_api_key   is not None: cfg.hl_api_key     = encrypt(body.hl_api_key)
    if body.mode         is not None:
        _enforce_golden_rules(cfg.pair, body.mode)
        cfg.mode = body.mode

    await db.commit()
    await db.refresh(cfg)
    return cfg


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bot(
    config_id: int,
    address: str = Depends(get_current_address),
    db: AsyncSession = Depends(get_db),
):
    cfg = await _get_own_config(config_id, address, db)
    if cfg.active:
        raise HTTPException(status_code=409, detail="Stop the bot before deleting its config")
    await db.delete(cfg)
    await db.commit()


@router.get("/{config_id}", response_model=BotConfigOut)
async def get_bot(
    config_id: int,
    address: str = Depends(get_current_address),
    db: AsyncSession = Depends(get_db),
):
    return await _get_own_config(config_id, address, db)


@router.get("/{config_id}/events", response_model=list[BotEventOut])
async def get_events(
    config_id: int,
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    address: str = Depends(get_current_address),
    db: AsyncSession = Depends(get_db),
):
    await _get_own_config(config_id, address, db)  # ownership check
    result = await db.execute(
        select(BotEvent)
        .where(BotEvent.config_id == config_id)
        .order_by(desc(BotEvent.ts))
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


@router.get("/{config_id}/status")
async def bot_status(
    config_id: int,
    address: str = Depends(get_current_address),
    db: AsyncSession = Depends(get_db),
):
    cfg = await _get_own_config(config_id, address, db)

    # Last event
    result = await db.execute(
        select(BotEvent)
        .where(BotEvent.config_id == config_id)
        .order_by(desc(BotEvent.ts))
        .limit(1)
    )
    last = result.scalar_one_or_none()

    from api.bot_manager import manager  # import here to avoid circular
    running = manager.is_running(config_id)

    return {
        "config_id": config_id,
        "active":    cfg.active,
        "running":   running,
        "pid":       manager.pid(config_id),
        "last_event": {
            "type": last.event_type,
            "price": float(last.price_at_event) if last.price_at_event else None,
            "pnl":   float(last.pnl) if last.pnl else None,
            "ts":    last.ts.isoformat(),
        } if last else None,
    }


@router.post("/{config_id}/start", status_code=status.HTTP_200_OK)
async def start_bot(
    config_id: int,
    address: str = Depends(get_current_address),
    db: AsyncSession = Depends(get_db),
):
    cfg = await _get_own_config(config_id, address, db)

    if not cfg.hl_api_key or not cfg.hl_wallet_addr:
        raise HTTPException(status_code=400, detail="HL API key and wallet address are required")

    from api.bot_manager import manager
    if manager.is_running(config_id):
        return {"status": "already_running"}

    config_dict = {
        "nft_token_id":   cfg.nft_token_id,
        "lower_bound":    str(cfg.lower_bound),
        "upper_bound":    str(cfg.upper_bound),
        "trigger_pct":    str(cfg.trigger_pct),
        "hedge_ratio":    str(cfg.hedge_ratio),
        "hl_api_key":     decrypt(cfg.hl_api_key),
        "hl_wallet_addr": cfg.hl_wallet_addr,
        "mode":           cfg.mode,
        "pair":           cfg.pair,
    }
    await manager.start(config_id, config_dict)
    cfg.active = True
    await db.commit()
    return {"status": "started"}


@router.post("/{config_id}/stop", status_code=status.HTTP_200_OK)
async def stop_bot(
    config_id: int,
    address: str = Depends(get_current_address),
    db: AsyncSession = Depends(get_db),
):
    cfg = await _get_own_config(config_id, address, db)

    from api.bot_manager import manager
    await manager.stop(config_id)
    cfg.active = False
    await db.commit()
    return {"status": "stopped"}
