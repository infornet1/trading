"""Tests for api.bot_manager state management and event mapping."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from api.bot_manager import BotManager, _EVENT_MAP


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
