"""Tests for api.bot_manager state management and event mapping."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from api.bot_manager import BotManager, _EVENT_MAP, build_start_config


@pytest.fixture
def manager():
    return BotManager()


class TestEventMap:
    def test_known_events_mapped(self):
        assert _EVENT_MAP["hedge_opened"] == "hedge_opened"
        assert _EVENT_MAP["tp_hit"] == "tp_hit"
        assert _EVENT_MAP["sl_hit"] == "sl_hit"
        assert _EVENT_MAP["fury_entry"] == "fury_entry"
        assert _EVENT_MAP["whale_new_position"] == "whale_new_position"

    def test_unknown_event_defaults_to_error(self):
        assert _EVENT_MAP.get("not_a_real_event", "error") == "error"


class TestProcessState:
    def test_is_running_false_when_not_started(self, manager):
        assert manager.is_running(17) is False

    def test_pid_none_when_not_running(self, manager):
        assert manager.pid(17) is None

    def test_is_running_true_with_mock_proc(self, manager):
        proc = MagicMock()
        proc.poll.return_value = None
        manager._procs[17] = proc
        assert manager.is_running(17) is True

    def test_pid_returns_pid_when_running(self, manager):
        proc = MagicMock()
        proc.poll.return_value = None
        proc.pid = 12345
        manager._procs[17] = proc
        assert manager.pid(17) == 12345

    def test_is_running_false_after_exit(self, manager):
        proc = MagicMock()
        proc.poll.return_value = 0
        manager._procs[17] = proc
        assert manager.is_running(17) is False


class TestPubSub:
    def test_subscribe_returns_queue(self, manager):
        q = manager.subscribe(17)
        assert isinstance(q, asyncio.Queue)
        assert q in manager._subscribers[17]

    def test_unsubscribe_removes_queue(self, manager):
        q = manager.subscribe(17)
        manager.unsubscribe(17, q)
        assert q not in manager._subscribers.get(17, [])


class TestLastSeen:
    def test_last_seen_starts_none(self, manager):
        assert manager.last_seen(17) is None

    def test_last_seen_records_timestamp(self, manager):
        now = datetime.now(timezone.utc)
        manager._last_seen[17] = now
        assert manager.last_seen(17) == now


def _fake_cfg(**overrides):
    """Minimal BotConfig stand-in for build_start_config (hl_api_key=None so
    decrypt() is never called)."""
    base = dict(
        nft_token_id="123", lower_bound=1000.0, upper_bound=2000.0,
        trigger_pct=-0.5, hedge_ratio=50.0, hl_api_key=None,
        hl_wallet_addr="0xabc", user_address="0xuser", mode="polymarket",
        pair="POLY", leverage=10, sl_pct=0.1, tp_pct=None,
        trailing_stop=True, auto_rearm=True,
        fury_symbol=None, fury_rsi_period=None, fury_rsi_long_th=None,
        fury_rsi_short_th=None, fury_leverage_max=None, fury_risk_pct=None,
        whale_top_n=None, whale_min_notional=None, whale_poll_interval=None,
        whale_custom_addresses=None, whale_watch_assets=None,
        whale_use_websocket=None, whale_oi_spike_threshold=None,
        polymarket_token_id="tok-1", polymarket_size_usd=25.0,
        polymarket_entry_price=None, polymarket_tp_price=0.7,
        polymarket_sl_price=0.3,
        paper_trade=True, engine_v2=False,
        from_above_dist_pct=7.5, use_funding_gate=True, funding_gate_pct=0.08,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class TestBuildStartConfig:
    def test_paper_trade_survives(self):
        # Regression: the auto-restart path used to drop paper_trade,
        # respawning paper bots LIVE after an API restart.
        cfg = build_start_config(_fake_cfg(paper_trade=True))
        assert cfg["paper_trade"] is True

    def test_polymarket_keys_survive(self):
        cfg = build_start_config(_fake_cfg())
        assert cfg["polymarket_token_id"] == "tok-1"
        assert cfg["polymarket_size_usd"] == "25.0"
        assert cfg["polymarket_tp_price"] == "0.7"
        assert cfg["polymarket_sl_price"] == "0.3"

    def test_gate_keys_survive(self):
        cfg = build_start_config(_fake_cfg())
        assert cfg["from_above_dist_pct"] == "7.5"
        assert cfg["use_funding_gate"] == "1"
        assert cfg["funding_gate_pct"] == "0.08"

    def test_defaults_when_columns_null(self):
        cfg = build_start_config(_fake_cfg(
            paper_trade=False, use_funding_gate=False,
            from_above_dist_pct=None, funding_gate_pct=None,
            polymarket_token_id=None,
        ))
        assert cfg["paper_trade"] is False
        assert cfg["use_funding_gate"] == "0"
        assert cfg["from_above_dist_pct"] == "5.0"
        assert cfg["funding_gate_pct"] == "0.05"
        assert cfg["polymarket_token_id"] == ""
        assert cfg["hl_api_key"] == ""


class TestHandleEvent:
    @pytest.mark.asyncio
    async def test_unknown_label_preserved_in_details(self, manager, monkeypatch):
        """Unknown event labels map to 'error' but the true label must survive."""
        written = {}

        async def fake_write(config_id, event_type, price, pnl, details):
            written["event_type"] = event_type
            written["details"] = details

        async def noop(*args, **kwargs):
            pass

        monkeypatch.setattr(manager, "_write_event", fake_write)
        monkeypatch.setattr(manager, "_update_bot_trade", noop)
        monkeypatch.setattr(manager, "_broadcast", noop)
        import api.telegram_alerts
        monkeypatch.setattr(api.telegram_alerts, "send_alert", noop)

        await manager._handle_event(17, {
            "event": "brand_new_event", "details": {"foo": 1},
        })
        assert written["event_type"] == "error"
        assert written["details"]["event_label"] == "brand_new_event"
        assert written["details"]["foo"] == 1

    @pytest.mark.asyncio
    async def test_known_label_not_annotated(self, manager, monkeypatch):
        written = {}

        async def fake_write(config_id, event_type, price, pnl, details):
            written["event_type"] = event_type
            written["details"] = details

        async def noop(*args, **kwargs):
            pass

        monkeypatch.setattr(manager, "_write_event", fake_write)
        monkeypatch.setattr(manager, "_update_bot_trade", noop)
        monkeypatch.setattr(manager, "_broadcast", noop)
        import api.telegram_alerts
        monkeypatch.setattr(api.telegram_alerts, "send_alert", noop)

        await manager._handle_event(17, {"event": "tp_hit", "details": None})
        assert written["event_type"] == "tp_hit"
        assert written["details"] is None
