"""
VIZNAGO FURY — RSI Trader (Standalone Perps Bot)

Strategy overview:
  - No LP position required — pure Hyperliquid perps on BTC or ETH
  - 6-gate signal stack on 15-minute candles with 1-hour MTF confirmation:
      Gate 1 (Trend):   EMA-8 vs EMA-21 direction
      Gate 2 (RSI):     RSI(9/OHLC4) < 35 long | > 65 short on 15m
      Gate 3 (MTF):     1h RSI confirms direction (< 50 long, > 50 short)
      Gate 4 (Volume):  Candle volume > 20-bar SMA
      Gate 5 (OBV):     5-bar OBV slope > 0 (longs only)
      Gate 6 (Funding): Funding rate bias (> +0.05% → SHORT only)
  - Dynamic leverage: gates 3=3x, 4=5x, 5=8x, 6=12x
  - ATR-12 hybrid stop: min(max(1.5×ATR, floor), ceiling)
  - Target: 3R (3× stop distance)
  - BTC golden rule: LONG-only always enforced
  - Circuit breaker: pause on 5% daily drawdown OR 3 consecutive losses

Required env vars (live mode):
    HYPERLIQUID_SECRET_KEY       — HL API-wallet private key
    HYPERLIQUID_ACCOUNT_ADDRESS  — HL main wallet address
    FURY_SYMBOL                  — 'BTC' | 'ETH'

Optional env vars (defaults shown):
    PAPER_TRADE        — Set to '1' for paper trading (no real orders)  (default: 0)
    PAPER_BALANCE      — Starting paper balance in USDC                 (default: 1000)
    CHECK_INTERVAL     — Seconds between price loops       (default: 60)
    CONFIG_ID          — SaaS bot_config row ID            (optional)
    EMAIL_RECIPIENTS   — Comma-separated email list        (optional)
    FURY_RSI_PERIOD    — RSI period                        (default: 9)
    FURY_RSI_LONG_TH   — RSI oversold threshold for longs  (default: 35)
    FURY_RSI_SHORT_TH  — RSI overbought threshold for shorts (default: 65)
    FURY_ATR_PERIOD    — ATR period                        (default: 12)
    FURY_ATR_MULT      — ATR stop multiplier               (default: 1.5)
    FURY_LEVERAGE_MAX  — Hard cap on leverage              (default: 12)
    FURY_RISK_PCT      — % of account risked per trade     (default: 2.0)
    FURY_MIN_GATES     — Minimum gates to open position    (default: 3)
    CANDLE_LIMIT       — How many 15m candles to fetch     (default: 100)
    CANDLE_LIMIT_1H    — How many 1h candles to fetch      (default: 50)

Signal computation rule:
    RSI and all indicators are computed ONLY on confirmed closed candles.
    The current (in-progress) candle is NEVER used for signal decisions.
    This prevents repainting.
"""

import json
import os
import sys
import time
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.data.price_fetcher import PriceFetcher
from src.indicators.technical import add_fury_indicators
from src.hedge.standalone_perps_simulator import _ATR_FLOORS, _ATR_CEILINGS, _GATE_LEVERAGE

# ── Paper trade mode ──────────────────────────────────────────────────────────
PAPER_TRADE   = os.getenv("PAPER_TRADE", "0") == "1"
PAPER_BALANCE = float(os.getenv("PAPER_BALANCE", "1000.0"))

# ── Required ──────────────────────────────────────────────────────────────────
HL_SECRET_KEY = os.getenv("HYPERLIQUID_SECRET_KEY")
HL_ADDRESS    = os.getenv("HYPERLIQUID_ACCOUNT_ADDRESS")
FURY_SYMBOL   = os.getenv("FURY_SYMBOL", "ETH").upper()

if not PAPER_TRADE and (not HL_SECRET_KEY or not HL_ADDRESS):
    print("❌ HYPERLIQUID_SECRET_KEY and HYPERLIQUID_ACCOUNT_ADDRESS are required (or set PAPER_TRADE=1).", flush=True)
    sys.exit(1)

if FURY_SYMBOL not in ("BTC", "ETH"):
    print(f"❌ FURY_SYMBOL must be 'BTC' or 'ETH', got '{FURY_SYMBOL}'.", flush=True)
    sys.exit(1)

# ── Optional with defaults ─────────────────────────────────────────────────────
CHECK_INTERVAL  = int(os.getenv("CHECK_INTERVAL",     "60"))
CONFIG_ID       = os.getenv("CONFIG_ID")

RSI_PERIOD      = int(os.getenv("FURY_RSI_PERIOD",    "9"))
RSI_LONG_TH     = float(os.getenv("FURY_RSI_LONG_TH", "35"))
RSI_SHORT_TH    = float(os.getenv("FURY_RSI_SHORT_TH","65"))
ATR_PERIOD      = int(os.getenv("FURY_ATR_PERIOD",    "12"))
ATR_MULT        = float(os.getenv("FURY_ATR_MULT",    "1.5"))
LEVERAGE_MAX    = int(os.getenv("FURY_LEVERAGE_MAX",  "12"))
RISK_PCT        = float(os.getenv("FURY_RISK_PCT",    "2.0")) / 100
MIN_GATES       = int(os.getenv("FURY_MIN_GATES",     "3"))
CANDLE_LIMIT    = int(os.getenv("CANDLE_LIMIT",       "100"))
CANDLE_LIMIT_1H = int(os.getenv("CANDLE_LIMIT_1H",   "50"))

# Minimum avg trade gain to cover fees (0.05% × 2 sides = 0.10% RT)
MIN_AVG_GAIN_PCT = 0.004  # 0.4%

# ── Hyperliquid init ───────────────────────────────────────────────────────────
info = Info(constants.MAINNET_API_URL, skip_ws=True)
if PAPER_TRADE:
    exchange = None
else:
    _account  = Account.from_key(HL_SECRET_KEY)
    exchange  = Exchange(_account, constants.MAINNET_API_URL, account_address=HL_ADDRESS)

fetcher = PriceFetcher()


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
    print(f"[FURY/{FURY_SYMBOL}] {msg}", flush=True)


# ── State ──────────────────────────────────────────────────────────────────────
position = None          # dict when open: side, entry, sl, tp, size_contracts, leverage
consecutive_losses = 0
circuit_breaker = False
daily_reset_date = None
daily_start_balance = None

last_candle_ts_15m = None   # track last CLOSED 15m candle timestamp

# Paper trade state
_paper_balance = PAPER_BALANCE   # mutated by simulated closes


# ── Helpers ────────────────────────────────────────────────────────────────────

def get_balance() -> float:
    if PAPER_TRADE:
        return _paper_balance
    state = info.user_state(HL_ADDRESS)
    return float(state["marginSummary"]["accountValue"])


def get_price() -> float:
    return float(info.all_mids()[FURY_SYMBOL])


def atr_stop_distance(atr: float) -> float:
    raw = atr * ATR_MULT
    floor = _ATR_FLOORS[FURY_SYMBOL]
    ceiling = _ATR_CEILINGS[FURY_SYMBOL]
    return max(floor, min(raw, ceiling))


def get_leverage(gate_score: int) -> int:
    lev = _GATE_LEVERAGE.get(gate_score, 3)
    return min(lev, LEVERAGE_MAX)


def check_funding_bias() -> str | None:
    """Return 'SHORT' if funding rate > threshold, else None (no bias)."""
    try:
        funding_data = info.funding_history(FURY_SYMBOL, 1)
        if funding_data:
            rate = float(funding_data[-1].get("fundingRate", 0))
            if rate > 0.0005:  # > +0.05%
                return "SHORT"
    except Exception:
        pass
    return None


def evaluate_gates(row_15m: dict, row_1h: dict | None) -> tuple[dict, int, str | None]:
    """Evaluate all 6 gates. Returns (gates, score, side)."""
    ema_signal = row_15m.get("ema_signal", 0)
    if ema_signal == 0:
        return {}, 0, None

    side = "LONG" if ema_signal > 0 else "SHORT"

    # BTC golden rule
    if FURY_SYMBOL == "BTC" and side == "SHORT":
        return {}, 0, None

    rsi_15m = row_15m.get("rsi")
    if rsi_15m is None or np.isnan(rsi_15m):
        return {}, 0, None

    g1 = True  # EMA direction
    g2 = (rsi_15m < RSI_LONG_TH) if side == "LONG" else (rsi_15m > RSI_SHORT_TH)

    rsi_1h = row_1h.get("rsi") if row_1h else None
    g3 = ((rsi_1h < 50) if side == "LONG" else (rsi_1h > 50)) \
        if (rsi_1h is not None and not np.isnan(rsi_1h)) else False

    vol = row_15m.get("volume", 0)
    vol_sma = row_15m.get("vol_sma20")
    g4 = bool(vol > vol_sma) if (vol_sma and not np.isnan(vol_sma)) else False

    obv_slope = row_15m.get("obv_slope")
    g5 = bool(obv_slope > 0) if (side == "LONG" and obv_slope is not None and not np.isnan(obv_slope)) else (side == "SHORT")

    funding_bias = check_funding_bias()
    g6 = (funding_bias is None or funding_bias == side)

    gates = {"ema": g1, "rsi": g2, "mtf": g3, "volume": g4, "obv": g5, "funding": g6}
    score = sum(1 for v in gates.values() if v)
    return gates, score, side


def fetch_prepared_candles():
    """Fetch and prepare 15m + 1h candles. Returns (df_15m, df_1h)."""
    symbol_pair = f"{FURY_SYMBOL}USDT"
    df_15m = fetcher.fetch_ohlcv(symbol_pair, interval="15m", limit=CANDLE_LIMIT)
    df_1h  = fetcher.fetch_ohlcv(symbol_pair, interval="1h",  limit=CANDLE_LIMIT_1H)

    if df_15m is None or len(df_15m) < 50:
        return None, None

    df_15m = add_fury_indicators(df_15m, rsi_period=RSI_PERIOD, atr_period=ATR_PERIOD)
    if df_1h is not None and len(df_1h) >= 10:
        df_1h = add_fury_indicators(df_1h, rsi_period=RSI_PERIOD, atr_period=ATR_PERIOD)
    else:
        df_1h = None

    return df_15m, df_1h


def get_last_1h_row(df_1h, ts_15m) -> dict | None:
    if df_1h is None:
        return None
    try:
        mask = df_1h["timestamp"] <= ts_15m
        if not mask.any():
            return None
        return df_1h[mask].iloc[-1].to_dict()
    except Exception:
        return None


# ── Order execution ────────────────────────────────────────────────────────────

def open_position(side: str, price: float, atr: float, gate_score: int, balance: float):
    global position

    leverage = get_leverage(gate_score)
    stop_dist = atr_stop_distance(atr)
    sl = price - stop_dist if side == "LONG" else price + stop_dist
    tp = price + stop_dist * 3 if side == "LONG" else price - stop_dist * 3

    risk_usd = balance * RISK_PCT
    stop_pct = stop_dist / price
    size_usd = min(risk_usd / stop_pct, balance * leverage)
    size_contracts = size_usd / price

    try:
        if not PAPER_TRADE:
            exchange.update_leverage(leverage, FURY_SYMBOL)
            is_buy = (side == "LONG")
            order = exchange.market_open(FURY_SYMBOL, is_buy, size_contracts, slippage=0.01)

            if order.get("status") != "ok":
                log(f"⚠️  Order failed: {order}")
                emit("error", price=price, details={"msg": f"open failed: {order}"})
                return

        position = {
            "side": side,
            "entry": price,
            "sl": sl,
            "tp": tp,
            "size_contracts": size_contracts,
            "size_usd": size_usd,
            "leverage": leverage,
            "gate_score": gate_score,
            "opened_at": datetime.now(timezone.utc).isoformat(),
        }
        paper_tag = " [PAPER]" if PAPER_TRADE else ""
        log(f"📈{paper_tag} Opened {side} {FURY_SYMBOL} @ {price:.2f} | SL {sl:.2f} | TP {tp:.2f} | {leverage}x | Gates {gate_score}")
        emit("fury_entry", price=price, details={
            "side": side, "sl": sl, "tp": tp,
            "size_usd": round(size_usd, 2),
            "leverage": leverage, "gate_score": gate_score,
            "paper_trade": PAPER_TRADE,
        })

    except Exception as e:
        log(f"❌ open_position error: {e}")
        emit("error", price=price, details={"msg": str(e)})


def close_position(price: float, reason: str):
    global position, consecutive_losses, circuit_breaker, daily_start_balance, _paper_balance

    if not position:
        return

    side = position["side"]
    entry = position["entry"]

    if PAPER_TRADE:
        # Simulate close — no real order, just compute P&L
        fee_pct = 0.001  # 0.1% per side (round-trip covered across open+close)
        if side == "LONG":
            pnl_pct = (price - entry) / entry - fee_pct
        else:
            pnl_pct = (entry - price) / entry - fee_pct
        pnl_usd = pnl_pct * position["size_usd"]
        _paper_balance += pnl_usd
    else:
        try:
            order = exchange.market_close(FURY_SYMBOL, position["size_contracts"])
            if order.get("status") != "ok":
                log(f"⚠️  Close order failed: {order}")
                emit("error", price=price, details={"msg": f"close failed: {order}"})
                return
        except Exception as e:
            log(f"❌ close_position error: {e}")
            emit("error", price=price, details={"msg": str(e)})
            return

        if side == "LONG":
            pnl_pct = (price - entry) / entry
        else:
            pnl_pct = (entry - price) / entry
        pnl_usd = pnl_pct * position["size_usd"]

    event_type = "fury_tp" if reason == "TAKE_PROFIT" else "fury_sl"
    emoji = "✅" if pnl_usd > 0 else "❌"
    paper_tag = " [PAPER]" if PAPER_TRADE else ""
    log(f"{emoji}{paper_tag} Closed {side} @ {price:.2f} ({reason}) | PnL ${pnl_usd:+.2f}"
        + (f" | Paper balance: ${_paper_balance:.2f}" if PAPER_TRADE else ""))
    close_details = {
        "side": side, "entry": entry, "reason": reason,
        "gate_score": position["gate_score"],
        "paper_trade": PAPER_TRADE,
    }
    if PAPER_TRADE:
        close_details["paper_balance"] = round(_paper_balance, 2)
    emit(event_type, price=price, pnl=round(pnl_usd, 4), details=close_details)

    # Circuit breaker tracking
    if pnl_usd <= 0:
        consecutive_losses += 1
    else:
        consecutive_losses = 0

    current_balance = get_balance()
    if daily_start_balance:
        daily_dd = (daily_start_balance - current_balance) / daily_start_balance
        if daily_dd >= 0.05 or consecutive_losses >= 3:
            circuit_breaker = True
            reason_cb = f"daily DD {daily_dd:.1%}" if daily_dd >= 0.05 else f"{consecutive_losses} consecutive losses"
            log(f"🔴 Circuit breaker triggered: {reason_cb}")
            emit("fury_circuit_breaker", price=price, details={"reason": reason_cb})

    position = None


def maybe_reset_circuit_breaker():
    global circuit_breaker, consecutive_losses, daily_start_balance, daily_reset_date
    today = date.today()
    if daily_reset_date != today:
        daily_reset_date = today
        daily_start_balance = get_balance()
        if circuit_breaker:
            circuit_breaker = False
            consecutive_losses = 0
            log(f"✅ Circuit breaker reset for {today}")


# ── Main loop ──────────────────────────────────────────────────────────────────

def main():
    global last_candle_ts_15m, daily_start_balance, daily_reset_date

    mode_tag = " [PAPER TRADE]" if PAPER_TRADE else ""
    log(f"Starting FURY RSI Trader{mode_tag} | Symbol: {FURY_SYMBOL} | Min gates: {MIN_GATES}")
    emit("started", price=get_price(), details={
        "symbol": FURY_SYMBOL,
        "rsi_period": RSI_PERIOD,
        "rsi_long_th": RSI_LONG_TH,
        "rsi_short_th": RSI_SHORT_TH,
        "leverage_max": LEVERAGE_MAX,
        "risk_pct": RISK_PCT * 100,
        "paper_trade": PAPER_TRADE,
    })

    daily_reset_date = date.today()
    daily_start_balance = get_balance()
    log(f"Starting balance: ${daily_start_balance:.2f}")

    while True:
        try:
            maybe_reset_circuit_breaker()

            df_15m, df_1h = fetch_prepared_candles()

            if df_15m is None:
                log("⚠️  Insufficient candle data, skipping cycle")
                time.sleep(CHECK_INTERVAL)
                continue

            # Use second-to-last candle = last CONFIRMED closed candle
            # (last candle in df is the current in-progress candle)
            closed_row = df_15m.iloc[-2].to_dict()
            closed_ts = closed_row.get("timestamp")

            # Only act when a new candle has closed (avoid acting twice per candle)
            if closed_ts == last_candle_ts_15m:
                time.sleep(CHECK_INTERVAL)
                continue
            last_candle_ts_15m = closed_ts

            current_price = get_price()

            # Check open position SL/TP against current live price
            if position:
                side = position["side"]
                if side == "LONG":
                    if current_price <= position["sl"]:
                        close_position(current_price, "STOP_LOSS")
                    elif current_price >= position["tp"]:
                        close_position(current_price, "TAKE_PROFIT")
                else:
                    if current_price >= position["sl"]:
                        close_position(current_price, "STOP_LOSS")
                    elif current_price <= position["tp"]:
                        close_position(current_price, "TAKE_PROFIT")
                time.sleep(CHECK_INTERVAL)
                continue

            if circuit_breaker:
                log("🔴 Circuit breaker active — no new entries")
                time.sleep(CHECK_INTERVAL)
                continue

            # Evaluate signal gates on the confirmed closed candle
            row_1h = get_last_1h_row(df_1h, closed_ts) if df_1h is not None else None
            gates, score, side = evaluate_gates(closed_row, row_1h)

            log(f"Gates: {score}/6 | {gates} | Side: {side}")

            if score >= MIN_GATES and side is not None:
                atr = closed_row.get("atr")
                if atr and not np.isnan(atr) and atr > 0:
                    balance = get_balance()
                    open_position(side, current_price, atr, score, balance)

        except Exception as e:
            log(f"❌ Loop error: {e}")
            emit("error", details={"msg": str(e)})

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
