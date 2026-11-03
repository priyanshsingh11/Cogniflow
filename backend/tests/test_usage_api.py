"""Usage & cost dashboard API: aggregation maths, tenancy, viewer access.

Rows are seeded directly (llm_calls with shared call_ids for fallbacks,
tool_calls behind a real MCP server/tool, workflow runs + step runs) so the
report's totals, breakdowns, zero-filled daily series and slowest lists are
all asserted without going through the LLM gateway.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import (
    LLMCall,
    McpServer,
    McpTool,
    StepRun,
    ToolCall,
    Workflow,
    WorkflowRun,
    WorkflowVersion,
)
from tests.conftest import TEST_DATABASE_URL
from tests.test_tenancy import _add_member, _first_org_and_workspace, _signup


async def _insert(session, *rows) -> None:
    for row in rows:
        session.add(row)
    await session.flush()


def _seed(workspace_id: uuid.UUID, agent_id: uuid.UUID | None = None) -> dict:
    """Seed one workspace's worth of usage rows; returns ids for assertions."""

    async def go():
        engine = create_async_engine(TEST_DATABASE_URL)
        try:
            async with async_sessionmaker(engine)() as s:
                call_a = uuid.uuid4()  # fallback: error then success
                call_b = uuid.uuid4()  # success, single attempt
                call_c = uuid.uuid4()  # failed: only attempts errored

                await _insert(
                    s,
                    LLMCall(
                        workspace_id=workspace_id,
                        agent_id=agent_id,
                        call_id=call_a,
                        request_id="req-a",
                        provider="groq",
                        model="llama-3.1-8b",
                        tier="small",
                        route_reason="step_type=classify",
                        attempt_no=1,
                        status="error",
                        error_type="RateLimitError",
                        prompt_tokens=10,
                        completion_tokens=0,
                        latency_ms=100,
                        cost_usd=Decimal("0"),
                    ),
                    LLMCall(
                        workspace_id=workspace_id,
                        agent_id=agent_id,
                        call_id=call_a,
                        request_id="req-a",
                        provider="groq",
                        model="llama-3.1-8b",
                        tier="small",
                        route_reason="step_type=classify",
                        attempt_no=2,
                        status="success",
                        prompt_tokens=40,
                        completion_tokens=20,
                        latency_ms=300,
                        cost_usd=Decimal("0"),
                    ),
                    LLMCall(
                        workspace_id=workspace_id,
                        agent_id=agent_id,
                        call_id=call_b,
                        request_id="req-b",
                        provider="openrouter",
                        model="qwen-2.5-7b",
                        tier="medium",
                        route_reason="",
                        attempt_no=1,
                        status="success",
                        prompt_tokens=100,
                        completion_tokens=50,
                        latency_ms=500,
                        cost_usd=Decimal("0"),
                    ),
                    LLMCall(
                        workspace_id=workspace_id,
                        agent_id=agent_id,
                        call_id=call_c,
                        request_id="req-c",
                        provider="groq",
                        model="llama-3.1-8b",
                        tier="small",
                        route_reason="",
                        attempt_no=1,
                        status="invalid_output",
                        error_type="ValidationError",
                        prompt_tokens=7,
                        completion_tokens=0,
                        latency_ms=50,
                        cost_usd=Decimal("0"),
                    ),
                )

                # MCP tool calls behind a real server/tool pair.
                server = McpServer(
                    workspace_id=workspace_id,
                    name="seed-server",
                    transport="stdio",
                    url_or_command="python",
                    status="connected",
                )
                s.add(server)
                await s.flush()
                tool = McpTool(
                    mcp_server_id=server.id,
                    name="seed_tool",
                    input_schema={"type": "object", "properties": {}},
                    approved=True,
                )
                s.add(tool)
                await s.flush()
                await _insert(
                    s,
                    ToolCall(
                        mcp_tool_id=tool.id,
                        workspace_id=workspace_id,
                        invoked_by="api",
                        arguments={},
                        result={"content": "ok"},
                        status="ok",
                        latency_ms=10,
                    ),
                    ToolCall(
                        mcp_tool_id=tool.id,
                        workspace_id=workspace_id,
                        invoked_by="api",
                        arguments={},
                        result={"error": "boom"},
                        status="error",
                        latency_ms=20,
                    ),
                )

                # Workflow + runs (one succeeded with timing, one failed).
                wf = Workflow(workspace_id=workspace_id, name="Seed Flow")
                s.add(wf)
                await s.flush()
                version = WorkflowVersion(workflow_id=wf.id, version=1, graph={"steps": []})
                s.add(version)
                await s.flush()
                wf.current_version_id = version.id

                now = datetime.now(UTC)
                ok_run = WorkflowRun(
                    workflow_id=wf.id,
                    workflow_version_id=version.id,
                    workspace_id=workspace_id,
                    status="succeeded",
                    started_at=now - timedelta(seconds=30),
                    finished_at=now - timedelta(seconds=5),
                )
                bad_run = WorkflowRun(
                    workflow_id=wf.id,
                    workflow_version_id=version.id,
                    workspace_id=workspace_id,
                    status="failed",
                    error="step blew up",
                    started_at=now - timedelta(seconds=10),
                    finished_at=now - timedelta(seconds=8),
                )
                s.add_all([ok_run, bad_run])
                await s.flush()
                await _insert(
                    s,
                    StepRun(
                        workflow_run_id=ok_run.id,
                        step_name="summarize",
                        attempt=1,
                        status="succeeded",
                        started_at=now - timedelta(seconds=28),
                        finished_at=now - timedelta(seconds=6),
                    ),
                    StepRun(
                        workflow_run_id=bad_run.id,
                        step_name="classify",
                        attempt=1,
                        status="failed",
                        started_at=now - timedelta(seconds=9),
                        finished_at=now - timedelta(seconds=8),
                    ),
                )
                await s.commit()
                return {"call_ids": [call_a, call_b, call_c], "workflow_id": str(wf.id)}
        finally:
            await engine.dispose()

    return asyncio.run(go())


def _report(client: TestClient, user: dict, ws: str, **params) -> dict:
    resp = client.get(f"/workspaces/{ws}/usage", params=params, headers=user["headers"])
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---- aggregation -------------------------------------------------------------


def test_usage_totals_and_breakdowns(client: TestClient):
    alice = _signup(client, "usage-a@test.dev", "Alice")
    _, ws = _first_org_and_workspace(client, alice)
    _seed(ws)

    data = _report(client, alice, ws, days=7)
    totals = data["totals"]

    # Logical calls (call_id grouped): 3 calls, 4 attempts, 1 fallback, 1 failed.
    assert totals["llm_calls"] == 3
    assert totals["llm_attempts"] == 4
    assert totals["fallback_calls"] == 1
    assert totals["failed_calls"] == 1
    assert totals["fallback_rate"] == pytest.approx(1 / 3, abs=1e-4)
    assert totals["failure_rate"] == pytest.approx(1 / 3, abs=1e-4)

    assert totals["prompt_tokens"] == 10 + 40 + 100 + 7
    assert totals["completion_tokens"] == 0 + 20 + 50 + 0
    assert totals["total_tokens"] == 227
    assert totals["cost_usd"] == 0.0

    assert totals["avg_latency_ms"] == pytest.approx((100 + 300 + 500 + 50) / 4, abs=0.5)
    assert totals["p95_latency_ms"] >= totals["avg_latency_ms"]
    assert totals["p95_latency_ms"] <= 500

    assert totals["tool_calls"] == 2
    assert totals["tool_call_errors"] == 1

    assert totals["runs"] == 2
    assert totals["runs_succeeded"] == 1
    assert totals["runs_failed"] == 1
    assert totals["run_success_rate"] == pytest.approx(0.5)

    # Tier breakdown: small = 3 attempts (call A x2 + call C), medium = 1.
    by_tier = {t["tier"]: t for t in data["by_tier"]}
    assert set(by_tier) == {"small", "medium"}
    assert by_tier["small"]["attempts"] == 3
    assert by_tier["small"]["calls"] == 2  # call A and call C are logical calls
    assert by_tier["small"]["errors"] == 2  # error + invalid_output
    assert by_tier["medium"]["attempts"] == 1 and by_tier["medium"]["errors"] == 0

    by_model = {(m["provider"], m["model"]): m for m in data["by_model"]}
    assert by_model[("groq", "llama-3.1-8b")]["attempts"] == 3
    assert by_model[("openrouter", "qwen-2.5-7b")]["attempts"] == 1
    assert by_model[("openrouter", "qwen-2.5-7b")]["tokens"] == 150

    # Unattributed (playground/chat) calls group under a null agent.
    assert len(data["by_agent"]) == 1
    assert data["by_agent"][0]["agent_id"] is None
    assert data["by_agent"][0]["attempts"] == 4


def test_usage_daily_series_is_zero_filled(client: TestClient):
    alice = _signup(client, "usage-day@test.dev", "Alice")
    _, ws = _first_org_and_workspace(client, alice)
    _seed(ws)

    data = _report(client, alice, ws, days=7)
    by_day = data["by_day"]
    today = datetime.now(UTC).date()
    assert len(by_day) == 7  # one entry per day, no gaps
    assert by_day[-1]["day"] == today.isoformat()
    assert by_day[0]["day"] == (today - timedelta(days=6)).isoformat()

    # Seeded rows are "today": the last bar carries the data, the rest are 0.
    assert by_day[-1]["calls"] == 3
    assert by_day[-1]["attempts"] == 4
    assert by_day[-1]["tokens"] == 227
    assert by_day[-1]["errors"] == 2
    assert all(d["calls"] == 0 for d in by_day[:-1])
    assert sum(d["calls"] for d in by_day) == data["totals"]["llm_calls"]

    # days is validated, not silently clamped.
    zero = client.get(
        f"/workspaces/{ws}/usage", params={"days": 0}, headers=alice["headers"]
    )
    assert zero.status_code == 422
    too_big = client.get(
        f"/workspaces/{ws}/usage", params={"days": 91}, headers=alice["headers"]
    )
    assert too_big.status_code == 422


def test_usage_recent_errors_and_slowest_lists(client: TestClient):
    alice = _signup(client, "usage-slow@test.dev", "Alice")
    _, ws = _first_org_and_workspace(client, alice)
    _seed(ws)

    data = _report(client, alice, ws)

    kinds = [e["kind"] for e in data["recent_errors"]]
    assert "llm_call" in kinds and "run" in kinds
    llm_err = next(e for e in data["recent_errors"] if e["kind"] == "llm_call")
    assert llm_err["message"] == "RateLimitError" or llm_err["message"] == "ValidationError"
    assert llm_err["context"]["provider"] in ("groq", "openrouter")
    run_err = next(e for e in data["recent_errors"] if e["kind"] == "run")
    assert run_err["message"] == "step blew up"
    # Newest first overall.
    stamps = [e["created_at"] for e in data["recent_errors"]]
    assert stamps == sorted(stamps, reverse=True)

    steps = data["slowest_steps"]
    assert len(steps) == 2
    assert steps[0]["step_name"] == "summarize"  # ~22s beats ~1s
    assert steps[0]["duration_ms"] > steps[1]["duration_ms"]
    assert steps[0]["workflow_name"] == "Seed Flow"

    wfs = data["slowest_workflows"]
    assert len(wfs) == 1
    assert wfs[0]["workflow_name"] == "Seed Flow"
    assert wfs[0]["runs"] == 2
    assert wfs[0]["max_duration_ms"] >= wfs[0]["avg_duration_ms"] > 0


def test_usage_days_window_excludes_old_rows(client: TestClient):
    alice = _signup(client, "usage-window@test.dev", "Alice")
    _, ws = _first_org_and_workspace(client, alice)
    _seed(ws)

    # A row older than a 1-day window (created_at is server-set now(), so we
    # assert the window behaviour by checking days=1 still reports today's
    # rows and the series collapses to a single bar).
    data = _report(client, alice, ws, days=1)
    assert data["days"] == 1
    assert len(data["by_day"]) == 1
    assert data["totals"]["llm_calls"] == 3


# ---- tenancy and RBAC ---------------------------------------------------------


def test_usage_is_workspace_scoped(client: TestClient):
    alice = _signup(client, "usage-iso-a@test.dev", "Alice")
    _, alice_ws = _first_org_and_workspace(client, alice)
    _seed(alice_ws)

    bob = _signup(client, "usage-iso-b@test.dev", "Bob")
    _, bob_ws = _first_org_and_workspace(client, bob)
    _seed(bob_ws)  # identical seed: numbers must not blend

    alice_data = _report(client, alice, alice_ws)
    bob_data = _report(client, bob, bob_ws)
    assert alice_data["totals"]["llm_calls"] == bob_data["totals"]["llm_calls"] == 3

    # Foreign workspace is a 404, not a partial report.
    assert (
        client.get(f"/workspaces/{alice_ws}/usage", headers=bob["headers"]).status_code == 404
    )
    assert client.get(f"/workspaces/{alice_ws}/usage").status_code == 401


def test_usage_is_readable_by_viewers_but_not_non_members(client: TestClient):
    alice = _signup(client, "usage-rbac@test.dev", "Alice")
    org, ws = _first_org_and_workspace(client, alice)
    _seed(ws)
    viewer = _add_member(client, alice, org, "usage-viewer@test.dev", "viewer")
    member = _add_member(client, alice, org, "usage-member@test.dev", "member")

    # Viewers get the full report (it's read-only).
    for user in (viewer, member, alice):
        data = _report(client, user, ws)
        assert data["totals"]["llm_calls"] == 3

    outsider = _signup(client, "usage-outside@test.dev", "Outsider")
    assert client.get(f"/workspaces/{ws}/usage", headers=outsider["headers"]).status_code == 404


def test_usage_empty_workspace_reports_zeros(client: TestClient):
    alice = _signup(client, "usage-empty@test.dev", "Alice")
    _, ws = _first_org_and_workspace(client, alice)

    data = _report(client, alice, ws)
    totals = data["totals"]
    assert totals["llm_calls"] == 0 and totals["llm_attempts"] == 0
    assert totals["cost_usd"] == 0.0
    assert totals["run_success_rate"] == 0.0  # no decided runs -> 0, not NaN
    assert totals["fallback_rate"] == 0.0 and totals["failure_rate"] == 0.0
    assert data["by_tier"] == [] and data["by_model"] == [] and data["by_agent"] == []
    assert len(data["by_day"]) == 30  # default window, still zero-filled
    assert data["recent_errors"] == []
    assert data["slowest_steps"] == [] and data["slowest_workflows"] == []
    assert all(d["calls"] == 0 for d in data["by_day"])
