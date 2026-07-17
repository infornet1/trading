"""Tests for JWT auth helpers."""

import pytest
from jose import jwt

from api.auth import create_access_token, decode_token, get_current_address


def test_create_and_decode_token():
    address = "0x" + "a" * 40
    token = create_access_token(address)
    payload = decode_token(token)
    assert payload["sub"].lower() == address.lower()
    assert "exp" in payload


def test_decode_invalid_token_raises():
    with pytest.raises(Exception):
        decode_token("not-a-valid-token")


def test_admin_claim():
    import os

    os.environ["ADMIN_WALLETS"] = "0x" + "a" * 40
    # Re-import to pick up the env var
    from api import auth

    auth._ADMIN_WALLETS = {
        w.strip().lower()
        for w in os.getenv("ADMIN_WALLETS", "").split(",")
        if w.strip()
    }
    token = auth.create_access_token("0x" + "a" * 40)
    payload = auth.decode_token(token)
    assert payload.get("is_admin") is True


def test_non_admin_does_not_get_claim():
    from api import auth

    auth._ADMIN_WALLETS = set()
    token = auth.create_access_token("0x" + "b" * 40)
    payload = auth.decode_token(token)
    assert "is_admin" not in payload
