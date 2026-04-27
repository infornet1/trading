"""
Admin router — emergency controls + monitoring overview. Admin-wallet only.
"""

import asyncio
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from api.auth import get_current_admin
from api.bot_manager import manager
from api.database import AsyncSessionLocal
from api.models import BotConfig, BotEvent, SignalEvent, User

_BASE_DIR    = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CACHE_DIR   = os.path.join(_BASE_DIR, "data_cache")
_TG_DIR      = os.path.join(_BASE_DIR, "telegram_listener")
_VENV_PYTHON = os.path.join(_BASE_DIR, "venv", "bin", "python3")

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Hyperliquid helper ──────────────────────────────────────────────────────

async def _fetch_hl_balance(wallet_addr: str) -> float | None:
    """Lightweight HL balance fetch — perp + spot USDC (unified account)."""
    def _sync():
        try:
            from hyperliquid.info import Info
            from hyperliquid.utils import constants
            info     = Info(constants.MAINNET_API_URL, skip_ws=True)
            state    = info.user_state(wallet_addr)
            perp_val = float(state["marginSummary"]["accountValue"])
            spot_usdc = 0.0
            try:
                spot = info.spot_user_state(wallet_addr)
                for b in spot.get("balances", []):
                    if b["coin"] == "USDC":
                        spot_usdc = float(b["total"])
                        break
            except Exception:
                pass
            return perp_val + spot_usdc
        except Exception:
            return None

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync)


async def _fetch_hl_data(wallet_addr: str) -> dict:
    """Query Hyperliquid Info API in a thread (blocking SDK calls)."""
    def _sync():
        try:
            from hyperliquid.info import Info
            from hyperliquid.utils import constants
            info = Info(constants.MAINNET_API_URL, skip_ws=True)
            state       = info.user_state(wallet_addr)
            fills       = info.user_fills(wallet_addr)
            open_orders = info.frontend_open_orders(wallet_addr)
            return {"state": state, "fills": fills[:30], "open_orders": open_orders, "error": None}
        except Exception as e:
            return {"state": None, "fills": [], "open_orders": [], "error": str(e)}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync)


def _parse_hl_position(state: dict, coin: str = "ETH") -> dict | None:
    """Extract open position for a specific coin from HL user_state response."""
    if not state:
        return None
    for ap in state.get("assetPositions", []):
        pos = ap.get("position", {})
        if pos.get("coin", "").upper() == coin.upper():
            size = float(pos.get("szi", 0))
            if size == 0:
                continue
            lev = pos.get("leverage", {})
            return {
                "coin":           pos.get("coin"),
                "size":           size,
                "side":           "SHORT" if size < 0 else "LONG",
                "entry_price":    float(pos.get("entryPx") or 0),
                "unrealized_pnl": float(pos.get("unrealizedPnl") or 0),
                "return_on_equity": float(pos.get("returnOnEquity") or 0),
                "leverage":       lev.get("value") if isinstance(lev, dict) else lev,
                "leverage_type":  lev.get("type", "cross") if isinstance(lev, dict) else "cross",
                "liquidation_px": float(pos.get("liquidationPx") or 0) if pos.get("liquidationPx") else None,
                "margin_used":    float(pos.get("marginUsed") or 0),
                "position_value": float(pos.get("positionValue") or 0),
            }
    return None


def _parse_margin_summary(state: dict) -> dict:
    if not state:
        return {}
    ms = state.get("marginSummary", {})
    return {
        "account_value":     float(ms.get("accountValue") or 0),
        "total_margin_used": float(ms.get("totalMarginUsed") or 0),
        "total_ntl_pos":     float(ms.get("totalNtlPos") or 0),
    }


def _parse_sl_order(open_orders: list, coin: str = "ETH") -> dict | None:
    """
    Find the native stop-loss trigger order for a given coin.
    For a short position, the SL fires when price rises above triggerPx
    (triggerCondition == 'above'), reduce_only=True.
    """
    for o in open_orders:
        if (o.get("coin", "").upper() == coin.upper()
                and o.get("isTrigger")
                and o.get("reduceOnly")):
            return {
                "oid":           o.get("oid"),
                "trigger_px":    float(o.get("triggerPx") or 0),
                "trigger_cond":  o.get("triggerCondition"),
                "order_type":    o.get("orderType"),
                "size":          float(o.get("sz") or 0),
                "side":          o.get("side"),
                "ts":            o.get("timestamp"),
            }
    return None


# ── Stop all ───────────────────────────────────────────────────────────────

@router.post("/stop-all")
async def nuclear_stop(admin: str = Depends(get_current_admin)):
    """
    Emergency stop: terminate every running bot and mark all active=False
    so they do NOT auto-restart on next API restart.
    """
    stopped = []
    for config_id in list(manager._procs.keys()):
        await manager.stop(config_id)
        stopped.append(config_id)

    async with AsyncSessionLocal() as db:
        await db.execute(
            update(BotConfig).where(BotConfig.active == True).values(active=False)
        )
        await db.commit()

    return {
        "status": "ok",
        "stopped_count": len(stopped),
        "stopped_ids": stopped,
        "triggered_by": admin,
    }


@router.post("/stop-whale-bots")
async def stop_whale_bots(admin: str = Depends(get_current_admin)):
    """Stop all running whale bots and mark them inactive (saves ~6.6% CPU + ~261 MB RAM)."""
    stopped = []
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(BotConfig).where(BotConfig.mode == "whale", BotConfig.active == True)
        )
        whale_configs = result.scalars().all()
        for cfg in whale_configs:
            if cfg.id in manager._procs:
                await manager.stop(cfg.id)
                stopped.append(cfg.id)
        await db.execute(
            update(BotConfig).where(BotConfig.mode == "whale").values(active=False)
        )
        await db.commit()
    return {"status": "ok", "stopped_count": len(stopped), "stopped_ids": stopped}


@router.post("/start-whale-bots")
async def start_whale_bots(admin: str = Depends(get_current_admin)):
    """Start all inactive whale bot configs."""
    from api.crypto import decrypt
    started = []
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(BotConfig).where(BotConfig.mode == "whale", BotConfig.active == False)
        )
        whale_configs = result.scalars().all()
        for bot in whale_configs:
            if bot.id in manager._procs:
                continue
            config = {
                "nft_token_id":             bot.nft_token_id,
                "lower_bound":              str(bot.lower_bound or 0),
                "upper_bound":              str(bot.upper_bound or 0),
                "trigger_pct":              str(bot.trigger_pct or 0),
                "hedge_ratio":              str(bot.hedge_ratio or 0),
                "hl_api_key":               "",
                "hl_wallet_addr":           "",
                "mode":                     "whale",
                "pair":                     bot.pair or "ETH",
                "leverage":                 str(bot.leverage or 10),
                "sl_pct":                   str(bot.sl_pct or 0.1),
                "tp_pct":                   str(bot.tp_pct) if bot.tp_pct else "",
                "trailing_stop":            "0",
                "auto_rearm":               "0",
                "fury_symbol":              "",
                "fury_rsi_period":          "9",
                "fury_rsi_long_th":         "35",
                "fury_rsi_short_th":        "65",
                "fury_leverage_max":        "12",
                "fury_risk_pct":            "2.0",
                "whale_top_n":              str(bot.whale_top_n or 50),
                "whale_min_notional":       str(bot.whale_min_notional or 50000),
                "whale_poll_interval":      str(bot.whale_poll_interval or 30),
                "whale_custom_addresses":   bot.whale_custom_addresses or "",
                "whale_watch_assets":       bot.whale_watch_assets or "",
                "whale_use_websocket":      bot.whale_use_websocket or False,
                "whale_oi_spike_threshold": str(bot.whale_oi_spike_threshold or 0.03),
                "engine_v2":               False,
            }
            try:
                await manager.start(bot.id, config)
                started.append(bot.id)
            except Exception as e:
                print(f"[WhaleStart] Failed to start bot {bot.id}: {e}", flush=True)
        if started:
            ids = [b.id for b in whale_configs if b.id in started]
            await db.execute(
                update(BotConfig)
                .where(BotConfig.id.in_(started))
                .values(active=True)
            )
            await db.commit()
    return {"status": "ok", "started_count": len(started), "started_ids": started}


# ── M2-28: Per-bot restart ─────────────────────────────────────────────────

@router.post("/restart/{config_id}")
async def restart_bot(config_id: int, admin: str = Depends(get_current_admin)):
    """Stop a bot process (if running) and re-launch it from current DB config."""
    from api.crypto import decrypt

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(BotConfig).where(BotConfig.id == config_id))
        cfg = result.scalar_one_or_none()
        if not cfg:
            raise HTTPException(status_code=404, detail=f"Config {config_id} not found")

        was_running = manager.is_running(config_id)
        if was_running:
            await manager.stop(config_id)

        config_dict = {
            "nft_token_id":              cfg.nft_token_id,
            "lower_bound":               str(cfg.lower_bound),
            "upper_bound":               str(cfg.upper_bound),
            "trigger_pct":               str(cfg.trigger_pct),
            "hedge_ratio":               str(cfg.hedge_ratio),
            "hl_api_key":                decrypt(cfg.hl_api_key) if cfg.hl_api_key else "",
            "hl_wallet_addr":            cfg.hl_wallet_addr or "",
            "mode":                      cfg.mode,
            "pair":                      cfg.pair,
            "leverage":                  str(cfg.leverage   or 10),
            "sl_pct":                    str(cfg.sl_pct     or 0.1),
            "tp_pct":                    str(cfg.tp_pct)    if cfg.tp_pct else "",
            "trailing_stop":             "1" if cfg.trailing_stop else "0",
            "auto_rearm":                "1" if cfg.auto_rearm    else "0",
            "fury_symbol":               cfg.fury_symbol          or "ETH",
            "fury_rsi_period":           str(cfg.fury_rsi_period  or 9),
            "fury_rsi_long_th":          str(cfg.fury_rsi_long_th or 35),
            "fury_rsi_short_th":         str(cfg.fury_rsi_short_th or 65),
            "fury_leverage_max":         str(cfg.fury_leverage_max or 12),
            "fury_risk_pct":             str(cfg.fury_risk_pct    or 2.0),
            "whale_top_n":               str(cfg.whale_top_n            or 50),
            "whale_min_notional":        str(cfg.whale_min_notional     or 50000),
            "whale_poll_interval":       str(cfg.whale_poll_interval    or 30),
            "whale_custom_addresses":    cfg.whale_custom_addresses     or "",
            "whale_watch_assets":        cfg.whale_watch_assets         or "",
            "whale_use_websocket":       bool(cfg.whale_use_websocket),
            "whale_oi_spike_threshold":  str(cfg.whale_oi_spike_threshold or 0.03),
            "paper_trade":               bool(cfg.paper_trade),
            "engine_v2":                 bool(cfg.engine_v2),
        }

        await manager.start(config_id, config_dict)
        cfg.active = True
        await db.commit()

    print(f"[Admin] Restart config {config_id} by {admin} (was_running={was_running})", flush=True)
    return {"status": "restarted", "config_id": config_id, "was_running": was_running}


# ── M2-30: Force LP reconciler scan ────────────────────────────────────────

@router.post("/reconcile-now")
async def reconcile_now(admin: str = Depends(get_current_admin)):
    """Trigger an immediate LP reconciler scan (normally runs hourly)."""
    from api.lp_reconciler import _reconcile_all
    print(f"[Admin] Force reconcile triggered by {admin}", flush=True)
    await _reconcile_all()
    return {"status": "ok", "message": "LP reconciler scan complete"}


# ── M2-34 / Signal Lab status ──────────────────────────────────────────────

@router.get("/signal-lab-status")
async def signal_lab_status(admin: str = Depends(get_current_admin)):
    """Signal Lab health: listener process, signal queue, LP range cache, reconciler."""

    # ── Listener ──────────────────────────────────────────────────────────
    pid_file   = os.path.join(_TG_DIR, "logs", "listener.pid")
    pause_flag = os.path.join(_TG_DIR, "logs", ".pause")
    listener_running = False
    listener_pid     = None
    if os.path.exists(pid_file):
        try:
            with open(pid_file) as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)   # signal 0 = check existence only
            listener_pid     = pid
            listener_running = True
        except (ProcessLookupError, ValueError, OSError):
            pass

    # ── Signal queue ──────────────────────────────────────────────────────
    async with AsyncSessionLocal() as db:
        last_received = (await db.execute(
            select(func.max(SignalEvent.received_at))
        )).scalar_one_or_none()

        pending_count = (await db.execute(
            select(func.count()).select_from(SignalEvent)
            .where(SignalEvent.status == "pending")
        )).scalar_one()

        cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)
        expired_24h = (await db.execute(
            select(func.count()).select_from(SignalEvent)
            .where(SignalEvent.status == "expired")
            .where(SignalEvent.received_at >= cutoff_24h)
        )).scalar_one()

        total_signals = (await db.execute(
            select(func.count()).select_from(SignalEvent)
        )).scalar_one()

    # ── LP range cache ────────────────────────────────────────────────────
    lp_cache = None
    lp_cache_path = os.path.join(_CACHE_DIR, "lp_range_latest.json")
    if os.path.exists(lp_cache_path):
        try:
            with open(lp_cache_path) as f:
                raw = json.load(f)
            saved_at = raw.get("saved_at")
            msg_date = raw.get("msg_date")
            cp = raw.get("ranges", {}).get("current_price")
            cache_age_h = None
            if saved_at:
                dt = datetime.fromisoformat(saved_at.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                cache_age_h = round((datetime.now(timezone.utc) - dt).total_seconds() / 3600, 1)
            lp_cache = {
                "saved_at":        saved_at,
                "msg_date":        msg_date,
                "current_price":   float(cp) if cp else None,
                "cache_age_hours": cache_age_h,
            }
        except Exception:
            pass

    # ── Reconciler last run ───────────────────────────────────────────────
    reconciler = {"last_run": None, "configs_checked": None}
    rec_path = os.path.join(_CACHE_DIR, "reconciler_state.json")
    if os.path.exists(rec_path):
        try:
            with open(rec_path) as f:
                reconciler = json.load(f)
        except Exception:
            pass

    return {
        "listener": {
            "running": listener_running,
            "pid":     listener_pid,
            "paused":  os.path.exists(pause_flag),
        },
        "signals": {
            "pending":      pending_count,
            "expired_24h":  expired_24h,
            "total":        total_signals,
            "last_received": last_received.isoformat() if last_received else None,
        },
        "lp_range_cache": lp_cache,
        "reconciler":     reconciler,
    }


@router.post("/signal-lab/refresh-lp-range")
async def refresh_lp_range(admin: str = Depends(get_current_admin)):
    """
    Pause listener → kill it → run eth_lp_range.py --save → unpause.
    Returns stdout/stderr. Listener watchdog restarts it automatically.
    """
    script    = os.path.join(_TG_DIR, "eth_lp_range.py")
    pid_file  = os.path.join(_TG_DIR, "logs", "listener.pid")
    pause_flag = os.path.join(_TG_DIR, "logs", ".pause")

    if not os.path.exists(script):
        raise HTTPException(status_code=404, detail="eth_lp_range.py not found")

    try:
        # 1. Pause watchdog so it doesn't restart the listener mid-run
        open(pause_flag, "w").close()

        # 2. Kill listener if running (free the Telethon session)
        if os.path.exists(pid_file):
            try:
                with open(pid_file) as f:
                    pid = int(f.read().strip())
                os.kill(pid, 15)   # SIGTERM
                await asyncio.sleep(2)
            except (ProcessLookupError, ValueError, OSError):
                pass

        # 3. Run eth_lp_range.py --save in thread (it calls Claude Vision — may take 30s)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: subprocess.run(
            [_VENV_PYTHON, script, "--save"],
            capture_output=True, text=True, timeout=90, cwd=_BASE_DIR,
        ))

        success = result.returncode == 0
        print(f"[Admin] LP range refresh by {admin}: rc={result.returncode}", flush=True)
        return {
            "status": "ok" if success else "error",
            "stdout": result.stdout[-600:] if result.stdout else "",
            "stderr": result.stderr[-300:] if result.stderr else "",
        }

    finally:
        # 4. Always unpause (watchdog will restart listener automatically)
        try:
            os.remove(pause_flag)
        except FileNotFoundError:
            pass


# ── Overview ───────────────────────────────────────────────────────────────

@router.get("/overview")
async def admin_overview(admin: str = Depends(get_current_admin)):
    """
    Full platform health snapshot — all wallets, all pools, aggregate stats.
    Includes last 5 events per pool and HL wallet address for detail lookups.
    """
    async with AsyncSessionLocal() as db:
        cfg_result = await db.execute(
            select(BotConfig)
            .options(selectinload(BotConfig.user))
            .order_by(BotConfig.user_address, BotConfig.id)
        )
        configs = cfg_result.scalars().all()

        pools = []
        total_volume = 0.0
        active_shorts = 0
        whale_bots = 0

        for cfg in configs:
            # Last event
            evt_result = await db.execute(
                select(BotEvent)
                .where(BotEvent.config_id == cfg.id)
                .order_by(BotEvent.id.desc())
                .limit(1)
            )
            last_evt = evt_result.scalar_one_or_none()

            # Recent events (last 5 with full details)
            recent_result = await db.execute(
                select(BotEvent)
                .where(BotEvent.config_id == cfg.id)
                .order_by(BotEvent.id.desc())
                .limit(5)
            )
            recent_evts = recent_result.scalars().all()

            # x_max_eth from last started event (used for pool value estimate)
            started_result = await db.execute(
                select(BotEvent)
                .where(BotEvent.config_id == cfg.id)
                .where(BotEvent.event_type == "started")
                .order_by(BotEvent.id.desc())
                .limit(1)
            )
            started_evt = started_result.scalar_one_or_none()
            x_max_eth = float(started_evt.details.get("x_max_eth", 0)) if started_evt and started_evt.details else None

            # Volume: sum notionals from hedge_opened events
            vol_result = await db.execute(
                select(BotEvent)
                .where(BotEvent.config_id == cfg.id)
                .where(BotEvent.event_type == "hedge_opened")
            )
            hedge_events = vol_result.scalars().all()
            config_volume = sum(
                float(e.details.get("notional", 0))
                for e in hedge_events
                if e.details
            )
            total_volume += config_volume

            running = cfg.id in manager._procs
            hb = manager.last_seen(cfg.id)
            last_heartbeat = hb.isoformat() if hb else None

            last_event_type = last_evt.event_type if last_evt else None
            if last_event_type == "hedge_opened" and running:
                active_shorts += 1
            if cfg.mode == "whale" and running:
                whale_bots += 1

            pools.append({
                "config_id":    cfg.id,
                "user_address": cfg.user_address,
                "user_plan":    cfg.user.plan if cfg.user else "free",
                "nft_token_id": cfg.nft_token_id,
                "pair":         cfg.pair,
                "chain_id":     cfg.chain_id,
                "lower_bound":  float(cfg.lower_bound),
                "upper_bound":  float(cfg.upper_bound),
                "mode":         cfg.mode,
                "leverage":     int(cfg.leverage)       if cfg.leverage       is not None else 10,
                "sl_pct":       float(cfg.sl_pct)       if cfg.sl_pct         is not None else 0.1,
                "tp_pct":       float(cfg.tp_pct)       if cfg.tp_pct         is not None else None,
                "trailing_stop": bool(cfg.trailing_stop) if cfg.trailing_stop is not None else True,
                "auto_rearm":   bool(cfg.auto_rearm)    if cfg.auto_rearm     is not None else True,
                "active":       cfg.active,
                "running":      running,
                "hl_wallet_addr": cfg.hl_wallet_addr,
                "created_at":     cfg.created_at.isoformat() if cfg.created_at else None,
                "last_heartbeat": last_heartbeat,
                "last_event": {
                    "type":    last_evt.event_type,
                    "price":   float(last_evt.price_at_event) if last_evt.price_at_event else None,
                    "pnl":     float(last_evt.pnl) if last_evt.pnl else None,
                    "ts":      last_evt.ts.isoformat() if last_evt.ts else None,
                    "details": last_evt.details,
                } if last_evt else None,
                "recent_events": [
                    {
                        "id":      e.id,
                        "type":    e.event_type,
                        "price":   float(e.price_at_event) if e.price_at_event else None,
                        "pnl":     float(e.pnl) if e.pnl else None,
                        "ts":      e.ts.isoformat() if e.ts else None,
                        "details": e.details,
                    }
                    for e in recent_evts
                ],
                "volume_usd":  round(config_volume, 2),
                "hedge_ratio": float(cfg.hedge_ratio) if cfg.hedge_ratio is not None else 50.0,
                "x_max_eth":   x_max_eth,
                "hl_account_value": None,  # filled below
            })

        # ── HL balance fetch (running bots only, parallel) ──────────────
        unique_hl_wallets = list({
            p["hl_wallet_addr"]
            for p in pools
            if p["running"] and p["hl_wallet_addr"]
        })
        if unique_hl_wallets:
            balances = await asyncio.gather(
                *[_fetch_hl_balance(w) for w in unique_hl_wallets],
                return_exceptions=True,
            )
            balance_map = {
                w: (b if not isinstance(b, Exception) else None)
                for w, b in zip(unique_hl_wallets, balances)
            }
            for p in pools:
                if p["hl_wallet_addr"] in balance_map:
                    p["hl_account_value"] = balance_map[p["hl_wallet_addr"]]

        # ── User acquisition stats ──────────────────────────────────────
        total_registered = (await db.execute(
            select(func.count()).select_from(User)
        )).scalar_one()

        cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)
        new_24h = (await db.execute(
            select(func.count()).select_from(User)
            .where(User.created_at >= cutoff_24h)
        )).scalar_one()

        # Wallets with at least one pool config
        wallets_with_pools = len({p["user_address"] for p in pools})
        # Wallets that signed up but never configured a pool
        inactive_wallets = total_registered - wallets_with_pools

        running_count = sum(1 for p in pools if p["running"])

        # M2-34: reconciler last-run timestamp
        reconciler_last_run = None
        rec_path = os.path.join(_CACHE_DIR, "reconciler_state.json")
        if os.path.exists(rec_path):
            try:
                with open(rec_path) as f:
                    reconciler_last_run = json.load(f).get("last_run")
            except Exception:
                pass

        return {
            "stats": {
                # Acquisition funnel
                "total_registered":  total_registered,
                "wallets_with_pools": wallets_with_pools,
                "inactive_wallets":  max(inactive_wallets, 0),
                "new_wallets_24h":   new_24h,
                # Operations
                "total_pools":       len(pools),
                "active_bots":       running_count,
                "active_shorts":     active_shorts,
                "whale_bots":        whale_bots,
                "total_volume_usd":  round(total_volume, 2),
                # Background jobs
                "reconciler_last_run": reconciler_last_run,
            },
            "pools": pools,
        }


# ── Per-pool HL detail ──────────────────────────────────────────────────────

@router.get("/pool/{config_id}/hl")
async def pool_hl_detail(config_id: int, admin: str = Depends(get_current_admin)):
    """
    Live Hyperliquid data for a specific pool:
      - Open position (size, entry, unrealizedPnL, leverage, liq price, margin)
      - Margin summary (account value, margin used)
      - Recent fills (last 30 trades on that wallet)
      - Full event history from DB (last 20 events)
    """
    async with AsyncSessionLocal() as db:
        cfg_result = await db.execute(
            select(BotConfig).where(BotConfig.id == config_id)
        )
        cfg = cfg_result.scalar_one_or_none()
        if not cfg:
            raise HTTPException(status_code=404, detail="Pool config not found")

        # Full event history (last 20)
        evt_result = await db.execute(
            select(BotEvent)
            .where(BotEvent.config_id == config_id)
            .order_by(BotEvent.id.desc())
            .limit(20)
        )
        events = evt_result.scalars().all()

    events_data = [
        {
            "id":      e.id,
            "type":    e.event_type,
            "price":   float(e.price_at_event) if e.price_at_event else None,
            "pnl":     float(e.pnl) if e.pnl else None,
            "ts":      e.ts.isoformat() if e.ts else None,
            "details": e.details,
        }
        for e in events
    ]

    # Derive coin from pair (e.g. "ETH/USDC" → "ETH")
    coin = cfg.pair.split("/")[0] if cfg.pair else "ETH"

    # Query HL if we have a wallet address
    hl_position  = None
    hl_margin    = {}
    hl_fills     = []
    hl_sl_order  = None
    hl_error     = None

    if cfg.hl_wallet_addr:
        hl_data   = await _fetch_hl_data(cfg.hl_wallet_addr)
        hl_error  = hl_data.get("error")
        if not hl_error:
            hl_position = _parse_hl_position(hl_data["state"], coin)
            hl_margin   = _parse_margin_summary(hl_data["state"])
            hl_sl_order = _parse_sl_order(hl_data.get("open_orders", []), coin)
            # Format fills
            for f in hl_data.get("fills", []):
                hl_fills.append({
                    "coin":  f.get("coin"),
                    "side":  "SELL/SHORT" if f.get("side") == "A" else "BUY/LONG",
                    "price": float(f.get("px") or 0),
                    "size":  float(f.get("sz") or 0),
                    "fee":   float(f.get("fee") or 0),
                    "ts":    f.get("time"),  # ms epoch
                    "oid":   f.get("oid"),
                })

    hb = manager.last_seen(config_id)

    return {
        "config_id":      config_id,
        "pair":           cfg.pair,
        "nft_token_id":   cfg.nft_token_id,
        "hl_wallet_addr": cfg.hl_wallet_addr,
        "hl_position":    hl_position,
        "hl_margin":      hl_margin,
        "hl_sl_order":    hl_sl_order,
        "hl_fills":       hl_fills,
        "hl_error":       hl_error,
        "last_heartbeat": hb.isoformat() if hb else None,
        "events":         events_data,
    }


# ── User registry ───────────────────────────────────────────────────────────

@router.get("/users")
async def admin_users(admin: str = Depends(get_current_admin)):
    """
    Full registered-wallet registry — every wallet that has ever signed in,
    regardless of whether they have active pools or bots.
    Returns each user with their plan, join date, last activity, pool count,
    and bot status — the full acquisition funnel in one call.
    """
    async with AsyncSessionLocal() as db:
        # All users ordered by join date desc
        users_result = await db.execute(
            select(User)
            .options(selectinload(User.bot_configs))
            .order_by(User.created_at.desc())
        )
        users = users_result.scalars().all()

        now = datetime.now(timezone.utc)
        rows = []
        for u in users:
            configs = u.bot_configs or []
            pool_count   = len(configs)
            active_pools = sum(1 for c in configs if c.active)
            running_bots = sum(1 for c in configs if c.id in manager._procs)

            # Last seen: normalize tz for comparison
            last_seen = u.last_seen
            if last_seen and last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            days_since = (now - last_seen).days if last_seen else None

            # Funnel stage
            if running_bots > 0:
                funnel = "bot_running"
            elif active_pools > 0:
                funnel = "bot_configured"
            elif pool_count > 0:
                funnel = "pool_added"
            else:
                funnel = "signed_up"

            rows.append({
                "address":      u.address,
                "plan":         u.plan,
                "created_at":   u.created_at.isoformat() if u.created_at else None,
                "last_seen":    last_seen.isoformat() if last_seen else None,
                "days_inactive": days_since,
                "pool_count":   pool_count,
                "active_pools": active_pools,
                "running_bots": running_bots,
                "funnel":       funnel,
            })

    return {"users": rows, "total": len(rows)}
