"""Rotate Fernet ENCRYPTION_KEY and re-encrypt all stored HL secrets.

This script does NOT rely on api.crypto (which loads ENCRYPTION_KEY at import
time). Instead it instantiates two Fernet objects explicitly from the old and
new keys.

Usage:
    export OLD_ENCRYPTION_KEY="<old>"
    export NEW_ENCRYPTION_KEY="<new>"
    export DB_URL="mysql+aiomysql://viznago:<pass>@localhost/viznago_dev"
    ./venv/bin/python scripts/rotate_encryption_key.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cryptography.fernet import Fernet
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker

from api.database import DB_URL
from api.models import BotConfig, SignalWallet


def _sync_db_url():
    url = os.getenv("DB_URL", DB_URL)
    if not url:
        raise RuntimeError("DB_URL environment variable is required")
    return url.replace("mysql+aiomysql://", "mysql+pymysql://")


def main():
    old_key = os.getenv("OLD_ENCRYPTION_KEY")
    new_key = os.getenv("NEW_ENCRYPTION_KEY")

    if not old_key or not new_key:
        print("ERROR: Set OLD_ENCRYPTION_KEY and NEW_ENCRYPTION_KEY env vars", file=sys.stderr)
        sys.exit(1)

    if old_key == new_key:
        print("ERROR: OLD_ENCRYPTION_KEY and NEW_ENCRYPTION_KEY must be different", file=sys.stderr)
        sys.exit(1)

    old_fernet = Fernet(old_key.encode())
    new_fernet = Fernet(new_key.encode())

    engine = create_engine(_sync_db_url())
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        bot_rows = session.execute(select(BotConfig.id, BotConfig.hl_api_key).where(BotConfig.hl_api_key.isnot(None))).all()
        print(f"[Rotate] Re-encrypting {len(bot_rows)} bot config(s)...")
        for row in bot_rows:
            try:
                plaintext = old_fernet.decrypt(row.hl_api_key.encode()).decode()
                new_cipher = new_fernet.encrypt(plaintext.encode()).decode()
                session.execute(
                    update(BotConfig)
                    .where(BotConfig.id == row.id)
                    .values(hl_api_key=new_cipher)
                )
                print(f"[Rotate] BotConfig {row.id}: OK")
            except Exception as e:
                print(f"[Rotate] BotConfig {row.id}: FAILED - {e}", file=sys.stderr)
                raise

        wallet_rows = session.execute(select(SignalWallet.id, SignalWallet.hl_secret_key).where(SignalWallet.hl_secret_key.isnot(None))).all()
        print(f"[Rotate] Re-encrypting {len(wallet_rows)} signal wallet(s)...")
        for row in wallet_rows:
            try:
                plaintext = old_fernet.decrypt(row.hl_secret_key.encode()).decode()
                new_cipher = new_fernet.encrypt(plaintext.encode()).decode()
                session.execute(
                    update(SignalWallet)
                    .where(SignalWallet.id == row.id)
                    .values(hl_secret_key=new_cipher)
                )
                print(f"[Rotate] SignalWallet {row.id}: OK")
            except Exception as e:
                print(f"[Rotate] SignalWallet {row.id}: FAILED - {e}", file=sys.stderr)
                raise

        session.commit()
        print("[Rotate] Re-encryption complete. Update api/.env ENCRYPTION_KEY to the new value and restart the API.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
