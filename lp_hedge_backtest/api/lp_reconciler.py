"""
VIZNIAGO — LP Reconciler
Background asyncio loop that scans all active aragan/avaro bot_configs
every hour, verifies each Uniswap v3 NFT on-chain, and auto-deactivates
configs where the LP is gone (liquidity=0 or NFT burned).

Admin is notified by email on every deactivation.
Running bots for deactivated configs are stopped via BotManager.

This job is independent of the V2 engine — it runs for V1 and V2 alike.
"""

import asyncio
import json
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

_BASE_DIR       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RECONCILE_STATE = os.path.join(_BASE_DIR, "data_cache", "reconciler_state.json")

from sqlalchemy import select, update
from web3 import Web3

from api.database import AsyncSessionLocal
from api.models import BotConfig, BotEvent

RECONCILE_INTERVAL = 3600   # seconds between full scans (1 hour)
STARTUP_DELAY      = 90     # seconds after API boot before first scan

RPC_URL           = os.getenv("ARBITRUM_RPC_URL", "https://arb1.arbitrum.io/rpc")
EMAIL_CONFIG_PATH = os.getenv("EMAIL_CONFIG_PATH", "/var/www/dev/trading/email_config.json")
ADMIN_EMAIL       = os.getenv("EMAIL_RECIPIENTS",  "perdomo.gustavo@gmail.com")

V3_POS_MANAGER = "0xC36442b4a4522E871399CD717aBDD847Ab11FE88"
V3_ABI = [
    {
        "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
        "name": "positions",
        "outputs": [
            {"internalType": "uint96",  "name": "nonce",          "type": "uint96"},
            {"internalType": "address", "name": "operator",       "type": "address"},
            {"internalType": "address", "name": "token0",         "type": "address"},
            {"internalType": "address", "name": "token1",         "type": "address"},
            {"internalType": "uint24",  "name": "fee",            "type": "uint24"},
            {"internalType": "int24",   "name": "tickLower",      "type": "int24"},
            {"internalType": "int24",   "name": "tickUpper",      "type": "int24"},
            {"internalType": "uint128", "name": "liquidity",      "type": "uint128"},
            {"internalType": "uint256", "name": "feeGrowthInside0LastX128", "type": "uint256"},
            {"internalType": "uint256", "name": "feeGrowthInside1LastX128", "type": "uint256"},
            {"internalType": "uint128", "name": "tokensOwed0",    "type": "uint128"},
            {"internalType": "uint128", "name": "tokensOwed1",    "type": "uint128"},
        ],
        "stateMutability": "view",
        "type": "function",
    }
]


async def run_lp_reconciler():
    """
    Long-running asyncio task.
    Waits STARTUP_DELAY seconds after boot, then scans every RECONCILE_INTERVAL.
    """
    await asyncio.sleep(STARTUP_DELAY)
    print(f"[LPReconciler] Starting — scanning every {RECONCILE_INTERVAL}s", flush=True)
    while True:
        try:
            await _reconcile_all()
        except Exception as e:
            print(f"[LPReconciler] Scan error: {e}", flush=True)
        await asyncio.sleep(RECONCILE_INTERVAL)


async def _reconcile_all():
    """Fetch all active aragan/avaro configs and verify each NFT on-chain."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(BotConfig).where(
                BotConfig.active == True,
                BotConfig.mode.in_(["aragan", "avaro"]),
            )
        )
        configs = result.scalars().all()

    if not configs:
        print("[LPReconciler] No active aragan/avaro configs to check", flush=True)
        _write_reconciler_state(0)
        return

    print(f"[LPReconciler] Scanning {len(configs)} active config(s)…", flush=True)

    loop = asyncio.get_event_loop()
    w3   = Web3(Web3.HTTPProvider(RPC_URL))
    contract = w3.eth.contract(address=V3_POS_MANAGER, abi=V3_ABI)

    for cfg in configs:
        await _check_config(cfg, contract, loop)

    _write_reconciler_state(len(configs))


def _write_reconciler_state(configs_checked: int):
    try:
        os.makedirs(os.path.dirname(_RECONCILE_STATE), exist_ok=True)
        with open(_RECONCILE_STATE, "w") as f:
            json.dump({
                "last_run": datetime.now(timezone.utc).isoformat(),
                "configs_checked": configs_checked,
            }, f)
    except Exception as e:
        print(f"[LPReconciler] Could not write state file: {e}", flush=True)


async def _check_config(cfg: BotConfig, contract, loop: asyncio.AbstractEventLoop):
    """Check a single config's NFT. Deactivate if LP is gone."""
    nft_id = int(cfg.nft_token_id)
    try:
        pos = await loop.run_in_executor(
            None, lambda: contract.functions.positions(nft_id).call()
        )
        liquidity = pos[7]

        if liquidity > 0:
            return  # LP healthy — nothing to do

        await _deactivate(
            cfg,
            event_type = "lp_removed",
            note       = f"LP liquidity=0 — user withdrew funds from NFT #{nft_id}",
        )

    except Exception as e:
        err = str(e).lower()
        if any(k in err for k in ("nonexistent token", "invalid token id", "owner query", "erc721")):
            await _deactivate(
                cfg,
                event_type = "lp_burned",
                note       = f"NFT #{nft_id} burned or no longer exists on-chain",
            )
        else:
            # RPC hiccup — skip this cycle, retry next hour
            print(f"[LPReconciler] Config {cfg.id} RPC error (skipping): {e}", flush=True)


async def _deactivate(cfg: BotConfig, event_type: str, note: str):
    """Set config inactive, log bot_event, stop running bot, email admin."""
    print(
        f"[LPReconciler] Deactivating config {cfg.id} "
        f"(NFT #{cfg.nft_token_id}, user {cfg.user_address}): {event_type}",
        flush=True,
    )

    async with AsyncSessionLocal() as db:
        await db.execute(
            update(BotConfig)
            .where(BotConfig.id == cfg.id)
            .values(active=False)
        )
        db.add(BotEvent(
            config_id      = cfg.id,
            event_type     = event_type,
            price_at_event = None,
            pnl            = None,
            details        = {
                "source":           "lp_reconciler",
                "note":             note,
                "auto_deactivated": True,
                "ts":               datetime.now(timezone.utc).isoformat(),
            },
        ))
        await db.commit()

    # Stop the running bot process if any
    try:
        from api.bot_manager import manager
        if manager.is_running(cfg.id):
            await manager.stop(cfg.id)
            print(f"[LPReconciler] Stopped running bot for config {cfg.id}", flush=True)
    except Exception as e:
        print(f"[LPReconciler] Could not stop bot {cfg.id}: {e}", flush=True)

    # Notify admin by email
    _send_admin_email(cfg, event_type, note)


def _send_admin_email(cfg: BotConfig, event_type: str, note: str):
    try:
        with open(EMAIL_CONFIG_PATH) as f:
            email_cfg = json.load(f)

        subject = (
            f"⚠️ [VIZNIAGO Admin] LP Removed — Config {cfg.id} Auto-Deactivated"
            if event_type == "lp_removed"
            else f"⚠️ [VIZNIAGO Admin] NFT Burned — Config {cfg.id} Auto-Deactivated"
        )
        body = (
            f"VIZNIAGO LP Reconciler auto-deactivated a bot config.\n\n"
            f"Config ID : {cfg.id}\n"
            f"NFT       : #{cfg.nft_token_id}\n"
            f"User      : {cfg.user_address}\n"
            f"Event     : {event_type}\n"
            f"Note      : {note}\n"
            f"Time      : {datetime.now(timezone.utc).isoformat()}\n\n"
            f"Config set to active=False.\n"
            f"If the user re-adds liquidity, they can re-arm protection from the dashboard."
        )

        msg = MIMEMultipart()
        msg["From"]    = email_cfg["sender_email"]
        msg["To"]      = ADMIN_EMAIL
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        s = smtplib.SMTP(email_cfg["smtp_server"], email_cfg["smtp_port"])
        s.starttls()
        s.login(email_cfg["smtp_username"], email_cfg["smtp_password"])
        s.send_message(msg)
        s.quit()
        print(f"[LPReconciler] Admin email sent for config {cfg.id}", flush=True)
    except Exception as e:
        print(f"[LPReconciler] Admin email failed: {e}", flush=True)
