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
EXPIRE_HOURS = 24

_bearer = HTTPBearer()


def create_access_token(address: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=EXPIRE_HOURS)
    return jwt.encode({"sub": address, "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> str:
    """Return wallet address or raise HTTPException 401."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        address: str = payload.get("sub")
        if not address:
            raise ValueError("no sub")
        return address
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
        )


def get_current_address(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> str:
    return decode_token(creds.credentials)
