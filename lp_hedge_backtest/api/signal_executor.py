"""
HL order placement helper for signal copy trading.
Synchronous — wrap with asyncio.to_thread() in async contexts.
"""
from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

from api.crypto import decrypt


def place_hl_order(hl_wallet_addr: str, hl_secret_key_encrypted: str, signal,
                   dry_run: bool = False) -> dict:
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
        entry             = float(signal.entry)

        # Cap leverage to HL's per-asset max (silently reduced, never raised)
        max_leverage = leverage_requested
        try:
            meta = info.meta()
            for asset in meta.get("universe", []):
                if asset.get("name", "").upper() == symbol:
                    max_leverage = int(asset.get("maxLeverage", leverage_requested))
                    break
        except Exception:
            pass  # meta fetch failed — proceed with signal leverage, update_leverage will catch it
        leverage          = min(leverage_requested, max_leverage)
        leverage_adjusted = leverage < leverage_requested

        margin   = balance * size_pct / 100
        size     = (margin * leverage) / entry   # base asset quantity

        if size * entry < 10:
            return {"success": False, "dry_run": dry_run,
                    "error": f"Notional too small: ${size*entry:.2f} (min $10)"}

        is_buy       = (signal.direction == "long")
        sl_price     = float(signal.stoploss)
        targets      = signal.targets or []
        tp_price     = float(targets[0]) if targets else None
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
                "symbol":             symbol,
                "balance":            round(balance, 2),
                "perp":               round(perp, 2),
                "spot":               round(spot_usdc, 2),
                "sl_price":           round(sl_price, 6),
                "tp_price":           round(tp_price, 6) if tp_price else None,
                "notional":           round(size * entry, 2),
            }

        # ── Open market position ─────────────────────────────────────────────
        exchange = Exchange(account, constants.MAINNET_API_URL, account_address=hl_wallet_addr)
        exchange.update_leverage(leverage, symbol)
        order = exchange.market_open(symbol, is_buy, size, slippage=0.01)

        if not order or order.get("status") != "ok":
            return {"success": False, "dry_run": False, "error": f"Order failed: {order}"}

        statuses    = order.get("response", {}).get("data", {}).get("statuses", [{}])
        filled      = statuses[0].get("filled", {}) if statuses else {}
        hl_order_id = str(filled.get("oid", ""))
        fill_price  = float(filled.get("avgPx", entry) or entry)

        # ── Native SL order ──────────────────────────────────────────────────
        exchange.order(
            symbol, close_is_buy, size, sl_price,
            {"trigger": {"triggerPx": sl_price, "isMarket": True, "tpsl": "sl"}},
            reduce_only=True,
        )

        # ── Native TP order (first target) ───────────────────────────────────
        if tp_price:
            exchange.order(
                symbol, close_is_buy, size, tp_price,
                {"trigger": {"triggerPx": tp_price, "isMarket": True, "tpsl": "tp"}},
                reduce_only=True,
            )

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
            "symbol":             symbol,
            "balance":            round(balance, 2),
        }

    except Exception as exc:
        return {"success": False, "dry_run": dry_run, "error": str(exc)}
