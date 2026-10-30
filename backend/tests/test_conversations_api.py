"""Conversations & chat: CRUD, RBAC/tenancy, cited turns persisted to Mongo."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.llm.deps import get_gateway
from app.llm.errors import RateLimitError
from app.llm.gateway import LLMGateway
from app.main import app
from tests.fakes import FakeProvider
from tests.test_knowledge_api import _fresh, _upload
from tests.test_llm_api import _llm_call_rows
from tests.test_llm_gateway import _no_sleep, _registry
from tests.test_tenancy import _add_member, _first_org_and_workspace, _signup

CITED = "The procedure restarts the worker [1]."


@pytest.fixture()
def fake(request):
    script = getattr(request, "param", {})
    g = FakeProvider("g", script)
    gateway = LLMGateway({"g": g, "o": FakeProvider("o", {})}, _registry(), sleep=_no_sleep)
    app.dependency_overrides[get_gateway] = lambda: gateway
    yield g
    app.dependency_overrides.pop(get_gateway, None)


def _setup(client: TestClient, email: str):
    user = _signup(client, email, email.split("@")[0].title())
    org_id, ws = _first_org_and_workspace(client, user)
    return user, org_id, ws


def _conv(client, user, ws, title: str | None = None):
    resp = client.post(
        f"/workspaces/{ws}/conversations",
        json={"title": title} if title is not None else {},
        headers=user["headers"],
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _upload_ready(client, user, ws) -> dict:
    resp = _upload(client, user, ws, "runbook.txt", "To recover, restart the worker process.")
    assert resp.status_code == 201, resp.text
    doc = _fresh(client, user, ws, resp).json()
    assert doc["status"] == "ready", doc
    return doc


def _message_rows():
    """Postgres staging rows via a dedicated engine (the app engine's pooled
    connections belong to the TestClient loop)."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models import Message
    from tests.conftest import TEST_DATABASE_URL

    async def go():
        engine = create_async_engine(TEST_DATABASE_URL)
        try:
            async with async_sessionmaker(engine)() as s:
                result = await s.execute(select(Message).order_by(Message.created_at))
                return result.scalars().all()
        finally:
            await engine.dispose()

    return asyncio.run(go())


# ---- CRUD and tenancy ------------------------------------------------------


def test_create_list_get_conversations(client: TestClient):
    user, _, ws = _setup(client, "conv-crud@test.dev")
    a = _conv(client, user, ws, "Ops questions")
    b = _conv(client, user, ws)  # default title
    assert a["title"] == "Ops questions" and b["title"] == ""
    assert a["user_id"] == user["user_id"]

    listing = client.get(f"/workspaces/{ws}/conversations", headers=user["headers"]).json()
    assert {c["id"] for c in listing} == {a["id"], b["id"]}

    one = client.get(f"/workspaces/{ws}/conversations/{a['id']}", headers=user["headers"])
    assert one.status_code == 200 and one.json()["title"] == "Ops questions"

    empty = client.get(
        f"/workspaces/{ws}/conversations/{a['id']}/messages", headers=user["headers"]
    )
    assert empty.status_code == 200 and empty.json() == []


def test_conversations_are_tenant_scoped(client: TestClient):
    alice, _, alice_ws = _setup(client, "alice-conv@test.dev")
    bob, _, bob_ws = _setup(client, "bob-conv@test.dev")
    conv = _conv(client, alice, alice_ws, "alice private thread")

    # Every path under Bob's workspace 404s for Alice's conversation.
    assert (
        client.get(
            f"/workspaces/{bob_ws}/conversations/{conv['id']}", headers=bob["headers"]
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/workspaces/{bob_ws}/conversations/{conv['id']}/messages",
            json={"content": "hi"},
            headers=bob["headers"],
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/workspaces/{bob_ws}/conversations/{conv['id']}/messages",
            headers=bob["headers"],
        ).status_code
        == 404
    )
    assert client.get(f"/workspaces/{bob_ws}/conversations", headers=bob["headers"]).json() == []


def test_viewer_reads_but_cannot_write(client: TestClient):
    owner, org, ws = _setup(client, "owner-conv@test.dev")
    conv = _conv(client, owner, ws, "team thread")
    viewer = _add_member(client, owner, org, "viewer-conv@test.dev", "viewer")

    listing = client.get(f"/workspaces/{ws}/conversations", headers=viewer["headers"])
    assert listing.status_code == 200
    assert (
        client.get(
            f"/workspaces/{ws}/conversations/{conv['id']}", headers=viewer["headers"]
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/workspaces/{ws}/conversations/{conv['id']}/messages",
            headers=viewer["headers"],
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/workspaces/{ws}/conversations", json={"title": "no"}, headers=viewer["headers"]
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/workspaces/{ws}/conversations/{conv['id']}/messages",
            json={"content": "hi"},
            headers=viewer["headers"],
        ).status_code
        == 403
    )


# ---- chat turns ------------------------------------------------------------


@pytest.mark.parametrize("fake", [{"m1": [CITED]}], indirect=True)
def test_turn_persists_messages_and_citations_in_mongo(client: TestClient, fake):
    user, _, ws = _setup(client, "turn@test.dev")
    _upload_ready(client, user, ws)
    conv = _conv(client, user, ws, "runbook thread")

    resp = client.post(
        f"/workspaces/{ws}/conversations/{conv['id']}/messages",
        json={"content": "How do I recover the service?"},
        headers=user["headers"],
    )
    assert resp.status_code == 200, resp.text
    turn = resp.json()
    assert turn["user_message"]["content"] == "How do I recover the service?"
    assert turn["assistant_message"]["content"] == CITED
    assert turn["tier"] == "medium" and turn["route_reason"]
    assert turn["assistant_message"]["meta"] == {
        "tier": turn["tier"],
        "route_reason": turn["route_reason"],
    }
    assert turn["assistant_message"]["citations"][0]["filename"] == "runbook.txt"

    # History comes from Mongo: both messages, ordered, citations intact.
    history = client.get(
        f"/workspaces/{ws}/conversations/{conv['id']}/messages", headers=user["headers"]
    ).json()
    assert [m["role"] for m in history] == ["user", "assistant"]
    assistant = history[1]
    assert assistant["content"] == CITED
    citation = assistant["citations"][0]
    assert citation["filename"] == "runbook.txt" and citation["chunk_index"] == 0
    assert 0.0 <= citation["score"] <= 1.0
    assert assistant["meta"]["tier"] == "medium"
    assert history[0]["citations"] == [] and history[0]["meta"] is None

    # Postgres staging rows are flipped: payload nulled after Mongo ack.
    rows = _message_rows()
    assert [r.role for r in rows] == ["user", "assistant"]
    assert all(r.status == "synced" and r.content is None for r in rows)
    assert all(r.citations is None and r.meta is None for r in rows)

    assert len(_llm_call_rows()) >= 1  # chat calls go through llm_calls


def test_post_message_requires_indexed_documents(client: TestClient):
    user, _, ws = _setup(client, "nodoc-conv@test.dev")
    conv = _conv(client, user, ws)

    resp = client.post(
        f"/workspaces/{ws}/conversations/{conv['id']}/messages",
        json={"content": "hello?"},
        headers=user["headers"],
    )
    assert resp.status_code == 400 and "No indexed" in resp.json()["detail"]
    # Atomic turn: a failed answer persists nothing anywhere.
    assert (
        client.get(
            f"/workspaces/{ws}/conversations/{conv['id']}/messages", headers=user["headers"]
        ).json()
        == []
    )
    assert _message_rows() == []


def test_tier_is_validated_not_crashing(client: TestClient):
    user, _, ws = _setup(client, "tier-conv@test.dev")
    _upload_ready(client, user, ws)
    conv = _conv(client, user, ws)
    resp = client.post(
        f"/workspaces/{ws}/conversations/{conv['id']}/messages",
        json={"content": "hi", "tier": "ultra"},
        headers=user["headers"],
    )
    assert resp.status_code == 422  # not a 500 from the router


def test_total_model_failure_502_persists_nothing(client: TestClient):
    down = RateLimitError("provider down")
    g = FakeProvider("g", {"s1": [down], "m1": [down], "l1": [down]})
    o = FakeProvider("o", {"s2": [down], "m2": [down], "l2": [down], "free": [down]})
    gateway = LLMGateway({"g": g, "o": o}, _registry(), sleep=_no_sleep)
    app.dependency_overrides[get_gateway] = lambda: gateway
    try:
        user, _, ws = _setup(client, "fail-conv@test.dev")
        _upload_ready(client, user, ws)
        conv = _conv(client, user, ws)

        resp = client.post(
            f"/workspaces/{ws}/conversations/{conv['id']}/messages",
            json={"content": "How do I recover?"},
            headers=user["headers"],
        )
        assert resp.status_code == 502
        assert (
            client.get(
                f"/workspaces/{ws}/conversations/{conv['id']}/messages",
                headers=user["headers"],
            ).json()
            == []
        )
        assert _message_rows() == []  # atomic turn: nothing staged either
        assert len(_llm_call_rows()) > 1  # every failed attempt was recorded
    finally:
        app.dependency_overrides.pop(get_gateway, None)
