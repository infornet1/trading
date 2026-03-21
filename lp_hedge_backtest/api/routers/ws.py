"""
WebSocket endpoint — streams live bot events to the dashboard.

WS URL: /ws/{bot_id}?token=<jwt>
Client receives JSON objects: { event, price, pnl, details, ts }
"""

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import select

from api.auth import decode_token
from api.bot_manager import manager
from api.database import AsyncSessionLocal
from api.models import BotConfig

router = APIRouter(tags=["realtime"])


@router.websocket("/ws/{config_id}")
async def ws_bot_events(
    websocket: WebSocket,
    config_id: int,
    token: str = Query(...),
):
    # 1. Authenticate via JWT passed as query param (WS headers are awkward in browsers)
    try:
        address = decode_token(token)["sub"]
    except Exception:
        await websocket.close(code=4001)
        return

    # 2. Verify ownership
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(BotConfig).where(BotConfig.id == config_id))
        cfg = result.scalar_one_or_none()
        if not cfg or cfg.user_address != address:
            await websocket.close(code=4003)
            return

    await websocket.accept()

    q = manager.subscribe(config_id)
    try:
        while True:
            try:
                payload = await asyncio.wait_for(q.get(), timeout=30.0)
                await websocket.send_text(json.dumps(payload))
            except asyncio.TimeoutError:
                # Send a keepalive ping
                await websocket.send_text(json.dumps({"event": "ping"}))
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        manager.unsubscribe(config_id, q)
