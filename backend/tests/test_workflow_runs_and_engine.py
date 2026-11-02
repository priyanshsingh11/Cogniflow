"""Workflow execution engine, LangGraph orchestration, step types, leases,

retries, idempotency and stuck-run reaper (Phase 5).
"""
import asyncio
import datetime
from datetime import timezone
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.postgres import SessionLocal
from app.llm.deps import get_gateway
from app.llm.gateway import LLMGateway
from app.main import app
from app.mcp import client as mcp_client
from app.mcp.client import DiscoveredTool, ToolOutcome
from app.models.document import Document, DocumentChunk
from app.models.llm_call import LLMCall
from app.models.mcp import ToolCall
from app.models.workflow import StepRun, WorkflowRun
from app.worker.tasks import execute_workflow_run, process_document, reap_stuck_runs
from app.workflows.executor import StepLeaseError, execute_run
from tests.fakes import FakeProvider
from tests.test_llm_gateway import _no_sleep, _registry
from tests.test_tenancy import _first_org_and_workspace, _signup

ADD = DiscoveredTool(
    "add",
    "Add two numbers.",
    {
        "type": "object",
        "properties": {
            "a": {"type": "number"},
            "b": {"type": "number"},
        },
        "required": ["a", "b"],
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
        "tools": [ADD],
        "outcome": ToolOutcome("sum is 42", False),
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


def test_trigger_run_and_idempotency_key(client: TestClient):
    alice, _, ws = _setup(client)
    wf_payload = {
        "name": "Idempotent Flow",
        "steps": [{"name": "step1", "type": "llm", "config": {"prompt": "hello"}}],
    }
    wf = client.post(f"/workspaces/{ws}/workflows", json=wf_payload, headers=alice["headers"]).json()

    # Trigger with idempotency key
    r1 = client.post(
        f"/workspaces/{ws}/workflows/{wf['id']}/runs",
        json={"input": {"topic": "ai"}, "idempotency_key": "idemp-test-1"},
        headers=alice["headers"],
    )
    assert r1.status_code == 201
    run1 = r1.json()
    assert run1["status"] == "queued"
    assert run1["idempotency_key"] == "idemp-test-1"

    # Trigger again with SAME idempotency key -> returns same run without creating new one
    r2 = client.post(
        f"/workspaces/{ws}/workflows/{wf['id']}/runs",
        json={"input": {"topic": "different"}, "idempotency_key": "idemp-test-1"},
        headers=alice["headers"],
    )
    assert r2.status_code in (200, 201)
    run2 = r2.json()
    assert run2["id"] == run1["id"]
    assert run2["input"] == {"topic": "ai"}  # Original input preserved


@pytest.mark.parametrize(
    "fake",
    [{"m1": ["Hello from model"]}],
    indirect=True,
)
def test_execute_llm_step_and_records_llm_calls(client: TestClient, fake):
    alice, _, ws = _setup(client)
    wf_payload = {
        "name": "LLM Flow",
        "steps": [
            {
                "name": "generate",
                "type": "llm",
                "config": {"prompt": "Write a greeting for {{ input.name }}"},
            }
        ],
    }
    wf = client.post(f"/workspaces/{ws}/workflows", json=wf_payload, headers=alice["headers"]).json()

    r = client.post(
        f"/workspaces/{ws}/workflows/{wf['id']}/runs",
        json={"input": {"name": "Alice"}},
        headers=alice["headers"],
    )
    assert r.status_code == 201
    run_id = r.json()["id"]

    # Execute run
    finished_run = _run_db(lambda: execute_run(uuid.UUID(run_id)))
    assert finished_run.status == "succeeded", finished_run.error
    assert finished_run.output is not None
    assert "generate" in finished_run.output
    assert finished_run.output["generate"]["content"] == "Hello from model"

    # Verify step_runs record and llm_calls association
    details = client.get(f"/workspaces/{ws}/runs/{run_id}", headers=alice["headers"]).json()
    assert details["status"] == "succeeded"
    assert len(details["step_runs"]) == 1
    sr = details["step_runs"][0]
    assert sr["step_name"] == "generate"
    assert sr["status"] == "succeeded"
    assert sr["llm_calls_count"] >= 1


@pytest.mark.parametrize(
    "fake",
    [
        {
            "m1": [
                "step 1 output",
                "step 2 received: step 1 output",
            ]
        }
    ],
    indirect=True,
)
def test_results_pass_between_steps(client: TestClient, fake):
    alice, _, ws = _setup(client)
    wf_payload = {
        "name": "Two-Step Pipeline",
        "steps": [
            {
                "name": "step_one",
                "type": "llm",
                "position": 0,
                "config": {"prompt": "Produce first piece"},
            },
            {
                "name": "step_two",
                "type": "llm",
                "position": 1,
                "config": {"prompt": "Refine: {{ steps.step_one.output.content }}"},
            },
        ],
    }
    wf = client.post(f"/workspaces/{ws}/workflows", json=wf_payload, headers=alice["headers"]).json()

    r = client.post(
        f"/workspaces/{ws}/workflows/{wf['id']}/runs",
        json={},
        headers=alice["headers"],
    )
    run_id = r.json()["id"]

    finished_run = _run_db(lambda: execute_run(uuid.UUID(run_id)))
    assert finished_run.status == "succeeded"
    assert "step_one" in finished_run.output
    assert "step_two" in finished_run.output
    assert finished_run.output["step_two"]["content"] == "step 2 received: step 1 output"


def test_knowledge_search_step(client: TestClient):
    alice, _, ws = _setup(client)

    # Seed a document in postgres directly
    async def seed_doc():
        async with SessionLocal() as session:
            doc = Document(
                workspace_id=uuid.UUID(ws),
                filename="manual.md",
                storage_path="manual.md",
                content_hash="hash1",
                size_bytes=100,
                status="ready",
            )
            session.add(doc)
            await session.flush()
            chunk = DocumentChunk(
                document_id=doc.id,
                workspace_id=uuid.UUID(ws),
                chunk_index=0,
                content="Antigravity provides durable background workflow execution.",
                embedding=[0.05] * 384,
                token_count=10,
            )
            session.add(chunk)
            await session.commit()

    _run_db(seed_doc)

    wf_payload = {
        "name": "Search Workflow",
        "steps": [
            {
                "name": "search",
                "type": "knowledge_search",
                "config": {"query": "{{ input.query }}", "top_k": 2},
            }
        ],
    }
    wf = client.post(f"/workspaces/{ws}/workflows", json=wf_payload, headers=alice["headers"]).json()

    r = client.post(
        f"/workspaces/{ws}/workflows/{wf['id']}/runs",
        json={"input": {"query": "workflow execution"}},
        headers=alice["headers"],
    )
    run_id = r.json()["id"]

    finished = _run_db(lambda: execute_run(uuid.UUID(run_id)))
    assert finished.status == "succeeded"
    search_out = finished.output["search"]
    assert search_out["count"] >= 1
    assert "durable background workflow" in search_out["passages"][0]["content"]


def test_mcp_tool_step(client: TestClient, fake_mcp):
    alice, _, ws = _setup(client)

    # Register and discover MCP tool
    s_resp = client.post(
        f"/workspaces/{ws}/mcp/servers",
        json={"name": "calc", "transport": "stdio", "command": "echo"},
        headers=alice["headers"],
    )
    s_id = s_resp.json()["id"]
    client.post(f"/workspaces/{ws}/mcp/servers/{s_id}/discover", headers=alice["headers"])

    tools = client.get(f"/workspaces/{ws}/mcp/tools", headers=alice["headers"]).json()
    tool_id = tools[0]["id"]

    # Approve tool
    client.patch(
        f"/workspaces/{ws}/mcp/tools/{tool_id}",
        json={"approved": True},
        headers=alice["headers"],
    )

    wf_payload = {
        "name": "MCP Flow",
        "steps": [
            {
                "name": "calc_step",
                "type": "mcp_tool",
                "config": {
                    "tool_name": "add",
                    "arguments": {"a": "{{ input.val_a }}", "b": 10},
                },
            }
        ],
    }
    wf = client.post(f"/workspaces/{ws}/workflows", json=wf_payload, headers=alice["headers"]).json()

    r = client.post(
        f"/workspaces/{ws}/workflows/{wf['id']}/runs",
        json={"input": {"val_a": 32}},
        headers=alice["headers"],
    )
    run_id = r.json()["id"]

    finished = _run_db(lambda: execute_run(uuid.UUID(run_id)))
    assert finished.status == "succeeded"
    assert finished.output["calc_step"]["content"] == "sum is 42"

    # Verify tool_calls row has step_run_id
    tc_resp = client.get(f"/workspaces/{ws}/mcp/tool-calls", headers=alice["headers"]).json()
    assert len(tc_resp) >= 1
    assert tc_resp[0]["invoked_by"] == "workflow"


def test_condition_step_routing(client: TestClient):
    alice, _, ws = _setup(client)

    wf_payload = {
        "name": "Conditional Routing",
        "steps": [
            {
                "name": "check",
                "type": "condition",
                "position": 0,
                "config": {
                    "expression": "{{ input.amount > 100 }}",
                    "then_step": "high_value",
                    "else_step": "low_value",
                },
            },
            {
                "name": "high_value",
                "type": "condition",
                "position": 1,
                "config": {"expression": "true"},
            },
            {
                "name": "low_value",
                "type": "condition",
                "position": 2,
                "config": {"expression": "false"},
            },
        ],
    }
    wf = client.post(f"/workspaces/{ws}/workflows", json=wf_payload, headers=alice["headers"]).json()

    # Case 1: amount = 250 -> routes to high_value
    r1 = client.post(
        f"/workspaces/{ws}/workflows/{wf['id']}/runs",
        json={"input": {"amount": 250}},
        headers=alice["headers"],
    ).json()
    run1 = _run_db(lambda: execute_run(uuid.UUID(r1["id"])))
    assert run1.status == "succeeded"
    assert "high_value" in run1.output

    # Case 2: amount = 50 -> routes to low_value
    r2 = client.post(
        f"/workspaces/{ws}/workflows/{wf['id']}/runs",
        json={"input": {"amount": 50}},
        headers=alice["headers"],
    ).json()
    run2 = _run_db(lambda: execute_run(uuid.UUID(r2["id"])))
    assert run2.status == "succeeded"
    assert "low_value" in run2.output


def test_step_lease_prevents_concurrent_execution(client: TestClient):
    alice, _, ws = _setup(client)
    wf_payload = {
        "name": "Lease Test Flow",
        "steps": [{"name": "step_busy", "type": "llm", "config": {"prompt": "test"}}],
    }
    wf = client.post(f"/workspaces/{ws}/workflows", json=wf_payload, headers=alice["headers"]).json()
    wf_id = uuid.UUID(wf["id"])
    ver_id = uuid.UUID(wf["current_version_id"])

    async def go():
        async with SessionLocal() as session:
            # Create a run and step run
            wf_run = WorkflowRun(
                workflow_id=wf_id,
                workflow_version_id=ver_id,
                workspace_id=uuid.UUID(ws),
                status="running",
            )
            session.add(wf_run)
            await session.flush()

            now = datetime.datetime.now(timezone.utc)
            future = now + datetime.timedelta(seconds=120)
            step_run = StepRun(
                workflow_run_id=wf_run.id,
                step_name="step_busy",
                attempt=1,
                status="running",
                lease_worker_id="worker-A",
                lease_expires_at=future,
            )
            session.add(step_run)
            await session.commit()
            return wf_run.id, step_run.id

    run_id, sr_id = _run_db(go)

    # Try to execute step from worker B
    async def try_lease():
        async with SessionLocal() as session:
            # A second worker tries to take the step
            from sqlalchemy import or_, update

            now = datetime.datetime.now(timezone.utc)
            stmt = (
                update(StepRun)
                .where(
                    StepRun.id == sr_id,
                    or_(
                        StepRun.lease_expires_at.is_(None),
                        StepRun.lease_expires_at < now,
                        StepRun.lease_worker_id == "worker-B",
                    ),
                )
                .values(lease_worker_id="worker-B")
            )
            res = await session.execute(stmt)
            return res.rowcount

    rowcount = _run_db(try_lease)
    assert rowcount == 0  # Blocked by worker A's lease!


def test_stuck_run_reaper(client: TestClient):
    alice, _, ws = _setup(client)
    wf_payload = {
        "name": "Stuck Reaper Flow",
        "steps": [{"name": "stuck_step", "type": "llm", "config": {"prompt": "test"}}],
    }
    wf = client.post(f"/workspaces/{ws}/workflows", json=wf_payload, headers=alice["headers"]).json()
    wf_id = uuid.UUID(wf["id"])
    ver_id = uuid.UUID(wf["current_version_id"])

    async def setup_stuck():
        async with SessionLocal() as session:
            wf_run = WorkflowRun(
                workflow_id=wf_id,
                workflow_version_id=ver_id,
                workspace_id=uuid.UUID(ws),
                status="running",
            )
            session.add(wf_run)
            await session.flush()

            # Past expiration
            past = datetime.datetime.now(timezone.utc) - datetime.timedelta(seconds=300)
            step_run = StepRun(
                workflow_run_id=wf_run.id,
                step_name="stuck_step",
                attempt=1,
                status="running",
                lease_worker_id="dead-worker",
                lease_expires_at=past,
            )
            session.add(step_run)
            await session.commit()
            return wf_run.id, step_run.id

    run_id, sr_id = _run_db(setup_stuck)

    # Run reaper
    reaped = _run_db(reap_stuck_runs)
    assert reaped >= 1

    # Verify step_run was reset to pending and attempt incremented
    async def check():
        async with SessionLocal() as session:
            sr = await session.get(StepRun, sr_id)
            wf = await session.get(WorkflowRun, run_id)
            assert sr.status == "pending"
            assert sr.attempt == 2
            assert sr.lease_worker_id is None
            assert wf.status == "queued"

    _run_db(check)


def test_cancel_run(client: TestClient):
    alice, _, ws = _setup(client)
    wf_payload = {
        "name": "Cancel Flow",
        "steps": [{"name": "step1", "type": "llm", "config": {"prompt": "test"}}],
    }
    wf = client.post(f"/workspaces/{ws}/workflows", json=wf_payload, headers=alice["headers"]).json()

    r = client.post(f"/workspaces/{ws}/workflows/{wf['id']}/runs", json={}, headers=alice["headers"]).json()
    run_id = r["id"]

    cancelled = client.post(f"/workspaces/{ws}/runs/{run_id}/cancel", headers=alice["headers"]).json()
    assert cancelled["status"] == "cancelled"
    assert cancelled["finished_at"] is not None
