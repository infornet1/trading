"""
VIZNAGO — Bot Defensor Bajista
LP + Directional Bear Hedge Bot

Strategy overview:
  - Provide liquidity on Uniswap v3 (ETH/USDC, Arbitrum, 0.05% fee)
  - Open SHORT on Hyperliquid in two scenarios:
      1. Price crosses UPPER bound downward (entry from above)
      2. Price breaks BELOW lower bound (classic IL protection)
  - One unified trailing SL manages the exit in both cases
  - No fixed Take Profit — the trailing SL locks in profits dynamically
  - Re-entry only on fresh confirmed signals

Required env vars:
    HYPERLIQUID_SECRET_KEY      — HL API-wallet private key
    HYPERLIQUID_ACCOUNT_ADDRESS — HL main wallet address

Optional env vars (sensible defaults shown):
    UNISWAP_NFT_ID            — Uniswap v3 NFT token ID     (default: 5364087)
    ARBITRUM_RPC_URL          — Arbitrum JSON-RPC URL
    CHECK_INTERVAL            — Price-check interval secs    (default: 30)
    CONFIG_ID                 — SaaS bot_config row ID       (optional)
    EMAIL_RECIPIENTS          — Comma-separated email list

Entry parameters:
    TRIGGER_OFFSET_PCT        — % below lower bound → short  (default: 0.5)
    UPPER_BUFFER_PCT          — % below upper bound → short  (default: 2.0)
                                (avoids false entries on brief dips into range)

Position sizing:
    HEDGE_RATIO               — % of X_max ETH to short      (default: 50.0)
    MAX_LEVERAGE              — Hard cap on leverage          (default: 10)
    MARGIN_BUFFER             — Safety margin multiplier      (default: 1.5)

Exit / SL parameters:
    SL_PCT                    — Initial hard SL above entry  (default: 0.5)
    BREAKEVEN_PCT             — Profit % to activate trail   (default: 1.0)
    TRAIL_PCT                 — Trail % above min price      (default: 1.5)
                                After breakeven:
                                  SL = min(entry, short_min × (1 + TRAIL_PCT))
                                  Moves DOWN as price falls, never back up.

Re-entry guard:
    REENTRY_BUFFER_PCT        — Price must rise this % above close price
                                before lower-break trigger can fire again (default: 0.5)

Bounds refresh:
    BOUNDS_REFRESH_HOURS      — Re-fetch LP range every N hours when idle (default: 4)
"""

import math
import os
import sys
import time
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from web3 import Web3
from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

# ── Required ──────────────────────────────────────────────────────────────────
# All config is injected via environment variables by BotManager (api/bot_manager.py).
# This script must NOT be run directly — always launched by the API.
HL_SECRET_KEY = os.getenv("HYPERLIQUID_SECRET_KEY")
HL_ADDRESS    = os.getenv("HYPERLIQUID_ACCOUNT_ADDRESS")

if not HL_SECRET_KEY or not HL_ADDRESS:
    print("❌ HYPERLIQUID_SECRET_KEY and HYPERLIQUID_ACCOUNT_ADDRESS are required.", flush=True)
    sys.exit(1)

# ── Optional with defaults ─────────────────────────────────────────────────────
RPC_URL             = os.getenv("ARBITRUM_RPC_URL",          "https://arb1.arbitrum.io/rpc")
NFT_ID              = int(os.getenv("UNISWAP_NFT_ID",        "5364087"))
CHECK_INTERVAL      = int(os.getenv("CHECK_INTERVAL",          "30"))
CONFIG_ID           = os.getenv("CONFIG_ID")
BOUNDS_REFRESH_H    = int(os.getenv("BOUNDS_REFRESH_HOURS",   "4"))

# Entry
TRIGGER_OFFSET      = float(os.getenv("TRIGGER_OFFSET_PCT",    "0.5")) / 100.0
UPPER_BUFFER        = float(os.getenv("UPPER_BUFFER_PCT",       "2.0")) / 100.0

# Sizing
HEDGE_RATIO         = float(os.getenv("HEDGE_RATIO",           "50.0"))
TARGET_LEVERAGE     = int(os.getenv("TARGET_LEVERAGE",         "10"))   # user-set target
MAX_LEVERAGE        = 15                                                  # hard cap, non-configurable
MARGIN_BUFFER       = float(os.getenv("MARGIN_BUFFER",          "1.5"))

# SL / trail
# Minimum SL floor: anything below 0.3% is smaller than normal price noise on HL
# and will trigger immediately (whipsaw). The user-set value is clamped to this floor.
_SL_FLOOR_PCT       = 0.003   # 0.3% hard minimum — never configurable
DEFAULT_SL_PCT      = max(float(os.getenv("SL_PCT", "0.5")) / 100.0, _SL_FLOOR_PCT)
BREAKEVEN_PCT       = float(os.getenv("BREAKEVEN_PCT",          "1.0")) / 100.0
TRAIL_PCT           = float(os.getenv("TRAIL_PCT",              "1.5")) / 100.0
REENTRY_BUFFER      = float(os.getenv("REENTRY_BUFFER_PCT",     "0.5")) / 100.0

# Optional TP (empty string = disabled)
_tp_env             = os.getenv("TP_PCT", "").strip()
TP_PCT              = float(_tp_env) / 100.0 if _tp_env else None

# Feature flags
TRAILING_STOP       = os.getenv("TRAILING_STOP", "1").strip() not in ("0", "false", "False")
AUTO_REARM          = os.getenv("AUTO_REARM",    "1").strip() not in ("0", "false", "False")

MIN_HEDGE_ETH = 0.001

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
    """Max ETH the LP holds when price is at lower bound (100% ETH, worst-case IL)."""
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


class LiveHedgeBot:
    def __init__(self):
        print(f"⚙️  Initializing VIZNAGO Defensor Bajista | NFT #{NFT_ID}", flush=True)
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
        self.current_sl_price  = None  # SL level — fires when price >= this
        self.breakeven_reached = False
        self.short_min_price   = None  # lowest price seen while short is active
        self.open_trigger      = None  # "from_above" | "below_range"

        # ── Direction tracking (for entry-from-above trigger) ──────────────
        # True when price has been above upper_bound since last reset.
        # Resets to False after a short is opened via this trigger,
        # or when price falls below lower_bound without triggering.
        self.price_was_above   = False

        # ── Re-entry guard (for below-range trigger) ───────────────────────
        # After a short closes, price must recover above this level before
        # the below-range trigger can fire again. None = guard inactive.
        self.reentry_guard_price = None

        # ── Margin failure guard ────────────────────────────────────────────
        # Tracks consecutive "Sizing/margin check failed" outcomes.
        # After MAX_MARGIN_FAILURES consecutive failures, the bot backs off
        # for MARGIN_BACKOFF_SECS and sends a single email alert instead of
        # hammering the API every 30 s indefinitely.
        self._margin_fail_count    = 0
        self._margin_backoff_until = 0.0   # epoch seconds; 0 = not in backoff

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
            msg["Subject"] = f"🛡️ [VIZNAGO Defensor Bajista] {subject}"
            msg.attach(MIMEText(body, "plain"))
            s = smtplib.SMTP(self.email_config["smtp_server"], self.email_config["smtp_port"])
            s.starttls()
            s.login(self.email_config["smtp_username"], self.email_config["smtp_password"])
            s.send_message(msg)
            s.quit()
            print(f"📧 Email sent to {len(RECIPIENTS)} recipients", flush=True)
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

            # Unified accounts: spot USDC also backs perp positions.
            # Query spot and add USDC so the margin check works correctly.
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
                print(f"💰 HL balance: ${perp_balance:.2f} perp + ${spot_usdc:.2f} spot (unified) = ${total:.2f}", flush=True)
            return total
        except Exception as e:
            print(f"⚠️  Could not fetch HL margin: {e}", flush=True)
            return 0.0

    # ── Position sizing ────────────────────────────────────────────────────────

    def _calc_order_params(self, price):
        """
        Returns (size_eth, leverage, notional, required_margin, x_max)
        or None if sizing / margin checks fail.
        """
        x_max = calc_x_max_eth(self.liquidity, self.tick_lower, self.tick_upper)
        if x_max < MIN_HEDGE_ETH:
            print(f"⚠️  X_max {x_max:.4f} ETH below minimum — skipping", flush=True)
            return None

        size     = round(x_max * HEDGE_RATIO / 100.0, 4)
        size     = max(size, MIN_HEDGE_ETH)
        size     = round(min(size, x_max), 4)  # re-round after min to avoid float_to_wire error
        margin   = self.get_hl_margin_balance()
        notional = size * price

        if margin <= 0:
            print("❌ HL account has no margin", flush=True)
            self.send_email("⚠️ Short SKIPPED — No Margin",
                f"NFT #{NFT_ID}: HL API wallet has no USDC balance.\n"
                f"Please fund the wallet to enable hedging.")
            return None

        # Use user's target leverage (capped at hard MAX_LEVERAGE).
        # Auto-reduce step by step if margin is insufficient, logging a warning event.
        target_lev = min(TARGET_LEVERAGE, MAX_LEVERAGE)
        leverage   = target_lev

        required_margin = notional / leverage
        if margin < required_margin * MARGIN_BUFFER:
            # Try to find a lower leverage that fits
            reduced = False
            for lev in range(leverage + 1, MAX_LEVERAGE + 1):
                req = notional / lev
                if margin >= req * MARGIN_BUFFER:
                    log_event("error", details={
                        "warning": f"Leverage auto-increased from {target_lev}x to {lev}x — "
                                   f"insufficient margin (have ${margin:.2f}, "
                                   f"need ${(notional/target_lev)*MARGIN_BUFFER:.2f})"
                    })
                    self.send_email(
                        "⚠️ Leverage Auto-Increased",
                        f"NFT #{NFT_ID}: Target leverage {target_lev}x exceeded available margin.\n"
                        f"Auto-increased to {lev}x to fit margin.\n"
                        f"Available: ${margin:.2f} | Notional: ${notional:.2f}"
                    )
                    leverage        = lev
                    required_margin = req
                    reduced         = True
                    break

            if not reduced:
                print(f"❌ Insufficient margin even at {MAX_LEVERAGE}x: have ${margin:.2f}, "
                      f"need ${(notional/MAX_LEVERAGE)*MARGIN_BUFFER:.2f}", flush=True)
                self.send_email("⚠️ Short SKIPPED — Low Margin",
                    f"NFT #{NFT_ID}: Not enough USDC even at {MAX_LEVERAGE}x leverage.\n"
                    f"Available: ${margin:.2f}\n"
                    f"Notional: ${notional:.2f}\n"
                    f"Min required: ${(notional/MAX_LEVERAGE)*MARGIN_BUFFER:.2f}")
                return None

        return size, leverage, notional, required_margin, x_max

    # ── Short open ─────────────────────────────────────────────────────────────

    # Margin failure guard constants
    _MAX_MARGIN_FAILURES  = 5      # consecutive failures before backoff
    _MARGIN_BACKOFF_SECS  = 300    # 5-minute pause after max failures

    def open_hedge(self, price, trigger):
        """
        trigger: "from_above" | "below_range"
        """
        # ── Margin failure backoff check ────────────────────────────────────
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
                    print(f"🔴 Margin failed {self._MAX_MARGIN_FAILURES}x — pausing "
                          f"{self._MARGIN_BACKOFF_SECS}s", flush=True)
                    log_event("error", price=price, details={
                        "msg": f"Margin check failed {self._MAX_MARGIN_FAILURES} times — "
                               f"pausing {self._MARGIN_BACKOFF_SECS}s. Fund HL wallet to resume."
                    })
                    self.send_email(
                        "⚠️ Bot Paused — Repeated Margin Failures",
                        f"NFT #{NFT_ID}: margin check failed {self._MAX_MARGIN_FAILURES} consecutive times.\n"
                        f"Bot paused for {self._MARGIN_BACKOFF_SECS // 60} minutes.\n\n"
                        f"Action required: fund the HL wallet ({HL_ADDRESS}) with USDC.\n"
                        f"Bot will resume automatically after the pause.",
                    )
                return
            size, leverage, notional, req_margin, x_max = params

            print(f"📐 Size: {size:.4f} ETH | X_max: {x_max:.4f} | "
                  f"Ratio: {HEDGE_RATIO}% | Leverage: {leverage}x | "
                  f"Notional: ${notional:.2f} | Margin: ${req_margin:.2f}", flush=True)

            self.exchange.update_leverage(leverage, "ETH")
            order = self.exchange.market_open("ETH", False, size, slippage=0.01)

            if order["status"] == "ok":
                self._margin_fail_count    = 0   # reset on successful open
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
                      f"SL: ${self.current_sl_price:.2f} | "
                      f"Trigger: {label}", flush=True)

                log_event("hedge_opened", price=price, details={
                    "trigger":   trigger,
                    "entry":     self.entry_price,
                    "sl":        round(self.current_sl_price, 4),
                    "size_eth":  size,
                    "x_max":     round(x_max, 4),
                    "ratio_pct": HEDGE_RATIO,
                    "leverage":  leverage,
                    "notional":  round(notional, 2),
                    "margin":    round(req_margin, 2),
                })
                self.send_email(
                    f"Short OPENED 🚨 ({label})",
                    f"SHORT opened on Hyperliquid\n"
                    f"Trigger:   {label}\n"
                    f"NFT:       #{NFT_ID}\n"
                    f"Entry:     ${self.entry_price:.2f}\n"
                    f"Size:      {size:.4f} ETH ({HEDGE_RATIO}% of {x_max:.4f} ETH max)\n"
                    f"Leverage:  {leverage}x\n"
                    f"Notional:  ${notional:.2f}\n"
                    f"Init SL:   ${self.current_sl_price:.2f} (+{DEFAULT_SL_PCT*100:.1f}%)\n"
                    f"Breakeven: at -{BREAKEVEN_PCT*100:.1f}% → trail {TRAIL_PCT*100:.1f}% from min",
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

            # Update trailing SL immediately when a new min is set (breakeven active)
            if self.breakeven_reached:
                trail_sl  = self.short_min_price * (1 + TRAIL_PCT)
                new_sl    = min(self.entry_price, trail_sl)
                # SL only moves DOWN (more protective), never back up
                if new_sl < self.current_sl_price:
                    self.current_sl_price = new_sl
                    print(f"📉 Trail SL → ${self.current_sl_price:.2f} "
                          f"(min ${self.short_min_price:.2f} + {TRAIL_PCT*100:.1f}%)",
                          flush=True)

        # ── 2. Fixed TP check (optional) ───────────────────────────────────
        if TP_PCT is not None:
            tp_price = self.entry_price * (1 - TP_PCT)
            if price <= tp_price:
                print(f"🎯 TP HIT at ${price:.2f} (target ${tp_price:.2f})", flush=True)
                self.close_hedge(price, reason="tp_hit")
                return

        # ── 3. SL check ────────────────────────────────────────────────────
        if price >= self.current_sl_price:
            reason = "trailing_stop" if self.breakeven_reached else "sl_hit"
            print(f"🛑 SL FIRED at ${price:.2f} | SL was ${self.current_sl_price:.2f}", flush=True)
            self.close_hedge(price, reason=reason)
            return

        # ── 4. Breakeven → activate trailing SL (only when enabled) ───────
        if not TRAILING_STOP:
            return  # fixed SL only — skip trailing logic

        if not self.breakeven_reached and price <= self.entry_price * (1 - BREAKEVEN_PCT):
            self.breakeven_reached = True
            # Set SL = min(entry, trail from current min)
            trail_sl              = self.short_min_price * (1 + TRAIL_PCT)
            self.current_sl_price = min(self.entry_price, trail_sl)
            pnl_est = (self.entry_price - price) / self.entry_price * 100
            print(f"🛡️  BREAKEVEN | Trail SL: ${self.current_sl_price:.2f} | "
                  f"Min: ${self.short_min_price:.2f}", flush=True)
            log_event("breakeven", price=price, pnl=pnl_est, details={
                "sl":       round(self.current_sl_price, 4),
                "min":      round(self.short_min_price, 4),
                "trail_pct": TRAIL_PCT * 100,
            })
            self.send_email(
                "Short Protected 🛡️ (Breakeven)",
                f"Short profit ≥ {BREAKEVEN_PCT*100:.0f}% — trailing SL activated.\n"
                f"NFT #{NFT_ID}\n"
                f"Entry:     ${self.entry_price:.2f}\n"
                f"Min price: ${self.short_min_price:.2f}\n"
                f"Trail SL:  ${self.current_sl_price:.2f} (trail {TRAIL_PCT*100:.1f}% from min)",
            )

    # ── Short close ────────────────────────────────────────────────────────────

    def close_hedge(self, price, reason):
        try:
            result = self.exchange.market_close("ETH")
            if result["status"] == "ok":
                pnl_est = (
                    (self.entry_price - price) / self.entry_price * 100
                    if self.entry_price else None
                )
                close_price = price

                # Reset short state
                self.hedge_active      = False
                self.breakeven_reached = False
                self.short_min_price   = None
                self.open_trigger      = None

                # Re-entry guard: price must recover above this before
                # the below-range trigger can fire again
                self.reentry_guard_price = close_price * (1 + REENTRY_BUFFER)

                # Reset direction flag so upper-cross trigger also needs a fresh setup
                self.price_was_above = False

                # If auto-rearm is disabled, stop the bot after the first close
                if not AUTO_REARM:
                    print("🛑 AUTO_REARM disabled — bot stopping after position close.", flush=True)
                    log_event("stopped", price=price, details={"reason": "auto_rearm_disabled"})
                    sys.exit(0)

                pnl_str = f"{pnl_est:.2f}%" if pnl_est is not None else "n/a"
                print(f"✅ SHORT CLOSED | Reason: {reason} | "
                      f"Exit: ${close_price:.2f} | PnL est: {pnl_str}", flush=True)
                log_event(reason, price=price, pnl=pnl_est, details={
                    "reentry_guard": round(self.reentry_guard_price, 4),
                })
                self.send_email(
                    f"Short CLOSED ✅ ({reason})",
                    f"Reason:  {reason}\n"
                    f"Exit:    ${close_price:.2f}\n"
                    f"PnL est: {pnl_str}\n"
                    f"NFT #{NFT_ID}\n\n"
                    f"Re-entry guard: price must recover above "
                    f"${self.reentry_guard_price:.2f} before next below-range short.",
                )
            else:
                print(f"❌ Close failed: {result}", flush=True)
                log_event("error", price=price, details={"msg": str(result)})
        except Exception as e:
            print(f"❌ close_hedge error: {e}", flush=True)
            log_event("error", price=price, details={"msg": str(e)})

    # ── Main loop ──────────────────────────────────────────────────────────────

    def run(self):
        print(f"🚀 VIZNAGO Defensor Bajista starting | NFT #{NFT_ID}", flush=True)

        self.fetch_position_bounds()

        lower_trigger = self.lower_bound * (1 - TRIGGER_OFFSET)
        upper_trigger = self.upper_bound * (1 - UPPER_BUFFER)   # 2% inside from top
        x_max         = calc_x_max_eth(self.liquidity, self.tick_lower, self.tick_upper)

        print(f"📐 Range:         ${self.lower_bound:.2f} — ${self.upper_bound:.2f}", flush=True)
        print(f"📐 Short triggers: BELOW ${lower_trigger:.2f} | "
              f"FROM ABOVE @ ${upper_trigger:.2f} (2% buffer)", flush=True)
        print(f"📐 X_max: {x_max:.4f} ETH | "
              f"Hedge ratio: {HEDGE_RATIO}% → {x_max * HEDGE_RATIO / 100:.4f} ETH | "
              f"Target leverage: {TARGET_LEVERAGE}x (hard cap {MAX_LEVERAGE}x)", flush=True)
        print(f"📐 SL: {DEFAULT_SL_PCT*100:.2f}% | "
              f"TP: {TP_PCT*100:.2f}% (fixed)" if TP_PCT else f"📐 SL: {DEFAULT_SL_PCT*100:.2f}% | TP: off",
              flush=True)
        print(f"📐 Trailing stop: {'on' if TRAILING_STOP else 'OFF'} | "
              f"Breakeven: {BREAKEVEN_PCT*100:.1f}% | Trail: {TRAIL_PCT*100:.1f}% | "
              f"Auto-rearm: {'on' if AUTO_REARM else 'OFF'}", flush=True)

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
            "trailing_stop":   TRAILING_STOP,
            "auto_rearm":      AUTO_REARM,
            "breakeven_pct":   BREAKEVEN_PCT * 100,
            "trail_pct":       TRAIL_PCT * 100,
        })
        self.send_email(
            "VIZNAGO Defensor Bajista Started 🚀",
            f"NFT #{NFT_ID}\n"
            f"Range:          ${self.lower_bound:.2f} — ${self.upper_bound:.2f}\n"
            f"Short triggers:\n"
            f"  1. FROM ABOVE @ ${upper_trigger:.2f} ({UPPER_BUFFER*100:.1f}% buffer)\n"
            f"  2. BELOW RANGE @ ${lower_trigger:.2f}\n"
            f"X_max ETH:      {x_max:.4f} ETH\n"
            f"Hedge ratio:    {HEDGE_RATIO}% → ~{x_max * HEDGE_RATIO / 100:.4f} ETH\n"
            f"Max leverage:   {MAX_LEVERAGE}x\n"
            f"Init SL:        {DEFAULT_SL_PCT*100:.1f}% above entry\n"
            f"Breakeven:      at {BREAKEVEN_PCT*100:.1f}% profit → trail activates\n"
            f"Trail:          {TRAIL_PCT*100:.1f}% above min price\n"
            f"Re-entry guard: {REENTRY_BUFFER*100:.1f}% recovery required after close",
        )

        while True:
            now   = time.time()
            price = self.get_eth_price()

            # ── Periodic bounds refresh (idle only) ──────────────────────────
            if (not self.hedge_active and
                    now - self.last_bounds_fetch > BOUNDS_REFRESH_H * 3600):
                old_lower, old_upper = self.lower_bound, self.upper_bound
                self.fetch_position_bounds()
                lower_trigger = self.lower_bound * (1 - TRIGGER_OFFSET)
                upper_trigger = self.upper_bound * (1 - UPPER_BUFFER)
                if self.lower_bound != old_lower or self.upper_bound != old_upper:
                    print(f"🔄 Range updated: "
                          f"${old_lower:.2f}–${old_upper:.2f} → "
                          f"${self.lower_bound:.2f}–${self.upper_bound:.2f}", flush=True)
                    log_event("bounds_refreshed", details={
                        "old_lower":  old_lower,  "old_upper":  old_upper,
                        "new_lower":  self.lower_bound,
                        "new_upper":  self.upper_bound,
                    })
                    self.send_email(
                        "LP Range Updated 🔄",
                        f"NFT #{NFT_ID} — range changed (idle refresh).\n"
                        f"Old: ${old_lower:.2f} — ${old_upper:.2f}\n"
                        f"New: ${self.lower_bound:.2f} — ${self.upper_bound:.2f}",
                    )

            if price:
                # ── Direction tracking ───────────────────────────────────────
                if price > self.upper_bound:
                    # Price is above range — arm the from-above trigger
                    if not self.price_was_above:
                        print(f"⬆️  Price above range (${price:.2f}) — "
                              f"from-above trigger armed", flush=True)
                    self.price_was_above = True
                elif price < self.lower_bound and self.price_was_above and not self.hedge_active:
                    # Price fell below range without triggering from-above — reset
                    self.price_was_above = False

                # ── Re-entry guard check ─────────────────────────────────────
                if self.reentry_guard_price and price >= self.reentry_guard_price:
                    print(f"🔓 Re-entry guard cleared at ${price:.2f} "
                          f"(was ${self.reentry_guard_price:.2f})", flush=True)
                    log_event("reentry_guard_cleared", price=price)
                    self.reentry_guard_price = None

                # ── Entry logic (no position open) ───────────────────────────
                if not self.hedge_active:
                    opened = False

                    # Trigger 1 — from above: price crosses upper_trigger downward
                    if self.price_was_above and price <= upper_trigger:
                        self.open_hedge(price, trigger="from_above")
                        self.price_was_above = False
                        opened = True

                    # Trigger 2 — below range: classic IL protection
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
                    be   = "BE✓" if self.breakeven_reached else "BE✗"
                    short_status = (
                        f"🛡️ SHORT {self.open_trigger} | "
                        f"min ${self.short_min_price:.2f} | "
                        f"SL ${self.current_sl_price:.2f} | {be}"
                    )
                else:
                    guard = f"guard ${self.reentry_guard_price:.2f}" if self.reentry_guard_price else "ready"
                    armed = " | ↓armed" if self.price_was_above else ""
                    short_status = f"⚪ IDLE ({guard}{armed})"

                print(
                    f"[{time.strftime('%H:%M:%S')}] ETH ${price:.2f} | "
                    f"{zone} | {short_status}",
                    end="\r", flush=True,
                )

            time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    bot = LiveHedgeBot()
    bot.run()
