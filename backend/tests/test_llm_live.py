"""Opt-in smoke test against the real free providers.
Run with: RUN_LIVE_LLM=1 uv run pytest tests/test_llm_live.py -s
Uses keys from backend/.env. Costs nothing but consumes free-tier quota."""

import asyncio
import os

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("RUN_LIVE_LLM"), reason="set RUN_LIVE_LLM=1")


def test_live_small_tier_answers():
    from app.llm.deps import build_gateway
    from app.llm.types import Message, RoutingHints

    async def go():
        gateway = build_gateway()
        try:
            return await gateway.complete(
                [Message("user", "Reply with exactly the word: pong")],
                RoutingHints(step_type="classify", params={"max_tokens": 200}),
            )
        finally:
            await gateway.close()

    result = asyncio.run(go())
    print(result.tier, result.response.provider, result.response.model, result.attempts)
    assert result.response.content.strip()
