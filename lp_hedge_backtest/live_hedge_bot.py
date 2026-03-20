"""
VIZNAGO FURY — Bot Aragan / Avaro
Live LP + Perps Hedge Bot

All configuration is read from environment variables so the SaaS
BotManager can spawn isolated per-user processes.

Required env vars (set by BotManager or .env for single-user mode):
    HYPERLIQUID_SECRET_KEY    — HL API-wallet private key
    HYPERLIQUID_ACCOUNT_ADDRESS — HL main wallet address

Optional env vars (have sensible defaults):
    UNISWAP_NFT_ID            — Uniswap v3 NFT token ID  (default: 5364087)
    ARBITRUM_RPC_URL          — Arbitrum JSON-RPC URL
    LOWER_BOUND               — LP range floor in USD    (auto-fetch if absent)
    UPPER_BOUND               — LP range ceiling in USD  (auto-fetch if absent)
    TRIGGER_OFFSET_PCT        — % below floor to trigger short (default: 0.5)
    HEDGE_SIZE_ETH            — ETH size per hedge order  (default: 0.05)
    LEVERAGE                  — Leverage for short        (default: 10)
    SL_PCT                    — Stop-loss %               (default: 0.5)
    BREAKEVEN_PCT             — Profit % to move SL to entry (default: 1.0)
    BOT_MODE                  — aragan | avaro            (default: aragan)
    CHECK_INTERVAL            — Price-check interval secs (default: 30)
    CONFIG_ID                 — SaaS bot_config row ID    (optional, for logging)
    EMAIL_RECIPIENTS          — Comma-separated email list (overrides default)
"""

import os
import sys
import time
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from decimal import Decimal
from dotenv import load_dotenv
from web3 import Web3
from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

load_dotenv()

# ── Required ──────────────────────────────────────────────────────────────
HL_SECRET_KEY = os.getenv("HYPERLIQUID_SECRET_KEY")
HL_ADDRESS    = os.getenv("HYPERLIQUID_ACCOUNT_ADDRESS")

if not HL_SECRET_KEY or not HL_ADDRESS:
    print("❌ HYPERLIQUID_SECRET_KEY and HYPERLIQUID_ACCOUNT_ADDRESS are required.", flush=True)
    sys.exit(1)

# ── Optional with defaults ────────────────────────────────────────────────
RPC_URL        = os.getenv("ARBITRUM_RPC_URL",      "https://arb1.arbitrum.io/rpc")
NFT_ID         = int(os.getenv("UNISWAP_NFT_ID",    "5364087"))
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL",    "30"))
TRIGGER_OFFSET = float(os.getenv("TRIGGER_OFFSET_PCT", "0.5")) / 100.0
HEDGE_SIZE_ETH = float(os.getenv("HEDGE_SIZE_ETH",  "0.05"))
LEVERAGE       = int(os.getenv("LEVERAGE",          "10"))
DEFAULT_SL_PCT = float(os.getenv("SL_PCT",          "0.5")) / 100.0
BREAKEVEN_PCT  = float(os.getenv("BREAKEVEN_PCT",   "1.0")) / 100.0
BOT_MODE       = os.getenv("BOT_MODE",              "aragan").lower()
CONFIG_ID      = os.getenv("CONFIG_ID")             # SaaS: bot_config row id

# Bounds can be pre-loaded by BotManager (saves an RPC call) or auto-fetched
LOWER_BOUND_ENV = os.getenv("LOWER_BOUND")
UPPER_BOUND_ENV = os.getenv("UPPER_BOUND")

# Email
EMAIL_CONFIG_PATH = os.getenv("EMAIL_CONFIG_PATH", "/var/www/dev/trading/email_config.json")
_recipients_env   = os.getenv("EMAIL_RECIPIENTS", "")
RECIPIENTS = (
    [r.strip() for r in _recipients_env.split(",") if r.strip()]
    or ["perdomo.gustavo@gmail.com", "carlosam81@gmail.com"]
)

# ── Uniswap v3 Position Manager ABI (minimal) ─────────────────────────────
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

# ── Structured event logging (parsed by BotManager tail loop) ─────────────
def log_event(event_type: str, price: float = None, pnl: float = None, details: dict = None):
    """
    Emit a machine-readable JSON line to stdout.
    BotManager reads these lines and writes them to bot_events table.
    Format: {"event": "...", "price": ..., "pnl": ..., "details": {...}}
    """
    record = {"event": event_type}
    if price   is not None: record["price"]   = round(price, 4)
    if pnl     is not None: record["pnl"]     = round(pnl, 4)
    if details is not None: record["details"] = details
    if CONFIG_ID:            record["config_id"] = CONFIG_ID
    print(f"[EVENT] {json.dumps(record)}", flush=True)


class LiveHedgeBot:
    def __init__(self):
        print(f"⚙️  Initializing Bot Aragan v1.3 | NFT #{NFT_ID} | Mode: {BOT_MODE.upper()}", flush=True)
        self.w3           = Web3(Web3.HTTPProvider(RPC_URL))
        self.contract     = self.w3.eth.contract(address=V3_POS_MANAGER, abi=V3_ABI)
        self.info         = Info(constants.MAINNET_API_URL, skip_ws=True)
        self.exchange     = Exchange(
            Account.from_key(HL_SECRET_KEY),
            constants.MAINNET_API_URL,
            account_address=HL_ADDRESS,
        )
        self.hedge_active      = False
        self.entry_price       = None
        self.current_sl_price  = None
        self.breakeven_reached = False
        self.lower_bound       = float(LOWER_BOUND_ENV) if LOWER_BOUND_ENV else None
        self.upper_bound       = float(UPPER_BOUND_ENV) if UPPER_BOUND_ENV else None
        self.email_config      = self._load_email_config()

    # ── Email ──────────────────────────────────────────────────────────────

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
            msg["Subject"] = f"🛡️ [Hedge Bot v1.3] {subject}"
            msg.attach(MIMEText(body, "plain"))
            server = smtplib.SMTP(self.email_config["smtp_server"], self.email_config["smtp_port"])
            server.starttls()
            server.login(self.email_config["smtp_username"], self.email_config["smtp_password"])
            server.send_message(msg)
            server.quit()
            print(f"📧 Email sent to {len(RECIPIENTS)} recipients", flush=True)
        except Exception as e:
            print(f"❌ Email failed: {e}", flush=True)

    # ── On-chain ───────────────────────────────────────────────────────────

    def fetch_position_bounds(self):
        """Fetch lower/upper bounds from chain. Only called if not pre-loaded."""
        try:
            pos = self.contract.functions.positions(NFT_ID).call()
            self.lower_bound = tick_to_price(pos[5])
            self.upper_bound = tick_to_price(pos[6])
            print(f"✅ Range fetched: ${self.lower_bound:.2f} — ${self.upper_bound:.2f}", flush=True)
        except Exception as e:
            print(f"❌ Error fetching position bounds: {e}", flush=True)
            sys.exit(1)

    def get_eth_price(self):
        try:
            return float(self.info.all_mids()["ETH"])
        except Exception:
            return None

    # ── Hedge logic ────────────────────────────────────────────────────────

    def open_hedge(self, price):
        print(f"🚨 TRIGGERED: ETH ${price:.2f} below range floor ${self.lower_bound:.2f}", flush=True)
        try:
            self.exchange.update_leverage(LEVERAGE, "ETH")
            result = self.exchange.market_open("ETH", False, HEDGE_SIZE_ETH, slippage=0.01)
            if result["status"] == "ok":
                self.entry_price       = price
                self.hedge_active      = True
                self.breakeven_reached = False
                self.current_sl_price  = max(
                    self.entry_price * (1 + DEFAULT_SL_PCT),
                    self.lower_bound
                )
                print(f"✅ Hedge OPENED | Entry: ${self.entry_price:.2f} | SL: ${self.current_sl_price:.2f}", flush=True)
                log_event("hedge_opened", price=price, details={
                    "entry": self.entry_price, "sl": self.current_sl_price,
                    "size": HEDGE_SIZE_ETH, "leverage": LEVERAGE,
                })
                self.send_email(
                    "Hedge OPENED 🚨",
                    f"10x SHORT opened\nEntry: ${self.entry_price:.2f}\nSL: ${self.current_sl_price:.2f}\nNFT #{NFT_ID}",
                )
            else:
                print(f"❌ Order failed: {result}", flush=True)
                log_event("error", price=price, details={"msg": str(result)})
        except Exception as e:
            print(f"❌ open_hedge error: {e}", flush=True)
            log_event("error", price=price, details={"msg": str(e)})

    def manage_active_hedge(self, price):
        # A. Stop loss
        if price >= self.current_sl_price:
            print(f"🛑 STOP LOSS at ${price:.2f}", flush=True)
            self.close_hedge(price, reason="sl_hit")
            return

        # B. Breakeven (short profit ≥ BREAKEVEN_PCT)
        if not self.breakeven_reached and price <= self.entry_price * (1 - BREAKEVEN_PCT):
            self.current_sl_price  = self.entry_price
            self.breakeven_reached = True
            pnl_est = (self.entry_price - price) / self.entry_price * 100
            print(f"🛡️  BREAKEVEN — SL moved to entry ${self.entry_price:.2f}", flush=True)
            log_event("breakeven", price=price, pnl=pnl_est)
            self.send_email(
                "Hedge Protected 🛡️",
                f"Short profit ≥ {BREAKEVEN_PCT*100:.0f}%. SL moved to entry ${self.entry_price:.2f}. Trade is risk-free.",
            )

        # C. Take profit — price back inside range
        if price >= self.lower_bound:
            print(f"🎉 TAKE PROFIT at ${price:.2f}", flush=True)
            self.close_hedge(price, reason="tp_hit")

    def close_hedge(self, price, reason):
        try:
            result = self.exchange.market_close("ETH")
            if result["status"] == "ok":
                pnl_est = (self.entry_price - price) / self.entry_price * 100 if self.entry_price else None
                self.hedge_active = False
                print(f"✅ Hedge CLOSED | Reason: {reason} | Exit: ${price:.2f}", flush=True)
                log_event(reason, price=price, pnl=pnl_est)
                self.send_email(
                    f"Hedge CLOSED ✅ ({reason})",
                    f"Reason: {reason}\nExit: ${price:.2f}\nNFT #{NFT_ID} is now unprotected.",
                )
            else:
                print(f"❌ Close failed: {result}", flush=True)
                log_event("error", price=price, details={"msg": str(result)})
        except Exception as e:
            print(f"❌ close_hedge error: {e}", flush=True)
            log_event("error", price=price, details={"msg": str(e)})

    # ── Main loop ──────────────────────────────────────────────────────────

    def run(self):
        print(f"🚀 Bot Aragan v1.3 starting | NFT #{NFT_ID} | {BOT_MODE.upper()} mode", flush=True)

        if self.lower_bound is None or self.upper_bound is None:
            self.fetch_position_bounds()

        trigger_price = self.lower_bound * (1 - TRIGGER_OFFSET)
        print(f"📐 Range: ${self.lower_bound:.2f} — ${self.upper_bound:.2f} | Trigger: ${trigger_price:.2f}", flush=True)

        log_event("started", details={
            "nft_id": NFT_ID, "lower": self.lower_bound, "upper": self.upper_bound,
            "trigger": trigger_price, "mode": BOT_MODE,
        })
        self.send_email(
            "Bot v1.3 Started 🚀",
            f"NFT #{NFT_ID}\nRange: ${self.lower_bound:.2f} — ${self.upper_bound:.2f}\nTrigger: ${trigger_price:.2f}\nMode: {BOT_MODE.upper()}",
        )

        while True:
            price = self.get_eth_price()
            if price:
                if not self.hedge_active:
                    if price <= trigger_price:
                        self.open_hedge(price)
                else:
                    self.manage_active_hedge(price)

                status = "🟢 IN RANGE" if price >= self.lower_bound else "🔴 OUT OF RANGE"
                hedge  = "🛡️ ON" if self.hedge_active else "⚪ OFF"
                print(f"[{time.strftime('%H:%M:%S')}] ETH: ${price:.2f} | {status} | Hedge: {hedge}", end="\r", flush=True)

            time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    bot = LiveHedgeBot()
    bot.run()
