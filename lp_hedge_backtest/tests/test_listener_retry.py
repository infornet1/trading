"""Tests for telegram_listener.listener retry helpers."""

import pytest

from telegram_listener.listener import _is_retryable, _retry_delay


class TestIsRetryable:
    @pytest.mark.parametrize(
        "error,expected",
        [
            ("502 Bad Gateway", True),
            ("bad gateway from HL", True),
            ("connection timeout", True),
            ("not filled", True),
            ("position not found", False),
            ("insufficient balance", False),
            ("", False),
        ],
    )
    def test_retryable_detection(self, error, expected):
        assert _is_retryable(error) is expected


class TestRetryDelay:
    def test_exponential_backoff(self):
        assert _retry_delay(1) == 2.0
        assert _retry_delay(2) == 4.0
        assert _retry_delay(3) == 8.0

    def test_max_delay_cap(self):
        # Cap at 10s even for higher attempts
        assert _retry_delay(10) == 10.0
