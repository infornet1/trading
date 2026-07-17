"""Tests for api/models helpers."""

from datetime import datetime, timezone

from api.models import _utcnow


def test_utcnow_returns_naive_utc_datetime():
    now = _utcnow()
    assert now.tzinfo is None
    # Should be within the last few seconds of real UTC time
    utc_now = datetime.now(timezone.utc).replace(tzinfo=None)
    assert abs((utc_now - now).total_seconds()) < 1.0
