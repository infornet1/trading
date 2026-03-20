"""
Auth router — wallet signature (EIP-191 personal_sign) → JWT.

Flow:
  1. GET  /auth/nonce?address=0xABC  →  { nonce: "abc123" }
  2. Wallet signs: "Sign in to VIZNAGO FURY\nNonce: abc123"
  3. POST /auth/verify { address, signature }  →  { access_token, token_type }
"""

import secrets
import re
from datetime import datetime, timedelta, timezone

from eth_account.messages import encode_defunct
from eth_account import Account
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models import Nonce, User
from api import auth as jwt_utils

router = APIRouter(prefix="/auth", tags=["auth"])

NONCE_TTL_MINUTES = 10
_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


# ── Schemas ────────────────────────────────────────────────────────────────

class VerifyRequest(BaseModel):
    address: str
    signature: str

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: str) -> str:
        if not _ADDRESS_RE.match(v):
            raise ValueError("Invalid Ethereum address")
        return v.lower()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get("/nonce")
async def get_nonce(
    address: str = Query(..., description="Wallet address (0x…)"),
    db: AsyncSession = Depends(get_db),
):
    """Issue (or refresh) a sign-in nonce for the given wallet address."""
    if not _ADDRESS_RE.match(address):
        raise HTTPException(status_code=400, detail="Invalid address")

    address = address.lower()
    nonce_val  = secrets.token_hex(16)           # 32 hex chars
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=NONCE_TTL_MINUTES)

    # Upsert nonce row
    result = await db.execute(select(Nonce).where(Nonce.address == address))
    row = result.scalar_one_or_none()
    if row:
        row.nonce      = nonce_val
        row.expires_at = expires_at
    else:
        db.add(Nonce(address=address, nonce=nonce_val, expires_at=expires_at))
    await db.commit()

    return {"nonce": nonce_val}


@router.post("/verify", response_model=TokenResponse)
async def verify_signature(
    body: VerifyRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Verify the wallet signature and return a JWT.
    Expects the wallet signed: "Sign in to VIZNAGO FURY\\nNonce: <nonce>"
    """
    address = body.address   # already lowercased by validator

    # 1. Fetch nonce
    result = await db.execute(select(Nonce).where(Nonce.address == address))
    nonce_row = result.scalar_one_or_none()
    if not nonce_row:
        raise HTTPException(status_code=400, detail="No nonce found — call /auth/nonce first")

    if datetime.now(timezone.utc) > nonce_row.expires_at.replace(tzinfo=timezone.utc):
        raise HTTPException(status_code=400, detail="Nonce expired — call /auth/nonce again")

    # 2. Recover signer from signature
    message  = f"Sign in to VIZNAGO FURY\nNonce: {nonce_row.nonce}"
    msg_hash = encode_defunct(text=message)
    try:
        recovered = Account.recover_message(msg_hash, signature=body.signature)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid signature: {e}")

    if recovered.lower() != address:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Signature address mismatch",
        )

    # 3. Delete used nonce (one-time use)
    await db.delete(nonce_row)

    # 4. Upsert user row
    result = await db.execute(select(User).where(User.address == address))
    user = result.scalar_one_or_none()
    if not user:
        user = User(address=address)
        db.add(user)
    user.last_seen = datetime.now(timezone.utc)
    await db.commit()

    # 5. Issue JWT
    token = jwt_utils.create_access_token(address)
    return TokenResponse(access_token=token)
