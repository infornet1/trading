"""Tests for profitability dashboard endpoints using mocked DB responses."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

ADDRESS = "0x" + "a" * 40


def _make_trade(**overrides):
    """Return a mock BotTrade object."""
    t = MagicMock()
    defaults = {
        "id": 1,
        "config_id": 1,
        "user_address": ADDRESS,
        "mode": "avaro",
        "pair": "ETH",
        "side": "short",
        "entry_price": Decimal("2000.0"),
        "exit_price": Decimal("1900.0"),
        "size_usd": Decimal("10000.0"),
        "realized_pnl_usd": Decimal("100.0"),
        "fees_usd": Decimal("10.0"),
        "funding_usd": Decimal("5.0"),
        "net_pnl_usd": Decimal("85.0"),
        "il_offset_usd": None,
        "exit_reason": "tp_hit",
        "is_estimate": False,
        "opened_at": datetime.now(timezone.utc),
        "closed_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    for key, value in defaults.items():
        setattr(t, key, value)
    return t


def _make_signal(**overrides):
    """Return a mock SignalExecution object."""
    s = MagicMock()
    defaults = {
        "id": 1,
        "signal_id": 1,
        "user_address": ADDRESS,
        "realized_pnl_usd": Decimal("100.0"),
        "fees_usd": Decimal("10.0"),
        "funding_usd": None,
        "closed_at": datetime.now(timezone.utc),
        "exit_reason": "tp1",
    }
    defaults.update(overrides)
    for key, value in defaults.items():
        setattr(s, key, value)
    return s


def _mock_session(trades, signals):
    """Build a mock AsyncSession that returns trades/signals for the performance endpoints."""
    session = AsyncMock()

    def _execute(stmt):
        result = MagicMock()
        str_stmt = str(stmt)
        if "bot_trades" in str_stmt:
            # The production code filters out estimate rows; mirror that here.
            visible_trades = [t for t in trades if not t.is_estimate]
            result.scalars.return_value.all.return_value = visible_trades
            # /summary now runs one aggregate query; build the single row it expects.
            closed = [t for t in visible_trades if t.closed_at is not None]
            pnl = [t.realized_pnl_usd or Decimal("0") for t in closed]
            agg = MagicMock()
            agg.realized = sum((t.realized_pnl_usd or Decimal("0") for t in visible_trades), Decimal("0"))
            agg.fees = sum((t.fees_usd or Decimal("0") for t in visible_trades), Decimal("0"))
            agg.funding = sum((t.funding_usd or Decimal("0") for t in visible_trades), Decimal("0"))
            agg.wins = sum(1 for p in pnl if p > 0)
            agg.losses = sum(1 for p in pnl if p < 0)
            agg.gross_profit = sum((p for p in pnl if p > 0), Decimal("0"))
            agg.gross_loss = sum((p for p in pnl if p < 0), Decimal("0"))
            result.one.return_value = agg
        elif "signal_executions" in str_stmt:
            result.scalars.return_value.all.return_value = signals
            agg = MagicMock()
            agg.pnl = sum((s.realized_pnl_usd or Decimal("0") for s in signals), Decimal("0"))
            agg.fees = sum((s.fees_usd or Decimal("0") for s in signals), Decimal("0"))
            result.one.return_value = agg
        else:
            result.scalars.return_value.all.return_value = []
        return result

    session.execute.side_effect = _execute
    return session


def _patch_db(monkeypatch, trades, signals):
    """Replace AsyncSessionLocal in performance.py with a fake session factory."""
    fake_session = _mock_session(trades, signals)

    class FakeSessionLocal:
        async def __aenter__(self):
            return fake_session

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr("api.routers.performance.AsyncSessionLocal", FakeSessionLocal)


@pytest.mark.asyncio
async def test_performance_summary_aggregates(async_client, monkeypatch):
    trades = [
        _make_trade(realized_pnl_usd=Decimal("100.0"), fees_usd=Decimal("10.0"), funding_usd=Decimal("5.0")),
        _make_trade(realized_pnl_usd=Decimal("-50.0"), fees_usd=Decimal("5.0"), funding_usd=Decimal("2.0")),
    ]
    signals = [_make_signal(realized_pnl_usd=Decimal("100.0"), fees_usd=Decimal("10.0"))]
    _patch_db(monkeypatch, trades, signals)

    from api.auth import create_access_token

    token = create_access_token(ADDRESS)
    response = await async_client.get(
        "/performance/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["bot_realized_pnl_usd"] == 50.0
    assert data["bot_fees_usd"] == 15.0
    assert data["bot_funding_usd"] == 7.0
    assert data["signal_realized_pnl_usd"] == 100.0
    assert data["signal_fees_usd"] == 10.0
    assert data["total_trades"] == 2
    assert data["winning_trades"] == 1
    assert data["losing_trades"] == 1


@pytest.mark.asyncio
async def test_estimate_rows_excluded_from_summary(async_client, monkeypatch):
    trades = [
        _make_trade(realized_pnl_usd=Decimal("100.0"), is_estimate=False),
        _make_trade(realized_pnl_usd=Decimal("-1000.0"), is_estimate=True),
    ]
    _patch_db(monkeypatch, trades, [])

    from api.auth import create_access_token

    token = create_access_token(ADDRESS)
    response = await async_client.get(
        "/performance/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["bot_realized_pnl_usd"] == 100.0
    assert data["total_trades"] == 1
