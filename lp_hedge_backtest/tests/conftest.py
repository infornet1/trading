"""Pytest configuration and shared fixtures."""

import os

# Test encryption key (same format as production). SECRET_KEY for JWT tests.
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("ENCRYPTION_KEY", "XeWdfauM9pkJb479kH6esX2lVqnHyrkh0UEKS8Fz264=")
os.environ.setdefault("DB_URL", "mysql+aiomysql://viznago_test:viznago_test@localhost/viznago_test")
os.environ.setdefault("PERFORMANCE_DASHBOARD_ENABLED", "true")

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

from api.main import app
from api.auth import create_access_token


def create_token(address: str) -> str:
    return create_access_token(address)


@pytest.fixture
def client():
    """Sync TestClient for the FastAPI app."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
async def async_client():
    """Async HTTP client for the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_headers():
    """Return headers for an authenticated test user."""
    address = "0x" + "a" * 40
    token = create_token(address)
    return {"Authorization": f"Bearer {token}"}
