"""
Admin router — emergency controls, admin-wallet only.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import update

from api.auth import get_current_admin
from api.bot_manager import manager
from api.database import AsyncSessionLocal
from api.models import BotConfig

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
