"""Playground endpoint: auth/tenancy rules and llm_calls recording."""

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.llm.deps import get_gateway
from app.llm.errors import RateLimitError
from app.llm.gateway import LLMGateway
from app.main import app
from tests.fakes import FakeProvider
from tests.test_llm_gateway import _no_sleep, _registry
from tests.test_tenancy import _first_org_and_workspace, _signup

BODY = {"messages": [{"role": "user", "content": "hello"}], "step_type": "classify"}


@pytest.fixture()
def fake_gateway():
    g = FakeProvider("g", {"s1": [RateLimitError("429")]})
    o = FakeProvider("o", {})
    gateway = LLMGateway({"g": g, "o": o}, _registry(), sleep=_no_sleep)
    app.dependency_overrides[get_gateway] = lambda: gateway
    yield gateway
    app.dependency_overrides.pop(get_gateway, None)


def _llm_call_rows():
    # Own engine: the app engine's pooled connections belong to the TestClient loop.
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models import LLMCall
    from tests.conftest import TEST_DATABASE_URL

    async def go():
        engine = create_async_engine(TEST_DATABASE_URL)
        try:
            async with async_sessionmaker(engine)() as s:
                result = await s.execute(select(LLMCall).order_by(LLMCall.attempt_no))
                return result.scalars().all()
        finally:
            await engine.dispose()

    return asyncio.run(go())


def test_chat_routes_falls_back_and_records_every_attempt(client: TestClient, fake_gateway):
    alice = _signup(client, "alice@test.dev", "Alice")
    _, ws = _first_org_and_workspace(client, alice)

    resp = client.post(f"/workspaces/{ws}/llm/chat", json=BODY, headers=alice["headers"])
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["model"] == "s2" and data["tier"] == "small"
    assert [a["status"] for a in data["attempts"]] == ["error", "success"]

    rows = _llm_call_rows()
    assert [(r.model, r.status) for r in rows] == [("s1", "error"), ("s2", "success")]
    assert str(rows[0].workspace_id) == ws and rows[0].route_reason == "step_type=classify"
    assert rows[1].prompt_tokens == 10 and float(rows[1].cost_usd) == 0.0


def test_chat_requires_auth_and_membership(client: TestClient, fake_gateway):
    alice = _signup(client, "alice@test.dev", "Alice")
    bob = _signup(client, "bob@test.dev", "Bob")
    _, alice_ws = _first_org_and_workspace(client, alice)

    url = f"/workspaces/{alice_ws}/llm/chat"
    assert client.post(url, json=BODY).status_code == 401
    assert client.post(url, json=BODY, headers=bob["headers"]).status_code == 404
    assert _llm_call_rows() == []


def test_chat_all_models_failed_returns_502_and_records_attempts(client: TestClient):
    err = RateLimitError("429")
    g = FakeProvider("g", {m: [err] for m in ("s1", "m1", "l1")})
    o = FakeProvider("o", {m: [err] for m in ("s2", "m2", "l2", "free")})
    gateway = LLMGateway({"g": g, "o": o}, _registry(), sleep=_no_sleep)
    app.dependency_overrides[get_gateway] = lambda: gateway
    try:
        alice = _signup(client, "alice@test.dev", "Alice")
        _, ws = _first_org_and_workspace(client, alice)
        resp = client.post(f"/workspaces/{ws}/llm/chat", json=BODY, headers=alice["headers"])
    finally:
        app.dependency_overrides.pop(get_gateway, None)
    assert resp.status_code == 502
    assert len(_llm_call_rows()) == 7
