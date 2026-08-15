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
from collections import deque
from datetime import datetime, timezone
from subprocess import PIPE, STDOUT
from typing import Optional

from api.database import AsyncSessionLocal
from api.email_config import load_email_config
from api.models import BotConfig, BotEvent, BotTrade

# Path to bot scripts and venv Python
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOT_SCRIPT       = os.path.join(_BASE, "live_hedge_bot.py")
BOT_V2_SCRIPT    = os.path.join(_BASE, "live_hedge_bot_v2.py")
FURY_BOT_SCRIPT  = os.path.join(_BASE, "live_fury_bot.py")
WHALE_BOT_SCRIPT = os.path.join(_BASE, "live_whale_bot.py")
POLY_BOT_SCRIPT  = os.path.join(_BASE, "live_polymarket_bot.py")
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
    # V2 recovery + circuit breaker
    "orphan_recovered":     "orphan_recovered",
    "circuit_breaker":      "circuit_breaker",
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
    # POLYMARKET events
    "poly_entry":           "poly_entry",
    "poly_tp":              "poly_tp",
    "poly_sl":              "poly_sl",
}

# High-frequency / non-enum event labels that are broadcast over WebSocket
# but never persisted to bot_events:
# - whale_snapshot: whale leaderboard poll (~every 5-10 min per whale bot);
#   in neither OPEN_EVENTS nor CLOSE_EVENTS, so no trade logic reads it.
# - bounds_refreshed: emitted by live_hedge_bot_v2; not a valid
#   bot_events.event_type enum value (it would default to 'error').
_SKIP_DB_EVENTS = {"whale_snapshot", "bounds_refreshed"}


def build_start_config(cfg: BotConfig) -> dict:
    """Build the complete config dict passed to BotManager.start().

    Single source of truth shared by every bot-launch path —
    POST /bots/{id}/start (api/routers/bots.py), POST /admin/restart/{id}
    (api/routers/admin.py) and the startup auto-restart
    (api/main.py::_auto_restart_bots). A bot respawned after an API restart
    must receive exactly the same config as one started by hand (a missing
    `paper_trade` key once respawned paper bots LIVE). Do NOT fork this
    logic at a call site — extend it here.
    """
    from api.crypto import decrypt
    return {
        "nft_token_id":   cfg.nft_token_id,
        "lower_bound":    str(cfg.lower_bound),
        "upper_bound":    str(cfg.upper_bound),
        "trigger_pct":    str(cfg.trigger_pct),
        "hedge_ratio":    str(cfg.hedge_ratio),
        "hl_api_key":     decrypt(cfg.hl_api_key) if cfg.hl_api_key else "",
        "hl_wallet_addr": cfg.hl_wallet_addr or "",
        "user_address":   cfg.user_address,
        "mode":           cfg.mode,
        "pair":           cfg.pair,
        "leverage":       str(cfg.leverage   or 10),
        "sl_pct":         str(cfg.sl_pct     or 0.1),
        "tp_pct":         str(cfg.tp_pct)    if cfg.tp_pct else "",
        "trailing_stop":  "1" if cfg.trailing_stop else "0",
        "auto_rearm":     "1" if cfg.auto_rearm    else "0",
        # FURY config (only used when mode='fury')
        "fury_symbol":       cfg.fury_symbol       or "ETH",
        "fury_rsi_period":   str(cfg.fury_rsi_period   or 9),
        "fury_rsi_long_th":  str(cfg.fury_rsi_long_th  or 35),
        "fury_rsi_short_th": str(cfg.fury_rsi_short_th or 65),
        "fury_leverage_max": str(cfg.fury_leverage_max or 12),
        "fury_risk_pct":     str(cfg.fury_risk_pct     or 2.0),
        # WHALE config (only used when mode='whale')
        "whale_top_n":              str(cfg.whale_top_n          or 50),
        "whale_min_notional":       str(cfg.whale_min_notional   or 50000),
        "whale_poll_interval":      str(cfg.whale_poll_interval  or 30),
        "whale_custom_addresses":   cfg.whale_custom_addresses   or "",
        "whale_watch_assets":       cfg.whale_watch_assets       or "",
        "whale_use_websocket":      bool(cfg.whale_use_websocket),
        "whale_oi_spike_threshold": str(cfg.whale_oi_spike_threshold or 0.03),
        # POLYMARKET config (only used when mode='polymarket')
        "polymarket_token_id":    cfg.polymarket_token_id    or "",
        "polymarket_size_usd":    str(cfg.polymarket_size_usd or 0),
        "polymarket_entry_price": str(cfg.polymarket_entry_price) if cfg.polymarket_entry_price else "",
        "polymarket_tp_price":    str(cfg.polymarket_tp_price or 0),
        "polymarket_sl_price":    str(cfg.polymarket_sl_price or 0),
        "paper_trade":         bool(cfg.paper_trade),
        "engine_v2":           bool(cfg.engine_v2),
        # M2-47: from-above distance gate (user-tunable, default 5%)
        "from_above_dist_pct": str(cfg.from_above_dist_pct or 5.0),
        # M2-44: funding rate gate (Phase 2, default off)
        "use_funding_gate":    "1" if cfg.use_funding_gate else "0",
        "funding_gate_pct":    str(cfg.funding_gate_pct or 0.05),
    }


class BotManager:
    def __init__(self):
        self._procs:  dict[int, subprocess.Popen]         = {}   # config_id → process
        self._tasks:  dict[int, asyncio.Task]              = {}   # config_id → tail task
        self._subscribers: dict[int, list[asyncio.Queue]] = {}   # config_id → WS queues
        self._last_seen:   dict[int, datetime]             = {}   # config_id → last stdout ts
        # config_id → (user_address, pair, mode), cached at start() so the
        # per-event bot_trades path doesn't re-SELECT BotConfig every line
        self._cfg_meta:    dict[int, tuple]                = {}
        self._shutting_down: bool = False

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def start(self, config_id: int, config: dict):
        if config_id in self._procs:
            return  # already running

        # Cache config metadata for the per-event bot_trades path (avoids a
        # BotConfig SELECT on every [EVENT] line). Requires the caller to
        # include user_address/pair/mode in the config dict; the event path
        # falls back to a DB query when absent.
        if config.get("user_address"):
            self._cfg_meta[config_id] = (
                config["user_address"],
                config.get("pair"),
                config.get("mode", "aragan"),
            )

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
            "ENCRYPTION_KEY":     os.environ.get("ENCRYPTION_KEY", ""),
            "EMAIL_CONFIG_PATH":  os.environ.get("EMAIL_CONFIG_PATH",
                                    "/var/www/dev/trading/lp_hedge_email_config.json"),
            "EMAIL_RECIPIENTS":   os.environ.get("EMAIL_RECIPIENTS", ""),
            # SMTP credentials passed as env vars (legacy file support removed)
            "SMTP_SERVER":        os.environ.get("SMTP_SERVER", ""),
            "SMTP_PORT":          os.environ.get("SMTP_PORT", ""),
            "SMTP_USERNAME":      os.environ.get("SMTP_USERNAME", ""),
            "SMTP_PASSWORD":      os.environ.get("SMTP_PASSWORD", ""),
            "SENDER_EMAIL":       os.environ.get("SENDER_EMAIL", ""),
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
            # M2-47: from-above distance gate (user-tunable, default 5%)
            "MAX_FROM_ABOVE_DIST_PCT":     str(config.get("from_above_dist_pct", "5.0")),
            # M2-44: funding rate gate (Phase 2, default off)
            "USE_FUNDING_GATE":            str(config.get("use_funding_gate", "0")),
            "FUNDING_GATE_PCT":            str(config.get("funding_gate_pct", "0.05")),
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
        elif bot_mode == "polymarket":
            script = POLY_BOT_SCRIPT
            # hl_api_key column holds the Polygon private key (encrypted);
            # hl_wallet_addr holds the Polygon funder address
            env["POLYMARKET_PRIVATE_KEY"] = config["hl_api_key"]     or ""
            env["POLYMARKET_FUNDER"]      = config["hl_wallet_addr"] or ""
            env["POLYMARKET_TOKEN_ID"]    = str(config.get("polymarket_token_id", ""))
            env["POLYMARKET_SIZE_USD"]    = str(config.get("polymarket_size_usd", "0"))
            env["POLYMARKET_TP_PRICE"]    = str(config.get("polymarket_tp_price", "0"))
            env["POLYMARKET_SL_PRICE"]    = str(config.get("polymarket_sl_price", "0"))
            if config.get("polymarket_entry_price"):
                env["POLYMARKET_ENTRY_PRICE"] = str(config["polymarket_entry_price"])
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
                # proc.wait() is blocking — keep it off the event loop.
                await asyncio.to_thread(proc.wait, timeout=3)
            except Exception:
                try: proc.kill()
                except Exception: pass
        self._procs.clear()
        self._tasks.clear()
        self._cfg_meta.clear()
        print("[BotManager] Graceful shutdown complete", flush=True)

    async def stop(self, config_id: int):
        proc = self._procs.pop(config_id, None)
        task = self._tasks.pop(config_id, None)
        self._cfg_meta.pop(config_id, None)
        if proc:
            proc.terminate()
            try:
                # proc.wait() is blocking — keep it off the event loop.
                await asyncio.to_thread(proc.wait, timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                await asyncio.to_thread(proc.wait)
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
        # Ring buffer of recent stdout lines for crash forensics — the
        # traceback otherwise only exists as transient WS log lines.
        recent_lines: deque = deque(maxlen=20)
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
                recent_lines.append(line)

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
                self._last_seen.pop(config_id, None)
                self._cfg_meta.pop(config_id, None)
                # Poll to get actual returncode (-15=SIGTERM, -9=SIGKILL, None=undetermined)
                proc.poll()
                killed_by_signal = proc.returncode is None or proc.returncode < 0
                if not self._shutting_down and not killed_by_signal:
                    # Crash — persist the last stdout lines so the cause is
                    # recoverable from bot_events, not just the live log.
                    crash_details = {
                        "msg":        f"process exited rc={proc.returncode}",
                        "last_lines": list(recent_lines),
                    }
                    await self._write_event(config_id, "error", None, None, crash_details)
                    await self._mark_inactive(config_id)
                    await self._broadcast(config_id, {
                        "event":     "stopped",
                        "config_id": config_id,
                        "details":   crash_details,
                    })
                    print(f"[BotManager] Bot {config_id} crashed (rc={proc.returncode}), marked inactive", flush=True)
                else:
                    print(f"[BotManager] Bot {config_id} terminated (rc={proc.returncode}), active=True preserved", flush=True)

    async def _handle_event(self, config_id: int, record: dict):
        event_label = record.get("event", "")
        event_type  = _EVENT_MAP.get(event_label, "error")
        price       = record.get("price")
        pnl         = record.get("pnl")
        details     = record.get("details")

        # Unknown labels persist as 'error' — keep the original label so the
        # true event identity survives in bot_events.details.
        if event_label not in _EVENT_MAP:
            details = {**(details or {}), "event_label": event_label}

        # Noisy / non-enum events: WebSocket broadcast only, no bot_events row.
        if event_label not in _SKIP_DB_EVENTS:
            await self._write_event(config_id, event_type, price, pnl, details)
        await self._update_bot_trade(config_id, event_type, price, pnl, details)
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

    # ── Profitability dashboard hooks ───────────────────────────────────────

    async def _update_bot_trade(self, config_id: int, event_type: str,
                                price, pnl, details):
        """Mirror open/close events into bot_trades for the profitability dashboard.

        Failures are logged but never propagate — we must not break live bot
        event processing because of a dashboard insert.
        """
        try:
            await self._do_update_bot_trade(config_id, event_type, price, pnl, details)
        except Exception as e:
            print(f"[BotManager] BotTrade update error (non-fatal): {e}", flush=True)

    async def _do_update_bot_trade(self, config_id: int, event_type: str,
                                   price, pnl, details):
        from sqlalchemy import select, update
        from decimal import Decimal

        details = details or {}
        now = datetime.now(timezone.utc)

        OPEN_EVENTS = {"hedge_opened", "fury_entry", "whale_new_position", "orphan_recovered",
                       "poly_entry"}
        CLOSE_EVENTS = {"tp_hit", "sl_hit", "trailing_stop", "stopped",
                        "fury_sl", "fury_tp", "whale_closed",
                        "poly_tp", "poly_sl"}

        # Resolve config metadata from the start-time cache; fall back to a
        # DB query (e.g. bots started before the cache existed).
        meta = self._cfg_meta.get(config_id)
        if meta is None:
            async with AsyncSessionLocal() as db:
                cfg_result = await db.execute(
                    select(BotConfig.user_address, BotConfig.pair, BotConfig.mode)
                    .where(BotConfig.id == config_id)
                )
                cfg = cfg_result.one_or_none()
                if cfg is None:
                    return
                meta = (cfg.user_address, cfg.pair, cfg.mode)
            self._cfg_meta[config_id] = meta
        user_address, pair, mode = meta

        async with AsyncSessionLocal() as db:
            if event_type in OPEN_EVENTS:
                # Compute side and size from event details.
                side = details.get("side")
                size_usd = details.get("notional") or details.get("size_usd")
                entry_price = details.get("entry") or price

                if mode in ("aragan", "avaro") and not side:
                    side = "short"

                db.add(BotTrade(
                    config_id=config_id,
                    user_address=user_address,
                    mode=mode,
                    pair=pair,
                    side=side,
                    entry_price=entry_price,
                    size_usd=size_usd,
                    opened_at=now,
                ))
                await db.commit()
                return

            if event_type in CLOSE_EVENTS:
                # Try to close the most recent open trade for this config.
                open_trade_result = await db.execute(
                    select(BotTrade)
                    .where(BotTrade.config_id == config_id)
                    .where(BotTrade.closed_at.is_(None))
                    .order_by(BotTrade.opened_at.desc())
                    .limit(1)
                )
                trade = open_trade_result.scalar_one_or_none()

                # Normalize PnL: FURY/WHALE already emit USD; LP bots emit %.
                realized_pnl_usd = None
                if pnl is not None:
                    try:
                        pnl_val = Decimal(str(pnl))
                        if mode in ("aragan", "avaro"):
                            # pnl is a percentage; convert using notional if known.
                            size = Decimal(str(trade.size_usd)) if trade and trade.size_usd else None
                            if size:
                                realized_pnl_usd = size * pnl_val / Decimal("100")
                        else:
                            realized_pnl_usd = pnl_val
                    except Exception:
                        pass

                fees_usd = details.get("fees_usd")
                funding_usd = details.get("funding_usdc_net")
                il_offset_usd = details.get("lp_value_close")  # placeholder

                if trade is not None:
                    upd = {
                        "exit_price": price,
                        "realized_pnl_usd": realized_pnl_usd,
                        "fees_usd": fees_usd,
                        "funding_usd": funding_usd,
                        "il_offset_usd": il_offset_usd,
                        "exit_reason": event_type,
                        "closed_at": now,
                    }
                    # Compute net_pnl if we have enough data.
                    try:
                        r = Decimal(str(realized_pnl_usd or 0))
                        f = Decimal(str(fees_usd or 0))
                        fund = Decimal(str(funding_usd or 0))
                        il = Decimal(str(il_offset_usd or 0))
                        trade.net_pnl_usd = r - f - fund + il
                    except Exception:
                        pass
                    for key, value in upd.items():
                        setattr(trade, key, value)
                    await db.commit()
                else:
                    # No matching open trade — record a closed-only estimate only if
                    # it carries enough data to be useful.
                    if mode == "whale":
                        # Whale tracker is read-only leaderboard; closed-only rows
                        # cannot be matched to a real system round-trip.
                        return
                    if event_type == "stopped" and not any([price, realized_pnl_usd, fees_usd, funding_usd]):
                        # LP bot stopped without any fill data — pure noise.
                        return

                    db.add(BotTrade(
                        config_id=config_id,
                        user_address=user_address,
                        mode=mode,
                        pair=pair,
                        exit_price=price,
                        realized_pnl_usd=realized_pnl_usd,
                        fees_usd=fees_usd,
                        funding_usd=funding_usd,
                        il_offset_usd=il_offset_usd,
                        exit_reason=event_type,
                        is_estimate=True,
                        closed_at=now,
                    ))
                    await db.commit()

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
        # Blocking smtplib work — keep it off the event loop.
        await asyncio.to_thread(self._send_admin_lp_gone_email, config_id, event_type, details)

    def _send_admin_lp_gone_email(self, config_id: int, event_type: str, details: Optional[dict]):
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        try:
            cfg = load_email_config()
            if not cfg:
                return
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
            s = smtplib.SMTP(cfg["smtp_server"], cfg["smtp_port"], timeout=15)
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
