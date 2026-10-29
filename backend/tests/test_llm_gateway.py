import asyncio

import pytest

from app.llm.errors import (
    AllModelsFailedError,
    ProviderRejectedError,
    ProviderUnavailableError,
    RateLimitError,
)
from app.llm.gateway import LLMGateway
from app.llm.ratelimit import RedisRateLimiter
from app.llm.registry import ModelRegistry
from app.llm.router import route
from app.llm.types import Message, ModelRef, RoutingHints, Tier
from tests.fakes import FakeProvider

MSG = [Message("user", "hi")]


def _registry() -> ModelRegistry:
    ref = ModelRef.parse
    return ModelRegistry(
        tiers={
            Tier.SMALL: [ref("g:s1"), ref("o:s2")],
            Tier.MEDIUM: [ref("g:m1"), ref("o:m2")],
            Tier.LARGE: [ref("g:l1"), ref("o:l2")],
        },
        last_resort=[ref("o:free")],
    )


async def _no_sleep(_: float) -> None:
    return None


def _gateway(g: FakeProvider, o: FakeProvider, **kw) -> LLMGateway:
    return LLMGateway({"g": g, "o": o}, _registry(), sleep=_no_sleep, **kw)


def _run(gateway: LLMGateway, hints: RoutingHints | None = None, validator=...):
    kwargs = {} if validator is ... else {"validator": validator}
    return asyncio.run(gateway.complete(MSG, hints or RoutingHints(step_type="classify"), **kwargs))


# ---- router ----------------------------------------------------------------


def test_router_step_types():
    assert route(MSG, RoutingHints(step_type="classify")).tier == Tier.SMALL
    assert route(MSG, RoutingHints(step_type="plan")).tier == Tier.LARGE
    assert route(MSG, RoutingHints()).tier == Tier.MEDIUM


def test_router_bumps_for_size_and_documents():
    assert route(MSG, RoutingHints(step_type="classify", num_documents=1)).tier == Tier.MEDIUM
    assert route(MSG, RoutingHints(step_type="classify", num_documents=5)).tier == Tier.LARGE
    big = [Message("user", "x" * 4 * 30_000)]
    decision = route(big, RoutingHints(step_type="classify"))
    assert decision.tier == Tier.LARGE and "tokens" in decision.reason


def test_router_respects_pinned_tier():
    d = route(MSG, RoutingHints(step_type="plan", pinned_tier=Tier.SMALL))
    assert d.tier == Tier.SMALL and "pinned" in d.reason


# ---- gateway ---------------------------------------------------------------


def test_success_on_first_model():
    g, o = FakeProvider("g", {}), FakeProvider("o", {})
    result = _run(_gateway(g, o))
    assert result.tier == "small" and result.response.model == "s1"
    assert len(result.attempts) == 1 and result.attempts[0].status == "success"
    assert o.calls == []


def test_rate_limit_falls_back_within_tier_without_retrying_same_model():
    g = FakeProvider("g", {"s1": [RateLimitError("429")]})
    o = FakeProvider("o", {})
    result = _run(_gateway(g, o))
    assert result.response.model == "s2" and result.tier == "small"
    assert g.calls == ["s1"]  # no retry on 429
    assert [a.status for a in result.attempts] == ["error", "success"]
    assert result.attempts[0].error_type == "RateLimitError"


def test_unavailable_is_retried_once_then_falls_back():
    g = FakeProvider("g", {"s1": [ProviderUnavailableError("503")]})
    o = FakeProvider("o", {})
    result = _run(_gateway(g, o))
    assert g.calls == ["s1", "s1"]  # original + one retry
    assert result.response.model == "s2"


def test_unavailable_recovers_on_retry():
    g = FakeProvider("g", {"s1": [ProviderUnavailableError("503"), "recovered"]})
    result = _run(_gateway(g, FakeProvider("o", {})))
    assert result.response.content == "recovered" and result.response.model == "s1"


def test_rejected_model_is_skipped_without_retry():
    g = FakeProvider("g", {"s1": [ProviderRejectedError("404 model")]})
    result = _run(_gateway(g, FakeProvider("o", {})))
    assert g.calls == ["s1"] and result.response.model == "s2"


def test_invalid_output_escalates_to_next_tier_skipping_rest_of_tier():
    g = FakeProvider("g", {"s1": ["bad"], "m1": ["good"]})
    o = FakeProvider("o", {})
    result = _run(_gateway(g, o), validator=lambda c: None if c == "good" else "not good")
    assert result.tier == "medium" and result.response.model == "m1"
    assert o.calls == []  # s2 (rest of the small tier) was skipped
    assert result.attempts[0].status == "invalid_output"
    assert result.attempts[0].error_type == "not good"


def test_empty_output_is_invalid_by_default():
    g = FakeProvider("g", {"s1": [""]})
    result = _run(_gateway(g, FakeProvider("o", {})))
    assert result.tier == "medium"  # escalated past the empty small answer


def test_escalation_never_goes_down():
    g, o = FakeProvider("g", {}), FakeProvider("o", {})
    _run(_gateway(g, o), RoutingHints(step_type="plan"))
    assert g.calls == ["l1"]  # started at large, never touched small/medium


def test_all_models_failed_raises_with_attempts_and_respects_cap():
    err = RateLimitError("429")
    g = FakeProvider("g", {m: [err] for m in ("s1", "m1", "l1")})
    o = FakeProvider("o", {m: [err] for m in ("s2", "m2", "l2", "free")})
    with pytest.raises(AllModelsFailedError) as info:
        _run(_gateway(g, o))
    assert len(info.value.attempts) == 7  # whole chain, one try each

    capped = _gateway(g, o, max_attempts=3)
    with pytest.raises(AllModelsFailedError) as info:
        _run(capped)
    assert len(info.value.attempts) == 3


def test_last_resort_used_when_tiers_exhausted():
    err = RateLimitError("429")
    g = FakeProvider("g", {m: [err] for m in ("s1", "m1", "l1")})
    o = FakeProvider("o", {m: [err] for m in ("s2", "m2", "l2")})
    result = _run(_gateway(g, o))
    assert result.tier == "last_resort" and result.response.model == "free"


def test_provider_without_key_is_skipped_silently():
    o = FakeProvider("o", {})
    gateway = LLMGateway({"o": o}, _registry(), sleep=_no_sleep)  # no "g" provider
    result = asyncio.run(gateway.complete(MSG, RoutingHints(step_type="classify")))
    assert result.response.model == "s2"


def test_pinned_model_tried_first():
    g, o = FakeProvider("g", {}), FakeProvider("o", {})
    hints = RoutingHints(step_type="classify", pinned_model=ModelRef.parse("o:custom"))
    result = _run(_gateway(g, o), hints)
    assert result.tier == "pinned" and result.response.model == "custom"


def test_local_rate_limiter_skips_provider_and_records_it():
    class DenyG:
        async def allow(self, provider: str) -> bool:
            return provider != "g"

    g, o = FakeProvider("g", {}), FakeProvider("o", {})
    result = _run(_gateway(g, o, limiter=DenyG()))
    assert g.calls == [] and result.response.model == "s2"
    assert result.attempts[0].status == "skipped_rate_limit"


# ---- redis limiter (fake redis) -------------------------------------------


class FakeRedis:
    def __init__(self, fail: bool = False) -> None:
        self.counts: dict[str, int] = {}
        self.fail = fail

    async def incr(self, key: str) -> int:
        if self.fail:
            raise ConnectionError("down")
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, seconds: int) -> None:
        return None


def test_redis_limiter_blocks_over_limit_and_fails_open():
    limiter = RedisRateLimiter(FakeRedis(), {"g": 2})
    results = [asyncio.run(limiter.allow("g")) for _ in range(3)]
    assert results == [True, True, False]
    assert asyncio.run(limiter.allow("unlimited")) is True
    assert asyncio.run(RedisRateLimiter(FakeRedis(fail=True), {"g": 1}).allow("g")) is True


def test_model_registry_loads_real_yaml_and_builds_chain():
    registry = ModelRegistry.load()
    chain = registry.chain(Tier.MEDIUM)
    labels = [label for label, _ in chain]
    assert "small" not in labels and labels[0] == "medium" and labels[-1] == "last_resort"
