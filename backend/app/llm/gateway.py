"""The one door to language models.

For each call: route to a starting tier, then walk an ordered chain of models.
- Failure fallback: rate-limited / unavailable / rejected -> next model.
- Quality escalation: output fails the caller's validator -> skip the rest of
  that tier and move up.
Hard cap on total attempts so a bad day on free tiers can never loop.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable

from app.llm.base import Provider
from app.llm.errors import (
    AllModelsFailedError,
    LLMError,
    ProviderUnavailableError,
    RateLimitError,
)
from app.llm.ratelimit import NoopRateLimiter, RateLimiter
from app.llm.registry import ModelRegistry
from app.llm.router import route
from app.llm.types import Attempt, GatewayResult, LLMResponse, Message, ModelRef, RoutingHints

# Returns None when the output is acceptable, else a short reason string.
Validator = Callable[[str], str | None]
Sleep = Callable[[float], Awaitable[None]]


def non_empty(content: str) -> str | None:
    return None if content.strip() else "empty output"


class LLMGateway:
    def __init__(
        self,
        providers: dict[str, Provider],
        registry: ModelRegistry,
        *,
        limiter: RateLimiter | None = None,
        max_attempts: int = 8,
        max_retries: int = 1,
        backoff_seconds: float = 0.5,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.providers = providers
        self.registry = registry
        self.limiter = limiter or NoopRateLimiter()
        self.max_attempts = max_attempts
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self._sleep = sleep

    async def complete(
        self,
        messages: list[Message],
        hints: RoutingHints | None = None,
        validator: Validator | None = non_empty,
    ) -> GatewayResult:
        hints = hints or RoutingHints()
        decision = route(messages, hints)
        chain: list[tuple[str, ModelRef]] = self.registry.chain(decision.tier)
        if hints.pinned_model is not None:
            chain.insert(0, ("pinned", hints.pinned_model))

        attempts: list[Attempt] = []
        skip_tier: str | None = None
        for label, ref in chain:
            if len(attempts) >= self.max_attempts:
                break
            if label == skip_tier:
                continue
            provider = self.providers.get(ref.provider)
            if provider is None:  # no API key configured for this vendor
                continue
            if not await self.limiter.allow(ref.provider):
                attempts.append(
                    Attempt(len(attempts) + 1, label, ref.provider, ref.model, "skipped_rate_limit")
                )
                continue

            response = await self._call_with_retry(provider, ref, label, messages, hints, attempts)
            if response is None:
                continue
            problem = validator(response.content) if validator else None
            if problem is None:
                self._stamp(attempts, decision.reason)
                return GatewayResult(response, label, decision.reason, attempts)
            attempts[-1].status = "invalid_output"
            attempts[-1].error_type = problem
            skip_tier = label  # quality problem: stop using this tier, escalate

        self._stamp(attempts, decision.reason)
        raise AllModelsFailedError(attempts)

    @staticmethod
    def _stamp(attempts: list[Attempt], reason: str) -> None:
        for a in attempts:
            a.route_reason = reason

    async def _call_with_retry(
        self,
        provider: Provider,
        ref: ModelRef,
        label: str,
        messages: list[Message],
        hints: RoutingHints,
        attempts: list[Attempt],
    ) -> LLMResponse | None:
        for retry in range(self.max_retries + 1):
            if len(attempts) >= self.max_attempts:
                return None
            started = time.monotonic()
            try:
                response = await provider.chat(ref.model, messages, **hints.params)
            except LLMError as exc:
                attempts.append(
                    Attempt(
                        len(attempts) + 1,
                        label,
                        ref.provider,
                        ref.model,
                        "error",
                        error_type=type(exc).__name__,
                        latency_ms=int((time.monotonic() - started) * 1000),
                    )
                )
                # Only transient failures are worth retrying the same model.
                if isinstance(exc, ProviderUnavailableError) and not isinstance(
                    exc, RateLimitError
                ):
                    if retry < self.max_retries:
                        await self._sleep(self.backoff_seconds * (2**retry))
                        continue
                return None
            attempts.append(
                Attempt(
                    len(attempts) + 1,
                    label,
                    ref.provider,
                    ref.model,
                    "success",
                    latency_ms=response.latency_ms,
                    prompt_tokens=response.prompt_tokens,
                    completion_tokens=response.completion_tokens,
                )
            )
            return response
        return None

    async def close(self) -> None:
        for provider in self.providers.values():
            await provider.close()
