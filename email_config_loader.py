"""Shared email configuration loader for the /var/www/dev/trading monorepo.

Prefer environment variables. Fall back to the JSON file (plaintext or
Fernet-encrypted) pointed to by EMAIL_CONFIG_PATH (default:
/var/www/dev/trading/email_config.json).

Env vars expected:
    SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SENDER_EMAIL

The JSON file may contain either a plaintext dict or an encrypted blob:
    {"encrypted": true, "data": "...", "version": 1}

Requires ENCRYPTION_KEY in the environment to decrypt.
"""

import json
import os
from base64 import urlsafe_b64encode
from pathlib import Path
from typing import Optional


def _fernet():
    from cryptography.fernet import Fernet

    key = os.getenv("ENCRYPTION_KEY", "").encode()
    if not key:
        raise RuntimeError("ENCRYPTION_KEY not set")
    # Accept either a raw 32-byte key or a standard base64url Fernet key.
    if len(key) == 32:
        key = urlsafe_b64encode(key)
    return Fernet(key)


def _decrypt(cfg: dict) -> dict:
    f = _fernet()
    decrypted = f.decrypt(cfg["data"].encode())
    return json.loads(decrypted)


def _normalize(cfg: dict) -> dict:
    if "smtp_port" in cfg:
        try:
            cfg["smtp_port"] = int(cfg["smtp_port"])
        except Exception:
            pass
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

    if path is None:
        path = os.getenv("EMAIL_CONFIG_PATH", "/var/www/dev/trading/email_config.json")

    default_path = "/var/www/dev/trading/email_config.json"

    if not path or not Path(path).exists():
        # If a specific path was requested and missing, fall back to the shared config.
        path = default_path
        if not Path(path).exists():
            return None

    try:
        with open(path) as f:
            cfg = json.load(f)
        if cfg.get("encrypted"):
            cfg = _decrypt(cfg)
        return _normalize(cfg)
    except Exception as e:
        print(f"⚠️ Could not load email config: {e}", flush=True)
        return None


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python email_config_loader.py <path_to_email_config.json>")
        sys.exit(1)

    cfg = load_email_config(sys.argv[1])
    if cfg:
        print(json.dumps({k: v for k, v in cfg.items() if "password" not in k}, indent=2))
    else:
        print("No config loaded")
