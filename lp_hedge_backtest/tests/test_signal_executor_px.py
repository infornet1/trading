"""
Tests for HL trigger-price rounding in api/signal_executor.py.

Regression from 2026-08-10: BTC signal 93 quoted a stoploss of 65682.1 — six
significant figures. Hyperliquid caps perp prices at five and rejected both
placement attempts with 'Invalid TP/SL price. asset=0', so H4 closed the entry
at market and the signal was skipped. Prices are now snapped to HL's rules
before any order is built.

HL's rule: at most 5 significant figures, AND at most
(MAX_DECIMALS - szDecimals) decimal places, with MAX_DECIMALS = 6 for perps.
Integers are always acceptable.
"""

import pytest

from api.signal_executor import _round_px


def _sig_figs(px: float) -> int:
    """
    Significant figures in px — the length of its mantissa.

    Trailing zeros are placeholders, not significant: 123460 carries the five
    figures 1-2-3-4-6, which is why HL accepts it. So strip zeros from both
    ends after removing the decimal point.
    """
    return len(f"{px:.10f}".replace(".", "").strip("0")) or 1


class TestRoundPx:
    def test_btc_stoploss_from_signal_93(self):
        """The exact value HL rejected: 65682.1 → 65682."""
        assert _round_px(65682.1, sz_decimals=5) == 65682

    def test_btc_targets_already_valid_are_unchanged(self):
        assert _round_px(62150.0, sz_decimals=5) == 62150.0
        assert _round_px(61500.0, sz_decimals=5) == 61500.0

    @pytest.mark.parametrize(
        "px,sz_decimals",
        [
            (65682.1,   5),   # BTC — 6 sig figs
            (123456.7,  5),   # 7 sig figs, rounds to 123460
            (1943.55,   4),   # ETH — 6 sig figs
            (8.5201,    1),   # LINK — 5 sig figs, at the boundary
            (0.0068964, 0),   # PENGU — decimal cap binds before sig figs
            (0.81652,   1),   # DOT
            (76.4321,   2),   # SOL — 6 sig figs
        ],
    )
    def test_result_always_satisfies_hl_rules(self, px, sz_decimals):
        out = _round_px(px, sz_decimals)
        assert _sig_figs(out) <= 5, f"{px} → {out} has too many significant figures"
        decimals = len(f"{out:.10f}".rstrip("0").split(".")[1])
        assert decimals <= 6 - sz_decimals, f"{px} → {out} has too many decimals"

    def test_rounds_to_nearest_not_toward_zero(self):
        # 65682.9 must not become 65682 — the stop would sit 0.9 too tight.
        assert _round_px(65682.9, sz_decimals=5) == 65683

    def test_decimal_cap_binds_for_high_sz_decimals(self):
        # 5 sig figs would allow 0.0012345, but szDecimals=3 caps at 3 decimals.
        assert _round_px(0.0012345, sz_decimals=3) == 0.001

    def test_small_prices_keep_precision(self):
        assert _round_px(0.005955, sz_decimals=0) == 0.005955

    @pytest.mark.parametrize("px", [None, 0, 0.0, -1])
    def test_non_positive_and_none_pass_through(self, px):
        # tp2 is legitimately None on single-target signals.
        assert _round_px(px, sz_decimals=2) == px

    def test_is_idempotent(self):
        once  = _round_px(65682.1, sz_decimals=5)
        twice = _round_px(once, sz_decimals=5)
        assert once == twice
