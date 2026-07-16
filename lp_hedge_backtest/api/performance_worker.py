"""Background worker for profitability dashboard data collection.

Runs inside the FastAPI lifespan. It periodically:
- Takes Hyperliquid wallet balance snapshots for active bots and Signal Lab wallets.
- Does NOT place trades or modify bot state.
"""

import asyncio
import os
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from api.config import WALLET_SNAPSHOT_INTERVAL_SECS
from api.database import AsyncSessionLocal
from api.models import BotConfig, SignalWallet, WalletSnapshot


def _fetch_hl_balance_sync(hl_wallet_addr: str) -> dict:
    """Synchronous HL balance fetch; called via asyncio.to_thread."""
    try:
        from hyperliquid.info import Info
        from hyperliquid.utils import constants

        info = Info(constants.MAINNET_API_URL, skip_ws=True)
        state = info.user_state(hl_wallet_addr)
        ms = state.get("marginSummary", {})
        perp_val = float(ms.get("accountValue") or 0)

        spot_usdc = 0.0
        try:
            spot = info.spot_user_state(hl_wallet_addr)
            for b in spot.get("balances", []):
                if b["coin"] == "USDC":
                    spot_usdc = float(b["total"])
                    break
        except Exception:
            pass

        return {
            "balance_usdc": perp_val + spot_usdc,
            "margin_used_usdc": float(ms.get("totalMarginUsed") or 0),
            "error": None,
        }
    except Exception as e:
        return {"balance_usdc": None, "margin_used_usdc": None, "error": str(e)}


async def _take_wallet_snapshots() -> int:
    """Fetch and store one snapshot per unique wallet. Returns number inserted."""
    inserted = 0
    async with AsyncSessionLocal() as db:
        # Active bot configs with a Hyperliquid wallet
        bot_result = await db.execute(
            select(BotConfig.user_address, BotConfig.hl_wallet_addr)
            .where(BotConfig.active == True)  # noqa: E712
            .where(BotConfig.hl_wallet_addr.isnot(None))
        )
        bot_wallets = bot_result.all()

        # Signal Lab registered wallets
        signal_result = await db.execute(
            select(SignalWallet.user_address, SignalWallet.hl_wallet_addr)
            .where(SignalWallet.active == True)  # noqa: E712
        )
        signal_wallets = signal_result.all()

        # Deduplicate by wallet address
        seen = set()
        wallet_sources = []
        for user_address, wallet_addr in bot_wallets:
            if wallet_addr and wallet_addr not in seen:
                seen.add(wallet_addr)
                wallet_sources.append((user_address, wallet_addr, "bot"))
        for user_address, wallet_addr in signal_wallets:
            if wallet_addr and wallet_addr not in seen:
                seen.add(wallet_addr)
                wallet_sources.append((user_address, wallet_addr, "signal_lab"))

        now = datetime.now(timezone.utc)
        for user_address, wallet_addr, source in wallet_sources:
            try:
                data = await asyncio.to_thread(_fetch_hl_balance_sync, wallet_addr)
                if data.get("error"):
                    continue
                db.add(
                    WalletSnapshot(
                        user_address=user_address,
                        wallet_addr=wallet_addr,
                        source=source,
                        balance_usdc=data.get("balance_usdc"),
                        margin_used_usdc=data.get("margin_used_usdc"),
                        snapshot_at=now,
                    )
                )
                inserted += 1
            except Exception as e:
                print(f"[PerformanceWorker] Snapshot failed for {wallet_addr}: {e}", flush=True)

        await db.commit()
    return inserted


async def run_performance_worker():
    """Long-running background task for wallet snapshots."""
    print(
        f"[PerformanceWorker] Starting with interval {WALLET_SNAPSHOT_INTERVAL_SECS}s",
        flush=True,
    )
    while True:
        try:
            inserted = await _take_wallet_snapshots()
            print(
                f"[PerformanceWorker] Snapshots inserted: {inserted} at {datetime.now(timezone.utc).isoformat()}",
                flush=True,
            )
        except Exception as e:
            print(f"[PerformanceWorker] Error: {e}", flush=True)
        await asyncio.sleep(WALLET_SNAPSHOT_INTERVAL_SECS)
