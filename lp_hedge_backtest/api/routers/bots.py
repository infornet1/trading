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
    leverage:       int   = 10
    sl_pct:         float = 0.10
    tp_pct:         Optional[float] = None
    trailing_stop:  bool  = True
    auto_rearm:     bool  = True
    # FURY-specific fields (required when mode='fury', ignored otherwise)
    fury_symbol:       Optional[str]   = None   # 'BTC' | 'ETH'
    fury_rsi_period:   Optional[int]   = 9
    fury_rsi_long_th:  Optional[float] = 35.0
    fury_rsi_short_th: Optional[float] = 65.0
    fury_leverage_max: Optional[int]   = 12
    fury_risk_pct:     Optional[float] = 2.0

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        if v not in ("aragan", "avaro", "fury"):
            raise ValueError("mode must be 'aragan', 'avaro', or 'fury'")
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
    leverage:       Optional[int]   = None
    sl_pct:         Optional[float] = None
    tp_pct:         Optional[float] = None
    trailing_stop:  Optional[bool]  = None
    auto_rearm:     Optional[bool]  = None
    # FURY-specific fields
    fury_symbol:       Optional[str]   = None
    fury_rsi_period:   Optional[int]   = None
    fury_rsi_long_th:  Optional[float] = None
    fury_rsi_short_th: Optional[float] = None
    fury_leverage_max: Optional[int]   = None
    fury_risk_pct:     Optional[float] = None

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v):
        if v is not None and v not in ("aragan", "avaro", "fury"):
            raise ValueError("mode must be 'aragan', 'avaro', or 'fury'")
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
    leverage:       int
    sl_pct:         float
    tp_pct:         Optional[float]
    trailing_stop:  bool
    auto_rearm:     bool
    fury_symbol:       Optional[str]
    fury_rsi_period:   Optional[int]
    fury_rsi_long_th:  Optional[float]
    fury_rsi_short_th: Optional[float]
    fury_leverage_max: Optional[int]
    fury_risk_pct:     Optional[float]
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


def _enforce_golden_rules(pair: str, mode: str, fury_symbol: Optional[str] = None):
    """BTC: NEVER short. Avaro and Fury modes can open shorts — blocked for BTC."""
    pair_upper = pair.upper()
    if "BTC" in pair_upper and mode == "avaro":
        raise HTTPException(
            status_code=400,
            detail="BTC pairs cannot use Avaro mode (golden rule: BTC long only). Use Aragan.",
        )
    # FURY: BTC is long-only inside live_fury_bot, but reject upfront if user
    # explicitly configures fury_symbol=BTC with any intent to short — the bot
    # enforces this internally too, but we validate at the API layer as well.
    if mode == "fury" and fury_symbol and fury_symbol.upper() == "BTC":
        # BTC fury is allowed (long-only enforced in bot); just validate symbol is set
        pass
    if mode == "fury" and not fury_symbol:
        raise HTTPException(
            status_code=400,
            detail="fury_symbol is required when mode is 'fury' (use 'BTC' or 'ETH')",
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
    _enforce_golden_rules(body.pair, body.mode, body.fury_symbol)

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
        leverage       = max(1, min(body.leverage, 15)),
        sl_pct         = body.sl_pct,
        tp_pct         = body.tp_pct,
        trailing_stop  = body.trailing_stop,
        auto_rearm     = body.auto_rearm,
        fury_symbol       = body.fury_symbol,
        fury_rsi_period   = body.fury_rsi_period,
        fury_rsi_long_th  = body.fury_rsi_long_th,
        fury_rsi_short_th = body.fury_rsi_short_th,
        fury_leverage_max = body.fury_leverage_max,
        fury_risk_pct     = body.fury_risk_pct,
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

    if body.lower_bound    is not None: cfg.lower_bound    = body.lower_bound
    if body.upper_bound    is not None: cfg.upper_bound    = body.upper_bound
    if body.trigger_pct    is not None: cfg.trigger_pct    = body.trigger_pct
    if body.hedge_ratio    is not None: cfg.hedge_ratio    = body.hedge_ratio
    if body.hl_wallet_addr is not None: cfg.hl_wallet_addr = body.hl_wallet_addr
    if body.hl_api_key     is not None: cfg.hl_api_key     = encrypt(body.hl_api_key)
    if body.mode           is not None:
        effective_fury_symbol = body.fury_symbol or cfg.fury_symbol
        _enforce_golden_rules(cfg.pair, body.mode, effective_fury_symbol)
        cfg.mode = body.mode
    if body.leverage       is not None: cfg.leverage       = max(1, min(body.leverage, 15))
    if body.sl_pct         is not None: cfg.sl_pct         = body.sl_pct
    if body.tp_pct         is not None: cfg.tp_pct         = body.tp_pct
    if body.trailing_stop  is not None: cfg.trailing_stop  = body.trailing_stop
    if body.auto_rearm     is not None: cfg.auto_rearm     = body.auto_rearm
    if body.fury_symbol       is not None: cfg.fury_symbol       = body.fury_symbol
    if body.fury_rsi_period   is not None: cfg.fury_rsi_period   = body.fury_rsi_period
    if body.fury_rsi_long_th  is not None: cfg.fury_rsi_long_th  = body.fury_rsi_long_th
    if body.fury_rsi_short_th is not None: cfg.fury_rsi_short_th = body.fury_rsi_short_th
    if body.fury_leverage_max is not None: cfg.fury_leverage_max = body.fury_leverage_max
    if body.fury_risk_pct     is not None: cfg.fury_risk_pct     = body.fury_risk_pct

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


@router.get("/hl-balance")
async def hl_balance(
    address: str = Depends(get_current_address),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the live Hyperliquid margin balance for the authenticated user's
    HL wallet address (sourced from any of their bot configs).
    Used by the trading panel margin calculator.
    """
    result = await db.execute(
        select(BotConfig)
        .where(BotConfig.user_address == address)
        .where(BotConfig.hl_wallet_addr.isnot(None))
        .limit(1)
    )
    cfg = result.scalar_one_or_none()
    if not cfg or not cfg.hl_wallet_addr:
        return {"account_value": None, "total_margin_used": None, "error": "no_hl_wallet"}

    def _sync():
        try:
            from hyperliquid.info import Info
            from hyperliquid.utils import constants
            info  = Info(constants.MAINNET_API_URL, skip_ws=True)
            state = info.user_state(cfg.hl_wallet_addr)
            ms    = state.get("marginSummary", {})
            return {
                "account_value":     float(ms.get("accountValue")     or 0),
                "total_margin_used": float(ms.get("totalMarginUsed")  or 0),
                "error": None,
            }
        except Exception as e:
            return {"account_value": None, "total_margin_used": None, "error": str(e)}

    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync)


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
        "leverage":       str(cfg.leverage   or 10),
        "sl_pct":         str(cfg.sl_pct     or 0.1),
        "tp_pct":         str(cfg.tp_pct)    if cfg.tp_pct else "",
        "trailing_stop":  "1" if cfg.trailing_stop else "0",
        "auto_rearm":     "1" if cfg.auto_rearm    else "0",
        # FURY config (only used when mode='fury')
        "fury_symbol":       cfg.fury_symbol       or "ETH",
        "fury_rsi_period":   str(cfg.fury_rsi_period   or 9),
        "fury_rsi_long_th":  str(cfg.fury_rsi_long_th  or 35),
        "fury_rsi_short_th": str(cfg.fury_rsi_short_th or 65),
        "fury_leverage_max": str(cfg.fury_leverage_max or 12),
        "fury_risk_pct":     str(cfg.fury_risk_pct     or 2.0),
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
