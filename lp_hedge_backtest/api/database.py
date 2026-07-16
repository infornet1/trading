"""
SQLAlchemy async engine + session factory for MariaDB (viznago_dev/prod).
DB_URL is read from the environment — set by the systemd service or .env.
"""

import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

DB_URL = os.getenv("DB_URL")
if not DB_URL:
    raise RuntimeError(
        "DB_URL environment variable is required. "
        "Set it in api/.env or the service EnvironmentFile."
    )

engine = create_async_engine(
    DB_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    """FastAPI dependency — yields a DB session and closes it when done."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
