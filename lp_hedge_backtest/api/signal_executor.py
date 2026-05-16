"""
HL order placement helper for signal copy trading.
Synchronous — wrap with asyncio.to_thread() in async contexts.
"""
import math
from typing import Optional

# Fixed $10 notional per trade (controlled live mode). Set to None for full size_pct sizing.
SIGNAL_TEST_NOTIONAL_USDC: float | None = 10.0

from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

from api.crypto import decrypt


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
        info       = Info(constants.MAINNET_API_URL, skip_ws=True)

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
            meta = info.meta()
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

        # ── Open market position ─────────────────────────────────────────────
        exchange = Exchange(account, constants.MAINNET_API_URL, account_address=hl_wallet_addr)
        exchange.update_leverage(leverage, symbol)
        order = exchange.market_open(symbol, is_buy, size, slippage=0.01)

        if not order or order.get("status") != "ok":
            return {"success": False, "dry_run": False, "error": f"Order failed: {order}"}

        statuses = order.get("response", {}).get("data", {}).get("statuses", [{}])
        first    = statuses[0] if statuses else {}
        filled   = first.get("filled", {})
        resting  = first.get("resting", {})

        if not filled or not filled.get("oid"):
            # Order was not filled immediately — cancel the resting entry to avoid orphans
            resting_oid = resting.get("oid") if resting else None
            if resting_oid:
                try:
                    exchange.cancel(symbol, resting_oid)
                except Exception:
                    pass
            return {"success": False, "dry_run": False,
                    "error": "Order was not filled (resting) — price may have moved. Entry cancelled."}

        hl_order_id = str(filled.get("oid", ""))
        fill_price  = float(filled.get("avgPx", entry) or entry)

        # ── Native SL — full size, reduce_only (covers runner after TP1 partial fill)
        sl_resp = exchange.order(
            symbol, close_is_buy, size, sl_price,
            {"trigger": {"triggerPx": sl_price, "isMarket": True, "tpsl": "sl"}},
            reduce_only=True,
        )
        sl_oid  = _extract_oid(sl_resp)
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
