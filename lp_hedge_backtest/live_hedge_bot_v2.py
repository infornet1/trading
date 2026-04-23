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
        self.info     = Info(constants.MAINNET_API_URL, skip_ws=True)
        self.exchange = Exchange(
            Account.from_key(HL_SECRET_KEY),
            constants.MAINNET_API_URL,
            account_address=HL_ADDRESS,
        )

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
        self.current_sl_price  = None
        self.breakeven_reached = False
        self.short_min_price   = None
        self.open_trigger      = None

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

        # ── M2-40: Cooldown post external_close ─────────────────────────────
        self._ext_close_cooldown_until = 0.0

        # ── Position sync ─────────────────────────────────────────────────────
        self.last_hl_sync = 0.0
        self.last_lp_sync = 0.0

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

    def fetch_position_bounds(self):
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
        except Exception as e:
            print(f"❌ Error fetching position: {e}", flush=True)
            sys.exit(1)

    def get_eth_price(self):
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

    # M2-39: circuit breaker
    _CB_STOP_THRESHOLD    = 3     # consecutive SL/trailing stops before pause
    _CB_PAUSE_SECS        = 1200  # 20 minutes

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

            self.exchange.update_leverage(leverage, "ETH")
            order = self.exchange.market_open("ETH", False, size, slippage=0.01)

            if order is None:
                print(f"❌ market_open returned None", flush=True)
                log_event("error", price=price, details={
                    "msg": "market_open returned None — verify HL agent wallet is approved"
                })
                return

            if order["status"] == "ok":
                self._margin_fail_count    = 0
                self._margin_backoff_until = 0.0
                self.entry_price       = price
                self.hedge_size_eth    = size
                self.leverage_used     = leverage
                self.hedge_active      = True
                self.breakeven_reached = False
                self.short_min_price   = price
                self.open_trigger      = trigger
                self.current_sl_price  = price * (1 + DEFAULT_SL_PCT)

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

                log_event("hedge_opened", price=price, details={
                    "trigger":    trigger,
                    "entry":      self.entry_price,
                    "sl":         round(self.current_sl_price, 4),
                    "sl_oid":     self.hl_sl_order_id,
                    "tp_oid":     self.hl_tp_order_id,
                    "size_eth":   size,
                    "x_max":      round(x_max, 4),
                    "ratio_pct":  HEDGE_RATIO,
                    "leverage":   leverage,
                    "notional":   round(notional, 2),
                    "margin":     round(req_margin, 2),
                    "engine":     "v2",
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
                    f"Breakeven at: -{BREAKEVEN_PCT*100:.1f}% → trail {TRAIL_PCT*100:.1f}% from min",
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
                if new_sl < self.current_sl_price:
                    self.current_sl_price = new_sl
                    print(f"📉 Trail SL → ${self.current_sl_price:.2f} "
                          f"(min ${self.short_min_price:.2f} + {TRAIL_PCT*100:.1f}%)", flush=True)
                    # V2: cancel + replace native SL
                    self._replace_native_sl(self.current_sl_price)

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

        if not self.breakeven_reached and price <= self.entry_price * (1 - BREAKEVEN_PCT):
            self.breakeven_reached = True
            trail_sl              = self.short_min_price * (1 + TRAIL_PCT)
            self.current_sl_price = min(self.entry_price, trail_sl)
            pnl_est = (self.entry_price - price) / self.entry_price * 100
            print(f"🛡️  BREAKEVEN | Trail SL: ${self.current_sl_price:.2f}", flush=True)

            # V2: replace native SL at the new trail level
            self._replace_native_sl(self.current_sl_price)

            log_event("breakeven", price=price, pnl=pnl_est, details={
                "sl":        round(self.current_sl_price, 4),
                "sl_oid":    self.hl_sl_order_id,
                "min":       round(self.short_min_price, 4),
                "trail_pct": TRAIL_PCT * 100,
            })
            self.send_email(
                "Short Protected 🛡️ (Breakeven)",
                f"Short profit ≥ {BREAKEVEN_PCT*100:.0f}% — trailing SL activated.\n"
                f"NFT #{NFT_ID}\n"
                f"Entry:     ${self.entry_price:.2f}\n"
                f"Min price: ${self.short_min_price:.2f}\n"
                f"Trail SL:  ${self.current_sl_price:.2f} (OID: {self.hl_sl_order_id or 'none'})",
            )

    # ── Short close ────────────────────────────────────────────────────────────

    def close_hedge(self, price, reason):
        try:
            # V2: cancel native SL + TP before market close to avoid double-fill
            self._cancel_native_sl()
            self._cancel_native_tp()

            result = self.exchange.market_close("ETH")
            if result is None:
                # M2-40: native SL fired between polls — set cooldown
                self._ext_close_cooldown_until = time.time() + self._EXT_COOLDOWN_SECS
                # M2-39: external_close is a de-facto SL hit — count toward circuit breaker
                self._consecutive_stops += 1
                if self._consecutive_stops >= self._CB_STOP_THRESHOLD:
                    self._circuit_breaker_until = time.time() + self._CB_PAUSE_SECS
                    self._consecutive_stops = 0
                    log_event("circuit_breaker", price=price, details={
                        "reason":  f"{self._CB_STOP_THRESHOLD} consecutive stops (external_close)",
                        "pause_s": self._CB_PAUSE_SECS,
                    })
                    self.send_email(
                        "⚠️ Circuit Breaker Activated (M2-39)",
                        f"NFT #{NFT_ID}: {self._CB_STOP_THRESHOLD} consecutive external closes — "
                        f"pausing re-entry for {self._CB_PAUSE_SECS // 60} min.\nLast exit: ${price:.2f}",
                    )
                    print(f"🔴 [M2-39] Circuit breaker — pausing {self._CB_PAUSE_SECS // 60} min", flush=True)
                print(f"⚠️  market_close returned None — position already gone. Resetting.", flush=True)
                self._reset_short_state(price)
                log_event("stopped", price=price, details={
                    "reason":            "external_close",
                    "note":              "HL position not found — native SL fired or manual close",
                    "cooldown":          self._EXT_COOLDOWN_SECS,
                    "consecutive_stops": self._consecutive_stops,
                })
                self.send_email("⚠️ Hedge Externally Closed",
                    f"NFT #{NFT_ID}: HL SHORT not found during close attempt.\n"
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
                close_price = price
                self._reset_short_state(close_price)

                if not AUTO_REARM:
                    log_event("stopped", price=price, details={"reason": "auto_rearm_disabled"})
                    sys.exit(0)

                # M2-39: track consecutive stops for circuit breaker
                if reason in ("sl_hit", "trailing_stop"):
                    self._consecutive_stops += 1
                    if self._consecutive_stops >= self._CB_STOP_THRESHOLD:
                        self._circuit_breaker_until = time.time() + self._CB_PAUSE_SECS
                        self._consecutive_stops = 0
                        log_event("circuit_breaker", price=price, details={
                            "reason":   f"{self._CB_STOP_THRESHOLD} consecutive stops",
                            "pause_s":  self._CB_PAUSE_SECS,
                        })
                        self.send_email(
                            "⚠️ Circuit Breaker Activated (M2-39)",
                            f"NFT #{NFT_ID}: {self._CB_STOP_THRESHOLD} consecutive stops — "
                            f"pausing re-entry for {self._CB_PAUSE_SECS // 60} min.\n"
                            f"Last exit: ${close_price:.2f}",
                        )
                        print(f"🔴 [M2-39] Circuit breaker — pausing {self._CB_PAUSE_SECS // 60} min", flush=True)
                elif reason == "tp_hit":
                    self._consecutive_stops = 0  # clean win resets the counter

                pnl_str = f"{pnl_est:.2f}%" if pnl_est is not None else "n/a"
                cb_str  = f" | streak {self._consecutive_stops}/{self._CB_STOP_THRESHOLD}" if reason in ("sl_hit", "trailing_stop") else ""
                print(f"✅ SHORT CLOSED | Reason: {reason} | Exit: ${close_price:.2f} | PnL: {pnl_str}{cb_str}", flush=True)
                log_event(reason, price=price, pnl=pnl_est, details={
                    "reentry_guard":      round(self.reentry_guard_price, 4),
                    "consecutive_stops":  self._consecutive_stops,
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

    def _reset_short_state(self, close_price: float):
        """Reset all short-related state after a close."""
        self.hedge_active        = False
        self.breakeven_reached   = False
        self.short_min_price     = None
        self.open_trigger        = None
        self.hl_sl_order_id      = None
        self.hl_tp_order_id      = None
        self.reentry_guard_price = close_price * (1 + REENTRY_BUFFER)
        self.sl_close_price      = close_price
        self.price_was_above     = False

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
                # V2: cancel any orphan SL/TP orders before resetting
                self._cancel_native_sl()
                self._cancel_native_tp()
                # M2-40: set cooldown before re-arm
                self._ext_close_cooldown_until = time.time() + self._EXT_COOLDOWN_SECS
                # M2-39: external_close is a de-facto SL hit — count toward circuit breaker
                self._consecutive_stops += 1
                if self._consecutive_stops >= self._CB_STOP_THRESHOLD:
                    self._circuit_breaker_until = time.time() + self._CB_PAUSE_SECS
                    self._consecutive_stops = 0
                    log_event("circuit_breaker", price=price, details={
                        "reason":  f"{self._CB_STOP_THRESHOLD} consecutive stops (external_close/sync)",
                        "pause_s": self._CB_PAUSE_SECS,
                    })
                    self.send_email(
                        "⚠️ Circuit Breaker Activated (M2-39)",
                        f"NFT #{NFT_ID}: {self._CB_STOP_THRESHOLD} consecutive external closes — "
                        f"pausing re-entry for {self._CB_PAUSE_SECS // 60} min.\nLast exit: ${price:.2f}",
                    )
                    print(f"🔴 [M2-39] Circuit breaker — pausing {self._CB_PAUSE_SECS // 60} min", flush=True)
                self._reset_short_state(price)
                log_event("stopped", price=price, details={
                    "reason":            "external_close",
                    "note":              "HL position not found during periodic sync",
                    "cooldown":          self._EXT_COOLDOWN_SECS,
                    "consecutive_stops": self._consecutive_stops,
                })
                self.send_email("⚠️ Hedge Externally Closed (sync)",
                    f"NFT #{NFT_ID}: ETH SHORT disappeared during routine sync.\n"
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

            # Recover bot state — start SL trail conservatively from entry
            self.hedge_active      = True
            self.entry_price       = entry_px
            self.hedge_size_eth    = size
            self.leverage_used     = lev_val
            self.current_sl_price  = entry_px * (1 + DEFAULT_SL_PCT)
            self.breakeven_reached = False
            self.short_min_price   = entry_px
            self.open_trigger      = "recovered"

            # Check for existing SL and TP orders on HL
            try:
                open_orders = self.info.open_orders(HL_ADDRESS)
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

            log_event("orphan_recovered", price=entry_px, details={
                "entry":   entry_px,
                "size":    size,
                "sl":      round(self.current_sl_price, 4),
                "sl_oid":  self.hl_sl_order_id,
                "tp_oid":  self.hl_tp_order_id,
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

        self.fetch_position_bounds()

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
        print(f"📐 Mode:          {BOT_MODE} | from_above={'ON' if FROM_ABOVE_ENABLED else 'OFF'}", flush=True)
        print(f"📐 SL: {DEFAULT_SL_PCT*100:.2f}% | "
              f"TP: {TP_PCT*100:.2f}% (fixed)" if TP_PCT else f"📐 SL: {DEFAULT_SL_PCT*100:.2f}% | TP: off",
              flush=True)
        print(f"📐 Trailing: {'on' if TRAILING_STOP else 'OFF'} | "
              f"Breakeven: {BREAKEVEN_PCT*100:.1f}% | Trail: {TRAIL_PCT*100:.1f}%", flush=True)
        print(f"📐 [V2] Native HL SL: enabled | Cancel+replace on trail: enabled", flush=True)

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
            if self.hedge_active and now - self.last_lp_sync > HL_SYNC_INTERVAL:
                self.last_lp_sync = now
                self._sync_lp_position(price or 0)

            if self.hedge_active and now - self.last_hl_sync > HL_SYNC_INTERVAL:
                self.last_hl_sync = now
                self._sync_hl_position(price or 0)

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
                    # M2-39: circuit breaker check
                    if now < self._circuit_breaker_until:
                        remaining = int(self._circuit_breaker_until - now)
                        print(f"🔴 [M2-39] Circuit breaker active — {remaining}s remaining",
                              end="\r", flush=True)
                    # M2-40: post-external_close cooldown check
                    elif now < self._ext_close_cooldown_until:
                        remaining = int(self._ext_close_cooldown_until - now)
                        print(f"⏸️  [M2-40] Ext-close cooldown — {remaining}s remaining",
                              end="\r", flush=True)
                    else:
                        opened = False

                        if FROM_ABOVE_ENABLED and self.price_was_above and price <= upper_trigger:
                            self.open_hedge(price, trigger="from_above")
                            self.price_was_above = False
                            opened = True

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
                        short_status = f"🔴 CIRCUIT BREAKER ({int(self._circuit_breaker_until - now)}s)"
                    elif now < self._ext_close_cooldown_until:
                        short_status = f"⏸️  EXT COOLDOWN ({int(self._ext_close_cooldown_until - now)}s)"
                    else:
                        guard = f"guard ${self.reentry_guard_price:.2f}" if self.reentry_guard_price else "ready"
                        armed = " | ↓armed" if self.price_was_above else ""
                        short_status = f"⚪ IDLE ({guard}{armed})"

                print(
                    f"[{time.strftime('%H:%M:%S')}] ETH ${price:.2f} | "
                    f"{zone} | {short_status} [V2]",
                    end="\r", flush=True,
                )

            time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    bot = LiveHedgeBotV2()
    bot.run()
