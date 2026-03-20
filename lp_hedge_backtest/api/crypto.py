"""
AES-256 (Fernet) helpers for encrypting HL API keys at rest.
ENCRYPTION_KEY must be a valid Fernet key (base64url, 32 bytes).
Generate with: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import os
from cryptography.fernet import Fernet, InvalidToken

_key = os.getenv("ENCRYPTION_KEY", "").encode()
_fernet = Fernet(_key) if _key else None


def encrypt(plaintext: str) -> str:
    if not _fernet:
        raise RuntimeError("ENCRYPTION_KEY not set")
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    if not _fernet:
        raise RuntimeError("ENCRYPTION_KEY not set")
    try:
        return _fernet.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise ValueError("Failed to decrypt — invalid key or corrupted data")
