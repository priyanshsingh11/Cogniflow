"""Agents CRUD + run endpoints: RBAC, tenant isolation, llm_calls recording."""

import pytest
from fastapi.testclient import TestClient

from app.llm.deps import get_gateway
from app.llm.gateway import LLMGateway
from app.main import app
from tests.fakes import FakeProvider
from tests.test_llm_api import _llm_call_rows
from tests.test_llm_gateway import _no_sleep, _registry
from tests.test_tenancy import _add_member, _first_org_and_workspace, _signup

AGENT = {"name": "Helper", "role": "custom", "system_prompt": "be brief"}
PLAN = '{"steps": [{"role": "research", "task": "find"}, {"role": "writing", "task": "write"}]}'


@pytest.fixture()
def fake(request):
    """Install a fake gateway; tests pass the g-script via indirect param."""
    script = getattr(request, "param", {})
    g = FakeProvider("g", script)
    gateway = LLMGateway({"g": g, "o": FakeProvider("o", {})}, _registry(), sleep=_no_sleep)
    app.dependency_overrides[get_gateway] = lambda: gateway
    yield g
    app.dependency_overrides.pop(get_gateway, None)


def _setup(client: TestClient):
    alice = _signup(client, "alice@test.dev", "Alice")
    org_id, ws = _first_org_and_workspace(client, alice)
    return alice, org_id, ws


def _create(client, owner, ws, **overrides):
    return client.post(
        f"/workspaces/{ws}/agents", json={**AGENT, **overrides}, headers=owner["headers"]
    )


def test_crud_happy_path(client: TestClient):
    alice, _, ws = _setup(client)
    created = _create(client, alice, ws, tier_pin="large", params={"temperature": 0.2})
    assert created.status_code == 201, created.text
    agent = created.json()
    assert agent["tier_pin"] == "large" and agent["params"] == {"temperature": 0.2}

    listing = client.get(f"/workspaces/{ws}/agents", headers=alice["headers"]).json()
    assert [a["name"] for a in listing] == ["Helper"]
    one = client.get(f"/workspaces/{ws}/agents/{agent['id']}", headers=alice["headers"])
    assert one.json()["id"] == agent["id"]

    patched = client.patch(
        f"/workspaces/{ws}/agents/{agent['id']}",
        json={"system_prompt": "be verbose", "tier_pin": None},
        headers=alice["headers"],
    )
    assert patched.status_code == 200
    assert patched.json()["system_prompt"] == "be verbose" and patched.json()["tier_pin"] is None
    assert patched.json()["name"] == "Helper"  # untouched fields survive

    assert (
        client.delete(
            f"/workspaces/{ws}/agents/{agent['id']}", headers=alice["headers"]
        ).status_code
        == 204
    )
    assert client.get(f"/workspaces/{ws}/agents", headers=alice["headers"]).json() == []


def test_validation_and_duplicates(client: TestClient):
    alice, _, ws = _setup(client)
    assert _create(client, alice, ws, role="wizard").status_code == 422
    assert _create(client, alice, ws, tier_pin="huge").status_code == 422
    assert _create(client, alice, ws, model_pin="no-colon").status_code == 422
    assert _create(client, alice, ws, model_pin="groq:openai/gpt-oss-20b").status_code == 201
    assert _create(client, alice, ws, model_pin=None).status_code == 409  # same name


def test_rbac_viewer_reads_member_runs_only_admin_edits(client: TestClient, fake):
    alice, org_id, ws = _setup(client)
    agent_id = _create(client, alice, ws).json()["id"]
    viewer = _add_member(client, alice, org_id, "viewer@test.dev", "viewer")
    member = _add_member(client, alice, org_id, "member@test.dev", "member")
    base = f"/workspaces/{ws}/agents"

    # viewers can read but not edit or run
    assert client.get(base, headers=viewer["headers"]).status_code == 200
    assert client.post(base, json=AGENT, headers=viewer["headers"]).status_code == 403
    run = client.post(f"{base}/{agent_id}/run", json={"input": "hi"}, headers=viewer["headers"])
    assert run.status_code == 403
    # members can run but not create/patch/delete
    assert (
        client.post(base, json={**AGENT, "name": "X"}, headers=member["headers"]).status_code == 403
    )
    assert (
        client.patch(
            f"{base}/{agent_id}", json={"name": "Y"}, headers=member["headers"]
        ).status_code
        == 403
    )
    assert client.delete(f"{base}/{agent_id}", headers=member["headers"]).status_code == 403
    ran = client.post(f"{base}/{agent_id}/run", json={"input": "hi"}, headers=member["headers"])
    assert ran.status_code == 200


def test_other_tenant_cannot_touch_agents(client: TestClient, fake):
    alice, _, alice_ws = _setup(client)
    bob = _signup(client, "bob@test.dev", "Bob")
    _, bob_ws = _first_org_and_workspace(client, bob)
    agent_id = _create(client, alice, alice_ws).json()["id"]

    assert client.get(f"/workspaces/{alice_ws}/agents", headers=bob["headers"]).status_code == 404
    # Bob's own workspace + Alice's agent id must not resolve either.
    cross = client.get(f"/workspaces/{bob_ws}/agents/{agent_id}", headers=bob["headers"])
    assert cross.status_code == 404
    cross_run = client.post(
        f"/workspaces/{bob_ws}/agents/{agent_id}/run", json={"input": "hi"}, headers=bob["headers"]
    )
    assert cross_run.status_code == 404
    assert (
        client.post(f"/workspaces/{alice_ws}/coordinator/run", json={"goal": "x"}).status_code
        == 401
    )


@pytest.mark.parametrize("fake", [{"m1": ["hello from the agent"]}], indirect=True)
def test_run_agent_records_llm_calls_with_agent_id(client: TestClient, fake):
    alice, _, ws = _setup(client)
    agent_id = _create(client, alice, ws).json()["id"]

    resp = client.post(
        f"/workspaces/{ws}/agents/{agent_id}/run", json={"input": "hi"}, headers=alice["headers"]
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["output"] == "hello from the agent" and body["models_used"] == ["g:m1"]

    rows = _llm_call_rows()
    assert len(rows) == 1 and str(rows[0].agent_id) == agent_id and rows[0].status == "success"


@pytest.mark.parametrize("fake", [{"l1": [PLAN], "m1": ["the facts", "the report"]}], indirect=True)
def test_coordinator_run_uses_workspace_agent_for_role(client: TestClient, fake):
    alice, _, ws = _setup(client)
    researcher = _create(
        client, alice, ws, name="Our Researcher", role="research", tier_pin="small"
    ).json()
    # tier_pin small -> researcher call goes to s1, not m1
    fake.script["s1"] = ["custom facts"]

    resp = client.post(
        f"/workspaces/{ws}/coordinator/run", json={"goal": "report on X"}, headers=alice["headers"]
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "completed" and body["final"] == "the facts"  # writer used m1
    assert [s["agent"] for s in body["steps"]] == ["Our Researcher", "Writer"]
    assert body["steps"][0]["output"] == "custom facts"

    rows = _llm_call_rows()
    assert len(rows) == body["llm_calls"] == 3
    by_agent = {str(r.agent_id): r for r in rows if r.agent_id}
    assert researcher["id"] in by_agent and by_agent[researcher["id"]].model == "s1"
    assert any(r.agent_id is None and r.route_reason == "step_type=plan" for r in rows)


def test_coordinator_plan_failure_is_502_and_recorded(client: TestClient, fake):
    from app.llm.errors import RateLimitError

    err = RateLimitError("429")
    fake.script.update({m: [err] for m in ("l1",)})
    o = app.dependency_overrides[get_gateway]().providers["o"]
    o.script.update({m: [err] for m in ("l2", "free")})

    alice, _, ws = _setup(client)
    resp = client.post(
        f"/workspaces/{ws}/coordinator/run", json={"goal": "x"}, headers=alice["headers"]
    )
    assert resp.status_code == 502
    assert len(_llm_call_rows()) == 3 and all(r.status == "error" for r in _llm_call_rows())
