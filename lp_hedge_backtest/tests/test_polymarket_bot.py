"""Tests for the Polymarket bot product: event mapping, router validation,
and the live_polymarket_bot pure helpers."""

import pytest
from fastapi import HTTPException

from api.bot_manager import _EVENT_MAP
from api.routers.bots import BotConfigCreate, _enforce_polymarket_rules
from live_polymarket_bot import check_exit, compute_pnl


# ── bot_manager event mapping ────────────────────────────────────────────────

class TestPolyEventMap:
    def test_poly_events_mapped(self):
        assert _EVENT_MAP["poly_entry"] == "poly_entry"
        assert _EVENT_MAP["poly_tp"] == "poly_tp"
        assert _EVENT_MAP["poly_sl"] == "poly_sl"


# ── Router schema validation ─────────────────────────────────────────────────

def _create_body(**overrides):
    base = dict(
        chain_id=137,
        nft_token_id="poly-test",
        pair="POLY",
        lower_bound=0,
        upper_bound=0,
        mode="polymarket",
        polymarket_token_id="123456789",
        polymarket_size_usd=10.0,
        polymarket_tp_price=0.88,
        polymarket_sl_price=0.68,
    )
    base.update(overrides)
    return BotConfigCreate(**base)


class TestPolymarketModeSchema:
    def test_mode_validator_accepts_polymarket(self):
        assert _create_body().mode == "polymarket"

    def test_mode_validator_rejects_unknown(self):
        with pytest.raises(ValueError):
            _create_body(mode="not_a_mode")


class TestEnforcePolymarketRules:
    def test_flag_disabled_rejected(self, monkeypatch):
        import api.routers.bots as bots_router
        monkeypatch.setattr(bots_router, "POLYMARKET_BOT_ENABLED", False)
        with pytest.raises(HTTPException) as exc:
            _enforce_polymarket_rules(_create_body())
        assert exc.value.status_code == 403

    def test_valid_body_accepted(self, monkeypatch):
        import api.routers.bots as bots_router
        monkeypatch.setattr(bots_router, "POLYMARKET_BOT_ENABLED", True)
        _enforce_polymarket_rules(_create_body())  # no raise

    def test_missing_token_rejected(self, monkeypatch):
        import api.routers.bots as bots_router
        monkeypatch.setattr(bots_router, "POLYMARKET_BOT_ENABLED", True)
        with pytest.raises(HTTPException) as exc:
            _enforce_polymarket_rules(_create_body(polymarket_token_id=None))
        assert exc.value.status_code == 400

    def test_tp_not_greater_than_sl_rejected(self, monkeypatch):
        import api.routers.bots as bots_router
        monkeypatch.setattr(bots_router, "POLYMARKET_BOT_ENABLED", True)
        with pytest.raises(HTTPException) as exc:
            _enforce_polymarket_rules(
                _create_body(polymarket_tp_price=0.60, polymarket_sl_price=0.68)
            )
        assert exc.value.status_code == 400

    def test_non_polymarket_mode_skipped(self):
        body = _create_body(mode="whale")
        _enforce_polymarket_rules(body)  # no raise even with flag state unknown


# ── Bot pure helpers ─────────────────────────────────────────────────────────

class TestCheckExit:
    def test_price_at_or_above_tp_triggers_tp(self):
        assert check_exit(0.88, 0.88, 0.68) == "tp"
        assert check_exit(0.95, 0.88, 0.68) == "tp"

    def test_price_at_or_below_sl_triggers_sl(self):
        assert check_exit(0.68, 0.88, 0.68) == "sl"
        assert check_exit(0.50, 0.88, 0.68) == "sl"

    def test_price_inside_band_holds(self):
        assert check_exit(0.80, 0.88, 0.68) is None


class TestComputePnl:
    def test_tp_scenario_from_product_spec(self):
        # Buy 10 shares @ $0.80, sell @ $0.88 → +$0.80
        assert compute_pnl(10, 0.80, 0.88) == pytest.approx(0.80)

    def test_sl_scenario_from_product_spec(self):
        # Buy 10 shares @ $0.80, sell @ $0.68 → -$1.20
        assert compute_pnl(10, 0.80, 0.68) == pytest.approx(-1.20)
