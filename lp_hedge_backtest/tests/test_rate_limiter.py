"""Tests for api.rate_limiter."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.rate_limiter import RateLimiter


def _request(ip: str = "1.2.3.4"):
    return SimpleNamespace(headers={}, client=SimpleNamespace(host=ip))


def test_429_includes_retry_after_header():
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    limiter(_request())  # consumes the only token
    with pytest.raises(HTTPException) as exc:
        limiter(_request())
    assert exc.value.status_code == 429
    assert exc.value.headers["Retry-After"] == "60"


def test_separate_ips_have_separate_buckets():
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    limiter(_request("1.1.1.1"))
    limiter(_request("2.2.2.2"))  # different IP — must not be limited
