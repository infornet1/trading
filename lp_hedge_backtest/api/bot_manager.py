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

# Path to bot scripts and venv Python
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOT_SCRIPT       = os.path.join(_BASE, "live_hedge_bot.py")
BOT_V2_SCRIPT    = os.path.join(_BASE, "live_hedge_bot_v2.py")
FURY_BOT_SCRIPT  = os.path.join(_BASE, "live_fury_bot.py")
WHALE_BOT_SCRIPT = os.path.join(_BASE, "live_whale_bot.py")
VENV_PYTHON      = os.path.join(_BASE, "venv", "bin", "python3")

# Map event label from bot stdout → DB enum value
_EVENT_MAP = {
    "started":              "started",
    "hedge_opened":         "hedge_opened",
    "breakeven":            "breakeven",
    "tp_hit":               "tp_hit",
    "sl_hit":               "sl_hit",
    "trailing_stop":        "trailing_stop",
    "stopped":              "stopped",
    "error":                "error",
    "reentry_guard_cleared": "reentry_guard_cleared",
    # LP safety events
    "lp_removed":           "lp_removed",
    "lp_burned":            "lp_burned",
    # V2 recovery
    "orphan_recovered":     "orphan_recovered",
    # FURY events
    "fury_entry":           "fury_entry",
    "fury_sl":              "fury_sl",
    "fury_tp":              "fury_tp",
    "fury_circuit_breaker": "fury_circuit_breaker",
    # WHALE events
    "whale_new_position":   "whale_new_position",
    "whale_closed":         "whale_closed",
    "whale_size_increase":  "whale_size_increase",
    "whale_size_decrease":  "whale_size_decrease",
    "whale_flip":           "whale_flip",
    "whale_snapshot":       "whale_snapshot",
    "whale_event":          "whale_event",
}


class BotManager:
    def __init__(self):
        self._procs:  dict[int, subprocess.Popen]         = {}   # config_id → process
        self._tasks:  dict[int, asyncio.Task]              = {}   # config_id → tail task
        self._subscribers: dict[int, list[asyncio.Queue]] = {}   # config_id → WS queues
        self._last_seen:   dict[int, datetime]             = {}   # config_id → last stdout ts
        self._shutting_down: bool = False

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def start(self, config_id: int, config: dict):
        if config_id in self._procs:
            return  # already running

        # Build a clean environment — never inherit pool-specific vars from the
        # parent process or any .env file. Only pass what the bot explicitly needs.
        env = {
            # System essentials
            "PATH":             os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME":             os.environ.get("HOME", "/root"),
            "LANG":             os.environ.get("LANG", "en_US.UTF-8"),
            "PYTHONUNBUFFERED": "1",
            # Global infrastructure (set at API level, safe to inherit)
            "ARBITRUM_RPC_URL":   os.environ.get("ARBITRUM_RPC_URL",
                                    "https://arb1.arbitrum.io/rpc"),
            "EMAIL_CONFIG_PATH":  os.environ.get("EMAIL_CONFIG_PATH",
                                    "/var/www/dev/trading/email_config.json"),
            "EMAIL_RECIPIENTS":   os.environ.get("EMAIL_RECIPIENTS", ""),
            # Per-bot config — sourced exclusively from DB, not from .env
            # Whale mode has no HL credentials (read-only leaderboard); fall back to ""
            "HYPERLIQUID_SECRET_KEY":      config["hl_api_key"]     or "",
            "HYPERLIQUID_ACCOUNT_ADDRESS": config["hl_wallet_addr"] or "",
            "UNISWAP_NFT_ID":              str(config["nft_token_id"]),
            "TRIGGER_OFFSET_PCT":          str(abs(float(config["trigger_pct"]))),
            "HEDGE_RATIO":                 str(config["hedge_ratio"]),
            "BOT_MODE":                    config["mode"],
            "CONFIG_ID":                   str(config_id),
            # Trading panel parameters (user-configured, with safe defaults)
            "TARGET_LEVERAGE":             str(config.get("leverage", "10")),
            "SL_PCT":                      str(config.get("sl_pct",  "0.1")),
            "TP_PCT":                      str(config.get("tp_pct",  "")),
            "TRAILING_STOP":               str(config.get("trailing_stop", "1")),
            "AUTO_REARM":                  str(config.get("auto_rearm",    "1")),
        }

        # Select bot script based on mode; inject mode-specific vars if needed
        bot_mode = config.get("mode", "aragan")
        if bot_mode == "fury":
            script = FURY_BOT_SCRIPT
            env["FURY_SYMBOL"]       = str(config.get("fury_symbol", "ETH"))
            env["FURY_RSI_PERIOD"]   = str(config.get("fury_rsi_period", "9"))
            env["FURY_RSI_LONG_TH"]  = str(config.get("fury_rsi_long_th", "35"))
            env["FURY_RSI_SHORT_TH"] = str(config.get("fury_rsi_short_th", "65"))
            env["FURY_LEVERAGE_MAX"] = str(config.get("fury_leverage_max", "12"))
            env["FURY_RISK_PCT"]     = str(config.get("fury_risk_pct", "2.0"))
            if config.get("paper_trade"):
                env["PAPER_TRADE"] = "1"
        elif bot_mode == "whale":
            script = WHALE_BOT_SCRIPT
            env["LEADERBOARD_TOP_N"]   = str(config.get("whale_top_n",          "50"))
            env["MIN_NOTIONAL_USD"]    = str(config.get("whale_min_notional",    "50000"))
            env["POLL_INTERVAL"]       = str(config.get("whale_poll_interval",   "30"))
            env["CUSTOM_ADDRESSES"]    = str(config.get("whale_custom_addresses",""))
            env["WATCH_ASSETS"]        = str(config.get("whale_watch_assets",    ""))
            env["USE_WEBSOCKET"]       = "1" if config.get("whale_use_websocket") else "0"
            env["OI_SPIKE_THRESHOLD"]  = str(config.get("whale_oi_spike_threshold", "0.03"))
            if config.get("paper_trade"):
                env["PAPER_TRADE"] = "1"
        else:
            # aragan/avaro: route to V2 engine if config flag is set
            if config.get("engine_v2", False):
                script = BOT_V2_SCRIPT
                env["ENGINE_V2"] = "1"
            else:
                script = BOT_SCRIPT

        proc = subprocess.Popen(
            [VENV_PYTHON, script],
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

    def last_seen(self, config_id: int) -> Optional[datetime]:
        """Timestamp of the last stdout line received from the bot process."""
        return self._last_seen.get(config_id)

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
                self._last_seen[config_id] = datetime.now(timezone.utc)

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
            # Process ended — only mark inactive if it crashed (not killed by signal/shutdown)
            if config_id in self._procs:
                self._procs.pop(config_id, None)
                self._tasks.pop(config_id, None)
                # Poll to get actual returncode (-15=SIGTERM, -9=SIGKILL, None=undetermined)
                proc.poll()
                killed_by_signal = proc.returncode is None or proc.returncode < 0
                if not self._shutting_down and not killed_by_signal:
                    await self._mark_inactive(config_id)
                    await self._broadcast(config_id, {"event": "stopped", "config_id": config_id})
                    print(f"[BotManager] Bot {config_id} crashed (rc={proc.returncode}), marked inactive", flush=True)
                else:
                    print(f"[BotManager] Bot {config_id} terminated (rc={proc.returncode}), active=True preserved", flush=True)

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

        # LP gone → auto-deactivate config + notify admin
        if event_type in ("lp_removed", "lp_burned"):
            await self._mark_inactive(config_id)
            asyncio.create_task(self._notify_admin_lp_gone(config_id, event_type, details))

        # Telegram alert — non-blocking, fire-and-forget
        from api.telegram_alerts import send_alert
        asyncio.create_task(send_alert(config_id, event_type, price, pnl, details))

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

    async def _notify_admin_lp_gone(self, config_id: int, event_type: str, details: Optional[dict]):
        """Send admin email when a bot is auto-deactivated due to LP removal."""
        import json as _json
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        try:
            email_path = os.environ.get("EMAIL_CONFIG_PATH",
                                        "/var/www/dev/trading/email_config.json")
            with open(email_path) as f:
                cfg = _json.load(f)
            admin = os.environ.get("EMAIL_RECIPIENTS", "perdomo.gustavo@gmail.com")
            msg = MIMEMultipart()
            msg["From"]    = cfg["sender_email"]
            msg["To"]      = admin
            msg["Subject"] = f"⚠️ [VIZNIAGO Admin] LP Gone — Config {config_id} Auto-Deactivated"
            reason = "LP removed (liquidity=0)" if event_type == "lp_removed" else "NFT burned"
            note   = (details or {}).get("note", "")
            body = (
                f"VIZNIAGO auto-deactivated bot config {config_id}.\n\n"
                f"Reason: {reason}\n"
                f"Note:   {note}\n"
                f"Time:   {datetime.now(timezone.utc).isoformat()}\n\n"
                f"Config set to active=False. User must re-add liquidity and re-arm from the dashboard."
            )
            msg.attach(MIMEText(body, "plain"))
            s = smtplib.SMTP(cfg["smtp_server"], cfg["smtp_port"])
            s.starttls()
            s.login(cfg["smtp_username"], cfg["smtp_password"])
            s.send_message(msg)
            s.quit()
            print(f"[BotManager] Admin LP-gone email sent for config {config_id}", flush=True)
        except Exception as e:
            print(f"[BotManager] Admin LP-gone email failed: {e}", flush=True)

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
