"""
Admin router — emergency controls + monitoring overview. Admin-wallet only.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from api.auth import get_current_admin
from api.bot_manager import manager
from api.database import AsyncSessionLocal
from api.models import BotConfig, BotEvent, User

router = APIRouter(prefix="/admin", tags=["admin"])


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

    # Mark ALL configs inactive in DB (catches any edge cases)
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


@router.get("/overview")
async def admin_overview(admin: str = Depends(get_current_admin)):
    """
    Full platform health snapshot — all wallets, all pools, aggregate stats.
    Used exclusively by the admin monitoring dashboard.
    """
    async with AsyncSessionLocal() as db:
        # All configs + owners
        cfg_result = await db.execute(
            select(BotConfig)
            .options(selectinload(BotConfig.user))
            .order_by(BotConfig.user_address, BotConfig.id)
        )
        configs = cfg_result.scalars().all()

        pools = []
        total_volume = 0.0
        active_shorts = 0

        for cfg in configs:
            # Last event for this config
            evt_result = await db.execute(
                select(BotEvent)
                .where(BotEvent.config_id == cfg.id)
                .order_by(BotEvent.id.desc())
                .limit(1)
            )
            last_evt = evt_result.scalar_one_or_none()

            # Total volume: sum notionals from all hedge_opened events
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

            last_event_type = last_evt.event_type if last_evt else None
            if last_event_type == "hedge_opened" and running:
                active_shorts += 1

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
                "active":       cfg.active,
                "running":      running,
                "created_at":   cfg.created_at.isoformat() if cfg.created_at else None,
                "last_event": {
                    "type":    last_evt.event_type,
                    "price":   float(last_evt.price_at_event) if last_evt.price_at_event else None,
                    "pnl":     float(last_evt.pnl) if last_evt.pnl else None,
                    "ts":      last_evt.ts.isoformat() if last_evt.ts else None,
                    "details": last_evt.details,
                } if last_evt else None,
                "volume_usd": round(config_volume, 2),
            })

        unique_wallets = len({p["user_address"] for p in pools})
        running_count  = sum(1 for p in pools if p["running"])

        return {
            "stats": {
                "total_wallets":  unique_wallets,
                "total_pools":    len(pools),
                "active_bots":    running_count,
                "active_shorts":  active_shorts,
                "total_volume_usd": round(total_volume, 2),
            },
            "pools": pools,
        }
