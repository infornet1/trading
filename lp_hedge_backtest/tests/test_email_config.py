"""Tests for email configuration loading / encryption."""

import json
import os
import tempfile

import pytest

from api.email_config import load_email_config
from api.email_encrypt import encrypt_email_config


def test_load_email_config_from_env_vars(monkeypatch):
    monkeypatch.setenv("SMTP_SERVER", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "user@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SENDER_EMAIL", "sender@example.com")

    cfg = load_email_config()
    assert cfg["smtp_server"] == "smtp.example.com"
    assert cfg["smtp_port"] == 587
    assert cfg["smtp_username"] == "user@example.com"
    assert cfg["smtp_password"] == "secret"
    assert cfg["sender_email"] == "sender@example.com"


def test_load_email_config_decrypts_encrypted_file():
    plain = {
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_username": "finanzas@ueipab.edu.ve",
        "smtp_password": "app-password",
        "sender_email": "finanzas@ueipab.edu.ve",
    }
    encrypted = encrypt_email_config(plain)

    with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as f:
        json.dump(encrypted, f)
        path = f.name

    try:
        cfg = load_email_config(path)
        assert cfg["smtp_server"] == "smtp.gmail.com"
        assert cfg["smtp_port"] == 587
        assert cfg["smtp_password"] == "app-password"
    finally:
        os.unlink(path)


def test_load_email_config_returns_none_when_missing(monkeypatch):
    monkeypatch.delenv("SMTP_SERVER", raising=False)
    monkeypatch.delenv("SMTP_PORT", raising=False)
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    monkeypatch.delenv("SENDER_EMAIL", raising=False)

    cfg = load_email_config("/nonexistent/path/email_config.json")
    assert cfg is None
