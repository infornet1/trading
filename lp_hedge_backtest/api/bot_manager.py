"""
BotManager — spawns/stops isolated live_hedge_bot.py subprocesses per user.

Each subprocess receives its full config via environment variables.
Stdout is tailed in an asyncio task; [EVENT] JSON lines are written to
bot_events table and pushed to any connected WebSocket subscribers.
"""

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from subprocess import PIPE, STDOUT
from typing import Optional

from api.database import AsyncSessionLocal
from api.models import BotConfig, BotEvent

# Path to the bot script and venv Python
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOT_SCRIPT  = os.path.join(_BASE, "live_hedge_bot.py")
VENV_PYTHON = os.path.join(_BASE, "venv", "bin", "python3")

# Map event label from bot stdout → DB enum value
_EVENT_MAP = {
    "started":      "started",
    "hedge_opened": "hedge_opened",
    "breakeven":    "breakeven",
    "tp_hit":       "tp_hit",
    "sl_hit":       "sl_hit",
    "stopped":      "stopped",
    "error":        "error",
}


class BotManager:
    def __init__(self):
        self._procs:  dict[int, subprocess.Popen]         = {}   # config_id → process
        self._tasks:  dict[int, asyncio.Task]              = {}   # config_id → tail task
        self._subscribers: dict[int, list[asyncio.Queue]] = {}   # config_id → WS queues
        self._shutting_down: bool = False

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def start(self, config_id: int, config: dict):
        if config_id in self._procs:
            return  # already running

        env = {
            **os.environ,
            "HYPERLIQUID_SECRET_KEY":     config["hl_api_key"],
            "HYPERLIQUID_ACCOUNT_ADDRESS": config["hl_wallet_addr"],
            "UNISWAP_NFT_ID":   config["nft_token_id"],
            "LOWER_BOUND":      config["lower_bound"],
            "UPPER_BOUND":      config["upper_bound"],
            "TRIGGER_OFFSET_PCT": str(abs(float(config["trigger_pct"]))),
            "BOT_MODE":         config["mode"],
            "CONFIG_ID":        str(config_id),
        }

        proc = subprocess.Popen(
            [VENV_PYTHON, BOT_SCRIPT],
            env=env,
            stdout=PIPE,
            stderr=STDOUT,
            text=True,
            bufsize=1,
        )
        self._procs[config_id] = proc
        task = asyncio.create_task(self._tail(config_id, proc))
        self._tasks[config_id] = task
        print(f"[BotManager] Started bot for config {config_id}, PID {proc.pid}", flush=True)

    async def shutdown(self):
        """Graceful API shutdown — terminate all bots without marking them inactive in DB."""
        self._shutting_down = True
        for config_id, proc in list(self._procs.items()):
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try: proc.kill()
                except Exception: pass
        self._procs.clear()
        self._tasks.clear()
        print("[BotManager] Graceful shutdown complete", flush=True)

    async def stop(self, config_id: int):
        proc = self._procs.pop(config_id, None)
        task = self._tasks.pop(config_id, None)
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            print(f"[BotManager] Stopped bot for config {config_id}", flush=True)
        if task and not task.done():
            task.cancel()

        # Write stopped event to DB
        await self._write_event(config_id, "stopped", None, None, None)
        # Notify WS subscribers
        await self._broadcast(config_id, {"event": "stopped", "config_id": config_id})

    def is_running(self, config_id: int) -> bool:
        proc = self._procs.get(config_id)
        if not proc:
            return False
        return proc.poll() is None  # None = still running

    def pid(self, config_id: int) -> Optional[int]:
        proc = self._procs.get(config_id)
        return proc.pid if proc and proc.poll() is None else None

    # ── Stdout tail ───────────────────────────────────────────────────────

    async def _tail(self, config_id: int, proc: subprocess.Popen):
        """
        Read stdout lines in a thread executor (blocking readline).
        Parse [EVENT] JSON lines → DB + WebSocket.
        """
        loop = asyncio.get_event_loop()
        try:
            while True:
                line = await loop.run_in_executor(None, proc.stdout.readline)
                if not line:
                    break  # process exited
                line = line.rstrip()
                if not line:
                    continue

                print(f"[Bot {config_id}] {line}", flush=True)

                if line.startswith("[EVENT] "):
                    try:
                        record = json.loads(line[len("[EVENT] "):])
                        await self._handle_event(config_id, record)
                    except Exception as e:
                        print(f"[BotManager] Event parse error: {e}", flush=True)
                else:
                    # Forward raw stdout lines as live log messages
                    await self._broadcast(config_id, {
                        "type": "log",
                        "msg":  line,
                        "ts":   datetime.now(timezone.utc).isoformat(),
                    })
        except Exception as e:
            print(f"[BotManager] Tail error for config {config_id}: {e}", flush=True)
        finally:
            # Process ended — mark inactive only if NOT a graceful API shutdown
            if config_id in self._procs:
                self._procs.pop(config_id, None)
                self._tasks.pop(config_id, None)
                if not self._shutting_down:
                    await self._mark_inactive(config_id)
                    await self._broadcast(config_id, {"event": "stopped", "config_id": config_id})
                    print(f"[BotManager] Bot {config_id} exited unexpectedly", flush=True)
                else:
                    print(f"[BotManager] Bot {config_id} stopped for shutdown (active=True preserved)", flush=True)

    async def _handle_event(self, config_id: int, record: dict):
        event_label = record.get("event", "")
        event_type  = _EVENT_MAP.get(event_label, "error")
        price       = record.get("price")
        pnl         = record.get("pnl")
        details     = record.get("details")

        await self._write_event(config_id, event_type, price, pnl, details)
        await self._broadcast(config_id, {
            "event":   event_type,
            "price":   price,
            "pnl":     pnl,
            "details": details,
            "ts":      datetime.now(timezone.utc).isoformat(),
        })

    # ── DB helpers ────────────────────────────────────────────────────────

    async def _write_event(self, config_id: int, event_type: str,
                           price, pnl, details):
        try:
            async with AsyncSessionLocal() as db:
                db.add(BotEvent(
                    config_id      = config_id,
                    event_type     = event_type,
                    price_at_event = price,
                    pnl            = pnl,
                    details        = details,
                ))
                await db.commit()
        except Exception as e:
            print(f"[BotManager] DB write error: {e}", flush=True)

    async def _mark_inactive(self, config_id: int):
        try:
            from sqlalchemy import update
            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(BotConfig)
                    .where(BotConfig.id == config_id)
                    .values(active=False)
                )
                await db.commit()
        except Exception as e:
            print(f"[BotManager] DB mark_inactive error: {e}", flush=True)

    # ── WebSocket pub/sub ─────────────────────────────────────────────────

    def subscribe(self, config_id: int) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.setdefault(config_id, []).append(q)
        return q

    def unsubscribe(self, config_id: int, q: asyncio.Queue):
        subs = self._subscribers.get(config_id, [])
        if q in subs:
            subs.remove(q)

    async def _broadcast(self, config_id: int, payload: dict):
        for q in list(self._subscribers.get(config_id, [])):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass  # slow consumer — drop


# Singleton instance shared across the API
manager = BotManager()
