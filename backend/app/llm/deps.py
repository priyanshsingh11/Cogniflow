"""Gateway construction from settings. Overridden in tests via
app.dependency_overrides[get_gateway]."""

from app.config import settings
from app.db.redis import redis
from app.llm.gateway import LLMGateway
from app.llm.providers.groq import GroqProvider
from app.llm.providers.openrouter import OpenRouterProvider
from app.llm.ratelimit import RedisRateLimiter
from app.llm.registry import ModelRegistry

_gateway: LLMGateway | None = None


def build_gateway() -> LLMGateway:
    providers = {}
    if settings.groq_api_key:
        providers["groq"] = GroqProvider(
            settings.groq_api_key, timeout=settings.llm_timeout_seconds
        )
    if settings.openrouter_api_key:
        providers["openrouter"] = OpenRouterProvider(
            settings.openrouter_api_key, timeout=settings.llm_timeout_seconds
        )
    return LLMGateway(
        providers,
        ModelRegistry.load(),
        limiter=RedisRateLimiter(
            redis, {"groq": settings.groq_rpm, "openrouter": settings.openrouter_rpm}
        ),
        max_attempts=settings.llm_max_attempts,
    )


def get_gateway() -> LLMGateway:
    global _gateway
    if _gateway is None:
        _gateway = build_gateway()
    return _gateway


async def shutdown_gateway() -> None:
    global _gateway
    if _gateway is not None:
        await _gateway.close()
        _gateway = None
