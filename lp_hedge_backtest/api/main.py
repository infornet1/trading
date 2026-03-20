"""
VIZNAGO FURY — SaaS API
FastAPI app on port 8001.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from api.database import engine, Base, AsyncSessionLocal
from api.routers import auth as auth_router
from api.routers import bots as bots_router
from api.routers import ws as ws_router
from api.routers import admin as admin_router


async def _auto_restart_bots():
    """On startup, re-launch any bot configs that were active before the last restart."""
    from api.models import BotConfig
    from api.crypto import decrypt
    from api.bot_manager import manager
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(BotConfig).where(BotConfig.active == True))
        bots = result.scalars().all()
        for bot in bots:
            try:
                config = {
                    "nft_token_id":   bot.nft_token_id,
                    "lower_bound":    str(bot.lower_bound),
                    "upper_bound":    str(bot.upper_bound),
                    "trigger_pct":    str(bot.trigger_pct),
                    "hedge_ratio":    str(bot.hedge_ratio),
                    "hl_api_key":     decrypt(bot.hl_api_key),
                    "hl_wallet_addr": bot.hl_wallet_addr,
                    "mode":           bot.mode,
                    "pair":           bot.pair,
                }
                await manager.start(bot.id, config)
                print(f"[Startup] Auto-restarted bot {bot.id} (NFT #{bot.nft_token_id})", flush=True)
            except Exception as e:
                print(f"[Startup] Failed to restart bot {bot.id}: {e}", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create all tables if they don't exist yet
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Re-launch bots that were active before last restart
    await _auto_restart_bots()
    yield
    # Graceful shutdown — bots stay active=True in DB so they restart next time
    from api.bot_manager import manager
    await manager.shutdown()
    await engine.dispose()


app = FastAPI(
    title="VIZNAGO FURY API",
    version="0.1.0",
    description="SaaS LP hedge bot management API",
    lifespan=lifespan,
)

# CORS — allow dashboard origin in dev; tighten in prod
_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "https://dev.ueipab.edu.ve,http://localhost:3000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────
app.include_router(auth_router.router)
app.include_router(bots_router.router)
app.include_router(ws_router.router)
app.include_router(admin_router.router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "viznago-fury-api"}
