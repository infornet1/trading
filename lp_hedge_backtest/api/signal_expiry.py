"""
Background task: marks pending signals older than 4 hours as expired.
Runs every 15 minutes alongside the LP reconciler.
"""

import asyncio
from datetime import datetime, timedelta

from sqlalchemy import update

from api.database import AsyncSessionLocal
from api.models import SignalEvent

EXPIRY_HOURS   = 4
SWEEP_INTERVAL = 900  # 15 minutes


async def run_signal_expiry() -> None:
    while True:
        await asyncio.sleep(SWEEP_INTERVAL)
        try:
            cutoff = datetime.utcnow() - timedelta(hours=EXPIRY_HOURS)
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    update(SignalEvent)
                    .where(SignalEvent.status == "pending", SignalEvent.received_at < cutoff)
                    .values(status="expired")
                )
                await db.commit()
                if result.rowcount > 0:
                    print(f"[SignalExpiry] Marked {result.rowcount} signal(s) as expired", flush=True)
        except Exception as e:
            print(f"[SignalExpiry] Error: {e}", flush=True)
