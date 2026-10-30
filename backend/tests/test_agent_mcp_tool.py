"""Approved MCP tools are exposed to agents as `mcp__<server>__<tool>` (phase 4b)."""

import pytest
from fastapi.testclient import TestClient

from tests.test_agent_rag_tool import _run_agent, _setup, fake  # noqa: F401
from tests.test_mcp_api import _discover, _register, fake_mcp  # noqa: F401

CALL = '{"tool": "mcp__demo__add", "arguments": {"a": 1, "b": 4}}'


def _prepare(client, user, ws, approve: bool):
    server_id = _register(client, user, ws, name="demo").json()["id"]
    tools = _discover(client, user, ws, server_id).json()["tools"]
    add = next(t for t in tools if t["name"] == "add")
    if approve:
        patched = client.patch(
            f"/workspaces/{ws}/mcp/tools/{add['id']}",
            json={"approved": True},
            headers=user["headers"],
        )
        assert patched.status_code == 200, patched.text
    return add["id"]


@pytest.mark.parametrize("fake", [{"m1": [CALL, "The sum is 5."]}], indirect=True)
def test_agent_calls_approved_mcp_tool_and_it_is_logged(client: TestClient, fake, fake_mcp):  # noqa: F811
    user, ws = _setup(client, "mcp-agent@test.dev")
    tool_id = _prepare(client, user, ws, approve=True)

    result = _run_agent(client, user, ws).json()
    assert result["status"] == "completed"
    step = result["steps"][0]
    assert step["kind"] == "tool" and step["tool"] == "mcp__demo__add"
    assert step["result"] == "sum is 5"

    calls = client.get(
        f"/workspaces/{ws}/mcp/tool-calls?tool_id={tool_id}", headers=user["headers"]
    ).json()
    assert [c["invoked_by"] for c in calls] == ["agent"]


@pytest.mark.parametrize("fake", [{"m1": [CALL, "I could not use that tool."]}], indirect=True)
def test_unapproved_mcp_tool_is_not_available_to_agents(client: TestClient, fake, fake_mcp):  # noqa: F811
    user, ws = _setup(client, "mcp-agent2@test.dev")
    _prepare(client, user, ws, approve=False)

    result = _run_agent(client, user, ws).json()
    assert result["steps"][0]["kind"] == "tool_error"
