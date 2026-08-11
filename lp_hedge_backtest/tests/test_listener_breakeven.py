"""
Tests for the Signal Lab breakeven monitor and auto-close P&L accounting.

Both cover regressions found by the 2026-08-09 health check:

* `_tp1_order_status` must never report a fill it did not see. The previous
  implementation inferred "TP1 filled" from an order's absence in
  `open_orders`, and its bare `except` returned an empty set — so a transient
  HL 502 made the monitor cancel the real stop-loss on four live positions.
* `_move_sl_to_breakeven` must place the breakeven stop before cancelling the
  original, so a failed placement can never leave a position unprotected.
* `_close_pnl_usd` must fill the profitability-dashboard columns that the
  channel-driven close path used to leave NULL.
"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from telegram_listener.listener import (
    _close_pnl_usd,
    _move_sl_to_breakeven,
    _tp1_order_status,
)


def _execution(fill_price="100", size="10", leverage=None, exec_id=1):
    return SimpleNamespace(
        id=exec_id,
        fill_price=Decimal(fill_price) if fill_price is not None else None,
        exec_size_usdt=Decimal(size) if size is not None else None,
        exec_leverage=leverage,
    )


class TestTp1OrderStatus:
    """Fail closed: an unknown state must never be reported as 'filled'."""

    def _info(self, response):
        info = MagicMock()
        info.query_order_by_oid.return_value = response
        return info

    def test_filled_is_reported(self):
        info = self._info({"status": "order", "order": {"status": "filled"}})
        with patch("telegram_listener.listener._hl_info", return_value=info):
            assert _tp1_order_status("0xabc", "123") == "filled"

    def test_open_is_reported(self):
        info = self._info({"status": "order", "order": {"status": "open"}})
        with patch("telegram_listener.listener._hl_info", return_value=info):
            assert _tp1_order_status("0xabc", "123") == "open"

    def test_hl_exception_returns_none_not_filled(self):
        # The 2026-08-09 incident: a 502 here used to look like "TP1 filled".
        info = MagicMock()
        info.query_order_by_oid.side_effect = Exception("502 Bad Gateway")
        with patch("telegram_listener.listener._hl_info", return_value=info):
            assert _tp1_order_status("0xabc", "123") is None

    def test_unknown_oid_returns_none(self):
        with patch("telegram_listener.listener._hl_info",
                   return_value=self._info({"status": "unknownOid"})):
            assert _tp1_order_status("0xabc", "123") is None

    @pytest.mark.parametrize("response", [None, {}, {"status": "order"}])
    def test_malformed_responses_return_none(self, response):
        with patch("telegram_listener.listener._hl_info", return_value=self._info(response)):
            assert _tp1_order_status("0xabc", "123") is None


class TestMoveSlToBreakeven:
    """The original SL must outlive any failure to place the new one."""

    ok_order = {
        "status": "ok",
        "response": {"type": "order", "data": {"statuses": [{"resting": {"oid": 999}}]}},
    }

    def _patched(self, order_result, position_size=1.3):
        info = MagicMock()
        info.user_state.return_value = {
            "assetPositions": [{"position": {"coin": "LINK", "szi": f"-{position_size}"}}]
        }
        exchange = MagicMock()
        if isinstance(order_result, Exception):
            exchange.order.side_effect = order_result
        else:
            exchange.order.return_value = order_result
        return info, exchange

    def _run(self, info, exchange):
        with patch("telegram_listener.listener._hl_info", return_value=info), \
             patch("telegram_listener.listener.decrypt", return_value="0x" + "1" * 64), \
             patch("telegram_listener.listener.Account.from_key", return_value=MagicMock()), \
             patch("telegram_listener.listener.Exchange", return_value=exchange):
            return _move_sl_to_breakeven(
                "0xabc", "enc", "LINK", is_long=False, entry_px=8.174, old_sl_oid="555"
            )

    def test_success_places_then_cancels_and_returns_new_oid(self):
        info, exchange = self._patched(self.ok_order)
        result = self._run(info, exchange)

        assert result["success"] is True
        assert result["new_sl_oid"] == "999"
        assert result["size"] == 1.3
        exchange.order.assert_called_once()
        exchange.cancel.assert_called_once_with("LINK", 555)

    def test_failed_placement_leaves_original_sl_alone(self):
        info, exchange = self._patched({"status": "err", "response": "502 Bad Gateway"})
        result = self._run(info, exchange)

        assert result["success"] is False
        # The critical assertion: no cancel means the position keeps its stop.
        exchange.cancel.assert_not_called()

    def test_order_exception_leaves_original_sl_alone(self):
        info, exchange = self._patched(Exception("502 Bad Gateway"))
        result = self._run(info, exchange)

        assert result["success"] is False
        exchange.cancel.assert_not_called()

    def test_rejected_status_leaves_original_sl_alone(self):
        rejected = {"status": "ok",
                    "response": {"data": {"statuses": [{"error": "Order would not reduce"}]}}}
        info, exchange = self._patched(rejected)
        result = self._run(info, exchange)

        assert result["success"] is False
        assert "reduce" in result["error"]
        exchange.cancel.assert_not_called()

    def test_no_position_is_permanent_and_touches_nothing(self):
        info, exchange = self._patched(self.ok_order, position_size=0)
        result = self._run(info, exchange)

        assert result["success"] is False
        assert result["permanent"] is True
        exchange.order.assert_not_called()
        exchange.cancel.assert_not_called()

    def test_cancel_failure_still_counts_as_success(self):
        # Breakeven stop is live; a lingering wider stop is harmless.
        info, exchange = self._patched(self.ok_order)
        exchange.cancel.side_effect = Exception("already cancelled")
        assert self._run(info, exchange)["success"] is True


class TestClosePnlUsd:
    """
    Gross P&L with fees separate — performance.py subtracts fees itself.

    exec_size_usdt is the NOTIONAL, so P&L is notional × price-return with no
    leverage term. Until 2026-08-11 the helper multiplied by leverage as well,
    inflating every stored value by that factor.
    """

    def test_short_win(self):
        # $10 notional, entry 100 → close 95 = +5% = +$0.50 gross
        pnl, fees = _close_pnl_usd(_execution(), 95.0, is_long=False)
        assert pnl == pytest.approx(Decimal("0.5"))
        assert fees == pytest.approx(Decimal("0.009"))

    def test_short_loss(self):
        pnl, _ = _close_pnl_usd(_execution(), 105.0, is_long=False)
        assert pnl == pytest.approx(Decimal("-0.5"))

    def test_long_win(self):
        pnl, _ = _close_pnl_usd(_execution(), 105.0, is_long=True)
        assert pnl == pytest.approx(Decimal("0.5"))

    def test_leverage_is_not_applied(self):
        """The regression guard: a 20× execution must not report 20× the P&L."""
        lev20 = _close_pnl_usd(_execution(leverage=20), 95.0, is_long=False)
        lev1  = _close_pnl_usd(_execution(leverage=1),  95.0, is_long=False)
        assert lev20 == lev1
        assert lev20[0] == pytest.approx(Decimal("0.5"))

    def test_matches_hyperliquid_closed_pnl(self):
        """
        Real numbers from exec 137 (DOT, 2026-08-11), which HL reported as
        closedPnl +0.2657 while the DB stored +2.6560 at 10× leverage.
        """
        execution = _execution(fill_price="0.81652", size="10.04", leverage=10)
        pnl, _ = _close_pnl_usd(execution, 0.79492, is_long=False)
        assert float(pnl) == pytest.approx(0.2657, abs=0.001)

    def test_fees_are_not_deducted_from_pnl(self):
        # Guards against double-counting: gross return, fees reported separately.
        pnl, fees = _close_pnl_usd(_execution(), 100.0, is_long=False)
        assert pnl == pytest.approx(Decimal("0"))
        assert fees > 0

    def test_fees_are_notional_based(self):
        pnl, fees = _close_pnl_usd(_execution(size="400"), 100.0, is_long=False)
        assert fees == pytest.approx(Decimal("0.36"))  # 400 × 0.0009

    @pytest.mark.parametrize("kwargs", [{"fill_price": None}, {"size": None}])
    def test_missing_inputs_return_none(self, kwargs):
        assert _close_pnl_usd(_execution(**kwargs), 95.0, False) == (None, None)

    def test_zero_close_price_returns_none(self):
        assert _close_pnl_usd(_execution(), 0.0, False) == (None, None)
