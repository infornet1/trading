#!/usr/bin/env python3
"""
seed_pools.py — ONE-TIME migration script.

Registers the owner's LP pools into the viznago_dev DB so BotManager
can manage them automatically. After this runs, the manual .env files
and systemd bot services are no longer needed.

Usage:
    cd /var/www/dev/trading/lp_hedge_backtest
    ENCRYPTION_KEY=<key> HYPERLIQUID_SECRET_KEY=<secret> python3 scripts/seed_pools.py

The script is idempotent — re-running it skips NFTs already registered.
"""

import asyncio
import math
import os
import sys

# ── Resolve project root so imports work ──────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from api.database import AsyncSessionLocal, engine, Base
from api.models import BotConfig, User
from api.crypto import encrypt

# ── Owner config ──────────────────────────────────────────────────────────────
OWNER_ADDRESS = "0xeF0DDF18382538F31dcfa0AF40B47eE8c5A2cf2f"
HL_WALLET     = "0xeF0DDF18382538F31dcfa0AF40B47eE8c5A2cf2f"
HL_SECRET_KEY = os.environ.get("HYPERLIQUID_SECRET_KEY", "")
RPC_URL       = os.environ.get("ARBITRUM_RPC_URL", "https://arb1.arbitrum.io/rpc")

if not HL_SECRET_KEY:
    print("❌  HYPERLIQUID_SECRET_KEY env var is required.")
    sys.exit(1)

if not os.environ.get("ENCRYPTION_KEY"):
    print("❌  ENCRYPTION_KEY env var is required.")
    sys.exit(1)

# ── Fetch live range from on-chain ────────────────────────────────────────────
from web3 import Web3

V3_POS_MANAGER = "0xC36442b4a4522E871399CD717aBDD847Ab11FE88"
V3_ABI = [
    {"inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
     "name": "positions", "outputs": [
        {"internalType": "uint96",  "name": "nonce",     "type": "uint96"},
        {"internalType": "address", "name": "operator",  "type": "address"},
        {"internalType": "address", "name": "token0",    "type": "address"},
        {"internalType": "address", "name": "token1",    "type": "address"},
        {"internalType": "uint24",  "name": "fee",       "type": "uint24"},
        {"internalType": "int24",   "name": "tickLower", "type": "int24"},
        {"internalType": "int24",   "name": "tickUpper", "type": "int24"},
        {"internalType": "uint128", "name": "liquidity", "type": "uint128"},
        {"internalType": "uint256", "name": "feeGrowthInside0LastX128", "type": "uint256"},
        {"internalType": "uint256", "name": "feeGrowthInside1LastX128", "type": "uint256"},
        {"internalType": "uint128", "name": "tokensOwed0", "type": "uint128"},
        {"internalType": "uint128", "name": "tokensOwed1", "type": "uint128"},
    ], "stateMutability": "view", "type": "function"}
]


def tick_to_price(tick: int) -> float:
    return (1.0001 ** tick) * (10 ** 12)


def fetch_range(nft_id: int) -> tuple[float, float]:
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    contract = w3.eth.contract(address=V3_POS_MANAGER, abi=V3_ABI)
    pos = contract.functions.positions(nft_id).call()
    return tick_to_price(pos[5]), tick_to_price(pos[6])


# ── Pools to register ─────────────────────────────────────────────────────────
POOLS = [
    {"nft_token_id": "5374616", "pair": "ETH/USDC"},
    {"nft_token_id": "5364575", "pair": "ETH/USDC"},
    {"nft_token_id": "5381818", "pair": "ETH/USDC"},
]


async def main():
    # Ensure tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    encrypted_key = encrypt(HL_SECRET_KEY)

    async with AsyncSessionLocal() as db:
        # Ensure owner user row exists
        result = await db.execute(select(User).where(User.address == OWNER_ADDRESS))
        if not result.scalar_one_or_none():
            db.add(User(address=OWNER_ADDRESS, plan="pro"))
            await db.commit()
            print(f"✅  Created user row for {OWNER_ADDRESS}")

        for pool in POOLS:
            nft_id = pool["nft_token_id"]

            # Skip if already registered
            existing = await db.execute(
                select(BotConfig).where(
                    BotConfig.user_address == OWNER_ADDRESS,
                    BotConfig.nft_token_id == nft_id,
                )
            )
            if existing.scalar_one_or_none():
                print(f"⏭️   NFT #{nft_id} already registered — skipping")
                continue

            print(f"🔍  Fetching on-chain range for NFT #{nft_id}...")
            lower, upper = fetch_range(int(nft_id))
            print(f"    Range: ${lower:.2f} — ${upper:.2f}")

            cfg = BotConfig(
                user_address   = OWNER_ADDRESS,
                chain_id       = 42161,            # Arbitrum One
                nft_token_id   = nft_id,
                pair           = pool["pair"],
                lower_bound    = lower,
                upper_bound    = upper,
                trigger_pct    = -0.50,
                hedge_ratio    = 50.00,
                hedge_exchange = "hyperliquid",
                hl_api_key     = encrypted_key,
                hl_wallet_addr = HL_WALLET,
                mode           = "aragan",
                active         = True,             # auto-start on next API boot
            )
            db.add(cfg)
            await db.commit()
            await db.refresh(cfg)
            print(f"✅  Registered NFT #{nft_id} as config ID {cfg.id} (active=True)")

    print()
    print("Done. Restart viznago_api.service to activate all bots:")
    print("  systemctl restart viznago_api.service")


if __name__ == "__main__":
    asyncio.run(main())
