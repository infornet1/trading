"""
VIZNIAGO POLY — Polymarket TP/SL Bot (Standalone Prediction-Market Bot)

Strategy overview:
  - Buys shares of a Polymarket outcome token (CLOB V2, Polygon).
  - Monitors the midpoint price and exits the full position automatically:
      price >= TP → market sell (take-profit)
      price <= SL → market sell (synthetic stop-loss)
  - Optional limit entry: rests a GTC limit buy until matched.
  - Crash-safe: open-position state is persisted to bot_state/ and restored
    on restart, so a respawned bot resumes monitoring instead of re-buying.

Required env vars (live mode):
    POLYMARKET_PRIVATE_KEY   — Polygon private key (order signing)
    POLYMARKET_FUNDER        — Polygon funder address holding USDC
    POLYMARKET_TOKEN_ID      — CLOB outcome token ID to buy
    POLYMARKET_SIZE_USD      — USDC amount to spend on entry
    POLYMARKET_TP_PRICE      — take-profit price (0-1)
    POLYMARKET_SL_PRICE      — stop-loss price (0-1)

Optional env vars (defaults shown):
    PAPER_TRADE            — Set to '1' for paper trading (no real orders) (default: 0)
    POLYMARKET_ENTRY_PRICE — Limit entry price; unset → market buy      (default: unset)
    CHECK_INTERVAL         — Seconds between price polls                (default: 10)
    CONFIG_ID              — SaaS bot_config row ID                     (optional)
    BOT_STATE_DIR          — State directory                            (default: ./bot_state)
"""

import json
import os
import signal
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Paper trade mode ──────────────────────────────────────────────────────────
PAPER_TRADE = os.getenv("PAPER_TRADE", "0") == "1"

# ── Config (validated in main) ────────────────────────────────────────────────
CONFIG_ID    = os.getenv("CONFIG_ID")
PRIVATE_KEY  = os.getenv("POLYMARKET_PRIVATE_KEY")
FUNDER       = os.getenv("POLYMARKET_FUNDER")
TOKEN_ID     = os.getenv("POLYMARKET_TOKEN_ID")
SIZE_USD     = float(os.getenv("POLYMARKET_SIZE_USD", "0") or 0)
TP_PRICE     = float(os.getenv("POLYMARKET_TP_PRICE", "0") or 0)
SL_PRICE     = float(os.getenv("POLYMARKET_SL_PRICE", "0") or 0)
ENTRY_PRICE  = os.getenv("POLYMARKET_ENTRY_PRICE")  # unset → market entry
ENTRY_PRICE  = float(ENTRY_PRICE) if ENTRY_PRICE else None

CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "10"))

CLOB_HOST = "https://clob.polymarket.com"
POLYGON_CHAIN_ID = 137

MAX_CONSECUTIVE_ERRORS = 20

STATE_DIR   = os.getenv("BOT_STATE_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_state"))
STATE_FILE  = os.path.join(STATE_DIR, f"poly_state_{CONFIG_ID or 'manual'}.json")

_client = None  # py_clob_client_v2 ClobClient, initialised in main()


def emit(event: str, price=None, pnl=None, details=None):
    """Emit a structured event line. BotManager parses [EVENT] prefix."""
    record = {"event": event, "config_id": CONFIG_ID, "ts": datetime.now(timezone.utc).isoformat()}
    if price is not None:
        record["price"] = price
    if pnl is not None:
        record["pnl"] = pnl
    if details is not None:
        record["details"] = details
    print(f"[EVENT] {json.dumps(record)}", flush=True)


def log(msg: str):
    print(f"[POLY] {msg}", flush=True)


# ── Pure helpers (unit-tested) ─────────────────────────────────────────────────

def check_exit(price: float, tp: float, sl: float):
    """Return 'tp' | 'sl' | None for the current price."""
    if price >= tp:
        return "tp"
    if price <= sl:
        return "sl"
    return None


def compute_pnl(shares: float, entry_price: float, exit_price: float) -> float:
    """USD PnL of a fully-closed long position in outcome shares."""
    return round(shares * (exit_price - entry_price), 4)


# ── State persistence (crash-safe resume) ──────────────────────────────────────

def _save_state(state: dict):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.replace(tmp, STATE_FILE)


def _load_state():
    if not os.path.exists(STATE_FILE):
        return None
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log(f"⚠️ Could not read state file ({e}) — starting fresh")
        return None


def _clear_state():
    try:
        os.remove(STATE_FILE)
    except FileNotFoundError:
        pass


# ── Market data ────────────────────────────────────────────────────────────────

def get_current_price() -> float:
    """Midpoint price of the token, falling back to the last trade price."""
    try:
        mid = _client.get_midpoint(TOKEN_ID)
        price = float(mid.get("mid") or mid.get("midpoint") or 0)
        if price > 0:
            return price
    except Exception as e:
        log(f"⚠️ midpoint fetch failed ({e}) — trying last trade price")
    last = _client.get_last_trade_price(TOKEN_ID)
    return float(last["price"])


# ── Order execution ────────────────────────────────────────────────────────────

def _parse_market_buy(resp: dict) -> tuple[float, float]:
    """Return (fill_price, shares) from a market BUY response."""
    making = float(resp.get("makingAmount") or 0)   # USDC spent
    taking = float(resp.get("takingAmount") or 0)   # shares received
    if making > 0 and taking > 0:
        return making / taking, taking
    price = get_current_price()
    return price, SIZE_USD / price


def enter_position() -> dict:
    """Open the position (or simulate it in paper mode). Returns state dict."""
    if PAPER_TRADE:
        fill = ENTRY_PRICE if ENTRY_PRICE else get_current_price()
        shares = SIZE_USD / fill
        log(f"📝 PAPER entry: {shares:.4f} shares @ ${fill:.4f} (${SIZE_USD:.2f})")
        return {"phase": "monitoring", "token_id": TOKEN_ID, "shares": shares,
                "entry_price": fill, "tp_price": TP_PRICE, "sl_price": SL_PRICE, "paper": True}

    from py_clob_client_v2.clob_types import MarketOrderArgsV2, OrderArgsV2, OrderType

    if ENTRY_PRICE is None:
        # Market entry — FOK market order sized in USDC
        log(f"📥 Market buy ${SIZE_USD:.2f} of token {TOKEN_ID[:12]}…")
        resp = _client.create_and_post_market_order(
            MarketOrderArgsV2(token_id=TOKEN_ID, amount=SIZE_USD, side="BUY", order_type=OrderType.FOK)
        )
        if not resp.get("success"):
            raise RuntimeError(f"market entry rejected: {resp}")
        fill, shares = _parse_market_buy(resp)
    else:
        # Limit entry — rest a GTC limit buy until matched
        shares = SIZE_USD / ENTRY_PRICE
        log(f"📥 Limit buy {shares:.4f} shares @ ${ENTRY_PRICE:.4f}…")
        resp = _client.create_and_post_order(
            OrderArgsV2(token_id=TOKEN_ID, price=ENTRY_PRICE, size=round(shares, 2), side="BUY"),
            order_type=OrderType.GTC,
        )
        if not resp.get("success"):
            raise RuntimeError(f"limit entry rejected: {resp}")
        order_id = resp["orderID"]
        log(f"⏳ Limit order {order_id} resting — waiting for fill…")
        while True:
            time.sleep(CHECK_INTERVAL)
            order = _client.get_order(order_id)
            status = order.get("status", "").upper()
            if status == "MATCHED":
                break
            if status in ("UNMATCHED", "CANCELED"):
                raise RuntimeError(f"limit entry ended with status {status}")
        fill = ENTRY_PRICE

    log(f"✅ Entry filled: {shares:.4f} shares @ ${fill:.4f}")
    return {"phase": "monitoring", "token_id": TOKEN_ID, "shares": shares,
            "entry_price": fill, "tp_price": TP_PRICE, "sl_price": SL_PRICE}


def exit_position(state: dict, reason: str) -> float:
    """Close the full position with a market sell. Returns exit price."""
    shares = state["shares"]
    if PAPER_TRADE or state.get("paper"):
        exit_price = get_current_price()
        log(f"📝 PAPER exit ({reason}): {shares:.4f} shares @ ${exit_price:.4f}")
        return exit_price

    from py_clob_client_v2.clob_types import MarketOrderArgsV2, OrderType

    log(f"📤 Market sell {shares:.4f} shares ({reason})…")
    resp = _client.create_and_post_market_order(
        MarketOrderArgsV2(token_id=TOKEN_ID, amount=round(shares, 2), side="SELL", order_type=OrderType.FOK)
    )
    if not resp.get("success"):
        raise RuntimeError(f"exit rejected: {resp}")
    taking = float(resp.get("takingAmount") or 0)   # USDC received
    making = float(resp.get("makingAmount") or 0)   # shares sold
    exit_price = taking / making if taking > 0 and making > 0 else get_current_price()
    log(f"✅ Exit filled @ ${exit_price:.4f}")
    return exit_price


# ── Main loop ──────────────────────────────────────────────────────────────────

def _validate_config():
    missing = []
    if not TOKEN_ID:
        missing.append("POLYMARKET_TOKEN_ID")
    if SIZE_USD <= 0:
        missing.append("POLYMARKET_SIZE_USD")
    if not (0 < TP_PRICE < 1):
        missing.append("POLYMARKET_TP_PRICE (must be 0-1)")
    if not (0 < SL_PRICE < 1):
        missing.append("POLYMARKET_SL_PRICE (must be 0-1)")
    if TP_PRICE and SL_PRICE and TP_PRICE <= SL_PRICE:
        missing.append("POLYMARKET_TP_PRICE must be > POLYMARKET_SL_PRICE")
    if not PAPER_TRADE and (not PRIVATE_KEY or not FUNDER):
        missing.append("POLYMARKET_PRIVATE_KEY and POLYMARKET_FUNDER (or set PAPER_TRADE=1)")
    if missing:
        print(f"❌ Missing/invalid config: {', '.join(missing)}", flush=True)
        sys.exit(1)


def main():
    global _client
    _validate_config()

    from py_clob_client_v2.client import ClobClient

    if PAPER_TRADE:
        _client = ClobClient(CLOB_HOST, POLYGON_CHAIN_ID)  # keyless — public data only
    else:
        _client = ClobClient(CLOB_HOST, POLYGON_CHAIN_ID, key=PRIVATE_KEY, funder=FUNDER)
        _client.set_api_creds(_client.create_or_derive_api_key())

    def _on_stop(signum, frame):
        # No "stopped" event here: the position stays open and BotTrade would
        # wrongly close the trade row. A respawned bot resumes monitoring.
        log(f"Received signal {signum} — stopping (position left open, state kept)")
        sys.exit(0)

    signal.signal(signal.SIGTERM, _on_stop)
    signal.signal(signal.SIGINT, _on_stop)

    emit("started", details={
        "token_id": TOKEN_ID, "size_usd": SIZE_USD,
        "tp": TP_PRICE, "sl": SL_PRICE,
        "entry_price": ENTRY_PRICE, "paper": PAPER_TRADE,
    })

    # Resume an open position after a crash/respawn instead of re-buying
    state = _load_state()
    if state and state.get("phase") == "monitoring" and state.get("token_id") == TOKEN_ID:
        log(f"♻️ Resumed open position: {state['shares']:.4f} shares @ ${state['entry_price']:.4f}")
    else:
        state = enter_position()
        _save_state(state)
        emit("poly_entry", price=state["entry_price"], details={
            "side": "buy", "size_usd": SIZE_USD, "shares": state["shares"],
            "entry": state["entry_price"], "token_id": TOKEN_ID,
            "tp": TP_PRICE, "sl": SL_PRICE, "paper": PAPER_TRADE or state.get("paper", False),
        })

    log(f"👁 Monitoring — TP ${TP_PRICE:.4f} / SL ${SL_PRICE:.4f} every {CHECK_INTERVAL}s")
    errors = 0
    while True:
        try:
            price = get_current_price()
            reason = check_exit(price, TP_PRICE, SL_PRICE)
            if reason:
                exit_price = exit_position(state, reason)
                pnl = compute_pnl(state["shares"], state["entry_price"], exit_price)
                emit(f"poly_{reason}", price=exit_price, pnl=pnl, details={
                    "side": "sell", "shares": state["shares"], "entry": state["entry_price"],
                    "token_id": TOKEN_ID, "paper": PAPER_TRADE or state.get("paper", False),
                })
                _clear_state()
                log(f"🏁 {reason.upper()} exit @ ${exit_price:.4f} | PnL ${pnl:+.4f} — done")
                return
            errors = 0
        except Exception as e:
            errors += 1
            log(f"⚠️ monitor error ({errors}/{MAX_CONSECUTIVE_ERRORS}): {e}")
            if errors >= MAX_CONSECUTIVE_ERRORS:
                emit("error", details={"error": str(e), "consecutive_errors": errors})
                sys.exit(1)
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
