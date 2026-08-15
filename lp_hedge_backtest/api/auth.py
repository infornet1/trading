"""
JWT utility helpers — create and validate tokens.
Uses python-jose with HS256. SECRET_KEY must be set in env.
"""

import os
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

SECRET_KEY  = os.getenv("SECRET_KEY", "")
ALGORITHM   = "HS256"
EXPIRE_HOURS = 168  # 7 days — reduces re-auth friction on dashboard revisit

_ADMIN_WALLETS = {
    w.strip().lower()
    for w in os.getenv("ADMIN_WALLETS", "").split(",")
    if w.strip()
}

# auto_error=False: a MISSING Authorization header must yield 401 (like an
# expired/invalid token), not HTTPBearer's default 403 — the frontend only
# handles 401 by redirecting to login.
_bearer = HTTPBearer(auto_error=False)


def _require_creds(creds: HTTPAuthorizationCredentials | None) -> HTTPAuthorizationCredentials:
    if creds is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return creds


def create_access_token(address: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=EXPIRE_HOURS)
    payload: dict = {"sub": address, "exp": exp}
    if address.lower() in _ADMIN_WALLETS:
        payload["is_admin"] = True
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Return full payload dict or raise HTTPException 401."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if not payload.get("sub"):
            raise ValueError("no sub")
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
        )


def get_current_address(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> str:
    return decode_token(_require_creds(creds).credentials)["sub"]


def get_current_admin(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> str:
    payload = decode_token(_require_creds(creds).credentials)
    if not payload.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return payload["sub"]
