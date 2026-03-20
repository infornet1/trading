"""
VIZNAGO FURY — SaaS API
FastAPI app on port 8001.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.database import engine, Base
from api.routers import auth as auth_router
from api.routers import bots as bots_router
from api.routers import ws as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create all tables if they don't exist yet
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
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


@app.get("/health")
async def health():
    return {"status": "ok", "service": "viznago-fury-api"}
