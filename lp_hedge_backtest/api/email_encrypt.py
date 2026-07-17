"""Encrypt / decrypt the legacy email_config.json file with Fernet.

Uses the same ENCRYPTION_KEY as HL API key encryption (api/crypto.py).
"""

import json
import os
from base64 import urlsafe_b64encode
from cryptography.fernet import Fernet


def _fernet():
    key = os.getenv("ENCRYPTION_KEY", "").encode()
    if not key:
        raise RuntimeError("ENCRYPTION_KEY not set")
    # Allow standard Fernet key (32 bytes base64-encoded) or raw 32-byte key.
    if len(key) == 32:
        key = urlsafe_b64encode(key)
    return Fernet(key)


def encrypt_email_config(cfg: dict) -> dict:
    f = _fernet()
    payload = json.dumps(cfg).encode()
    return {
        "encrypted": True,
        "data": f.encrypt(payload).decode(),
        "version": 1,
    }


def decrypt_email_config(cfg: dict) -> dict:
    f = _fernet()
    decrypted = f.decrypt(cfg["data"].encode())
    return json.loads(decrypted)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m api.email_encrypt <path_to_email_config.json>")
        sys.exit(1)

    path = sys.argv[1]
    with open(path) as f:
        plaintext = json.load(f)

    encrypted = encrypt_email_config(plaintext)
    backup = path + ".backup"
    os.rename(path, backup)
    with open(path, "w") as f:
        json.dump(encrypted, f, indent=2)

    print(f"Encrypted {path}")
    print(f"Plaintext backup saved to {backup}")
