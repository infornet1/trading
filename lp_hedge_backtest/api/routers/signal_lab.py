"""
Signal Lab API router.

Endpoints (user, JWT required):
  GET  /signal-lab/signals              List recent signals
  GET  /signal-lab/lp-range             Latest cached ETH/BTC LP range
  POST /signal-lab/execute              Execute signal → real HL order if wallet registered
  GET  /signal-lab/history              Closed signal history
  GET  /signal-lab/price/{symbol}       Live HL mid price (for drift warning)
  GET  /signal-lab/sources              Active signal sources

Admin endpoints (admin JWT required):
  GET    /signal-lab/wallets            List registered copy-trade wallets
  POST   /signal-lab/wallets            Register a new copy-trade wallet
  PATCH  /signal-lab/wallets/{id}       Toggle auto_execute or active
  DELETE /signal-lab/wallets/{id}       Deactivate wallet
"""

import asyncio
import json
import os
import time
from datetime import datetime, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_address, get_current_admin
from api.crypto import encrypt, decrypt
from api.database import get_db
from api.models import BotConfig, SignalEvent, SignalExecution, SignalSource, SignalUserDefault, SignalWallet
from api.signal_executor import place_hl_order

SIGNAL_EXPIRY_HOURS = 7
_HL_ASSETS_CACHE: list | None = None
_HL_ASSETS_TS:    float       = 0.0
_HL_ASSETS_TTL:   int         = 3600  # refresh every hour

router = APIRouter(prefix="/signal-lab", tags=["signal-lab"])

_LP_RANGE_CACHE = os.path.join(
    os.path.dirname(__file__), "..", "..", "data_cache", "lp_range_latest.json"
)


# ── Schemas ────────────────────────────────────────────────────────────────

class ExecuteRequest(BaseModel):
    signal_id:          int
    hl_wallet_addr:     str
    override_leverage:  Optional[int]   = None
    override_size_usdt: Optional[float] = None
    override_sl:        Optional[float] = None
    override_tp1:       Optional[float] = None
    override_tp2:       Optional[float] = None


class UserDefaultRequest(BaseModel):
    leverage:  Optional[int]   = None
    size_usdt: Optional[float] = None


class RegisterWalletRequest(BaseModel):
    label:          str
    hl_wallet_addr: str
    hl_secret_key:  Optional[str] = None  # plaintext private key — empty = reuse stored
    auto_execute:   bool = False


class PatchWalletRequest(BaseModel):
    auto_execute: Optional[bool] = None
    active:       Optional[bool] = None
    label:        Optional[str]  = None


# ── Helpers ────────────────────────────────────────────────────────────────

async def _expire_stale_signals(db: AsyncSession) -> int:
    cutoff = datetime.utcnow() - timedelta(hours=SIGNAL_EXPIRY_HOURS)
    result = await db.execute(
        update(SignalEvent)
        .where(SignalEvent.status == "pending", SignalEvent.received_at < cutoff)
        .values(status="expired")
    )
    await db.commit()
    return result.rowcount


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


async def _fetch_hl_balance(addr: str) -> dict:
    """Returns {total, perp, spot, spot_usable} where spot_usable=True means
    HL unified account — spot USDC counts as perp margin, no transfer needed."""
    def _sync():
        try:
            from hyperliquid.info import Info
            from hyperliquid.utils import constants
            info = Info(constants.MAINNET_API_URL, skip_ws=True)
            perp = float(info.user_state(addr)["marginSummary"]["accountValue"])
            spot = 0.0
            spot_usable = False
            try:
                spot_state = info.spot_user_state(addr)
                for b in spot_state.get("balances", []):
                    if b["coin"] == "USDC":
                        spot = float(b["total"])
                        break
                # tokenToAvailableAfterMaintenance[[token_id, amount]] — token 0 = USDC
                # Non-zero entry means HL unified account: spot USDC usable as perp margin
                for entry in spot_state.get("tokenToAvailableAfterMaintenance", []):
                    if entry[0] == 0 and float(entry[1]) > 0:
                        spot_usable = True
                        break
            except Exception:
                pass
            return {
                "total":       round(perp + spot, 4),
                "perp":        round(perp, 4),
                "spot":        round(spot, 4),
                "spot_usable": spot_usable,
            }
        except Exception:
            return {"total": None, "perp": None, "spot": None, "spot_usable": False}
    return await asyncio.to_thread(_sync)


# ── User routes ────────────────────────────────────────────────────────────

@router.get("/signals")
async def list_signals(
    status:  Optional[str] = Query(None),
    limit:   int           = Query(20, ge=1, le=100),
    db:      AsyncSession  = Depends(get_db),
    address: str           = Depends(get_current_address),
):
    await _expire_stale_signals(db)
    q = select(SignalEvent).order_by(desc(SignalEvent.received_at)).limit(limit)
    if status:
        q = q.where(SignalEvent.status == status)
    result = await db.execute(q)
    signals = result.scalars().all()

    # Which signals are currently running on any of the connected user's wallets?
    running_res = await db.execute(
        select(SignalExecution.signal_id)
        .join(SignalWallet, SignalExecution.hl_wallet_addr == SignalWallet.hl_wallet_addr)
        .where(
            SignalWallet.user_address   == address.lower(),
            SignalExecution.outcome     == "filled",
            SignalExecution.close_price.is_(None),
        )
    )
    running_ids = {row[0] for row in running_res.fetchall()}

    return {"signals": [
        {**_signal_to_dict(e), "is_running": e.id in running_ids}
        for e in signals
    ]}


@router.get("/lp-range")
async def get_lp_range(address: str = Depends(get_current_address)):
    cache_path = os.path.abspath(_LP_RANGE_CACHE)
    if not os.path.exists(cache_path):
        return {"available": False, "message": "No analysis available yet."}
    try:
        with open(cache_path) as f:
            data = json.load(f)
        return {"available": True, **data}
    except Exception as e:
        return {"available": False, "message": f"Cache read error: {e}"}


@router.post("/execute")
async def execute_signal(
    body:    ExecuteRequest,
    address: str           = Depends(get_current_address),
    db:      AsyncSession  = Depends(get_db),
):
    """
    Execute a signal.
    - If hl_wallet_addr is a registered signal wallet → places real HL order.
    - Otherwise → records intent only (manual fallback).
    """
    wallet_addr = body.hl_wallet_addr.lower().strip()

    # 1. Signal must exist
    ev_res = await db.execute(select(SignalEvent).where(SignalEvent.id == body.signal_id))
    signal = ev_res.scalar_one_or_none()
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")

    # Block only if THIS wallet already filled this signal (not global status)
    dup_res = await db.execute(
        select(SignalExecution).where(
            SignalExecution.signal_id      == body.signal_id,
            SignalExecution.hl_wallet_addr == wallet_addr,
            SignalExecution.outcome        == "filled",
        )
    )
    if dup_res.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="This wallet already executed this signal")

    # 2. LP bot conflict guard — hard block
    conflict_res = await db.execute(
        select(BotConfig).where(
            BotConfig.hl_wallet_addr == wallet_addr,
            BotConfig.active == True,
        )
    )
    active_bot = conflict_res.scalar_one_or_none()
    if active_bot:
        raise HTTPException(
            status_code=409,
            detail=f"LP Bot #{active_bot.id} is active on this wallet. Pause it first.",
        )

    # 3. Look up registered signal wallet — must belong to the requesting user
    sw_res = await db.execute(
        select(SignalWallet).where(
            SignalWallet.hl_wallet_addr == wallet_addr,
            SignalWallet.user_address   == address.lower(),
            SignalWallet.active         == True,
        )
    )
    signal_wallet = sw_res.scalar_one_or_none()

    hl_order_id = None
    fill_price  = None
    outcome     = "pending"
    order_result = None

    if signal_wallet:
        # ── Registered wallet → place real HL order ──────────────────────────
        _overrides: dict | None = None
        if any([body.override_leverage, body.override_size_usdt,
                body.override_sl, body.override_tp1, body.override_tp2]):
            _overrides = {
                "leverage":  body.override_leverage,
                "size_usdt": body.override_size_usdt,
                "sl":        body.override_sl,
                "tp1":       body.override_tp1,
                "tp2":       body.override_tp2,
            }
        result = await asyncio.to_thread(
            place_hl_order,
            signal_wallet.hl_wallet_addr,
            signal_wallet.hl_secret_key,
            signal,
            False,
            _overrides,
        )
        if not result["success"]:
            raise HTTPException(status_code=502, detail=f"HL order failed: {result['error']}")

        hl_order_id  = result["hl_order_id"]
        fill_price   = result["fill_price"]
        outcome      = "filled"
        order_result = result

        # Mark signal as executed
        signal.status = "executed"
        await db.commit()

    # 4. Record execution
    execution = SignalExecution(
        signal_id      = signal.id,
        user_address   = address.lower(),
        hl_wallet_addr = wallet_addr,
        hl_order_id    = hl_order_id,
        fill_price     = fill_price,
        outcome        = outcome,
        sl_order_id    = order_result.get("sl_order_id")  if order_result else None,
        tp1_order_id   = order_result.get("tp1_order_id") if order_result else None,
        tp2_order_id   = order_result.get("tp2_order_id") if order_result else None,
        exec_leverage  = body.override_leverage,
        exec_size_usdt = body.override_size_usdt,
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)

    # 5. Build response
    base = (signal.pair or "").split("/")[0].upper()
    response = {
        "execution_id": execution.id,
        "auto_executed": signal_wallet is not None,
        "order": {
            "symbol":    base,
            "direction": signal.direction,
            "leverage":  signal.leverage,
            "entry":     float(signal.entry)    if signal.entry    else None,
            "stoploss":  float(signal.stoploss) if signal.stoploss else None,
            "targets":   signal.targets or [],
            "size_pct":  float(signal.size_pct) if signal.size_pct else 2.0,
        },
    }
    if order_result:
        response["fill"] = {
            "hl_order_id": hl_order_id,
            "fill_price":  fill_price,
            "size":        order_result["size"],
            "margin_used": order_result["margin_used"],
            "leverage":    order_result["leverage"],
        }
        response["message"] = f"Order placed on Hyperliquid. Fill: ${fill_price}"
    else:
        response["message"] = "Intent recorded. Place this order manually on Hyperliquid."

    return response


@router.get("/auto-status")
async def get_auto_status(
    db:      AsyncSession = Depends(get_db),
    address: str          = Depends(get_current_address),
):
    """Return auto-execute armed state for the Signal Lab page (no secret keys)."""
    res = await db.execute(
        select(SignalWallet).where(
            SignalWallet.user_address == address.lower(),
            SignalWallet.active       == True,
            SignalWallet.auto_execute == True,
        )
    )
    wallets = res.scalars().all()

    balances = await asyncio.gather(*[_fetch_hl_balance(w.hl_wallet_addr) for w in wallets])

    armed = [
        {
            "id":             w.id,
            "label":          w.label,
            "addr_short":     w.hl_wallet_addr[:6] + "…" + w.hl_wallet_addr[-4:],
            "hl_wallet_addr": w.hl_wallet_addr,
            "balance_usdc":   bal["total"],
        }
        for w, bal in zip(wallets, balances)
    ]
    return {"armed": len(armed) > 0, "wallets": armed}


@router.get("/sources")
async def list_sources(
    db:      AsyncSession = Depends(get_db),
    address: str          = Depends(get_current_address),
):
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


@router.get("/price/{symbol}")
async def get_signal_price(
    symbol:  str,
    address: str = Depends(get_current_address),
):
    sym = symbol.upper().strip()
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.post(
                "https://api.hyperliquid.xyz/info",
                json={"type": "allMids"},
                headers={"Content-Type": "application/json"},
            )
            r.raise_for_status()
            mids = r.json()
        price = mids.get(sym)
        if price is None:
            return {"symbol": sym, "price": None, "available": False}
        return {"symbol": sym, "price": float(price), "available": True}
    except Exception as e:
        return {"symbol": sym, "price": None, "available": False, "error": str(e)}


def _calc_pnl(direction: str, leverage: int, fill_price: float,
              close_price: float | None, status: str,
              stoploss: float | None, targets: list) -> float | None:
    """Estimate P&L % using actual close price when available, else signal levels."""
    is_long    = direction == "long"
    actual_close = close_price
    if not actual_close:
        if status == "tp_hit" and targets:
            actual_close = float(targets[0])
        elif status == "stopped" and stoploss:
            actual_close = float(stoploss)
        else:
            return None
    raw = (actual_close - fill_price) / fill_price if is_long else (fill_price - actual_close) / fill_price
    return round(raw * leverage * 100, 2)


@router.get("/history")
async def signal_history(
    limit:   int          = Query(50, ge=1, le=200),
    db:      AsyncSession = Depends(get_db),
    address: str          = Depends(get_current_address),
):
    events_res = await db.execute(
        select(SignalEvent)
        .where(SignalEvent.status.in_(["stopped", "tp_hit", "expired", "cancelled", "executed"]))
        .order_by(desc(SignalEvent.received_at))
        .limit(limit)
    )
    events = events_res.scalars().all()

    history = []
    for ev in events:
        d = _signal_to_dict(ev)
        # Most recent filled execution for this signal
        exc_res = await db.execute(
            select(SignalExecution)
            .where(SignalExecution.signal_id == ev.id, SignalExecution.outcome == "filled")
            .order_by(desc(SignalExecution.executed_at))
            .limit(1)
        )
        exc = exc_res.scalar_one_or_none()
        fill  = float(exc.fill_price)  if exc and exc.fill_price  else None
        close = float(exc.close_price) if exc and exc.close_price else None
        d["fill_price"]  = fill
        d["close_price"] = close
        d["pnl_pct"]     = _calc_pnl(
            ev.direction, int(ev.leverage or 1), fill, close,
            ev.status, float(ev.stoploss) if ev.stoploss else None, ev.targets or [],
        ) if fill else None
        d["estimated_pnl"] = close is None and d["pnl_pct"] is not None
        history.append(d)

    tp_n      = sum(1 for s in history if s["status"] == "tp_hit")
    sl_n      = sum(1 for s in history if s["status"] == "stopped")
    exp_n     = sum(1 for s in history if s["status"] in ("expired", "cancelled"))
    decided   = tp_n + sl_n
    win_rate  = round(tp_n / decided * 100) if decided else None

    return {
        "history": history,
        "stats": {
            "tp": tp_n, "sl": sl_n, "expired": exp_n,
            "win_rate": win_rate, "decided": decided,
        },
    }


# ── User self-service copy-trading wallet routes ───────────────────────────

@router.get("/my-wallet")
async def get_my_wallet(
    db:      AsyncSession = Depends(get_db),
    address: str          = Depends(get_current_address),
):
    """Return the current user's registered copy-trading wallet (if any).
    Also signals whether a stored (possibly inactive) key exists for UX pre-fill."""
    addr = address.lower()

    # Active registration
    res = await db.execute(
        select(SignalWallet).where(
            SignalWallet.user_address == addr,
            SignalWallet.active       == True,
        )
    )
    wallet = res.scalar_one_or_none()
    if wallet:
        bal = await _fetch_hl_balance(wallet.hl_wallet_addr)
        return {
            "registered":     True,
            "id":             wallet.id,
            "label":          wallet.label,
            "hl_wallet_addr": wallet.hl_wallet_addr,
            "addr_short":     wallet.hl_wallet_addr[:6] + "…" + wallet.hl_wallet_addr[-4:],
            "auto_execute":   wallet.auto_execute,
            "balance_usdc":   bal["total"],
            "balance_perp":   bal["perp"],
            "balance_spot":   bal["spot"],
            "spot_usable":    bal["spot_usable"],
            "has_stored_key": True,
        }

    # Check for any stored entry (active or inactive) matching the connected address
    stored_res = await db.execute(
        select(SignalWallet).where(SignalWallet.hl_wallet_addr == addr)
    )
    stored = stored_res.scalar_one_or_none()

    return {
        "registered":     False,
        "has_stored_key": stored is not None and bool(stored.hl_secret_key),
        "stored_label":   stored.label if stored else None,
    }


@router.post("/my-wallet", status_code=201)
async def register_my_wallet(
    body:    RegisterWalletRequest,
    db:      AsyncSession = Depends(get_db),
    address: str          = Depends(get_current_address),
):
    """Register or reactivate a copy-trading wallet.
    If hl_secret_key is empty and a stored entry exists, reactivates with the stored key."""
    addr      = body.hl_wallet_addr.lower().strip()
    new_key   = (body.hl_secret_key or "").strip()

    # Look for any existing entry (active or inactive) for this address
    existing_res = await db.execute(
        select(SignalWallet).where(SignalWallet.hl_wallet_addr == addr)
    )
    existing = existing_res.scalar_one_or_none()

    if new_key:
        # Validate key is a well-formed private key (agent key ≠ main account by design — do NOT check address match)
        try:
            from eth_account import Account
            Account.from_key(new_key)   # raises if malformed
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Invalid private key: {e}")
        encrypted_key = encrypt(new_key)
    else:
        # No new key — must have a stored one to reuse
        if not existing or not existing.hl_secret_key:
            raise HTTPException(status_code=422, detail="Private key required — no stored key found.")
        encrypted_key = existing.hl_secret_key  # reuse stored encrypted key

    label = body.label.strip() or "My Copy Wallet"

    if existing:
        # Reactivate (update) existing entry
        existing.label        = label
        existing.hl_secret_key = encrypted_key
        existing.user_address  = address.lower()
        existing.auto_execute  = body.auto_execute
        existing.active        = True
        await db.commit()
        wallet = existing
    else:
        wallet = SignalWallet(
            label          = label,
            hl_wallet_addr = addr,
            hl_secret_key  = encrypted_key,
            user_address   = address.lower(),
            auto_execute   = body.auto_execute,
            active         = True,
        )
        db.add(wallet)
        await db.commit()
        await db.refresh(wallet)

    bal = await _fetch_hl_balance(addr)
    return {
        "registered":     True,
        "id":             wallet.id,
        "label":          wallet.label,
        "hl_wallet_addr": wallet.hl_wallet_addr,
        "addr_short":     wallet.hl_wallet_addr[:6] + "…" + wallet.hl_wallet_addr[-4:],
        "auto_execute":   wallet.auto_execute,
        "balance_usdc":   bal["total"],
        "balance_perp":   bal["perp"],
        "balance_spot":   bal["spot"],
        "has_stored_key": True,
    }


@router.patch("/my-wallet")
async def patch_my_wallet(
    body:    PatchWalletRequest,
    db:      AsyncSession = Depends(get_db),
    address: str          = Depends(get_current_address),
):
    """Toggle auto_execute or label on the user's own copy-trading wallet."""
    res = await db.execute(
        select(SignalWallet).where(
            SignalWallet.user_address == address.lower(),
            SignalWallet.active       == True,
        )
    )
    wallet = res.scalar_one_or_none()
    if not wallet:
        raise HTTPException(status_code=404, detail="No copy-trading wallet registered.")

    if body.auto_execute is not None: wallet.auto_execute = body.auto_execute
    if body.label        is not None: wallet.label        = body.label.strip()
    await db.commit()

    return {"id": wallet.id, "auto_execute": wallet.auto_execute, "label": wallet.label}


@router.delete("/my-wallet", status_code=204)
async def delete_my_wallet(
    db:      AsyncSession = Depends(get_db),
    address: str          = Depends(get_current_address),
):
    """Deregister the user's copy-trading wallet."""
    res = await db.execute(
        select(SignalWallet).where(
            SignalWallet.user_address == address.lower(),
            SignalWallet.active       == True,
        )
    )
    wallet = res.scalar_one_or_none()
    if not wallet:
        raise HTTPException(status_code=404, detail="No copy-trading wallet registered.")
    wallet.active = False
    await db.commit()


# ── Admin routes ───────────────────────────────────────────────────────────

@router.get("/wallets")
async def list_signal_wallets(
    db:      AsyncSession = Depends(get_db),
    address: str          = Depends(get_current_admin),
):
    """List registered copy-trade wallets with live HL balance."""
    result  = await db.execute(select(SignalWallet).order_by(SignalWallet.id))
    wallets = result.scalars().all()

    rows = []
    for w in wallets:
        bal = await _fetch_hl_balance(w.hl_wallet_addr)
        rows.append({
            "id":             w.id,
            "label":          w.label,
            "hl_wallet_addr": w.hl_wallet_addr,
            "auto_execute":   w.auto_execute,
            "active":         w.active,
            "balance_usdc":   bal["total"],
            "created_at":     w.created_at.isoformat() + "Z",
        })
    return {"wallets": rows}


@router.post("/wallets", status_code=201)
async def register_signal_wallet(
    body:    RegisterWalletRequest,
    db:      AsyncSession = Depends(get_db),
    address: str          = Depends(get_current_admin),
):
    """Register a new HL wallet for signal copy trading."""
    addr = body.hl_wallet_addr.lower().strip()

    # Check duplicate
    existing = await db.execute(
        select(SignalWallet).where(SignalWallet.hl_wallet_addr == addr)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Wallet already registered")

    # Verify key is well-formed (agent key ≠ main account address by design — do NOT check match)
    try:
        from eth_account import Account
        Account.from_key(body.hl_secret_key)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid private key: {e}")

    wallet = SignalWallet(
        label          = body.label.strip(),
        hl_wallet_addr = addr,
        hl_secret_key  = encrypt(body.hl_secret_key),
        auto_execute   = body.auto_execute,
        active         = True,
    )
    db.add(wallet)
    await db.commit()
    await db.refresh(wallet)

    bal = await _fetch_hl_balance(addr)
    return {
        "id":             wallet.id,
        "label":          wallet.label,
        "hl_wallet_addr": wallet.hl_wallet_addr,
        "auto_execute":   wallet.auto_execute,
        "active":         wallet.active,
        "balance_usdc":   bal["total"],
    }


@router.patch("/wallets/{wallet_id}")
async def patch_signal_wallet(
    wallet_id: int,
    body:      PatchWalletRequest,
    db:        AsyncSession = Depends(get_db),
    address:   str          = Depends(get_current_admin),
):
    """Update auto_execute / active / label on a signal wallet."""
    res = await db.execute(select(SignalWallet).where(SignalWallet.id == wallet_id))
    wallet = res.scalar_one_or_none()
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

    if body.auto_execute is not None: wallet.auto_execute = body.auto_execute
    if body.active       is not None: wallet.active       = body.active
    if body.label        is not None: wallet.label        = body.label.strip()

    await db.commit()
    return {"id": wallet.id, "auto_execute": wallet.auto_execute, "active": wallet.active, "label": wallet.label}


@router.get("/hl-assets")
async def get_hl_assets(address: str = Depends(get_current_address)):
    """Return HL perpetual asset metadata (max leverage, sz decimals). Cached 1h."""
    global _HL_ASSETS_CACHE, _HL_ASSETS_TS
    if _HL_ASSETS_CACHE is not None and (time.time() - _HL_ASSETS_TS) < _HL_ASSETS_TTL:
        return {"assets": _HL_ASSETS_CACHE, "cached": True}

    def _fetch():
        from hyperliquid.info import Info
        from hyperliquid.utils import constants
        info = Info(constants.MAINNET_API_URL, skip_ws=True)
        meta = info.meta()
        return sorted(
            [
                {
                    "coin":         a["name"],
                    "max_leverage": int(a.get("maxLeverage", 10)),
                    "sz_decimals":  int(a.get("szDecimals", 4)),
                }
                for a in meta.get("universe", [])
                if a.get("name")
            ],
            key=lambda x: x["coin"],
        )

    assets = await asyncio.to_thread(_fetch)
    _HL_ASSETS_CACHE = assets
    _HL_ASSETS_TS    = time.time()
    return {"assets": assets, "cached": False}


@router.get("/user-defaults")
async def get_user_defaults(
    db:      AsyncSession = Depends(get_db),
    address: str          = Depends(get_current_address),
):
    """Return the connected user's saved per-coin execution defaults."""
    res = await db.execute(
        select(SignalUserDefault).where(SignalUserDefault.user_address == address.lower())
    )
    rows = res.scalars().all()
    return {
        "defaults": {
            r.coin: {
                "leverage":  r.leverage,
                "size_usdt": float(r.size_usdt) if r.size_usdt else None,
            }
            for r in rows
        }
    }


@router.put("/user-defaults/{coin}", status_code=200)
async def upsert_user_default(
    coin:    str,
    body:    UserDefaultRequest,
    db:      AsyncSession = Depends(get_db),
    address: str          = Depends(get_current_address),
):
    """Upsert a per-coin execution default (leverage + size_usdt)."""
    coin = coin.upper().strip()
    res  = await db.execute(
        select(SignalUserDefault).where(
            SignalUserDefault.user_address == address.lower(),
            SignalUserDefault.coin         == coin,
        )
    )
    row = res.scalar_one_or_none()
    if row:
        if body.leverage  is not None: row.leverage  = body.leverage
        if body.size_usdt is not None: row.size_usdt = body.size_usdt
    else:
        row = SignalUserDefault(
            user_address = address.lower(),
            coin         = coin,
            leverage     = body.leverage,
            size_usdt    = body.size_usdt,
        )
        db.add(row)
    await db.commit()
    return {
        "coin":      coin,
        "leverage":  row.leverage,
        "size_usdt": float(row.size_usdt) if row.size_usdt else None,
    }


@router.delete("/user-defaults/{coin}", status_code=204)
async def delete_user_default(
    coin:    str,
    db:      AsyncSession = Depends(get_db),
    address: str          = Depends(get_current_address),
):
    """Delete a per-coin execution default."""
    coin = coin.upper().strip()
    res  = await db.execute(
        select(SignalUserDefault).where(
            SignalUserDefault.user_address == address.lower(),
            SignalUserDefault.coin         == coin,
        )
    )
    row = res.scalar_one_or_none()
    if row:
        await db.delete(row)
        await db.commit()


@router.get("/hl-positions")
async def get_hl_positions(
    db:      AsyncSession = Depends(get_db),
    address: str          = Depends(get_current_address),
):
    """Return live Hyperliquid positions + SL/TP orders for all active wallets of the user."""
    res = await db.execute(
        select(SignalWallet).where(
            SignalWallet.user_address == address.lower(),
            SignalWallet.active       == True,
        )
    )
    wallets = res.scalars().all()
    if not wallets:
        return {"positions": [], "total_pnl": 0.0}

    def _fetch_one(wallet):
        try:
            from hyperliquid.info import Info
            from hyperliquid.utils import constants
            info        = Info(constants.MAINNET_API_URL, skip_ws=True)
            state       = info.user_state(wallet.hl_wallet_addr)
            open_orders = info.open_orders(wallet.hl_wallet_addr)

            orders_by_coin: dict = {}
            for o in open_orders:
                orders_by_coin.setdefault(o["coin"], []).append(o)

            result = []
            for ap in state.get("assetPositions", []):
                pos     = ap["position"]
                coin    = pos["coin"]
                szi     = float(pos.get("szi", 0))
                if szi == 0:
                    continue
                side     = "short" if szi < 0 else "long"
                size     = abs(szi)
                entry_px = float(pos.get("entryPx", 0))
                upnl     = float(pos.get("unrealizedPnl", 0))
                roe      = float(pos.get("returnOnEquity", 0))
                pos_val  = float(pos.get("positionValue", 0))
                margin   = float(pos.get("marginUsed", 0))
                liq_raw  = pos.get("liquidationPx")
                liq_px   = float(liq_raw) if liq_raw else None
                lev      = pos.get("leverage", {})
                lev_val  = int(lev.get("value", 1)) if isinstance(lev, dict) else 1
                lev_type = lev.get("type", "cross") if isinstance(lev, dict) else "cross"

                reduce_orders = [o for o in orders_by_coin.get(coin, []) if o.get("reduceOnly")]
                sl_price: Optional[float] = None
                tp_prices: list           = []

                if side == "short":
                    sl_cands = [o for o in reduce_orders if float(o["limitPx"]) > entry_px]
                    tp_cands = sorted(
                        [o for o in reduce_orders if float(o["limitPx"]) < entry_px],
                        key=lambda o: float(o["limitPx"]), reverse=True,
                    )
                    if sl_cands:
                        sl_price = float(max(sl_cands, key=lambda o: float(o["limitPx"]))["limitPx"])
                else:
                    sl_cands = [o for o in reduce_orders if float(o["limitPx"]) < entry_px]
                    tp_cands = sorted(
                        [o for o in reduce_orders if float(o["limitPx"]) > entry_px],
                        key=lambda o: float(o["limitPx"]),
                    )
                    if sl_cands:
                        sl_price = float(min(sl_cands, key=lambda o: float(o["limitPx"]))["limitPx"])

                tp_prices = [float(o["limitPx"]) for o in tp_cands]

                result.append({
                    "wallet_addr":    wallet.hl_wallet_addr,
                    "wallet_label":   wallet.label,
                    "coin":           coin,
                    "side":           side,
                    "size":           size,
                    "entry_px":       entry_px,
                    "pos_value":      round(pos_val, 4),
                    "unrealized_pnl": round(upnl, 4),
                    "roe_pct":        round(roe * 100, 2),
                    "leverage":       lev_val,
                    "leverage_type":  lev_type,
                    "margin_used":    round(margin, 4),
                    "liq_px":         round(liq_px, 4) if liq_px else None,
                    "sl_price":       sl_price,
                    "tp_prices":      tp_prices,
                })
            return result
        except Exception:
            return []

    results      = await asyncio.gather(*[asyncio.to_thread(_fetch_one, w) for w in wallets])
    all_positions = [p for wallet_pos in results for p in wallet_pos]
    total_pnl     = round(sum(p["unrealized_pnl"] for p in all_positions), 4)
    return {"positions": all_positions, "total_pnl": total_pnl}


@router.delete("/wallets/{wallet_id}", status_code=204)
async def delete_signal_wallet(
    wallet_id: int,
    db:        AsyncSession = Depends(get_db),
    address:   str          = Depends(get_current_admin),
):
    """Deactivate (soft-delete) a signal wallet."""
    res = await db.execute(select(SignalWallet).where(SignalWallet.id == wallet_id))
    wallet = res.scalar_one_or_none()
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    wallet.active = False
    await db.commit()
