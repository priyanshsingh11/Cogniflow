import time
from typing import Protocol

from redis.asyncio import Redis


class RateLimiter(Protocol):
    async def allow(self, provider: str) -> bool: ...


class NoopRateLimiter:
    async def allow(self, provider: str) -> bool:
        return True


class RedisRateLimiter:
    """Fixed-window requests-per-minute limiter per provider. Avoids burning
    attempts on free-tier 429s. Fails open: if Redis is down we still try."""

    def __init__(self, redis: Redis, limits_per_minute: dict[str, int]) -> None:
        self._redis = redis
        self._limits = limits_per_minute

    async def allow(self, provider: str) -> bool:
        limit = self._limits.get(provider)
        if not limit:
            return True
        key = f"llm:rl:{provider}:{int(time.time() // 60)}"
        try:
            count = await self._redis.incr(key)
            if count == 1:
                await self._redis.expire(key, 70)
        except Exception:
            return True
        return count <= limit
