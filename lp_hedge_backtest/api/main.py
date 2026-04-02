"""
VIZNIAGO FURY — SaaS API
FastAPI app on port 8001.
"""

import os
import time
import asyncio
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text

from api.database import engine, Base, AsyncSessionLocal
from api.auth import get_current_admin
from api.routers import auth as auth_router
from api.routers import bots as bots_router
from api.routers import ws as ws_router
from api.routers import admin as admin_router
from api.routers import assistant as assistant_router
from api.routers import telegram as telegram_router


async def _run_column_migrations():
    """Add new columns to existing tables if they don't exist. Safe to re-run on every startup."""
    migrations = [
        "ALTER TABLE bot_configs ADD COLUMN IF NOT EXISTS leverage INT NOT NULL DEFAULT 10",
        "ALTER TABLE bot_configs ADD COLUMN IF NOT EXISTS sl_pct DECIMAL(5,3) NOT NULL DEFAULT 0.100",
        "ALTER TABLE bot_configs ADD COLUMN IF NOT EXISTS tp_pct DECIMAL(5,3) NULL",
        "ALTER TABLE bot_configs ADD COLUMN IF NOT EXISTS trailing_stop TINYINT(1) NOT NULL DEFAULT 1",
        "ALTER TABLE bot_configs ADD COLUMN IF NOT EXISTS auto_rearm TINYINT(1) NOT NULL DEFAULT 1",
        # FURY mode columns
        "ALTER TABLE bot_configs ADD COLUMN IF NOT EXISTS fury_symbol VARCHAR(5) NULL",
        "ALTER TABLE bot_configs ADD COLUMN IF NOT EXISTS fury_rsi_period INT NULL DEFAULT 9",
        "ALTER TABLE bot_configs ADD COLUMN IF NOT EXISTS fury_rsi_long_th DECIMAL(5,2) NULL DEFAULT 35.00",
        "ALTER TABLE bot_configs ADD COLUMN IF NOT EXISTS fury_rsi_short_th DECIMAL(5,2) NULL DEFAULT 65.00",
        "ALTER TABLE bot_configs ADD COLUMN IF NOT EXISTS fury_leverage_max INT NULL DEFAULT 12",
        "ALTER TABLE bot_configs ADD COLUMN IF NOT EXISTS fury_risk_pct DECIMAL(5,2) NULL DEFAULT 2.00",
        # WHALE mode missing columns
        "ALTER TABLE bot_configs ADD COLUMN IF NOT EXISTS whale_use_websocket TINYINT(1) NULL DEFAULT 0",
        "ALTER TABLE bot_configs ADD COLUMN IF NOT EXISTS whale_oi_spike_threshold DECIMAL(5,3) NULL DEFAULT 0.030",
        # Telegram alerts
        (
            "CREATE TABLE IF NOT EXISTS telegram_links ("
            "  id               INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,"
            "  user_address     VARCHAR(42)  NOT NULL UNIQUE,"
            "  telegram_chat_id BIGINT       NOT NULL UNIQUE,"
            "  linked_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP"
            ")"
        ),
    ]
    async with engine.begin() as conn:
        for sql in migrations:
            try:
                await conn.execute(text(sql))
            except Exception as e:
                print(f"[Migration] Skipped (likely exists): {e}", flush=True)


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
                if not bot.hl_api_key or not bot.hl_wallet_addr:
                    print(f"[Startup] Skipping bot {bot.id} — missing credentials (hl_api_key or hl_wallet_addr is NULL)", flush=True)
                    continue
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
                    "leverage":       str(bot.leverage   or 10),
                    "sl_pct":         str(bot.sl_pct     or 0.1),
                    "tp_pct":         str(bot.tp_pct)    if bot.tp_pct else "",
                    "trailing_stop":  "1" if bot.trailing_stop else "0",
                    "auto_rearm":     "1" if bot.auto_rearm    else "0",
                    # FURY config (only used when mode='fury')
                    "fury_symbol":       bot.fury_symbol       or "ETH",
                    "fury_rsi_period":   str(bot.fury_rsi_period   or 9),
                    "fury_rsi_long_th":  str(bot.fury_rsi_long_th  or 35),
                    "fury_rsi_short_th": str(bot.fury_rsi_short_th or 65),
                    "fury_leverage_max": str(bot.fury_leverage_max or 12),
                    "fury_risk_pct":     str(bot.fury_risk_pct     or 2.0),
                    # WHALE config (only used when mode='whale')
                    "whale_top_n":              str(bot.whale_top_n          or 50),
                    "whale_min_notional":       str(bot.whale_min_notional   or 50000),
                    "whale_poll_interval":      str(bot.whale_poll_interval  or 30),
                    "whale_custom_addresses":   bot.whale_custom_addresses   or "",
                    "whale_watch_assets":       bot.whale_watch_assets       or "",
                    "whale_use_websocket":      bot.whale_use_websocket      or False,
                    "whale_oi_spike_threshold": str(bot.whale_oi_spike_threshold or 0.03),
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
    # Add new columns to existing tables (idempotent)
    await _run_column_migrations()
    # Re-launch bots that were active before last restart
    await _auto_restart_bots()
    # Start Telegram long-poller (fallback when webhook DNS fails)
    from api.telegram_poller import run_poller
    tg_task = asyncio.create_task(run_poller())
    yield
    # Graceful shutdown
    tg_task.cancel()
    try:
        await tg_task
    except asyncio.CancelledError:
        pass
    from api.bot_manager import manager
    await manager.shutdown()
    await engine.dispose()


app = FastAPI(
    title="VIZNIAGO FURY API",
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
app.include_router(assistant_router.router)
app.include_router(telegram_router.router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "viznago-fury-api"}


# ── Maintenance flag (file-based, persists across restarts) ───────────────
_MAINTENANCE_FLAG = "/tmp/viznago_maintenance.flag"


@app.get("/status/maintenance")
async def maintenance_status():
    """Public endpoint — dashboard polls this to show/hide maintenance banner."""
    active = os.path.exists(_MAINTENANCE_FLAG)
    msg    = ""
    if active:
        try:
            with open(_MAINTENANCE_FLAG) as f:
                msg = f.read().strip()
        except Exception:
            pass
    return {"maintenance": active, "message": msg}


@app.post("/admin/maintenance")
async def set_maintenance(
    payload: dict,
    admin: str = Depends(get_current_admin),
):
    """Admin only — toggle maintenance mode. Body: {active: bool, message: str}"""
    enable = bool(payload.get("active", False))
    message = str(payload.get("message", ""))
    if enable:
        with open(_MAINTENANCE_FLAG, "w") as f:
            f.write(message)
    else:
        try:
            os.remove(_MAINTENANCE_FLAG)
        except FileNotFoundError:
            pass
    return {"maintenance": enable, "message": message}


# ── Price proxy (avoids CORS + rate-limit exposure on the client) ─────────
_price_cache: dict = {"data": None, "ts": 0.0}
_PRICE_TTL = 30  # seconds


@app.get("/prices")
async def get_prices():
    """Server-side proxy for CoinGecko prices — cached 30 s to avoid rate limits."""
    now = time.monotonic()
    if _price_cache["data"] and now - _price_cache["ts"] < _PRICE_TTL:
        return _price_cache["data"]

    url = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum,bitcoin&vs_currencies=usd"
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(url)
            r.raise_for_status()
            _price_cache["data"] = r.json()
            _price_cache["ts"]   = now
            return _price_cache["data"]
    except Exception as e:
        # Return last cached value if available, else empty
        if _price_cache["data"]:
            return _price_cache["data"]
        return {"ethereum": {"usd": None}, "bitcoin": {"usd": None}}
