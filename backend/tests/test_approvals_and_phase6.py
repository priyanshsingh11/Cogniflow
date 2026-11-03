"""Phase 6: Human-in-the-loop approvals, run pause/resume, and unlocking tools

that require approval.
"""

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.postgres import SessionLocal
from app.llm.deps import get_gateway
from app.llm.gateway import LLMGateway
from app.main import app
from app.mcp import client as mcp_client
from app.mcp.client import DiscoveredTool, ToolOutcome
from app.models.workflow import Approval
from app.workflows.executor import execute_run
from tests.fakes import FakeProvider
from tests.test_llm_gateway import _no_sleep, _registry
from tests.test_tenancy import _add_member, _first_org_and_workspace, _signup

REFUND_TOOL = DiscoveredTool(
    "issue_refund",
    "Process a financial refund.",
    {
        "type": "object",
        "properties": {
            "customer_id": {"type": "string"},
            "amount": {"type": "number"},
        },
        "required": ["customer_id", "amount"],
    },
)


@pytest.fixture()
def fake(request):
    from app.llm.deps import set_gateway

    script = getattr(request, "param", {})
    g = FakeProvider("g", script)
    gateway = LLMGateway({"g": g, "o": FakeProvider("o", {})}, _registry(), sleep=_no_sleep)
    set_gateway(gateway)
    app.dependency_overrides[get_gateway] = lambda: gateway
    yield g
    set_gateway(None)
    app.dependency_overrides.pop(get_gateway, None)


@pytest.fixture()
def fake_mcp(monkeypatch):
    state = {
        "tools": [REFUND_TOOL],
        "outcome": ToolOutcome("refund processed for $50", False),
    }

    async def list_tools(server):
        return list(state["tools"])

    async def call_tool(server, name, arguments):
        return state["outcome"]

    monkeypatch.setattr(mcp_client, "list_tools", list_tools)
    monkeypatch.setattr(mcp_client, "call_tool", call_tool)
    return state


def _setup(client: TestClient, email: str = "alice@test.dev"):
    user = _signup(client, email, email.split("@")[0].title())
    org_id, ws_id = _first_org_and_workspace(client, user)
    return user, org_id, ws_id


def _run_db(coro_fn):
    async def go():
        from app.db.postgres import engine

        await engine.dispose()
        try:
            return await coro_fn()
        finally:
            await engine.dispose()

    return asyncio.run(go())


def test_workflow_pauses_for_human_approval(client: TestClient):
    alice, _, ws = _setup(client)

    wf_payload = {
        "name": "Approval Pausing Flow",
        "steps": [
            {
                "name": "prep_data",
                "type": "condition",
                "position": 0,
                "config": {"expression": "true"},
            },
            {
                "name": "approval_gate",
                "type": "approval",
                "position": 1,
                "config": {
                    "description": "Please sign off on deployment to production",
                    "details": {"env": "production"},
                },
            },
            {
                "name": "post_deploy",
                "type": "condition",
                "position": 2,
                "config": {"expression": "true"},
            },
        ],
    }
    wf = client.post(
        f"/workspaces/{ws}/workflows", json=wf_payload, headers=alice["headers"]
    ).json()

    # Trigger run
    r = client.post(
        f"/workspaces/{ws}/workflows/{wf['id']}/runs", json={}, headers=alice["headers"]
    ).json()
    run_id = r["id"]

    # Execute run
    paused_run = _run_db(lambda: execute_run(uuid.UUID(run_id)))
    assert paused_run.status == "waiting_approval"

    # Verify run details and approvals inbox
    details = client.get(f"/workspaces/{ws}/runs/{run_id}", headers=alice["headers"]).json()
    assert details["status"] == "waiting_approval"
    step_runs = {sr["step_name"]: sr for sr in details["step_runs"]}
    assert step_runs["prep_data"]["status"] == "succeeded"
    assert step_runs["approval_gate"]["status"] == "waiting_approval"
    assert "post_deploy" not in step_runs  # Paused before post_deploy ran!

    # Check approval list
    approvals = client.get(f"/workspaces/{ws}/approvals", headers=alice["headers"]).json()
    assert len(approvals) == 1
    appr = approvals[0]
    assert appr["status"] == "pending"
    assert "Please sign off" in appr["description"]
    assert appr["details"] == {"env": "production"}


def test_approval_rejection_fails_run(client: TestClient):
    alice, _, ws = _setup(client)

    wf_payload = {
        "name": "Rejection Flow",
        "steps": [
            {
                "name": "gate",
                "type": "approval",
                "config": {"description": "Sign off"},
            }
        ],
    }
    wf = client.post(
        f"/workspaces/{ws}/workflows", json=wf_payload, headers=alice["headers"]
    ).json()
    r = client.post(
        f"/workspaces/{ws}/workflows/{wf['id']}/runs", json={}, headers=alice["headers"]
    ).json()
    _run_db(lambda: execute_run(uuid.UUID(r["id"])))

    approvals = client.get(
        f"/workspaces/{ws}/approvals?status=pending", headers=alice["headers"]
    ).json()
    appr_id = approvals[0]["id"]

    # Reject
    decide_res = client.post(
        f"/workspaces/{ws}/approvals/{appr_id}/decide",
        json={"action": "reject", "reason": "Budget denied"},
        headers=alice["headers"],
    )
    assert decide_res.status_code == 200
    decided = decide_res.json()
    assert decided["status"] == "rejected"
    assert decided["reason"] == "Budget denied"

    # Verify run marked failed
    details = client.get(f"/workspaces/{ws}/runs/{r['id']}", headers=alice["headers"]).json()
    assert details["status"] == "failed"
    assert "approval rejected" in details["error"].lower()


@pytest.mark.parametrize(
    "fake",
    [{"m1": ["draft report", "final published report"]}],
    indirect=True,
)
def test_approval_grant_resumes_and_finishes_workflow(client: TestClient, fake):
    alice, _, ws = _setup(client)

    wf_payload = {
        "name": "Publish Flow",
        "steps": [
            {
                "name": "draft",
                "type": "llm",
                "position": 0,
                "config": {"prompt": "Draft report"},
            },
            {
                "name": "sign_off",
                "type": "approval",
                "position": 1,
                "config": {"description": "Approve publishing"},
            },
            {
                "name": "publish",
                "type": "llm",
                "position": 2,
                "config": {"prompt": "Publishing: {{ steps.draft.output.content }}"},
            },
        ],
    }
    wf = client.post(
        f"/workspaces/{ws}/workflows", json=wf_payload, headers=alice["headers"]
    ).json()
    r = client.post(
        f"/workspaces/{ws}/workflows/{wf['id']}/runs", json={}, headers=alice["headers"]
    ).json()
    run_id = r["id"]

    # Initial execution pauses at sign_off
    paused = _run_db(lambda: execute_run(uuid.UUID(run_id)))
    assert paused.status == "waiting_approval"

    # Approve
    approvals = client.get(
        f"/workspaces/{ws}/approvals?status=pending", headers=alice["headers"]
    ).json()
    appr_id = approvals[0]["id"]
    client.post(
        f"/workspaces/{ws}/approvals/{appr_id}/decide",
        json={"action": "approve", "reason": "Looks good"},
        headers=alice["headers"],
    )

    # Resume execution
    resumed = _run_db(lambda: execute_run(uuid.UUID(run_id), resume=True))
    assert resumed.status == "succeeded"
    assert "draft" in resumed.output
    assert "sign_off" in resumed.output
    assert resumed.output["sign_off"]["approved"] is True
    assert "publish" in resumed.output
    assert resumed.output["publish"]["content"] == "final published report"


def test_cannot_decide_already_decided_approval_409(client: TestClient):
    alice, _, ws = _setup(client)

    wf_payload = {
        "name": "Single Gate",
        "steps": [{"name": "gate", "type": "approval", "config": {}}],
    }
    wf = client.post(
        f"/workspaces/{ws}/workflows", json=wf_payload, headers=alice["headers"]
    ).json()
    r = client.post(
        f"/workspaces/{ws}/workflows/{wf['id']}/runs", json={}, headers=alice["headers"]
    ).json()
    _run_db(lambda: execute_run(uuid.UUID(r["id"])))

    approvals = client.get(f"/workspaces/{ws}/approvals", headers=alice["headers"]).json()
    appr_id = approvals[0]["id"]

    # First decision
    r1 = client.post(
        f"/workspaces/{ws}/approvals/{appr_id}/decide",
        json={"action": "approve"},
        headers=alice["headers"],
    )
    assert r1.status_code == 200

    # Second decision -> 409 Conflict
    r2 = client.post(
        f"/workspaces/{ws}/approvals/{appr_id}/decide",
        json={"action": "reject"},
        headers=alice["headers"],
    )
    assert r2.status_code == 409


def test_mcp_tool_requiring_approval_pauses_workflow_and_resumes(client: TestClient, fake_mcp):
    alice, _, ws = _setup(client)

    # Register and discover refund tool
    s_resp = client.post(
        f"/workspaces/{ws}/mcp/servers",
        json={"name": "billing", "transport": "stdio", "command": "python"},
        headers=alice["headers"],
    ).json()
    client.post(f"/workspaces/{ws}/mcp/servers/{s_resp['id']}/discover", headers=alice["headers"])

    tools = client.get(f"/workspaces/{ws}/mcp/tools", headers=alice["headers"]).json()
    tool_id = tools[0]["id"]

    # Approve tool for agent/workflow use, but set requires_approval=True
    client.patch(
        f"/workspaces/{ws}/mcp/tools/{tool_id}",
        json={"approved": True, "requires_approval": True},
        headers=alice["headers"],
    )

    wf_payload = {
        "name": "Refund Pipeline",
        "steps": [
            {
                "name": "refund_step",
                "type": "mcp_tool",
                "config": {
                    "tool_name": "issue_refund",
                    "arguments": {"customer_id": "cust-99", "amount": 50},
                },
            }
        ],
    }
    wf = client.post(
        f"/workspaces/{ws}/workflows", json=wf_payload, headers=alice["headers"]
    ).json()
    r = client.post(
        f"/workspaces/{ws}/workflows/{wf['id']}/runs", json={}, headers=alice["headers"]
    ).json()
    run_id = r["id"]

    # Run pauses because tool has requires_approval=True
    paused = _run_db(lambda: execute_run(uuid.UUID(run_id)))
    assert paused.status == "waiting_approval"

    # An approval was created with tool arguments
    approvals = client.get(
        f"/workspaces/{ws}/approvals?status=pending", headers=alice["headers"]
    ).json()
    assert len(approvals) == 1
    assert approvals[0]["details"]["arguments"] == {"customer_id": "cust-99", "amount": 50}

    # Decide approve
    client.post(
        f"/workspaces/{ws}/approvals/{approvals[0]['id']}/decide",
        json={"action": "approve"},
        headers=alice["headers"],
    )

    # Resume run -> tool is unlocked and invoked!
    resumed = _run_db(lambda: execute_run(uuid.UUID(run_id), resume=True))
    assert resumed.status == "succeeded"
    assert resumed.output["refund_step"]["content"] == "refund processed for $50"


def test_mcp_standalone_invoke_unlocked_with_approval(client: TestClient, fake_mcp):
    alice, _, ws = _setup(client)

    s_resp = client.post(
        f"/workspaces/{ws}/mcp/servers",
        json={"name": "billing2", "transport": "stdio", "command": "python"},
        headers=alice["headers"],
    ).json()
    client.post(f"/workspaces/{ws}/mcp/servers/{s_resp['id']}/discover", headers=alice["headers"])
    tools = client.get(f"/workspaces/{ws}/mcp/tools", headers=alice["headers"]).json()
    tool_id = tools[0]["id"]
    client.patch(
        f"/workspaces/{ws}/mcp/tools/{tool_id}",
        json={"approved": True, "requires_approval": True},
        headers=alice["headers"],
    )

    # 1. Direct invoke without approval fails with 403
    r_fail = client.post(
        f"/workspaces/{ws}/mcp/tools/{tool_id}/invoke",
        json={"arguments": {"customer_id": "c1", "amount": 10}},
        headers=alice["headers"],
    )
    assert r_fail.status_code == 403
    assert "requires human approval" in r_fail.json()["detail"]

    # 2. Create an approved approval
    async def create_appr():
        async with SessionLocal() as session:
            appr = Approval(
                workspace_id=uuid.UUID(ws),
                status="approved",
                description="Manual sign-off",
            )
            session.add(appr)
            await session.commit()
            return str(appr.id)

    appr_id = _run_db(create_appr)

    # 3. Direct invoke with approval_id succeeds!
    r_ok = client.post(
        f"/workspaces/{ws}/mcp/tools/{tool_id}/invoke",
        json={"arguments": {"customer_id": "c1", "amount": 10}, "approval_id": appr_id},
        headers=alice["headers"],
    )
    assert r_ok.status_code == 200
    assert r_ok.json()["content"] == "refund processed for $50"


def test_approvals_rbac(client: TestClient):
    alice, org, ws = _setup(client, "alice@test.dev")
    bob = _add_member(client, alice, org, "bob@test.dev", "viewer")

    # Create a pending approval
    async def seed():
        async with SessionLocal() as session:
            appr = Approval(workspace_id=uuid.UUID(ws), status="pending", description="Sign off")
            session.add(appr)
            await session.commit()
            return str(appr.id)

    appr_id = _run_db(seed)

    # Viewer can view
    r_list = client.get(f"/workspaces/{ws}/approvals", headers=bob["headers"])
    assert r_list.status_code == 200
    r_get = client.get(f"/workspaces/{ws}/approvals/{appr_id}", headers=bob["headers"])
    assert r_get.status_code == 200

    # Viewer cannot decide (403)
    r_decide_v = client.post(
        f"/workspaces/{ws}/approvals/{appr_id}/decide",
        json={"action": "approve"},
        headers=bob["headers"],
    )
    assert r_decide_v.status_code == 403

    # Owner can decide
    r_decide_o = client.post(
        f"/workspaces/{ws}/approvals/{appr_id}/decide",
        json={"action": "approve"},
        headers=alice["headers"],
    )
    assert r_decide_o.status_code == 200
