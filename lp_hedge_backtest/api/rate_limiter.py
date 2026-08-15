"""Simple in-memory rate limiter for FastAPI dependencies.

Designed for a single-worker API process. Limits are per client IP or per
authenticated address, depending on the dependency used.
"""

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from fastapi import Depends, HTTPException, Request, status


@dataclass
class _Bucket:
    tokens: float = 0.0
    last: float = field(default_factory=time.monotonic)


class RateLimiter:
    """Token-bucket rate limiter."""

    def __init__(
        self,
        max_requests: int = 30,
        window_seconds: float = 60.0,
        key_func: Optional[Callable[[Request], str]] = None,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.key_func = key_func or self._ip_key
        self._buckets: dict[str, _Bucket] = {}

    @staticmethod
    def _ip_key(request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def is_allowed(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _Bucket(tokens=float(self.max_requests), last=now)
            self._buckets[key] = bucket

        # Replenish tokens
        elapsed = now - bucket.last
        bucket.tokens = min(
            float(self.max_requests),
            bucket.tokens + elapsed * (self.max_requests / self.window_seconds),
        )
        bucket.last = now

        if bucket.tokens >= 1:
            bucket.tokens -= 1
            return True
        return False

    def __call__(self, request: Request) -> None:
        key = self.key_func(request)
        if not self.is_allowed(key):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please slow down.",
                headers={"Retry-After": str(int(self.window_seconds))},
            )


# ── Pre-configured limiters ────────────────────────────────────────────────

# General API limit: 60 requests/minute per IP
ip_limiter = RateLimiter(max_requests=60, window_seconds=60)

# Performance dashboard endpoints: 30 requests/minute per IP
performance_limiter = RateLimiter(max_requests=30, window_seconds=60)

# Admin endpoints: 60 requests/minute per IP (admin actions should be deliberate)
admin_limiter = RateLimiter(max_requests=60, window_seconds=60)

# Auth endpoints: stricter to prevent brute force (10 requests/minute per IP)
auth_limiter = RateLimiter(max_requests=10, window_seconds=60)
