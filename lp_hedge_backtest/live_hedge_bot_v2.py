"""
VIZNIAGO — Bot Defensor Bajista V2
LP + Directional Bear Hedge Bot

V2 additions over V1:
  - Native HL trigger (stop-market) SL order placed immediately when SHORT opens.
    If the bot process crashes, HL fires the SL automatically — no orphan risk.
  - Cancel + replace native SL on every trailing-stop move.
  - Startup reconciliation: detects orphan SHORTs from prior crashes, recovers
    state and places a native SL if none exists.
  - Graceful degradation: if native SL placement/replace fails, code-evaluated
    SL remains active and a warning event is logged.
  - LP→DB deactivation: emits lp_removed/lp_burned events that bot_manager
    picks up to set active=False and notify admin.

All V1 env var interface is preserved — V2 is a drop-in replacement.
"""

import math
import os
import sys
import time
import json
import smtplib
from collections import deque
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from web3 import Web3
from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

# ── Required ──────────────────────────────────────────────────────────────────
HL_SECRET_KEY = os.getenv("HYPERLIQUID_SECRET_KEY")
HL_ADDRESS    = os.getenv("HYPERLIQUID_ACCOUNT_ADDRESS")

if not HL_SECRET_KEY or not HL_ADDRESS:
    print("❌ HYPERLIQUID_SECRET_KEY and HYPERLIQUID_ACCOUNT_ADDRESS are required.", flush=True)
    sys.exit(1)

# ── Optional with defaults ─────────────────────────────────────────────────────
RPC_URL          = os.getenv("ARBITRUM_RPC_URL",        "https://arb1.arbitrum.io/rpc")
NFT_ID           = int(os.getenv("UNISWAP_NFT_ID",      "5364087"))
CHECK_INTERVAL   = int(os.getenv("CHECK_INTERVAL",        "30"))
CONFIG_ID        = os.getenv("CONFIG_ID")
BOUNDS_REFRESH_H = int(os.getenv("BOUNDS_REFRESH_HOURS", "4"))

# M1: WebSocket price feed — HL pushes allMids sub-second; the 30s REST poll
# becomes the fallback when the WS goes stale. USE_WS_PRICE=0 reverts fully.
USE_WS_PRICE  = os.getenv("USE_WS_PRICE", "1").strip() not in ("0", "false", "False")
WS_TICK_SECS  = int(os.getenv("WS_TICK_SECS", "3"))   # loop cadence while WS is fresh
WS_STALE_SECS = 15.0                                   # WS older than this → REST fallback

# M2: max slippage for market entries — old 1% was wider than the SL distance
MAX_SLIPPAGE  = float(os.getenv("MAX_SLIPPAGE_PCT", "0.3")) / 100.0

# M7: trail-state persistence — restarts used to reset breakeven/trail to entry
# (59 orphan recoveries vs 15 clean starts). State is saved on every change and
# restored at recovery when it matches the live HL position.
STATE_DIR = os.getenv(
    "BOT_STATE_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_state"),
)

# Entry
TRIGGER_OFFSET = float(os.getenv("TRIGGER_OFFSET_PCT", "0.5")) / 100.0
UPPER_BUFFER   = TRIGGER_OFFSET

# Sizing
HEDGE_RATIO    = float(os.getenv("HEDGE_RATIO",     "50.0"))
TARGET_LEVERAGE = int(os.getenv("TARGET_LEVERAGE",  "10"))
MAX_LEVERAGE   = 15
MARGIN_BUFFER  = float(os.getenv("MARGIN_BUFFER",   "1.5"))

# SL / trail — no silent floor
DEFAULT_SL_PCT = float(os.getenv("SL_PCT",         "0.5")) / 100.0
BREAKEVEN_PCT  = float(os.getenv("BREAKEVEN_PCT",   "1.0")) / 100.0
TRAIL_PCT      = float(os.getenv("TRAIL_PCT",       "1.5")) / 100.0

# M2-49: ATR-adaptive breakeven — effective BE = max(BREAKEVEN_PCT, ATR_MULT_BE × ATR(ATR_PERIOD))
ATR_PERIOD   = int(os.getenv("ATR_PERIOD",   "14"))
ATR_MULT_BE  = float(os.getenv("ATR_MULT_BE", "1.5"))
# M2-47: from_above distance gate — skip entry if price is more than X% below upper_bound
MAX_FROM_ABOVE_DIST_PCT = float(os.getenv("MAX_FROM_ABOVE_DIST_PCT", "5.0"))
# M2-44: funding rate awareness — Phase 1 (log) + Phase 2 (optional gate)
USE_FUNDING_GATE = os.getenv("USE_FUNDING_GATE", "0").strip() not in ("0", "false", "False")
FUNDING_GATE_PCT = float(os.getenv("FUNDING_GATE_PCT", "0.05"))  # block entry when rate < -X%/1h
REENTRY_BUFFER = float(os.getenv("REENTRY_BUFFER_PCT", "0.5")) / 100.0

_tp_env  = os.getenv("TP_PCT", "").strip()
TP_PCT   = float(_tp_env) / 100.0 if _tp_env else None

TRAILING_STOP = os.getenv("TRAILING_STOP", "1").strip() not in ("0", "false", "False")
AUTO_REARM    = os.getenv("AUTO_REARM",    "1").strip() not in ("0", "false", "False")

# M2-13: mode enforcement — aragan (Bajista) = below_range trigger only
#         avaro (Alcista) = both triggers (from_above + below_range)
BOT_MODE           = os.getenv("BOT_MODE", "avaro").strip().lower()
FROM_ABOVE_ENABLED = BOT_MODE != "aragan"

MIN_HEDGE_ETH    = 0.001
MIN_NOTIONAL_USD = 10.0
HL_SYNC_INTERVAL = 300

# ── Email ──────────────────────────────────────────────────────────────────────
EMAIL_CONFIG_PATH = os.getenv("EMAIL_CONFIG_PATH", "/var/www/dev/trading/email_config.json")
_recipients_env   = os.getenv("EMAIL_RECIPIENTS", "")
RECIPIENTS = (
    [r.strip() for r in _recipients_env.split(",") if r.strip()]
    or ["perdomo.gustavo@gmail.com"]
)

# ── Uniswap v3 Position Manager ABI (minimal) ─────────────────────────────────
V3_POS_MANAGER = "0xC36442b4a4522E871399CD717aBDD847Ab11FE88"
V3_ABI = [
    {"inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
     "name": "positions", "outputs": [
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
    ], "stateMutability": "view", "type": "function"}
]


def tick_to_price(tick):
    return (1.0001 ** tick) * (10 ** 12)


def calc_x_max_eth(liquidity, tick_lower, tick_upper):
    if liquidity == 0:
        return 0.0
    sqrt_pa = math.sqrt(1.0001 ** tick_lower)
    sqrt_pb = math.sqrt(1.0001 ** tick_upper)
    return liquidity * (1.0 / sqrt_pa - 1.0 / sqrt_pb) / 1e18


def calc_lp_value_usdc(liquidity, tick_lower, tick_upper, price_usdc):
    """M2-43: LP position value in USDC at given ETH price.
    ETH=token0 (1e18 decimals), USDC=token1 (1e6 decimals).
    P_raw = price_usdc / 1e12 adjusts for the decimal difference.
    """
    if liquidity == 0 or price_usdc <= 0:
        return 0.0
    sqrt_pa = math.sqrt(1.0001 ** tick_lower)
    sqrt_pb = math.sqrt(1.0001 ** tick_upper)
    sqrt_p  = math.sqrt(price_usdc / 1e12)
    if sqrt_p <= sqrt_pa:
        x_eth  = liquidity * (1 / sqrt_pa - 1 / sqrt_pb) / 1e18
        return x_eth * price_usdc
    elif sqrt_p >= sqrt_pb:
        return liquidity * (sqrt_pb - sqrt_pa) / 1e6
    else:
        x_eth  = liquidity * (1 / sqrt_p  - 1 / sqrt_pb) / 1e18
        y_usdc = liquidity * (sqrt_p - sqrt_pa) / 1e6
        return x_eth * price_usdc + y_usdc


def log_event(event_type: str, price: float = None, pnl: float = None, details: dict = None):
    record = {"event": event_type}
    if price   is not None: record["price"]   = round(price, 4)
    if pnl     is not None: record["pnl"]     = round(pnl, 4)
    if details is not None: record["details"] = details
    if CONFIG_ID:            record["config_id"] = CONFIG_ID
    print(f"[EVENT] {json.dumps(record)}", flush=True)


class LiveHedgeBotV2:
    def __init__(self):
        print(f"⚙️  [V2] Initializing VIZNIAGO Defensor Bajista V2 | NFT #{NFT_ID}", flush=True)
        self.w3       = Web3(Web3.HTTPProvider(RPC_URL))
        self.contract = self.w3.eth.contract(address=V3_POS_MANAGER, abi=V3_ABI)
        self.info     = Info(constants.MAINNET_API_URL, skip_ws=not USE_WS_PRICE)
        self.exchange = Exchange(
            Account.from_key(HL_SECRET_KEY),
            constants.MAINNET_API_URL,
            account_address=HL_ADDRESS,
        )

        # M1: WS-pushed price (updated by callback thread; read by main loop)
        self._ws_price: Optional[float] = None
        self._ws_price_ts: float        = 0.0
        self._last_status_print: float  = 0.0
        if USE_WS_PRICE:
            try:
                self.info.subscribe({"type": "allMids"}, self._on_mids)
                print("📡 [M1] WS allMids subscription active — REST poll is fallback", flush=True)
            except Exception as e:
                print(f"⚠️  [M1] WS subscribe failed ({e}) — REST polling only", flush=True)

        # ── LP position ────────────────────────────────────────────────────
        self.lower_bound       = None
        self.upper_bound       = None
        self.tick_lower        = None
        self.tick_upper        = None
        self.liquidity         = None
        self.last_bounds_fetch = 0.0

        # ── Short state ────────────────────────────────────────────────────
        self.hedge_active      = False
        self.entry_price       = None
        self.hedge_size_eth    = None
        self.leverage_used     = None
        self.open_time         = None   # M2-44: wall-clock timestamp when hedge opened
        self.current_sl_price  = None
        self.breakeven_reached        = False
        self.short_min_price          = None
        self.open_trigger             = None
        self._effective_breakeven_pct = BREAKEVEN_PCT  # M2-49: set per-trade at open_hedge()

        # V2: native HL order tracking
        self.hl_sl_order_id: Optional[int] = None
        self.hl_tp_order_id: Optional[int] = None

        # ── Direction tracking ─────────────────────────────────────────────
        self.price_was_above   = False

        # ── Re-entry guard ─────────────────────────────────────────────────
        # sl_close_price: price when last short closed — M2-23 re-arm check
        self.reentry_guard_price = None
        self.sl_close_price      = None

        # ── Margin failure guard ────────────────────────────────────────────
        self._margin_fail_count    = 0
        self._margin_backoff_until = 0.0

        # ── M2-39: Circuit breaker ──────────────────────────────────────────
        self._consecutive_stops      = 0
        self._circuit_breaker_until  = 0.0
        self._stop_timestamps        = deque()   # rolling window (rate trigger)
        self._cb_fire_times          = deque()   # escalation history

        # ── M2-39C: Daily loss cap ───────────────────────────────────────────
        self._session_loss_usd       = 0.0
        self._session_date           = datetime.now(timezone.utc).date()

        # ── M2-40: Cooldown post external_close ─────────────────────────────
        self._ext_close_cooldown_until = 0.0

        # ── Position sync ─────────────────────────────────────────────────────
        self.last_hl_sync = 0.0
        self.last_lp_sync = 0.0

        # M7: trail-state file (one per config; NFT id when standalone)
        self._state_path = os.path.join(
            STATE_DIR, f"hedge_state_{CONFIG_ID or NFT_ID}.json"
        )

        self.email_config = self._load_email_config()

    # ── Email ──────────────────────────────────────────────────────────────────

    def _load_email_config(self):
        try:
            with open(EMAIL_CONFIG_PATH) as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️  Could not load email config: {e}", flush=True)
            return None

    def send_email(self, subject, body):
        if not self.email_config:
            return
        try:
            msg = MIMEMultipart()
            msg["From"]    = self.email_config["sender_email"]
            msg["To"]      = ", ".join(RECIPIENTS)
            msg["Subject"] = f"🛡️ [VIZNIAGO V2 Defensor] {subject}"
            msg.attach(MIMEText(body, "plain"))
            s = smtplib.SMTP(self.email_config["smtp_server"], self.email_config["smtp_port"])
            s.starttls()
            s.login(self.email_config["smtp_username"], self.email_config["smtp_password"])
            s.send_message(msg)
            s.quit()
        except Exception as e:
            print(f"❌ Email failed: {e}", flush=True)

    # ── On-chain ───────────────────────────────────────────────────────────────

    def fetch_position_bounds(self, fatal: bool = False, retries: int = 3) -> bool:
        """Fetch LP range/liquidity from the Uniswap position NFT.

        H3: retries with backoff on RPC errors. Only exits the process when
        fatal=True (initial startup, where no previous bounds exist). On the
        periodic in-loop refresh a failure keeps the previous bounds — a
        transient Arbitrum RPC blip used to sys.exit(1), which bot_manager
        treated as a crash and set active=False, silently disabling protection.
        """
        last_err = None
        for attempt in range(1, retries + 1):
            try:
                pos = self.contract.functions.positions(NFT_ID).call()
                self.tick_lower        = pos[5]
                self.tick_upper        = pos[6]
                self.liquidity         = pos[7]
                self.lower_bound       = tick_to_price(self.tick_lower)
                self.upper_bound       = tick_to_price(self.tick_upper)
                self.last_bounds_fetch = time.time()
                x_max = calc_x_max_eth(self.liquidity, self.tick_lower, self.tick_upper)
                print(f"✅ Range: ${self.lower_bound:.2f} — ${self.upper_bound:.2f} | "
                      f"Liquidity: {self.liquidity} | X_max: {x_max:.4f} ETH", flush=True)
                return True
            except Exception as e:
                last_err = e
                print(f"❌ Error fetching position (attempt {attempt}/{retries}): {e}", flush=True)
                if attempt < retries:
                    time.sleep(5 * attempt)

        if fatal:
            print(f"❌ Could not fetch LP position at startup after {retries} attempts — exiting.", flush=True)
            sys.exit(1)

        # In-loop refresh failed — keep previous bounds, retry in 10 min
        self.last_bounds_fetch = time.time() - BOUNDS_REFRESH_H * 3600 + 600
        print(f"⚠️  [H3] Bounds refresh failed after {retries} attempts — keeping previous range, retry in 10 min", flush=True)
        log_event("error", details={
            "warning": f"[H3] Bounds refresh failed ({last_err}) — keeping previous range",
        })
        return False

    def _on_mids(self, msg):
        """M1: WS callback (runs on the SDK's websocket thread)."""
        try:
            mid = msg.get("data", {}).get("mids", {}).get("ETH")
            if mid:
                self._ws_price    = float(mid)
                self._ws_price_ts = time.monotonic()
        except Exception:
            pass

    def _ws_fresh(self) -> bool:
        return (USE_WS_PRICE and self._ws_price is not None
                and (time.monotonic() - self._ws_price_ts) < WS_STALE_SECS)

    def get_eth_price(self):
        # M1: prefer the WS-pushed mid; REST only when the WS is stale/down
        if self._ws_fresh():
            return self._ws_price
        try:
            return float(self.info.all_mids()["ETH"])
        except Exception:
            return None

    def get_hl_margin_balance(self):
        try:
            state = self.info.user_state(HL_ADDRESS)
            perp_balance = float(state["marginSummary"]["accountValue"])
            spot_usdc = 0.0
            try:
                spot_state = self.info.spot_user_state(HL_ADDRESS)
                for bal in spot_state.get("balances", []):
                    if bal["coin"] == "USDC":
                        spot_usdc = float(bal["total"])
                        break
            except Exception:
                pass
            total = perp_balance + spot_usdc
            if spot_usdc > 0:
                print(f"💰 HL balance: ${perp_balance:.2f} perp + ${spot_usdc:.2f} spot = ${total:.2f}", flush=True)
            return total
        except Exception as e:
            print(f"⚠️  Could not fetch HL margin: {e}", flush=True)
            return 0.0

    # ── V2: Native SL order management ────────────────────────────────────────

    def _place_native_sl(self, sl_price: float, size: float) -> Optional[int]:
        """
        Place a native HL stop-market trigger order as SL.
        Returns the oid (order ID) on success, None on failure.
        Failure is non-fatal — code-evaluated SL remains active.
        """
        try:
            # grouping="na" + tpsl="sl" = standalone trigger stop (manageable, returns OID).
            # tpsl="" → HTTP 422. normalTpsl → "Main order cannot be trigger order."
            # positionTpsl → "waitingForTrigger" with no usable OID (can't cancel/replace).
            # HL ETH trigger prices must be whole-dollar increments at this price range.
            trigger_px = round(sl_price)          # nearest $1
            limit_px   = round(sl_price * 1.03)   # 3% above trigger, $1 granularity
            order_req = {
                "coin":       "ETH",
                "is_buy":     True,        # buy back = close SHORT
                "sz":         size,
                "limit_px":   float(limit_px),
                "order_type": {
                    "trigger": {
                        "triggerPx": float(trigger_px),
                        "isMarket":  True,
                        "tpsl":      "sl",
                    }
                },
                "reduce_only": True,
            }
            result = self.exchange.bulk_orders([order_req], grouping="na")
            # Log full raw response for debugging on any failure
            if not result:
                print(f"⚠️  [V2] Native SL placement: None response from exchange", flush=True)
                return None

            if result.get("status") != "ok":
                print(f"⚠️  [V2] Native SL placement top-level error: {result}", flush=True)
                return None

            statuses = result.get("response", {}).get("data", {}).get("statuses", [])
            if not statuses:
                print(f"⚠️  [V2] Native SL placement: empty statuses — full response: {result}", flush=True)
                return None

            s0 = statuses[0]
            if "resting" in s0:
                oid = s0["resting"]["oid"]
                print(f"🛡️  [V2] Native SL placed | OID {oid} | trigger ${sl_price:.2f} | limit ${limit_px:.2f}", flush=True)
                return oid
            if "filled" in s0:
                # Triggered immediately — position likely already closed
                print(f"⚠️  [V2] Native SL filled immediately @ ${sl_price:.2f} — position may be gone", flush=True)
                return None
            if "error" in s0:
                print(f"⚠️  [V2] Native SL order rejected by HL: '{s0['error']}' — full: {result}", flush=True)
                return None

            print(f"⚠️  [V2] Native SL unexpected status: {s0} — full: {result}", flush=True)
            return None
        except Exception as e:
            print(f"⚠️  [V2] Native SL placement exception: {e}", flush=True)
            return None

    def _cancel_native_sl(self) -> bool:
        """
        Cancel the current native SL order.
        Returns True if cancelled or no order was active.
        Returns False if cancel failed (keep old order, don't place replacement).
        """
        if self.hl_sl_order_id is None:
            return True
        try:
            result = self.exchange.cancel("ETH", self.hl_sl_order_id)
            if result and result.get("status") == "ok":
                print(f"🗑️  [V2] Native SL cancelled | OID {self.hl_sl_order_id}", flush=True)
                self.hl_sl_order_id = None
                return True
            # Order may have already been filled/cancelled externally
            err_msg = str(result)
            if "order not found" in err_msg.lower() or "no order" in err_msg.lower():
                print(f"ℹ️  [V2] Native SL OID {self.hl_sl_order_id} already gone (external fill?)", flush=True)
                self.hl_sl_order_id = None
                return True
            print(f"⚠️  [V2] Native SL cancel failed: {result}", flush=True)
            return False
        except Exception as e:
            print(f"⚠️  [V2] Native SL cancel exception: {e}", flush=True)
            return False

    def _place_native_tp(self, tp_price: float, size: float) -> Optional[int]:
        """
        Place a native HL take-profit trigger order.
        For a SHORT, TP fires when price drops to tp_price — buy back at a discount.
        Returns the oid on success, None on failure (graceful degradation).
        """
        try:
            trigger_px = round(tp_price)
            limit_px   = round(tp_price * 0.97)   # 3% below trigger — fill at better price
            order_req = {
                "coin":       "ETH",
                "is_buy":     True,
                "sz":         size,
                "limit_px":   float(limit_px),
                "order_type": {
                    "trigger": {
                        "triggerPx": float(trigger_px),
                        "isMarket":  True,
                        "tpsl":      "tp",
                    }
                },
                "reduce_only": True,
            }
            result = self.exchange.bulk_orders([order_req], grouping="na")
            if not result:
                print(f"⚠️  [V2] Native TP placement: None response from exchange", flush=True)
                return None

            if result.get("status") != "ok":
                print(f"⚠️  [V2] Native TP placement top-level error: {result}", flush=True)
                return None

            statuses = result.get("response", {}).get("data", {}).get("statuses", [])
            if not statuses:
                print(f"⚠️  [V2] Native TP placement: empty statuses — full response: {result}", flush=True)
                return None

            s0 = statuses[0]
            if "resting" in s0:
                oid = s0["resting"]["oid"]
                print(f"🎯 [V2] Native TP placed | OID {oid} | trigger ${tp_price:.2f} | limit ${limit_px:.2f}", flush=True)
                return oid
            if "filled" in s0:
                print(f"⚠️  [V2] Native TP filled immediately @ ${tp_price:.2f} — position may be gone", flush=True)
                return None
            if "error" in s0:
                print(f"⚠️  [V2] Native TP order rejected by HL: '{s0['error']}' — full: {result}", flush=True)
                return None

            print(f"⚠️  [V2] Native TP unexpected status: {s0} — full: {result}", flush=True)
            return None
        except Exception as e:
            print(f"⚠️  [V2] Native TP placement exception: {e}", flush=True)
            return None

    def _cancel_native_tp(self) -> bool:
        """Cancel the current native TP order. Returns True if cancelled or no order was active."""
        if self.hl_tp_order_id is None:
            return True
        try:
            result = self.exchange.cancel("ETH", self.hl_tp_order_id)
            if result and result.get("status") == "ok":
                print(f"🗑️  [V2] Native TP cancelled | OID {self.hl_tp_order_id}", flush=True)
                self.hl_tp_order_id = None
                return True
            err_msg = str(result)
            if "order not found" in err_msg.lower() or "no order" in err_msg.lower():
                print(f"ℹ️  [V2] Native TP OID {self.hl_tp_order_id} already gone (external fill?)", flush=True)
                self.hl_tp_order_id = None
                return True
            print(f"⚠️  [V2] Native TP cancel failed: {result}", flush=True)
            return False
        except Exception as e:
            print(f"⚠️  [V2] Native TP cancel exception: {e}", flush=True)
            return False

    def _replace_native_sl(self, new_sl_price: float) -> bool:
        """
        Cancel existing SL and place a new one at new_sl_price.
        If cancel fails, keeps old order (safe — it's more conservative).
        Returns True if replacement succeeded.
        """
        if not self._cancel_native_sl():
            # Cancel failed — old order still active. Keep it; don't place duplicate.
            log_event("error", details={
                "warning": f"[V2] Native SL cancel failed during trail — old order still active",
                "old_oid": self.hl_sl_order_id,
            })
            return False

        oid = self._place_native_sl(new_sl_price, self.hedge_size_eth)
        if oid:
            self.hl_sl_order_id = oid
            return True

        # Placement failed after successful cancel — code-evaluated SL only now
        log_event("error", details={
            "warning": f"[V2] Native SL replacement failed at ${new_sl_price:.2f} — code-evaluated only",
        })
        return False

    # ── Position sizing ────────────────────────────────────────────────────────

    _MAX_MARGIN_FAILURES  = 5
    _MARGIN_BACKOFF_SECS  = 300

    # M2-39: circuit breaker — consecutive streak trigger
    _CB_STOP_THRESHOLD    = 3     # consecutive stops before pause
    _CB_PAUSE_STEPS       = [1200, 3600, 14400]  # 20m → 1h → 4h (escalating)
    _CB_ESCALATION_WINDOW = 14400  # 4 h — window to count prior CB fires for escalation

    # M2-39B: rolling-window rate trigger (independent of streak)
    _CB_RATE_THRESHOLD    = 5     # stops in rolling window → pause
    _CB_RATE_WINDOW_SECS  = 1800  # 30-minute window
    _CB_RATE_PAUSE_SECS   = 3600  # 1-hour pause when rate trigger fires

    # M2-39C / H2: daily loss cap — pause rest of UTC day when net loss exceeds it.
    # Dynamic by default: 3× the expected single-stop loss at current sizing
    # (the old flat -$5 was below ONE real stop at 1.5% SL × ~$1k notional,
    # so a single close ended the trading day and left the LP unhedged).
    # Env DAILY_LOSS_CAP_USD overrides with a fixed value; floor is $5.
    _DAILY_CAP_STOPS      = float(os.getenv("DAILY_LOSS_CAP_STOPS", "3"))
    _env_cap              = os.getenv("DAILY_LOSS_CAP_USD", "").strip()
    _DAILY_LOSS_CAP_FIXED = -abs(float(_env_cap)) if _env_cap else None  # None → dynamic

    # M2-40: cooldown after native SL fires between polls (external_close)
    _EXT_COOLDOWN_SECS    = 300   # 5 minutes

    def _calc_order_params(self, price):
        x_max = calc_x_max_eth(self.liquidity, self.tick_lower, self.tick_upper)
        if x_max < MIN_HEDGE_ETH:
            print(f"⚠️  X_max {x_max:.4f} ETH below minimum — skipping", flush=True)
            return None

        size     = round(x_max * HEDGE_RATIO / 100.0, 4)
        size     = max(size, MIN_HEDGE_ETH)
        size     = round(min(size, x_max), 4)
        margin   = self.get_hl_margin_balance()
        notional = size * price

        if notional < MIN_NOTIONAL_USD:
            print(f"⚠️  Notional ${notional:.2f} below HL min ${MIN_NOTIONAL_USD:.0f} — skipping", flush=True)
            self.send_email(
                "⚠️ Short SKIPPED — LP Too Small",
                f"NFT #{NFT_ID}: hedge notional ${notional:.2f} < HL minimum ${MIN_NOTIONAL_USD:.0f}.\n"
                f"x_max={x_max:.4f} ETH | ratio={HEDGE_RATIO}% | price=${price:,.2f}\n"
                f"Add more liquidity to enable protection.",
            )
            return None

        if margin <= 0:
            print("❌ HL account has no margin", flush=True)
            self.send_email("⚠️ Short SKIPPED — No Margin",
                f"NFT #{NFT_ID}: HL wallet has no USDC balance.")
            return None

        target_lev = min(TARGET_LEVERAGE, MAX_LEVERAGE)
        leverage   = target_lev
        required_margin = notional / leverage

        if margin < required_margin * MARGIN_BUFFER:
            reduced = False
            for lev in range(leverage + 1, MAX_LEVERAGE + 1):
                req = notional / lev
                if margin >= req * MARGIN_BUFFER:
                    log_event("error", details={
                        "warning": f"Leverage auto-increased {target_lev}x→{lev}x (margin ${margin:.2f})"
                    })
                    leverage        = lev
                    required_margin = req
                    reduced         = True
                    break
            if not reduced:
                print(f"❌ Insufficient margin at {MAX_LEVERAGE}x", flush=True)
                self.send_email("⚠️ Short SKIPPED — Low Margin",
                    f"NFT #{NFT_ID}: not enough USDC at {MAX_LEVERAGE}x.\n"
                    f"Available: ${margin:.2f} | Notional: ${notional:.2f}")
                return None

        return size, leverage, notional, required_margin, x_max

    # ── Short open ─────────────────────────────────────────────────────────────

    def open_hedge(self, price, trigger):
        if time.time() < self._margin_backoff_until:
            remaining = int(self._margin_backoff_until - time.time())
            print(f"⏸️  Margin backoff active — {remaining}s remaining", flush=True)
            return

        label = "FROM ABOVE" if trigger == "from_above" else "BELOW RANGE"
        print(f"🚨 SHORT TRIGGERED ({label}): ETH ${price:.2f}", flush=True)
        try:
            params = self._calc_order_params(price)
            if params is None:
                self._margin_fail_count += 1
                log_event("error", price=price, details={
                    "msg": "Sizing/margin check failed",
                    "consecutive_failures": self._margin_fail_count,
                })
                if self._margin_fail_count >= self._MAX_MARGIN_FAILURES:
                    self._margin_backoff_until = time.time() + self._MARGIN_BACKOFF_SECS
                    self._margin_fail_count    = 0
                    log_event("error", price=price, details={
                        "msg": f"Margin check failed {self._MAX_MARGIN_FAILURES}x — pausing {self._MARGIN_BACKOFF_SECS}s"
                    })
                    self.send_email("⚠️ Bot Paused — Repeated Margin Failures",
                        f"NFT #{NFT_ID}: margin check failed {self._MAX_MARGIN_FAILURES}x. "
                        f"Paused {self._MARGIN_BACKOFF_SECS // 60} min. Fund the HL wallet to resume.")
                return

            size, leverage, notional, req_margin, x_max = params
            print(f"📐 Size: {size:.4f} ETH | Leverage: {leverage}x | "
                  f"Notional: ${notional:.2f} | Margin: ${req_margin:.2f}", flush=True)

            # M2-44: fetch funding rate; Phase 2 gate blocks entry if rate is too negative
            funding_rate = self._fetch_funding_rate()
            if funding_rate is not None:
                fr_pct = funding_rate * 100
                marker = "✓ favorable" if funding_rate >= 0 else f"⚠ cost ({fr_pct:.4f}%/1h)"
                print(f"💸 [M2-44] Funding rate: {fr_pct:.4f}%/1h — {marker}", flush=True)
            if USE_FUNDING_GATE and funding_rate is not None:
                if funding_rate < -(FUNDING_GATE_PCT / 100):
                    print(f"⏭️  [M2-44] Funding gate blocked — rate {funding_rate*100:.4f}%/1h "
                          f"< threshold -{FUNDING_GATE_PCT:.4f}%", flush=True)
                    log_event("stopped", price=price, details={
                        "reason":           "funding_gate",
                        "funding_rate_1h":  round(funding_rate * 100, 5),
                        "gate_threshold":   FUNDING_GATE_PCT,
                    })
                    return

            self.exchange.update_leverage(leverage, "ETH")

            # M2: 0.3% slippage cap (was 1% — wider than the SL distance) with one
            # re-quote retry; market_open re-fetches the current mid on each call.
            # Top-level status "ok" does NOT mean filled — must check statuses[0].
            order  = None
            filled = {}
            for attempt in (1, 2):
                order = self.exchange.market_open("ETH", False, size, slippage=MAX_SLIPPAGE)
                if order is None:
                    break
                if order.get("status") == "ok":
                    statuses = order.get("response", {}).get("data", {}).get("statuses", [{}])
                    first    = statuses[0] if statuses else {}
                    filled   = first.get("filled", {})
                    if filled.get("oid"):
                        break
                    print(f"⚠️  [M2] Entry attempt {attempt}/2 not filled within "
                          f"{MAX_SLIPPAGE*100:.2f}% slippage: {first}", flush=True)
                else:
                    print(f"⚠️  [M2] Entry attempt {attempt}/2 rejected: {order}", flush=True)

            if order is None:
                print(f"❌ market_open returned None", flush=True)
                log_event("error", price=price, details={
                    "msg": "market_open returned None — verify HL agent wallet is approved"
                })
                return

            if filled.get("oid"):
                # M2: anchor entry/SL on the ACTUAL fill price, not the poll price
                fill_px = float(filled.get("avgPx", price) or price)
                self._margin_fail_count    = 0
                self._margin_backoff_until = 0.0
                self.entry_price              = fill_px
                self.hedge_size_eth           = size
                self.leverage_used            = leverage
                self.hedge_active             = True
                self.breakeven_reached        = False
                self.short_min_price          = fill_px
                self.open_trigger             = trigger
                self.current_sl_price         = fill_px * (1 + DEFAULT_SL_PCT)
                self._effective_breakeven_pct = self._compute_atr_breakeven(fill_px)  # M2-49
                self.open_time                = time.time()                            # M2-44

                print(f"✅ SHORT OPENED | Entry: ${self.entry_price:.2f} | "
                      f"SL: ${self.current_sl_price:.2f} | Trigger: {label}", flush=True)

                # V2: place native SL — small delay lets HL settle the fill before SL request
                time.sleep(1)
                oid = self._place_native_sl(self.current_sl_price, size)
                if oid:
                    self.hl_sl_order_id = oid
                else:
                    log_event("error", price=price, details={
                        "warning": "[V2] Native SL placement failed at open — code-evaluated SL active",
                        "sl": round(self.current_sl_price, 4),
                    })
                    self.send_email(
                        "⚠️ [V2] Native SL Placement Failed at Open",
                        f"NFT #{NFT_ID}: SHORT opened but native SL could not be placed on HL.\n"
                        f"Code-evaluated SL active at ${self.current_sl_price:.2f}.\n"
                        f"If the bot crashes, this SHORT has no native HL protection until restart.",
                    )

                # V2: place native TP if configured
                if TP_PCT is not None:
                    tp_price = self.entry_price * (1 - TP_PCT)
                    tp_oid = self._place_native_tp(tp_price, size)
                    if tp_oid:
                        self.hl_tp_order_id = tp_oid
                    else:
                        log_event("error", price=price, details={
                            "warning": "[V2] Native TP placement failed at open — code-evaluated TP active",
                            "tp": round(tp_price, 4),
                        })

                self._save_trail_state()  # M7

                log_event("hedge_opened", price=price, details={
                    "trigger":      trigger,
                    "entry":        self.entry_price,
                    "sl":           round(self.current_sl_price, 4),
                    "sl_oid":       self.hl_sl_order_id,
                    "tp_oid":       self.hl_tp_order_id,
                    "size_eth":     size,
                    "x_max":        round(x_max, 4),
                    "ratio_pct":    HEDGE_RATIO,
                    "leverage":     leverage,
                    "notional":     round(notional, 2),
                    "margin":       round(req_margin, 2),
                    "engine":       "v2",
                    "breakeven_pct":    round(self._effective_breakeven_pct * 100, 2),  # M2-49
                    "funding_rate_1h":  round(funding_rate * 100, 5) if funding_rate is not None else None,  # M2-44
                })
                tp_line = (
                    f"Native TP:    ${self.entry_price * (1 - TP_PCT):.2f} (OID: {self.hl_tp_order_id or 'FAILED'})\n"
                    if TP_PCT is not None else ""
                )
                self.send_email(
                    f"Short OPENED 🚨 ({label})",
                    f"SHORT opened — VIZNIAGO V2\n"
                    f"Trigger:      {label}\n"
                    f"NFT:          #{NFT_ID}\n"
                    f"Entry:        ${self.entry_price:.2f}\n"
                    f"Size:         {size:.4f} ETH\n"
                    f"Leverage:     {leverage}x\n"
                    f"Notional:     ${notional:.2f}\n"
                    f"Native SL:    ${self.current_sl_price:.2f} (OID: {self.hl_sl_order_id or 'FAILED'})\n"
                    f"{tp_line}"
                    f"Breakeven at: -{self._effective_breakeven_pct*100:.2f}% → trail {TRAIL_PCT*100:.1f}% from min"
                    + (f" [ATR-adaptive, base {BREAKEVEN_PCT*100:.1f}%]"
                       if self._effective_breakeven_pct > BREAKEVEN_PCT else ""),
                )
            else:
                print(f"❌ Order failed: {order}", flush=True)
                log_event("error", price=price, details={"msg": str(order)})

        except Exception as e:
            print(f"❌ open_hedge error: {e}", flush=True)
            log_event("error", price=price, details={"msg": str(e)})

    # ── Short management ───────────────────────────────────────────────────────

    def manage_active_hedge(self, price):
        # ── 1. Track minimum price ─────────────────────────────────────────
        if price < self.short_min_price:
            self.short_min_price = price

            if self.breakeven_reached:
                trail_sl = self.short_min_price * (1 + TRAIL_PCT)
                new_sl   = min(self.entry_price, trail_sl)
                # L1: only cancel+replace when the SL improves ≥0.1% — every
                # replace has a brief no-native-SL window and costs 2 API actions
                if new_sl < self.current_sl_price * (1 - 0.001):
                    self.current_sl_price = new_sl
                    print(f"📉 Trail SL → ${self.current_sl_price:.2f} "
                          f"(min ${self.short_min_price:.2f} + {TRAIL_PCT*100:.1f}%)", flush=True)
                    # V2: cancel + replace native SL
                    self._replace_native_sl(self.current_sl_price)
                    self._save_trail_state()  # M7

        # ── 2. Fixed TP check ──────────────────────────────────────────────
        if TP_PCT is not None:
            tp_price = self.entry_price * (1 - TP_PCT)
            if price <= tp_price:
                print(f"🎯 TP HIT at ${price:.2f}", flush=True)
                self.close_hedge(price, reason="tp_hit")
                return

        # ── 3. SL check ────────────────────────────────────────────────────
        if price >= self.current_sl_price:
            reason = "trailing_stop" if self.breakeven_reached else "sl_hit"
            print(f"🛑 SL FIRED at ${price:.2f} | SL was ${self.current_sl_price:.2f}", flush=True)
            self.close_hedge(price, reason=reason)
            return

        # ── 4. Breakeven → activate trailing SL ────────────────────────────
        if not TRAILING_STOP:
            return

        if not self.breakeven_reached and price <= self.entry_price * (1 - self._effective_breakeven_pct):
            self.breakeven_reached = True
            trail_sl              = self.short_min_price * (1 + TRAIL_PCT)
            self.current_sl_price = min(self.entry_price, trail_sl)
            pnl_est = (self.entry_price - price) / self.entry_price * 100
            print(f"🛡️  BREAKEVEN | BE={self._effective_breakeven_pct*100:.2f}% | "
                  f"Trail SL: ${self.current_sl_price:.2f}", flush=True)

            # V2: replace native SL at the new trail level
            self._replace_native_sl(self.current_sl_price)
            self._save_trail_state()  # M7

            log_event("breakeven", price=price, pnl=pnl_est, details={
                "sl":        round(self.current_sl_price, 4),
                "sl_oid":    self.hl_sl_order_id,
                "min":       round(self.short_min_price, 4),
                "trail_pct": TRAIL_PCT * 100,
            })
            self.send_email(
                "Short Protected 🛡️ (Breakeven)",
                f"Short profit ≥ {self._effective_breakeven_pct*100:.2f}% — trailing SL activated.\n"
                f"NFT #{NFT_ID}\n"
                f"Entry:     ${self.entry_price:.2f}\n"
                f"Min price: ${self.short_min_price:.2f}\n"
                f"Trail SL:  ${self.current_sl_price:.2f} (OID: {self.hl_sl_order_id or 'none'})",
            )

    # ── Short close ────────────────────────────────────────────────────────────

    def close_hedge(self, price, reason):
        try:
            # H1: capture native order IDs before cancelling — needed to classify
            # the close from HL fills if the position turns out to be already gone.
            sl_oid, tp_oid = self.hl_sl_order_id, self.hl_tp_order_id

            # V2: cancel native SL + TP before market close to avoid double-fill
            self._cancel_native_sl()
            self._cancel_native_tp()

            # L2: close only the bot's recorded size — market_close("ETH") with no
            # sz would also close any manual ETH trade sharing this wallet.
            result = self.exchange.market_close("ETH", sz=self.hedge_size_eth)
            if result is None:
                # M2-40: native SL fired between polls — set cooldown
                self._ext_close_cooldown_until = time.time() + self._EXT_COOLDOWN_SECS
                # H1: classify the external close from actual HL fills (win vs loss)
                outcome = self._classify_external_close(sl_oid, tp_oid)
                # M2-39: all CB systems updated here (before state reset)
                self._on_stop_event(
                    price,
                    is_win=outcome["is_win"] if outcome else False,
                    pnl_usd=outcome["pnl_usd"] if outcome else None,
                )
                print(f"⚠️  market_close returned None — position already gone. Resetting.", flush=True)
                self._reset_short_state(price)
                log_event("stopped", price=price, details={
                    "reason":            "external_close",
                    "note":              "HL position not found — native SL fired or manual close",
                    "cooldown":          self._EXT_COOLDOWN_SECS,
                    "consecutive_stops": self._consecutive_stops,
                    **(outcome or {"classified": "unavailable"}),
                })
                _oc_line = (
                    f"Resultado real (fills HL): {outcome['reason']} | "
                    f"cierre ${outcome['close_px']:.2f} | "
                    f"PnL neto ${outcome['pnl_usd']:+.2f} ({'WIN' if outcome['is_win'] else 'LOSS'})\n"
                    if outcome else
                    "Resultado real: no se pudieron leer los fills de HL — contado como pérdida estimada.\n"
                )
                self.send_email("⚠️ Hedge Externally Closed",
                    f"NFT #{NFT_ID}: HL SHORT not found during close attempt.\n"
                    f"{_oc_line}"
                    f"Bot reset to IDLE — {self._EXT_COOLDOWN_SECS // 60} min cooldown before re-arm (M2-40).\n"
                    f"Consecutive stops: {self._consecutive_stops}/{self._CB_STOP_THRESHOLD}")
                if not AUTO_REARM:
                    sys.exit(0)
                return

            if result["status"] == "ok":
                pnl_est = (
                    (self.entry_price - price) / self.entry_price * 100
                    if self.entry_price else None
                )
                # M2-43: capture IL attribution before state reset
                il_attr = self._calc_il_attribution(self.entry_price, price) if self.entry_price else {}
                # M2-44: capture actual cumulative funding cost before state reset
                fund_attr = self._calc_funding_cost(
                    self.open_time, self.hedge_size_eth or 0, self.entry_price or 0
                ) if self.open_time else {}
                close_price = price
                self._reset_short_state(close_price)

                if not AUTO_REARM:
                    log_event("stopped", price=price, details={"reason": "auto_rearm_disabled"})
                    sys.exit(0)

                # M2-39: all CB systems (win resets streak; loss feeds all three)
                is_win = reason in ("tp_hit", "trailing_stop")
                self._on_stop_event(close_price, is_win=is_win)

                pnl_str = f"{pnl_est:.2f}%" if pnl_est is not None else "n/a"
                cb_str  = f" | streak {self._consecutive_stops}/{self._CB_STOP_THRESHOLD}" if reason in ("sl_hit", "trailing_stop") else ""
                # M2-43: build IL attribution log line
                il_str = ""
                if il_attr and "lp_chg_pct" in il_attr:
                    il_str = (f" | LP {il_attr['lp_chg_pct']:+.2f}% "
                              f"Hedge {il_attr['hedge_offset_pct']:+.2f}% "
                              f"Net {il_attr['net_pct']:+.2f}%")
                print(f"✅ SHORT CLOSED | Reason: {reason} | Exit: ${close_price:.2f} | PnL: {pnl_str}{cb_str}{il_str}", flush=True)
                log_event(reason, price=price, pnl=pnl_est, details={
                    "reentry_guard":      round(self.reentry_guard_price, 4),
                    "consecutive_stops":  self._consecutive_stops,
                    **il_attr,
                    **fund_attr,
                })
                self.send_email(
                    f"Short CLOSED ✅ ({reason})",
                    f"Reason:  {reason}\n"
                    f"Exit:    ${close_price:.2f}\n"
                    f"PnL est: {pnl_str}\n"
                    f"NFT #{NFT_ID}\n\n"
                    f"Re-entry guard: price must recover above "
                    f"${self.reentry_guard_price:.2f} before next short.",
                )
            else:
                print(f"❌ Close failed: {result}", flush=True)
                log_event("error", price=price, details={"msg": str(result)})
        except Exception as e:
            print(f"❌ close_hedge error: {e}", flush=True)
            log_event("error", price=price, details={"msg": str(e)})

    def _on_stop_event(self, price: float, is_win: bool = False,
                       pnl_usd: Optional[float] = None) -> None:
        """Central CB handler called after every trade close.

        Updates all three circuit-breaker systems:
          A) Consecutive-streak trigger (original M2-39, now with escalating pause)
          B) Rolling-window rate trigger  (new)
          C) Daily net-loss cap           (new)

        H1: pnl_usd, when provided, is the ACTUAL net P&L from HL fills
        (classified external close) — used instead of the worst-case SL estimate.
        Wins offset the daily net-loss cap.

        Must be called BEFORE _reset_short_state so entry_price/size are still set.
        """
        now = time.time()

        today = datetime.now(timezone.utc).date()
        if today != self._session_date:           # new UTC day → reset counter
            self._session_loss_usd = 0.0
            self._session_date = today

        if is_win:
            self._consecutive_stops = 0
            if pnl_usd is not None:
                self._session_loss_usd += pnl_usd  # H1: wins offset the daily cap
            return

        # ── A+B: record this stop ─────────────────────────────────────────
        self._consecutive_stops += 1
        self._stop_timestamps.append(now)
        while self._stop_timestamps and self._stop_timestamps[0] < now - self._CB_RATE_WINDOW_SECS:
            self._stop_timestamps.popleft()

        # ── C: accumulate loss — actual fills (H1) or worst-case estimate ─
        if pnl_usd is not None:
            est_loss = pnl_usd
        else:
            entry  = self.entry_price or price
            size   = self.hedge_size_eth or 0.0
            notional = entry * size
            est_loss = -(notional * DEFAULT_SL_PCT) - (notional * 0.00045 * 2)
        self._session_loss_usd += est_loss

        # ── Determine if any CB trigger fires ─────────────────────────────
        daily_cap   = self._daily_loss_cap()
        streak_fire = self._consecutive_stops >= self._CB_STOP_THRESHOLD
        rate_fire   = len(self._stop_timestamps) >= self._CB_RATE_THRESHOLD
        cap_fire    = self._session_loss_usd <= daily_cap

        if not (streak_fire or rate_fire or cap_fire):
            return

        # ── Compute escalated pause (A/B share escalation; C uses fixed EOD) ─
        if cap_fire:
            # Pause until next UTC midnight
            midnight = datetime.now(timezone.utc).replace(
                hour=23, minute=59, second=59, microsecond=0
            )
            pause_secs = max(int(midnight.timestamp() - now), 1800)
            reason_str = (f"Daily loss cap hit (net ${self._session_loss_usd:.2f} "
                          f"≤ cap ${daily_cap:.2f})")
            self._session_loss_usd = 0.0   # reset so it doesn't re-fire immediately
        else:
            # Escalating pause based on how many CBs fired in the last window
            self._cb_fire_times.append(now)
            while self._cb_fire_times and self._cb_fire_times[0] < now - self._CB_ESCALATION_WINDOW:
                self._cb_fire_times.popleft()
            step = min(len(self._cb_fire_times) - 1, len(self._CB_PAUSE_STEPS) - 1)
            if rate_fire:
                pause_secs = self._CB_RATE_PAUSE_SECS
                reason_str = (f"{self._CB_RATE_THRESHOLD} stops in "
                              f"{self._CB_RATE_WINDOW_SECS // 60}min window")
                self._stop_timestamps.clear()
            else:
                pause_secs = self._CB_PAUSE_STEPS[step]
                reason_str = f"{self._CB_STOP_THRESHOLD} consecutive stops (level {step + 1})"
            self._consecutive_stops = 0

        self._circuit_breaker_until = max(self._circuit_breaker_until, now + pause_secs)
        log_event("circuit_breaker", price=price, details={
            "reason":  reason_str,
            "pause_s": pause_secs,
            "session_loss_usd": round(self._session_loss_usd, 2),
        })
        self.send_email(
            "⚠️ Circuit Breaker Activated (M2-39)",
            f"NFT #{NFT_ID}: {reason_str}\n"
            f"Pausing re-entry for {pause_secs // 60} min.\n"
            f"Last exit: ${price:.2f} | Session est. loss: ${self._session_loss_usd:.2f}",
        )
        print(f"🔴 [M2-39] Circuit breaker ({reason_str}) — pausing {pause_secs // 60} min",
              flush=True)

    def _daily_loss_cap(self) -> float:
        """H2: daily net-loss cap in USD (negative).

        Env DAILY_LOSS_CAP_USD wins when set; otherwise _DAILY_CAP_STOPS × the
        expected single-stop loss (SL distance + round-trip taker fees) at the
        sizing of the trade being closed. $5 magnitude floor.
        Must be called BEFORE _reset_short_state so entry/size are still set.
        """
        if self._DAILY_LOSS_CAP_FIXED is not None:
            return self._DAILY_LOSS_CAP_FIXED
        notional = (self.entry_price or 0.0) * (self.hedge_size_eth or 0.0)
        per_stop = notional * DEFAULT_SL_PCT + notional * 0.00045 * 2
        return -max(5.0, self._DAILY_CAP_STOPS * per_stop)

    # ── H1: external close classification ────────────────────────────────────

    def _classify_external_close(self, sl_oid: Optional[int],
                                 tp_oid: Optional[int]) -> Optional[dict]:
        """Determine the actual outcome of an externally-closed SHORT from HL fills.

        Native SL/TP triggers fire on HL between polls, so almost every close is
        "external" — previously all were counted as losses. This matches the
        buy-back fills since open_time against the known SL/TP order IDs and
        computes real net P&L (incl. taker fees).

        Returns {close_px, pnl_usd, pnl_pct, reason, is_win} or None if fills
        can't be read (caller falls back to the conservative loss estimate).
        Must be called BEFORE _reset_short_state.
        """
        try:
            if not self.open_time or not self.entry_price or not self.hedge_size_eth:
                return None
            start_ms = int(self.open_time * 1000)
            fills = self.info.user_fills(HL_ADDRESS) or []
            close_fills = [
                f for f in fills
                if f.get("coin") == "ETH"
                and f.get("side") == "B"            # buy-back closes a SHORT
                and int(f.get("time", 0)) >= start_ms
            ]
            if not close_fills:
                return None
            total_sz = sum(abs(float(f.get("sz", 0))) for f in close_fills)
            if total_sz <= 0:
                return None
            close_px = sum(
                float(f["px"]) * abs(float(f.get("sz", 0))) for f in close_fills
            ) / total_sz

            fill_oids = {str(f.get("oid", "")) for f in close_fills}
            if tp_oid is not None and str(tp_oid) in fill_oids:
                reason = "native_tp"
            elif sl_oid is not None and str(sl_oid) in fill_oids:
                # Trailed SL below entry is a win; classification comes from P&L below
                reason = "native_sl"
            else:
                reason = "manual_or_unknown"

            gross   = (self.entry_price - close_px) * self.hedge_size_eth
            fees    = (self.entry_price + close_px) * self.hedge_size_eth * 0.00045
            pnl_usd = gross - fees
            pnl_pct = (self.entry_price - close_px) / self.entry_price * 100
            result = {
                "close_px": round(close_px, 4),
                "pnl_usd":  round(pnl_usd, 4),
                "pnl_pct":  round(pnl_pct, 4),
                "reason":   reason,
                "is_win":   pnl_usd > 0,
            }
            print(
                f"🔎 [H1] External close classified: {reason} @ ${close_px:.2f} | "
                f"net ${pnl_usd:+.2f} ({'WIN' if pnl_usd > 0 else 'LOSS'})",
                flush=True,
            )
            return result
        except Exception as e:
            print(f"⚠️  [H1] External-close classification failed: {e}", flush=True)
            return None

    # ── M7: trail-state persistence ───────────────────────────────────────────

    def _save_trail_state(self):
        """Persist the trail state so a restart doesn't reset it (atomic write)."""
        if not self.hedge_active:
            return
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            tmp = self._state_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump({
                    "entry_price":             self.entry_price,
                    "hedge_size_eth":          self.hedge_size_eth,
                    "open_time":               self.open_time,
                    "open_trigger":            self.open_trigger,
                    "breakeven_reached":       self.breakeven_reached,
                    "short_min_price":         self.short_min_price,
                    "current_sl_price":        self.current_sl_price,
                    "effective_breakeven_pct": self._effective_breakeven_pct,
                    "saved_at":                time.time(),
                }, f)
            os.replace(tmp, self._state_path)
        except Exception as e:
            print(f"⚠️  [M7] Trail-state save failed: {e}", flush=True)

    def _clear_trail_state(self):
        try:
            os.remove(self._state_path)
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"⚠️  [M7] Trail-state clear failed: {e}", flush=True)

    def _load_trail_state(self, entry_px: float, size: float) -> Optional[dict]:
        """Return saved trail state if it matches the recovered HL position
        (entry within 0.1%, identical size) — otherwise None."""
        try:
            with open(self._state_path) as f:
                st = json.load(f)
            saved_entry = float(st.get("entry_price") or 0)
            saved_size  = float(st.get("hedge_size_eth") or 0)
            if (saved_entry > 0 and entry_px > 0
                    and abs(saved_entry - entry_px) / entry_px < 0.001
                    and abs(saved_size - size) < 1e-9):
                return st
            print(f"⚠️  [M7] Saved trail state doesn't match HL position "
                  f"(saved ${saved_entry:.2f}/{saved_size} vs live ${entry_px:.2f}/{size}) — ignoring",
                  flush=True)
            return None
        except FileNotFoundError:
            return None
        except Exception as e:
            print(f"⚠️  [M7] Trail-state load failed: {e}", flush=True)
            return None

    def _reset_short_state(self, close_price: float):
        """Reset all short-related state after a close."""
        self.hedge_active        = False
        self.breakeven_reached   = False
        self.short_min_price     = None
        self.open_trigger        = None
        self.hl_sl_order_id      = None
        self.hl_tp_order_id      = None
        self.open_time           = None
        self.reentry_guard_price = close_price * (1 + REENTRY_BUFFER)
        self.sl_close_price      = close_price
        self.price_was_above     = False
        self._clear_trail_state()  # M7

    # ── M2-49: ATR-adaptive breakeven ────────────────────────────────────────

    def _compute_atr_breakeven(self, entry_price: float) -> float:
        """Return max(BREAKEVEN_PCT, ATR_MULT_BE × ATR(ATR_PERIOD)) as a fraction.
        Fetches the last ATR_PERIOD+2 hourly candles from HL.
        Falls back to the static BREAKEVEN_PCT on any failure."""
        try:
            now_ms   = int(time.time() * 1000)
            start_ms = now_ms - (ATR_PERIOD + 3) * 3_600_000
            candles  = self.info.candles_snapshot("ETH", "1h", start_ms, now_ms)
            # L3: drop the in-progress candle — its partial range understates TR
            if candles:
                candles = [c for c in candles if int(c.get("T", 0)) <= now_ms]
            if not candles or len(candles) < ATR_PERIOD + 1:
                print(f"⚠️  [M2-49] ATR: only {len(candles) if candles else 0} candles — "
                      f"using static BE {BREAKEVEN_PCT*100:.1f}%", flush=True)
                return BREAKEVEN_PCT
            candles = sorted(candles, key=lambda c: c["t"])[-ATR_PERIOD - 1:]
            true_ranges = []
            for i in range(1, len(candles)):
                h      = float(candles[i]["h"])
                lo     = float(candles[i]["l"])
                prev_c = float(candles[i - 1]["c"])
                true_ranges.append(max(h - lo, abs(h - prev_c), abs(lo - prev_c)))
            atr     = sum(true_ranges[-ATR_PERIOD:]) / ATR_PERIOD
            atr_pct = atr / entry_price
            effective = max(BREAKEVEN_PCT, ATR_MULT_BE * atr_pct)
            marker = "↑ ATR adaptive" if effective > BREAKEVEN_PCT else "= static floor"
            print(f"📊 [M2-49] ATR({ATR_PERIOD})=${atr:.2f} ({atr_pct*100:.2f}%) → "
                  f"BE={effective*100:.2f}% {marker}", flush=True)
            return effective
        except Exception as exc:
            print(f"⚠️  [M2-49] ATR fetch failed ({exc}) — using static BE {BREAKEVEN_PCT*100:.1f}%",
                  flush=True)
            return BREAKEVEN_PCT

    # ── M2-43: IL attribution ─────────────────────────────────────────────────

    def _calc_il_attribution(self, entry_price: float, close_price: float) -> dict:
        """Compute LP value change and hedge offset at trade close.
        Returns dict with lp_chg_pct, hedge_offset_pct, net_pct, lp_value_entry,
        lp_value_close — all rounded. Empty dict on missing data or error."""
        try:
            if not self.liquidity or not self.tick_lower or not self.tick_upper:
                return {}
            v_entry = calc_lp_value_usdc(
                self.liquidity, self.tick_lower, self.tick_upper, entry_price
            )
            v_close = calc_lp_value_usdc(
                self.liquidity, self.tick_lower, self.tick_upper, close_price
            )
            if v_entry <= 0:
                return {}
            lp_chg_pct      = (v_close - v_entry) / v_entry * 100
            hedge_pnl_usdc  = (entry_price - close_price) * (self.hedge_size_eth or 0)
            hedge_offset_pct = hedge_pnl_usdc / v_entry * 100
            return {
                "lp_value_entry":    round(v_entry, 2),
                "lp_value_close":    round(v_close, 2),
                "lp_chg_pct":        round(lp_chg_pct, 3),
                "hedge_offset_pct":  round(hedge_offset_pct, 3),
                "net_pct":           round(lp_chg_pct + hedge_offset_pct, 3),
            }
        except Exception as exc:
            return {"il_calc_err": str(exc)}

    # ── M2-44: Funding rate awareness ────────────────────────────────────────

    def _fetch_funding_rate(self) -> Optional[float]:
        """Return latest 1h ETH funding rate on HL, or None on failure.
        Positive = longs pay shorts (favorable for our SHORT).
        Negative = shorts pay longs (cost for our SHORT)."""
        try:
            now_ms   = int(time.time() * 1000)
            start_ms = now_ms - 2 * 3_600_000  # last 2 h, enough to get the latest record
            records  = self.info.funding_history("ETH", start_ms, now_ms)
            if records:
                return float(records[-1]["fundingRate"])
        except Exception as exc:
            print(f"⚠️  [M2-44] Funding fetch failed: {exc}", flush=True)
        return None

    def _calc_funding_cost(self, open_time_secs: float, hedge_size_eth: float,
                           entry_price: float) -> dict:
        """Query user's actual funding payments since open_time and return summary dict."""
        try:
            hours    = (time.time() - open_time_secs) / 3600
            start_ms = int(open_time_secs * 1000)
            records  = self.info.user_funding_history(HL_ADDRESS, start_ms) or []
            eth_recs = [r for r in records if r.get("coin") == "ETH"]
            total_usdc = sum(float(r.get("usdc", 0)) for r in eth_recs)
            pos_usdc   = hedge_size_eth * entry_price
            funding_pct = (total_usdc / pos_usdc * 100) if pos_usdc > 0 else 0.0
            return {
                "funding_hours":    round(hours, 1),
                "funding_usdc_net": round(total_usdc, 4),   # + = received, – = paid
                "funding_pct_net":  round(funding_pct, 4),  # % of position value
            }
        except Exception as exc:
            return {"funding_calc_err": str(exc)}

    # ── HL position sync ──────────────────────────────────────────────────────

    def _sync_hl_position(self, price):
        try:
            address = self.exchange.account_address or self.exchange.wallet.address
            state   = self.info.user_state(address, "")
            if state is None:
                return
            found = any(
                p["position"]["coin"] == "ETH"
                for p in state.get("assetPositions", [])
            )
            if not found:
                print(f"⚠️  HL sync: ETH SHORT not found — external close. Resetting.", flush=True)
                # H1: capture order IDs before cancelling — needed for classification
                sl_oid, tp_oid = self.hl_sl_order_id, self.hl_tp_order_id
                # V2: cancel any orphan SL/TP orders before resetting
                self._cancel_native_sl()
                self._cancel_native_tp()
                # M2-40: set cooldown before re-arm
                self._ext_close_cooldown_until = time.time() + self._EXT_COOLDOWN_SECS
                # H1: classify the external close from actual HL fills (win vs loss)
                outcome = self._classify_external_close(sl_oid, tp_oid)
                # M2-39: all CB systems updated here (before state reset)
                self._on_stop_event(
                    price,
                    is_win=outcome["is_win"] if outcome else False,
                    pnl_usd=outcome["pnl_usd"] if outcome else None,
                )
                self._reset_short_state(price)
                log_event("stopped", price=price, details={
                    "reason":            "external_close",
                    "note":              "HL position not found during periodic sync",
                    "cooldown":          self._EXT_COOLDOWN_SECS,
                    "consecutive_stops": self._consecutive_stops,
                    **(outcome or {"classified": "unavailable"}),
                })
                _oc_line = (
                    f"Resultado real (fills HL): {outcome['reason']} | "
                    f"cierre ${outcome['close_px']:.2f} | "
                    f"PnL neto ${outcome['pnl_usd']:+.2f} ({'WIN' if outcome['is_win'] else 'LOSS'})\n"
                    if outcome else
                    "Resultado real: no se pudieron leer los fills de HL — contado como pérdida estimada.\n"
                )
                self.send_email("⚠️ Hedge Externally Closed (sync)",
                    f"NFT #{NFT_ID}: ETH SHORT disappeared during routine sync.\n"
                    f"{_oc_line}"
                    f"Bot reset to IDLE — {self._EXT_COOLDOWN_SECS // 60} min cooldown before re-arm (M2-40).\n"
                    f"Consecutive stops: {self._consecutive_stops}/{self._CB_STOP_THRESHOLD}")
                if not AUTO_REARM:
                    sys.exit(0)
        except Exception as e:
            print(f"⚠️  HL sync check failed: {e}", flush=True)

    # ── LP position sync ──────────────────────────────────────────────────────

    def _sync_lp_position(self, price):
        try:
            pos       = self.contract.functions.positions(NFT_ID).call()
            liquidity = pos[7]

            if liquidity == 0:
                print(f"⚠️  LP sync: NFT #{NFT_ID} liquidity=0 — closing hedge.", flush=True)
                log_event("lp_removed", price=price, details={
                    "nft_id": NFT_ID,
                    "note":   "LP liquidity=0 while hedge was active — auto-closing SHORT",
                })
                self.send_email("⚠️ LP Removed — Hedge Auto-Closed",
                    f"NFT #{NFT_ID}: Uniswap v3 LP withdrawn (liquidity=0).\n"
                    f"VIZNIAGO closed the HL SHORT to prevent naked exposure.\n"
                    f"Re-add liquidity and re-arm from the dashboard.")
                self.close_hedge(price, reason="stopped")

        except Exception as e:
            err = str(e)
            if "nonexistent token" in err or "owner query" in err.lower() or "invalid token id" in err.lower():
                print(f"⚠️  LP sync: NFT #{NFT_ID} burned — closing hedge.", flush=True)
                log_event("lp_burned", price=price, details={
                    "nft_id": NFT_ID,
                    "note":   "NFT burned while hedge was active — auto-closing SHORT",
                })
                self.send_email("⚠️ LP Burned — Hedge Auto-Closed",
                    f"NFT #{NFT_ID}: Uniswap v3 LP burned entirely.\n"
                    f"VIZNIAGO closed the HL SHORT to prevent naked exposure.\n"
                    f"Create a new LP and add it to VIZNIAGO to resume protection.")
                self.close_hedge(price, reason="stopped")
            else:
                print(f"⚠️  LP sync RPC error (skipping): {e}", flush=True)

    # ── V2: Startup reconciliation ─────────────────────────────────────────────

    def _reconcile_on_startup(self):
        """
        Check HL state before entering the main loop.
        If an orphan SHORT exists (bot crashed while short was open):
          - Recover hedge state from HL position data
          - Find existing native SL order if any, or place a fresh one
          - Log orphan_recovered event and email alert
        If no position: clean start.
        """
        print("[V2] Startup reconciliation — checking HL for orphan positions…", flush=True)
        try:
            state = self.info.user_state(HL_ADDRESS)
            if state is None:
                print("⚠️  [V2] Reconciliation: could not fetch HL state — skipping", flush=True)
                return

            positions = state.get("assetPositions", [])
            eth_pos = next(
                (p for p in positions if p["position"]["coin"] == "ETH"),
                None
            )

            if eth_pos is None:
                print("✅ [V2] Reconciliation: no open ETH position — clean start", flush=True)
                return

            pos = eth_pos["position"]
            szi = float(pos.get("szi", 0))

            if szi >= 0:
                print(f"ℹ️  [V2] Reconciliation: ETH LONG found (szi={szi}) — not our SHORT, ignoring", flush=True)
                return

            # Orphan SHORT confirmed
            entry_px = float(pos.get("entryPx", 0))
            size     = abs(szi)
            lev      = pos.get("leverage", {})
            lev_val  = int(lev.get("value", TARGET_LEVERAGE)) if isinstance(lev, dict) else TARGET_LEVERAGE

            print(
                f"⚠️  [V2] Orphan SHORT found | entry ${entry_px:.2f} | "
                f"size {size:.4f} ETH | lev {lev_val}x",
                flush=True,
            )

            # Recover bot state
            self.hedge_active   = True
            self.entry_price    = entry_px
            self.hedge_size_eth = size
            self.leverage_used  = lev_val

            # M7: restore the persisted trail if it matches this position;
            # otherwise fall back to conservative defaults from entry.
            st = self._load_trail_state(entry_px, size)
            if st:
                self.breakeven_reached        = bool(st.get("breakeven_reached"))
                self.short_min_price          = float(st.get("short_min_price") or entry_px)
                self.current_sl_price         = float(st.get("current_sl_price")
                                                       or entry_px * (1 + DEFAULT_SL_PCT))
                self.open_trigger             = st.get("open_trigger") or "recovered"
                self._effective_breakeven_pct = float(st.get("effective_breakeven_pct")
                                                       or BREAKEVEN_PCT)
                self.open_time                = float(st.get("open_time") or time.time())
                print(f"♻️  [M7] Trail state restored | "
                      f"BE={'✓' if self.breakeven_reached else '✗'} | "
                      f"min ${self.short_min_price:.2f} | SL ${self.current_sl_price:.2f}",
                      flush=True)
            else:
                self.current_sl_price         = entry_px * (1 + DEFAULT_SL_PCT)
                self.breakeven_reached        = False
                self.short_min_price          = entry_px
                self.open_trigger             = "recovered"
                self._effective_breakeven_pct = BREAKEVEN_PCT  # M2-49: static (no ATR context)
                # H1: actual fill time unknown — use recovery time so a later
                # external close can still be classified from fills.
                self.open_time                = time.time()

            # Check for existing SL and TP orders on HL
            try:
                # H6: must be frontend_open_orders — the basic open_orders endpoint
                # omits triggerPx/orderType, so trigger orders were never matched
                # and every recovery placed a duplicate SL.
                open_orders = self.info.frontend_open_orders(HL_ADDRESS)
                trigger_orders = [
                    o for o in open_orders
                    if o.get("coin") == "ETH"
                    and o.get("side", "").upper() == "B"
                    and o.get("triggerPx") is not None
                ]
                # HL open_orders includes an "orderType" field: "Stop Market" for SL, "Take Profit Market" for TP
                existing_sl = next(
                    (o for o in trigger_orders if "stop" in o.get("orderType", "").lower()),
                    None,
                )
                existing_tp = next(
                    (o for o in trigger_orders if "take profit" in o.get("orderType", "").lower()),
                    None,
                )

                if existing_sl:
                    self.hl_sl_order_id = existing_sl["oid"]
                    print(
                        f"✅ [V2] Existing SL order found | OID {self.hl_sl_order_id} "
                        f"| trigger ${existing_sl.get('triggerPx', '?')}",
                        flush=True,
                    )
                else:
                    print(f"⚠️  [V2] No native SL found — placing at ${self.current_sl_price:.2f}", flush=True)
                    oid = self._place_native_sl(self.current_sl_price, size)
                    if oid:
                        self.hl_sl_order_id = oid
                        print(f"✅ [V2] Recovery SL placed | OID {oid}", flush=True)
                    else:
                        print(f"⚠️  [V2] Recovery SL placement failed — code-evaluated only", flush=True)

                if TP_PCT is not None:
                    if existing_tp:
                        self.hl_tp_order_id = existing_tp["oid"]
                        print(
                            f"✅ [V2] Existing TP order found | OID {self.hl_tp_order_id} "
                            f"| trigger ${existing_tp.get('triggerPx', '?')}",
                            flush=True,
                        )
                    else:
                        tp_price = entry_px * (1 - TP_PCT)
                        print(f"⚠️  [V2] No native TP found — placing at ${tp_price:.2f}", flush=True)
                        tp_oid = self._place_native_tp(tp_price, size)
                        if tp_oid:
                            self.hl_tp_order_id = tp_oid
                            print(f"✅ [V2] Recovery TP placed | OID {tp_oid}", flush=True)
                        else:
                            print(f"⚠️  [V2] Recovery TP placement failed — code-evaluated only", flush=True)

            except Exception as e:
                print(f"⚠️  [V2] Could not check open orders: {e}", flush=True)

            self._save_trail_state()  # M7: refresh file (covers default-recovery case)

            log_event("orphan_recovered", price=entry_px, details={
                "entry":          entry_px,
                "size":           size,
                "sl":             round(self.current_sl_price, 4),
                "sl_oid":         self.hl_sl_order_id,
                "tp_oid":         self.hl_tp_order_id,
                "trail_restored": bool(st),  # M7
                "note":    "Bot restarted while SHORT was open — state recovered from HL",
            })
            tp_recovery_line = (
                f"  TP price:    ${entry_px * (1 - TP_PCT):.2f} (-{TP_PCT*100:.1f}%)\n"
                f"  TP OID:      {self.hl_tp_order_id or 'placement failed'}\n"
                if TP_PCT is not None else ""
            )
            self.send_email(
                "⚠️ [V2] Orphan SHORT Recovered at Startup",
                f"NFT #{NFT_ID}: VIZNIAGO V2 detected an orphan SHORT at startup.\n"
                f"(Bot likely crashed or was restarted while a SHORT was open.)\n\n"
                f"Recovered state:\n"
                f"  Entry price: ${entry_px:.2f}\n"
                f"  Size:        {size:.4f} ETH\n"
                f"  Leverage:    {lev_val}x\n"
                f"  SL price:    ${self.current_sl_price:.2f} (+{DEFAULT_SL_PCT*100:.1f}%)\n"
                f"  SL OID:      {self.hl_sl_order_id or 'placement failed'}\n"
                f"{tp_recovery_line}"
                f"\nBot is now managing this position. Trail restarts from entry price.",
            )

        except Exception as e:
            print(f"⚠️  [V2] Reconciliation error: {e}", flush=True)

    # ── Main loop ──────────────────────────────────────────────────────────────

    def run(self):
        print(f"🚀 [V2] VIZNIAGO Defensor Bajista V2 starting | NFT #{NFT_ID}", flush=True)

        self.fetch_position_bounds(fatal=True)

        # V2: reconcile before entering the main loop
        self._reconcile_on_startup()

        lower_trigger = self.lower_bound * (1 - TRIGGER_OFFSET)
        upper_trigger = self.upper_bound * (1 - UPPER_BUFFER)
        x_max         = calc_x_max_eth(self.liquidity, self.tick_lower, self.tick_upper)

        trigger_desc = (
            f"BELOW ${lower_trigger:.2f} | FROM ABOVE @ ${upper_trigger:.2f}"
            if FROM_ABOVE_ENABLED else
            f"BELOW ${lower_trigger:.2f} only (mode=aragan/Bajista)"
        )
        print(f"📐 Range:         ${self.lower_bound:.2f} — ${self.upper_bound:.2f}", flush=True)
        print(f"📐 Short triggers: {trigger_desc}", flush=True)
        print(f"📐 Mode:          {BOT_MODE} | from_above={'ON' if FROM_ABOVE_ENABLED else 'OFF'}"
              f"{f' | M2-47 gate: ≤{MAX_FROM_ABOVE_DIST_PCT:.1f}% below upper' if FROM_ABOVE_ENABLED else ''}",
              flush=True)
        print(f"📐 SL: {DEFAULT_SL_PCT*100:.2f}% | "
              f"TP: {TP_PCT*100:.2f}% (fixed)" if TP_PCT else f"📐 SL: {DEFAULT_SL_PCT*100:.2f}% | TP: off",
              flush=True)
        print(f"📐 Trailing: {'on' if TRAILING_STOP else 'OFF'} | "
              f"Breakeven: {BREAKEVEN_PCT*100:.1f}% base (ATR-adaptive, {ATR_MULT_BE}×ATR{ATR_PERIOD}) | "
              f"Trail: {TRAIL_PCT*100:.1f}%", flush=True)
        print(f"📐 [V2] Native HL SL: enabled | Cancel+replace on trail: enabled", flush=True)
        print(f"📐 [M2-44] Funding: logged at open+close | "
              f"Gate: {'ON (block if rate < -' + str(FUNDING_GATE_PCT) + '%/1h)' if USE_FUNDING_GATE else 'OFF (log-only)'}",
              flush=True)

        # Only emit started event if not recovering an orphan (reconcile already logged)
        if not self.hedge_active:
            log_event("started", details={
                "nft_id":          NFT_ID,
                "lower":           self.lower_bound,
                "upper":           self.upper_bound,
                "lower_trigger":   lower_trigger,
                "upper_trigger":   upper_trigger,
                "x_max_eth":       round(x_max, 4),
                "hedge_ratio":     HEDGE_RATIO,
                "target_leverage": TARGET_LEVERAGE,
                "sl_pct":          DEFAULT_SL_PCT * 100,
                "tp_pct":          TP_PCT * 100 if TP_PCT else None,
                "trailing_stop":      TRAILING_STOP,
                "auto_rearm":         AUTO_REARM,
                "breakeven_pct":      BREAKEVEN_PCT * 100,
                "trail_pct":          TRAIL_PCT * 100,
                "engine":             "v2",
                "mode":               BOT_MODE,
                "from_above_enabled": FROM_ABOVE_ENABLED,
            })
            self.send_email(
                "VIZNIAGO V2 Defensor Started 🚀",
                f"NFT #{NFT_ID}\n"
                f"Range:          ${self.lower_bound:.2f} — ${self.upper_bound:.2f}\n"
                f"Short triggers:\n"
                f"  1. FROM ABOVE @ ${upper_trigger:.2f}\n"
                f"  2. BELOW RANGE @ ${lower_trigger:.2f}\n"
                f"Init SL:        {DEFAULT_SL_PCT*100:.1f}% above entry (native HL order)\n"
                f"Breakeven:      at {BREAKEVEN_PCT*100:.1f}% profit → trail activates\n"
                f"Trail:          {TRAIL_PCT*100:.1f}% above min price (cancel+replace on each move)",
            )

        while True:
            now   = time.time()
            price = self.get_eth_price()

            # ── Periodic safety syncs ────────────────────────────────────────
            # L4: skip syncs when the price fetch failed — running them with
            # price=0 corrupted reentry_guard/CB state if a close was detected
            if price and self.hedge_active and now - self.last_lp_sync > HL_SYNC_INTERVAL:
                self.last_lp_sync = now
                self._sync_lp_position(price)

            if price and self.hedge_active and now - self.last_hl_sync > HL_SYNC_INTERVAL:
                self.last_hl_sync = now
                self._sync_hl_position(price)

            # ── Periodic bounds refresh (idle only) ──────────────────────────
            if (not self.hedge_active and
                    now - self.last_bounds_fetch > BOUNDS_REFRESH_H * 3600):
                old_lower, old_upper = self.lower_bound, self.upper_bound
                self.fetch_position_bounds()
                lower_trigger = self.lower_bound * (1 - TRIGGER_OFFSET)
                upper_trigger = self.upper_bound * (1 - UPPER_BUFFER)
                if self.lower_bound != old_lower or self.upper_bound != old_upper:
                    print(f"🔄 Range updated: ${old_lower:.2f}–${old_upper:.2f} → "
                          f"${self.lower_bound:.2f}–${self.upper_bound:.2f}", flush=True)
                    log_event("bounds_refreshed", details={
                        "old_lower": old_lower, "old_upper": old_upper,
                        "new_lower": self.lower_bound, "new_upper": self.upper_bound,
                    })

            if price:
                # ── Direction tracking ───────────────────────────────────────
                # M2-13: from_above only tracked/fired when mode allows it (avaro)
                if FROM_ABOVE_ENABLED and price > self.upper_bound:
                    if not self.price_was_above:
                        print(f"⬆️  Price above range (${price:.2f}) — from-above trigger armed", flush=True)
                    self.price_was_above = True
                elif price < self.lower_bound and self.price_was_above and not self.hedge_active:
                    self.price_was_above = False

                # ── Re-entry guard check ─────────────────────────────────────
                if self.reentry_guard_price and price >= self.reentry_guard_price:
                    print(f"🔓 Re-entry guard cleared at ${price:.2f}", flush=True)
                    log_event("reentry_guard_cleared", price=price)
                    self.reentry_guard_price = None
                    self.sl_close_price      = None
                elif (self.reentry_guard_price and self.sl_close_price
                        and price < self.sl_close_price):
                    # M2-23: price continued below where SL closed — whipsaw risk
                    # gone, re-arm immediately without waiting for guard level
                    print(f"🔓 [V2] Re-entry guard cleared — price ${price:.2f} below "
                          f"SL-close ${self.sl_close_price:.2f} (continued downside)",
                          flush=True)
                    log_event("reentry_guard_cleared", price=price)
                    self.reentry_guard_price = None
                    self.sl_close_price      = None
                    self.price_was_above     = True

                # ── Entry logic ──────────────────────────────────────────────
                if not self.hedge_active:
                    # M2-39: circuit breaker check (shown in the status line below)
                    if now < self._circuit_breaker_until:
                        pass
                    # M2-40: post-external_close cooldown check (status line below)
                    elif now < self._ext_close_cooldown_until:
                        pass
                    else:
                        opened = False

                        if FROM_ABOVE_ENABLED and self.price_was_above and price <= upper_trigger:
                            # M2-47: skip if price is too far below upper_bound (stale arm)
                            fa_min_px = self.upper_bound * (1 - MAX_FROM_ABOVE_DIST_PCT / 100)
                            if price >= fa_min_px:
                                self.open_hedge(price, trigger="from_above")
                                self.price_was_above = False
                                opened = True
                            else:
                                dist_pct = (self.upper_bound - price) / self.upper_bound * 100
                                print(
                                    f"⏭️  [M2-47] from_above skipped — price ${price:.2f} is "
                                    f"{dist_pct:.1f}% below upper_bound "
                                    f"(gate: {MAX_FROM_ABOVE_DIST_PCT:.1f}%)",
                                    flush=True,
                                )

                        if not opened and price <= lower_trigger:
                            if self.reentry_guard_price is None:
                                self.open_hedge(price, trigger="below_range")
                            else:
                                print(f"⏸️  Below trigger but re-entry guard active "
                                      f"(need ${self.reentry_guard_price:.2f})", flush=True)

                # ── Manage open short ────────────────────────────────────────
                elif self.hedge_active:
                    self.manage_active_hedge(price)

                # ── Status line ──────────────────────────────────────────────
                if price < self.lower_bound:
                    zone = "🔴 BELOW"
                elif price > self.upper_bound:
                    zone = "🟡 ABOVE"
                else:
                    zone = "🟢 IN   "

                if self.hedge_active:
                    be  = "BE✓" if self.breakeven_reached else "BE✗"
                    sl_src = f"OID:{self.hl_sl_order_id}" if self.hl_sl_order_id else "code"
                    short_status = (
                        f"🛡️ SHORT {self.open_trigger} | "
                        f"min ${self.short_min_price:.2f} | "
                        f"SL ${self.current_sl_price:.2f} [{sl_src}] | {be}"
                    )
                else:
                    if now < self._circuit_breaker_until:
                        # show escalation level in status
                        lvl = min(len(self._cb_fire_times), len(self._CB_PAUSE_STEPS))
                        short_status = (f"🔴 CIRCUIT BREAKER L{lvl} "
                                        f"({int(self._circuit_breaker_until - now)}s"
                                        f" | loss≈${self._session_loss_usd:.2f})")
                    elif now < self._ext_close_cooldown_until:
                        short_status = f"⏸️  EXT COOLDOWN ({int(self._ext_close_cooldown_until - now)}s)"
                    else:
                        guard = f"guard ${self.reentry_guard_price:.2f}" if self.reentry_guard_price else "ready"
                        armed = " | ↓armed" if self.price_was_above else ""
                        short_status = f"⚪ IDLE ({guard}{armed})"

                # M1: at the fast WS tick, throttle the status line to every 30s
                if now - self._last_status_print >= 30:
                    self._last_status_print = now
                    src = "ws" if self._ws_fresh() else "rest"
                    print(
                        f"[{time.strftime('%H:%M:%S')}] ETH ${price:.2f} ({src}) | "
                        f"{zone} | {short_status} [V2]",
                        end="\r", flush=True,
                    )

            # M1: fast cadence while the WS feed is fresh; REST interval otherwise
            time.sleep(WS_TICK_SECS if self._ws_fresh() else CHECK_INTERVAL)


if __name__ == "__main__":
    bot = LiveHedgeBotV2()
    bot.run()
