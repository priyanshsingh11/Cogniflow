"""Per-user / per-workspace API rate limits (phase 8).

Redis fixed-window counters keyed like the provider limiter
(``rl:<bucket>:<subject>:<window>``). Fails open: if Redis is unreachable the
request proceeds — availability beats strictness for a shared free tier.

Over-limit requests raise 429 with `Retry-After` (seconds until the window
resets) and `X-RateLimit-Limit` / `X-RateLimit-Remaining`.
"""

import time
from dataclasses import dataclass

from fastapi import HTTPException, Request

from app.config import settings
from app.core.metrics import record_rate_limited
from app.db.redis import redis

# Importable for tests: monkeypatch `app.core.ratelimit.redis` with a fake.


@dataclass(frozen=True)
class LimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int  # seconds until the window resets (0 when allowed)


async def consume(key: str, limit: int, window: int) -> LimitResult:
    """Count one hit against `limit` per `window` seconds for `key`."""
    if not settings.rate_limits_enabled:
        return LimitResult(True, limit, limit, 0)
    bucket = int(time.time() // window)
    full_key = f"rl:{key}:{bucket}"
    try:
        count = await redis.incr(full_key)
        if count == 1:
            await redis.expire(full_key, window + 5)
    except Exception:  # Redis down -> fail open (same rule as the provider limiter)
        return LimitResult(True, limit, limit, 0)
    allowed = count <= limit
    retry_after = window - int(time.time() % window) + 1
    return LimitResult(allowed, limit, max(limit - count, 0), retry_after if not allowed else 0)


async def enforce(bucket: str, subject: str, limit: int, window: int) -> None:
    """Raise 429 unless one more request from `subject` fits the window."""
    result = await consume(f"{bucket}:{subject}", limit, window)
    if not result.allowed:
        record_rate_limited()
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded for {bucket}; retry in {result.retry_after}s",
            headers={
                "Retry-After": str(result.retry_after),
                "X-RateLimit-Limit": str(result.limit),
                "X-RateLimit-Remaining": "0",
            },
        )


def client_ip(request: Request) -> str:
    """First X-Forwarded-For hop when proxied, else the socket peer."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"
