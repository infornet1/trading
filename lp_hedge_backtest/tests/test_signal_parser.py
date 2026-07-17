"""Tests for telegram_listener.signal_parser."""

import pytest

from telegram_listener.signal_parser import Signal, parse_format_a, parse_format_b, parse_signal, parse_update


FORMAT_A = """BCH/USDT = Short ( 📊)
       (20x leverage)

◼️Entry: $459.08 (activated)
◼️Stoploss is at $466.94 (-56%)
◼️Target: $442.16 & $430.00

💻Looks good for further move here!"""

FORMAT_B = """📊 BCH/USDT

Size: 3%
Leverage: 20x
Entry: $436.16 (market price entry)
Target: $429 (+33%)
Stoploss: $439 (-13%)

🌩 Formed MSB"""

FORMAT_A_THOUSAND = """ETH/USDT = Short ( 📊)
   (20x leverage)

◼️Entry: $3,356.09 (activated)
◼️Stoploss is at $2,399.49 (-56%)
◼️Target: $2,283.19 & $2,248.86 & $2,207.48

💻slightly went from entry away but still solid entry!"""


class TestParseFormatA:
    def test_parse_format_a(self):
        sig = parse_format_a(FORMAT_A)
        assert sig is not None
        assert sig.pair == "BCH/USDT"
        assert sig.direction == "short"
        assert sig.leverage == 20
        assert sig.entry == 459.08
        assert sig.stoploss == 466.94
        assert sig.targets == [442.16, 430.0]
        assert sig.size_pct is None

    def test_parse_format_a_thousand_separator(self):
        sig = parse_format_a(FORMAT_A_THOUSAND)
        assert sig is not None
        assert sig.pair == "ETH/USDT"
        assert sig.entry == 3356.09
        assert sig.stoploss == 2399.49
        assert sig.targets == [2283.19, 2248.86, 2207.48]

    def test_parse_format_a_no_match(self):
        assert parse_format_a("random message") is None


class TestParseFormatB:
    def test_parse_format_b(self):
        sig = parse_format_b(FORMAT_B)
        assert sig is not None
        assert sig.pair == "BCH/USDT"
        assert sig.direction == "short"  # target < entry
        assert sig.leverage == 20
        assert sig.size_pct == 3.0
        assert sig.entry == 436.16
        assert sig.stoploss == 439.0
        assert sig.targets == [429.0]

    def test_parse_format_b_long_direction(self):
        text = """📊 BTC/USDT

Size: 5%
Leverage: 10x
Entry: $60,000
Target: $65,000
Stoploss: $58,000
"""
        sig = parse_format_b(text)
        assert sig is not None
        assert sig.direction == "long"

    def test_parse_format_b_no_match(self):
        assert parse_format_b("random message") is None


class TestParseSignal:
    def test_prefers_format_a(self):
        sig = parse_signal(FORMAT_A)
        assert sig is not None
        assert sig.pair == "BCH/USDT"
        assert sig.direction == "short"

    def test_falls_back_to_format_b(self):
        sig = parse_signal(FORMAT_B)
        assert sig is not None
        assert sig.pair == "BCH/USDT"

    def test_returns_none_for_garbage(self):
        assert parse_signal("Hello world") is None


class TestParseUpdate:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("🚫Got Stopped", "stopped"),
            ("SL hit on BTC", "stopped"),
            ("✅ Target reached!", "target_hit"),
            ("TP1 hit", "target_hit"),
            ("Took 50% profits", "partial"),
            ("partial close here", "partial"),
            ("Cancel this signal", "cancelled"),
            ("void trade", "cancelled"),
            ("random comment", None),
        ],
    )
    def test_parse_update(self, text, expected):
        assert parse_update(text) == expected
