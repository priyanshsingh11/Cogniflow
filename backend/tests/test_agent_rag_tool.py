"""Agent runtime gains its first real tool: knowledge_search (phase 3a)."""

import pytest
from fastapi.testclient import TestClient

from app.llm.deps import get_gateway
from app.llm.gateway import LLMGateway
from app.main import app
from tests.fakes import FakeProvider
from tests.test_llm_gateway import _no_sleep, _registry
from tests.test_tenancy import _first_org_and_workspace, _signup

CALL = '{"tool": "knowledge_search", "arguments": {"query": "restart the worker"}}'


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
    _, ws = _first_org_and_workspace(client, user)
    return user, ws


def _upload(client, user, ws, filename: str, content: bytes):
    resp = client.post(
        f"/workspaces/{ws}/documents",
        files={"file": (filename, content, "text/plain")},
        headers=user["headers"],
    )
    assert resp.status_code == 201
    # Re-fetch: the 201 body predates the background indexing task.
    fresh = client.get(
        f"/workspaces/{ws}/documents/{resp.json()['id']}", headers=user["headers"]
    )
    assert fresh.json()["status"] == "ready", fresh.json()
    return fresh.json()


def _run_agent(client, user, ws, name="Researcher"):
    created = client.post(
        f"/workspaces/{ws}/agents",
        json={"name": name, "role": "research", "system_prompt": "use tools"},
        headers=user["headers"],
    )
    assert created.status_code == 201, created.text
    agent_id = created.json()["id"]
    return client.post(
        f"/workspaces/{ws}/agents/{agent_id}/run",
        json={"input": "How do I recover the service?"},
        headers=user["headers"],
    )


@pytest.mark.parametrize(
    "fake", [{"m1": [CALL, "The worker must be restarted [1]."]}], indirect=True
)
def test_agent_calls_knowledge_search_and_cites_result(client: TestClient, fake):
    user, ws = _setup(client, "rag-agent@test.dev")
    _upload(client, user, ws, "runbook.txt", "To recover the service, restart the worker.")

    resp = _run_agent(client, user, ws)
    assert resp.status_code == 200, resp.text
    result = resp.json()

    assert result["status"] == "completed"
    assert [s["kind"] for s in result["steps"]] == ["tool"]
    step = result["steps"][0]
    assert step["tool"] == "knowledge_search"
    assert step["arguments"] == {"query": "restart the worker"}
    assert "[1] (runbook.txt #0)" in step["result"]
    assert "restart the worker" in step["result"]
    assert result["output"] == "The worker must be restarted [1]."


@pytest.mark.parametrize("fake", [{"m1": [CALL, "Nothing found in sources."]}], indirect=True)
def test_knowledge_tool_is_tenant_scoped(client: TestClient, fake):
    """The agent runs in Bob's empty workspace: the tool must not reach
    Alice's documents even though they exist in the same database."""
    alice, alice_ws = _setup(client, "alice-rag@test.dev")
    _upload(client, alice, alice_ws, "secret.txt", "alice proprietary recovery notes")
    bob, bob_ws = _setup(client, "bob-rag@test.dev")

    result = _run_agent(client, bob, bob_ws, name="BobBot").json()
    assert result["steps"][0]["kind"] == "tool"
    assert "No relevant passages found" in result["steps"][0]["result"]
    assert "proprietary" not in result["steps"][0]["result"]
