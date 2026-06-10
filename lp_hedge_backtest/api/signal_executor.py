"""
HL order placement helper for signal copy trading.
Synchronous — wrap with asyncio.to_thread() in async contexts.
"""
import math
import os
import time
from typing import Optional

# Fixed $10 notional per trade (controlled live mode). Set to None for full size_pct sizing.
SIGNAL_TEST_NOTIONAL_USDC: float | None = 10.0

# M2: execution-quality guards
# Max slippage on the market entry (old 1% could eat most of a tight signal SL)
MAX_SLIPPAGE_PCT    = float(os.getenv("SIGNAL_MAX_SLIPPAGE_PCT", "0.3")) / 100
# Reject entry if the market already drifted this far past the signal entry price
MAX_ENTRY_DRIFT_PCT = float(os.getenv("SIGNAL_MAX_ENTRY_DRIFT_PCT", "1.0")) / 100

from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

from api.crypto import decrypt

# L5/M4: Info() construction itself costs ~2 REST calls (fetches meta+spot_meta)
# and meta() was re-fetched per order — share one client and cache meta 1h.
_INFO_CLIENT: Optional[Info] = None
_META_CACHE:  Optional[dict] = None
_META_TS:     float = 0.0
_META_TTL:    float = 3600.0


def _get_info() -> Info:
    global _INFO_CLIENT
    if _INFO_CLIENT is None:
        _INFO_CLIENT = Info(constants.MAINNET_API_URL, skip_ws=True)
    return _INFO_CLIENT


def _get_meta(info: Info) -> dict:
    global _META_CACHE, _META_TS
    if _META_CACHE is not None and (time.monotonic() - _META_TS) < _META_TTL:
        return _META_CACHE
    _META_CACHE = info.meta()
    _META_TS    = time.monotonic()
    return _META_CACHE


def _extract_oid(resp) -> Optional[str]:
    """Extract order ID from a trigger (resting) HL order response."""
    try:
        statuses = resp.get("response", {}).get("data", {}).get("statuses", [{}])
        resting  = statuses[0].get("resting", {}) if statuses else {}
        oid      = resting.get("oid") if resting else None
        return str(oid) if oid else None
    except Exception:
        return None


def place_hl_order(hl_wallet_addr: str, hl_secret_key_encrypted: str, signal,
                   dry_run: bool = False, overrides: dict | None = None) -> dict:
    """
    Place market order + native SL/TP on Hyperliquid for a parsed signal.
    signal: any object with .pair .direction .leverage .entry .stoploss .targets .size_pct
    dry_run=True: validates balance + calculates size but skips real HL order placement.
    Returns: {"success": bool, "dry_run": bool, ...}
    """
    try:
        secret_key = decrypt(hl_secret_key_encrypted)
        account    = Account.from_key(secret_key)
        info       = _get_info()  # L5: shared client

        # ── Balance check (unified account: perp + spot USDC both usable as margin)
        state   = info.user_state(hl_wallet_addr)
        perp    = float(state["marginSummary"]["accountValue"])
        spot_usdc = 0.0
        try:
            for b in info.spot_user_state(hl_wallet_addr).get("balances", []):
                if b["coin"] == "USDC":
                    spot_usdc = float(b["total"])
                    break
        except Exception:
            pass
        balance = perp + spot_usdc
        if balance < 10:
            return {"success": False, "dry_run": dry_run,
                    "error": f"Insufficient balance: ${balance:.2f} USDC (min $10)"}

        # ── Size calculation ─────────────────────────────────────────────────
        symbol            = (signal.pair or "").split("/")[0].upper()
        size_pct          = float(signal.size_pct) if signal.size_pct else 2.0
        leverage_requested = int(signal.leverage)  if signal.leverage  else 10
        if overrides and overrides.get("leverage"):
            leverage_requested = int(overrides["leverage"])
        entry             = float(signal.entry)

        # Cap leverage to HL's per-asset max; also grab szDecimals for size rounding
        max_leverage = leverage_requested
        sz_decimals  = 4  # safe default; HL rejects sizes with too many decimal places
        try:
            meta = _get_meta(info)  # M4: cached 1h — was a fresh fetch per order
            for asset in meta.get("universe", []):
                if asset.get("name", "").upper() == symbol:
                    max_leverage = int(asset.get("maxLeverage", leverage_requested))
                    sz_decimals  = int(asset.get("szDecimals", sz_decimals))
                    break
        except Exception:
            pass  # meta fetch failed — proceed with signal leverage, update_leverage will catch it
        leverage          = min(leverage_requested, max_leverage)
        leverage_adjusted = leverage < leverage_requested

        size_scaled = False
        factor      = 10 ** sz_decimals
        if overrides and overrides.get("size_usdt") and float(overrides["size_usdt"]) >= 10:
            notional = float(overrides["size_usdt"])
            size     = math.ceil((notional / entry) * factor) / factor
            margin   = size * entry / leverage
        elif SIGNAL_TEST_NOTIONAL_USDC:
            # Testing phase: ignore size_pct, use fixed notional
            notional = SIGNAL_TEST_NOTIONAL_USDC
            size     = math.ceil((notional / entry) * factor) / factor
            margin   = size * entry / leverage
        else:
            margin   = balance * size_pct / 100
            size     = round((margin * leverage) / entry, sz_decimals)
            if size * entry < 10:
                # ceil to nearest valid lot to guarantee notional >= $10 (round() can round down)
                min_size = math.ceil((10.0 / entry) * factor) / factor
                if min_size * entry / leverage > balance:
                    return {"success": False, "dry_run": dry_run,
                            "error": f"Notional too small and insufficient margin: ${balance:.2f} balance (need ${10/leverage:.2f} margin for $10 notional)"}
                size = min_size
                size_scaled = True

        is_buy       = (signal.direction == "long")
        sl_price     = float(signal.stoploss)
        targets      = signal.targets or []
        tp1_price    = float(targets[0]) if len(targets) >= 1 else None
        tp2_price    = float(targets[1]) if len(targets) >= 2 else None
        if overrides:
            if overrides.get("sl"):  sl_price  = float(overrides["sl"])
            if overrides.get("tp1"): tp1_price = float(overrides["tp1"])
            if overrides.get("tp2"): tp2_price = float(overrides["tp2"])
        split_tps    = tp2_price is not None
        # 50/50 split when two targets; full size when only one
        tp1_size     = round(size / 2, sz_decimals) if split_tps else size
        tp2_size     = round(size / 2, sz_decimals) if split_tps else None
        close_is_buy = not is_buy

        if dry_run:
            # Return simulated fill — no real orders placed
            return {
                "success":            True,
                "dry_run":            True,
                "hl_order_id":        "DRY-RUN-0000",
                "fill_price":         round(entry, 6),
                "size":               round(size, 6),
                "margin_used":        round(margin, 2),
                "leverage":           leverage,
                "leverage_requested": leverage_requested,
                "leverage_adjusted":  leverage_adjusted,
                "size_scaled":        size_scaled,
                "symbol":             symbol,
                "balance":            round(balance, 2),
                "perp":               round(perp, 2),
                "spot":               round(spot_usdc, 2),
                "sl_price":           round(sl_price, 6),
                "tp1_price":          round(tp1_price, 6) if tp1_price else None,
                "tp2_price":          round(tp2_price, 6) if tp2_price else None,
                "split_tps":          split_tps,
                "tp1_size":           round(tp1_size, 6),
                "tp2_size":           round(tp2_size, 6) if tp2_size else None,
                "notional":           round(size * entry, 2),
            }

        # ── M2: stale-price guard — has the market run away from the signal? ──
        try:
            mid = float(info.all_mids().get(symbol, 0) or 0)
        except Exception:
            mid = 0.0  # mid unavailable — proceed; the slippage cap still protects
        if mid > 0:
            if (is_buy and mid <= sl_price) or (not is_buy and mid >= sl_price):
                return {"success": False, "dry_run": False,
                        "error": f"Price ${mid:,.6g} already beyond stoploss ${sl_price:,.6g} — entry skipped"}
            drift = (mid - entry) / entry if is_buy else (entry - mid) / entry
            if drift > MAX_ENTRY_DRIFT_PCT:
                return {"success": False, "dry_run": False,
                        "error": f"Price drifted {drift*100:.2f}% past signal entry "
                                 f"(${entry:,.6g} → ${mid:,.6g}, max {MAX_ENTRY_DRIFT_PCT*100:.1f}%) — entry skipped"}

        # ── Open market position ─────────────────────────────────────────────
        exchange = Exchange(account, constants.MAINNET_API_URL, account_address=hl_wallet_addr)
        exchange.update_leverage(leverage, symbol)

        # M2: 0.3% slippage cap (was 1%) + one re-quote retry on an IOC miss;
        # market_open re-fetches the current mid on each call.
        filled = {}
        for attempt in (1, 2):
            order = exchange.market_open(symbol, is_buy, size, slippage=MAX_SLIPPAGE_PCT)
            if not order or order.get("status") != "ok":
                return {"success": False, "dry_run": False, "error": f"Order failed: {order}"}

            statuses = order.get("response", {}).get("data", {}).get("statuses", [{}])
            first    = statuses[0] if statuses else {}
            filled   = first.get("filled", {})
            if filled.get("oid"):
                break

            # Not filled — cancel any resting remainder before retrying
            resting_oid = (first.get("resting") or {}).get("oid")
            if resting_oid:
                try:
                    exchange.cancel(symbol, resting_oid)
                except Exception:
                    pass
            print(f"[M2] Entry attempt {attempt}/2 not filled for {symbol} "
                  f"(slippage cap {MAX_SLIPPAGE_PCT*100:.2f}%)", flush=True)

        if not filled or not filled.get("oid"):
            return {"success": False, "dry_run": False,
                    "error": "Order was not filled after 2 attempts — price may have moved. Entry cancelled."}

        hl_order_id = str(filled.get("oid", ""))
        fill_price  = float(filled.get("avgPx", entry) or entry)

        # ── Native SL — full size, reduce_only (covers runner after TP1 partial fill)
        # H4: the SL is mandatory. Verify placement and retry once; if it still
        # fails, close the entry immediately — never hold a naked leveraged
        # position. (Previously a rejected SL was stored silently as NULL.)
        sl_oid = None
        sl_resp = None
        for attempt in (1, 2):
            try:
                sl_resp = exchange.order(
                    symbol, close_is_buy, size, sl_price,
                    {"trigger": {"triggerPx": sl_price, "isMarket": True, "tpsl": "sl"}},
                    reduce_only=True,
                )
                sl_oid = _extract_oid(sl_resp)
            except Exception as sl_exc:
                sl_resp = {"exception": str(sl_exc)}
            if sl_oid:
                break
            print(f"[H4] SL placement attempt {attempt}/2 failed for {symbol}: {sl_resp}", flush=True)

        if not sl_oid:
            try:
                close_resp = exchange.market_close(symbol)
                if close_resp is None:
                    closed_note = "position already gone (no emergency close needed)"
                else:
                    closed_note = "entry closed at market to avoid a naked position"
            except Exception as close_exc:
                closed_note = (f"EMERGENCY CLOSE FAILED: {close_exc} — "
                               f"POSITION OPEN WITHOUT SL, close manually NOW")
            return {"success": False, "dry_run": False,
                    "hl_order_id": hl_order_id,
                    "fill_price":  round(fill_price, 6),
                    "error": f"SL placement failed after 2 attempts ({sl_resp}) — {closed_note}"}

        tp1_oid = None
        tp2_oid = None

        # ── Native TP orders ─────────────────────────────────────────────────
        if split_tps:
            # TP1: 50% at first target
            tp1_resp = exchange.order(
                symbol, close_is_buy, tp1_size, tp1_price,
                {"trigger": {"triggerPx": tp1_price, "isMarket": True, "tpsl": "tp"}},
                reduce_only=True,
            )
            tp1_oid = _extract_oid(tp1_resp)
            # TP2: remaining 50% at second target
            tp2_resp = exchange.order(
                symbol, close_is_buy, tp2_size, tp2_price,
                {"trigger": {"triggerPx": tp2_price, "isMarket": True, "tpsl": "tp"}},
                reduce_only=True,
            )
            tp2_oid = _extract_oid(tp2_resp)
        elif tp1_price:
            # Single target — close full size at TP
            tp1_resp = exchange.order(
                symbol, close_is_buy, size, tp1_price,
                {"trigger": {"triggerPx": tp1_price, "isMarket": True, "tpsl": "tp"}},
                reduce_only=True,
            )
            tp1_oid = _extract_oid(tp1_resp)

        return {
            "success":            True,
            "dry_run":            False,
            "hl_order_id":        hl_order_id,
            "fill_price":         round(fill_price, 6),
            "size":               round(size, 6),
            "margin_used":        round(margin, 2),
            "leverage":           leverage,
            "leverage_requested": leverage_requested,
            "leverage_adjusted":  leverage_adjusted,
            "size_scaled":        size_scaled,
            "symbol":             symbol,
            "balance":            round(balance, 2),
            "sl_price":           round(sl_price, 6),
            "tp1_price":          round(tp1_price, 6) if tp1_price else None,
            "tp2_price":          round(tp2_price, 6) if tp2_price else None,
            "split_tps":          split_tps,
            "tp1_size":           round(tp1_size, 6),
            "tp2_size":           round(tp2_size, 6) if tp2_size else None,
            "sl_order_id":        sl_oid,
            "tp1_order_id":       tp1_oid,
            "tp2_order_id":       tp2_oid,
        }

    except Exception as exc:
        return {"success": False, "dry_run": dry_run, "error": str(exc)}
