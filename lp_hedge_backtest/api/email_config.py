"""Email configuration loader.

Prefer environment variables. Fall back to the legacy JSON file only if
EMAIL_CONFIG_PATH is set explicitly and the env vars are missing.
The legacy file may be plaintext or encrypted with Fernet (see api/email_encrypt.py).

Env vars expected:
  SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SENDER_EMAIL

Legacy file keys:
  smtp_server, smtp_port, smtp_username, smtp_password, sender_email
"""

import json
import os
from typing import Optional

from api.email_encrypt import decrypt_email_config

_DEFAULT_LEGACY_PATH = "/var/www/dev/trading/lp_hedge_email_config.json"


def _normalize_port(cfg: dict) -> dict:
    if "smtp_port" in cfg:
        cfg["smtp_port"] = int(cfg["smtp_port"])
    return cfg


def load_email_config(path: Optional[str] = None) -> Optional[dict]:
    """Return email config dict or None if not configured."""
    server = os.getenv("SMTP_SERVER")
    port = os.getenv("SMTP_PORT")
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SENDER_EMAIL")

    if server and port and username and password and sender:
        return {
            "smtp_server": server,
            "smtp_port": int(port),
            "smtp_username": username,
            "smtp_password": password,
            "sender_email": sender,
        }

    # Legacy fallback — only used when env vars are not set.
    path = path or os.getenv("EMAIL_CONFIG_PATH", _DEFAULT_LEGACY_PATH)
    if path and os.path.exists(path):
        try:
            with open(path) as f:
                cfg = json.load(f)

            if cfg.get("encrypted"):
                cfg = decrypt_email_config(cfg)

            return _normalize_port(cfg)
        except Exception as e:
            print(f"⚠️ Could not load email config: {e}", flush=True)

    return None


def has_email_config() -> bool:
    return load_email_config() is not None
