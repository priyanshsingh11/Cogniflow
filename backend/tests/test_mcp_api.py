"""MCP layer: server registry, discovery upsert, validated invocation and
tool_calls logging (phase 4a). The MCP client is faked at the module boundary
(`app.mcp.client`), exactly like FakeProvider for the gateway; the real SDK
path is covered by tests/test_mcp_live.py (opt-in)."""

import sys

import pytest
from fastapi.testclient import TestClient

from app.mcp import client as mcp_client
from app.mcp.client import DiscoveredTool, McpConnectionError, ToolOutcome

from tests.test_tenancy import _add_member, _first_org_and_workspace, _signup

ADD = DiscoveredTool(
    "add",
    "Add two numbers.",
    {
        "type": "object",
        "properties": {
            "a": {"type": "number", "description": "first addend"},
            "b": {"type": "number", "description": "second addend"},
        },
        "required": ["a", "b"],
    },
)
PING = DiscoveredTool("ping", "Health check.", {"type": "object", "properties": {}})
NEWS = DiscoveredTool("news", "Fetch headlines.", {"type": "object", "properties": {}})


@pytest.fixture()
def fake_mcp(monkeypatch):
    """Scripted MCP client. Tests mutate the state dict."""
    state = {
        "tools": [ADD, PING],
        "outcome": ToolOutcome("sum is 5", False),
        "list_error": None,  # Exception -> discovery fails
        "call_error": None,  # Exception -> invocation fails
    }

    async def list_tools(server):
        if state["list_error"] is not None:
            raise state["list_error"]
        return list(state["tools"])

    async def call_tool(server, name, arguments):
        if state["call_error"] is not None:
            raise state["call_error"]
        return state["outcome"]

    monkeypatch.setattr(mcp_client, "list_tools", list_tools)
    monkeypatch.setattr(mcp_client, "call_tool", call_tool)
    return state


def _setup(client: TestClient, email: str):
    user = _signup(client, email, email.split("@")[0].title())
    org, ws = _first_org_and_workspace(client, user)
    return user, org, ws


def _register(client, user, ws, name="demo", transport="stdio", **cfg):
    payload = {"name": name, "transport": transport}
    if transport == "stdio":
        payload["command"] = cfg.get("command", sys.executable)
        payload["args"] = cfg.get("args", ["server.py"])
    else:
        payload["url"] = cfg.get("url", "https://example.com/mcp")
    return client.post(
        f"/workspaces/{ws}/mcp/servers", json=payload, headers=user["headers"]
    )


def _discover(client, user, ws, server_id, expect=200):
    resp = client.post(
        f"/workspaces/{ws}/mcp/servers/{server_id}/discover", headers=user["headers"]
    )
    assert resp.status_code == expect, resp.text
    return resp


def _invoke(client, user, ws, tool_id, arguments=None, expect=200):
    resp = client.post(
        f"/workspaces/{ws}/mcp/tools/{tool_id}/invoke",
        json={"arguments": arguments or {}},
        headers=user["headers"],
    )
    assert resp.status_code == expect, resp.text
    return resp


def _tools(client, user, ws) -> dict:
    """name -> tool dict."""
    resp = client.get(f"/workspaces/{ws}/mcp/tools", headers=user["headers"])
    assert resp.status_code == 200, resp.text
    return {t["name"]: t for t in resp.json()}


def _tool_call_rows():
    """tool_calls via a dedicated engine (the app engine's pool belongs to
    the TestClient loop)."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models import ToolCall
    from tests.conftest import TEST_DATABASE_URL

    async def go():
        engine = create_async_engine(TEST_DATABASE_URL)
        try:
            async with async_sessionmaker(engine)() as s:
                result = await s.execute(select(ToolCall).order_by(ToolCall.created_at))
                return result.scalars().all()
        finally:
            await engine.dispose()

    import asyncio

    return asyncio.run(go())


# ---- servers: validation, CRUD, RBAC --------------------------------------


def test_server_registration_validates_config(client: TestClient):
    user, _, ws = _setup(client, "mcp-valid@test.dev")
    h = user["headers"]

    assert (
        client.post(
            f"/workspaces/{ws}/mcp/servers",
            json={"name": "s", "transport": "stdio"},
            headers=h,
        ).status_code
        == 422
    )  # stdio without command
    assert (
        client.post(
            f"/workspaces/{ws}/mcp/servers",
            json={"name": "s", "transport": "http"},
            headers=h,
        ).status_code
        == 422
    )  # http without url
    assert (
        client.post(
            f"/workspaces/{ws}/mcp/servers",
            json={"name": "s", "transport": "http", "url": "ftp://x"},
            headers=h,
        ).status_code
        == 422
    )  # bad scheme
    assert (
        client.post(
            f"/workspaces/{ws}/mcp/servers",
            json={"name": "bad name!", "transport": "stdio", "command": "x"},
            headers=h,
        ).status_code
        == 422
    )  # name charset
    assert client.get(f"/workspaces/{ws}/mcp/servers", headers=h).json() == []


def test_server_crud_and_duplicate_name(client: TestClient):
    user, _, ws = _setup(client, "mcp-crud@test.dev")
    h = user["headers"]

    created = _register(client, user, ws, name="demo")
    assert created.status_code == 201, created.text
    server = created.json()
    assert server["status"] == "registered" and server["url_or_command"].endswith(".py")
    assert server["args"] == ["server.py"]

    dup = _register(client, user, ws, name="demo")
    assert dup.status_code == 409, dup.text

    listing = client.get(f"/workspaces/{ws}/mcp/servers", headers=h).json()
    assert [s["id"] for s in listing] == [server["id"]]

    one = client.get(f"/workspaces/{ws}/mcp/servers/{server['id']}", headers=h)
    assert one.status_code == 200 and one.json()["name"] == "demo"

    renamed = client.patch(
        f"/workspaces/{ws}/mcp/servers/{server['id']}",
        json={"name": "renamed"},
        headers=h,
    )
    assert renamed.status_code == 200 and renamed.json()["name"] == "renamed"
    # Renaming does not reset status; changing the command does.
    assert renamed.json()["status"] == "registered"

    deleted = client.delete(f"/workspaces/{ws}/mcp/servers/{server['id']}", headers=h)
    assert deleted.status_code == 204
    assert client.get(f"/workspaces/{ws}/mcp/servers", headers=h).json() == []


def test_server_rbac_and_transport_patch_rules(client: TestClient):
    user, org, ws = _setup(client, "mcp-rbac@test.dev")
    owner = user
    viewer = _add_member(client, owner, org, "viewer-mcp@test.dev", "viewer")
    member = _add_member(client, owner, org, "member-mcp@test.dev", "member")
    server_id = _register(client, owner, ws, name="demo").json()["id"]

    # viewer: reads only
    assert client.get(f"/workspaces/{ws}/mcp/servers", headers=viewer["headers"]).status_code == 200
    assert _register(client, viewer, ws, name="v").status_code == 403
    assert (
        client.patch(
            f"/workspaces/{ws}/mcp/servers/{server_id}",
            json={"name": "x"},
            headers=viewer["headers"],
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/workspaces/{ws}/mcp/servers/{server_id}/discover",
            headers=viewer["headers"],
        ).status_code
        == 403
    )
    # member: config is admin-only, usage is allowed
    assert _register(client, member, ws, name="m").status_code == 403
    assert (
        client.delete(
            f"/workspaces/{ws}/mcp/servers/{server_id}", headers=member["headers"]
        ).status_code
        == 403
    )
    # transport-specific patch fields rejected on a stdio server
    assert (
        client.patch(
            f"/workspaces/{ws}/mcp/servers/{server_id}",
            json={"url": "https://example.com/mcp"},
            headers=owner["headers"],
        ).status_code
        == 422
    )
    patched = client.patch(
        f"/workspaces/{ws}/mcp/servers/{server_id}",
        json={"args": ["other.py"]},
        headers=owner["headers"],
    )
    assert patched.status_code == 200 and patched.json()["args"] == ["other.py"]


def test_servers_and_tools_are_tenant_scoped(client: TestClient, fake_mcp):
    alice, _, alice_ws = _setup(client, "alice-mcp@test.dev")
    server_id = _register(client, alice, alice_ws, name="demo").json()["id"]
    tool_id = _discover(client, alice, alice_ws, server_id).json()["tools"][0]["id"]

    bob, _, bob_ws = _setup(client, "bob-mcp@test.dev")
    bh = bob["headers"]
    assert (
        client.get(f"/workspaces/{bob_ws}/mcp/servers/{server_id}", headers=bh).status_code
        == 404
    )
    assert (
        client.patch(
            f"/workspaces/{bob_ws}/mcp/servers/{server_id}",
            json={"name": "stolen"},
            headers=bh,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/workspaces/{bob_ws}/mcp/servers/{server_id}/discover", headers=bh
        ).status_code
        == 404
    )
    _invoke(client, bob, bob_ws, tool_id, expect=404)  # foreign id -> 404
    assert (
        client.patch(
            f"/workspaces/{bob_ws}/mcp/tools/{tool_id}",
            json={"approved": True},
            headers=bh,
        ).status_code
        == 404
    )
    # Bob sees his own empty lists.
    assert client.get(f"/workspaces/{bob_ws}/mcp/servers", headers=bh).json() == []
    assert client.get(f"/workspaces/{bob_ws}/mcp/tools", headers=bh).json() == []
    assert client.get(f"/workspaces/{bob_ws}/mcp/tool-calls", headers=bh).json() == []


# ---- discovery -------------------------------------------------------------


def test_discover_upserts_and_retires_tools(client: TestClient, fake_mcp):
    user, _, ws = _setup(client, "mcp-discover@test.dev")
    server_id = _register(client, user, ws, name="demo").json()["id"]

    found = _discover(client, user, ws, server_id).json()
    assert found["status"] == "connected"
    by_name = {t["name"]: t for t in found["tools"]}
    assert set(by_name) == {"add", "ping"}
    assert by_name["add"]["approved"] is False and by_name["add"]["active"] is True
    assert by_name["add"]["server_name"] == "demo"
    assert by_name["add"]["input_schema"]["required"] == ["a", "b"]
    # Never connected via API? status flips on the server row:
    assert client.get(f"/workspaces/{ws}/mcp/servers/{server_id}", headers=user["headers"]).json()[
        "status"
    ] == "connected"

    # Approve `add`, then change what the server exposes.
    add_id = by_name["add"]["id"]
    patched = client.patch(
        f"/workspaces/{ws}/mcp/tools/{add_id}",
        json={"approved": True},
        headers=user["headers"],
    )
    assert patched.status_code == 200 and patched.json()["approved"] is True

    fake_mcp["tools"] = [ADD, NEWS]  # ping disappears, add stays, news appears
    found = _discover(client, user, ws, server_id).json()
    by_name = {t["name"]: t for t in found["tools"]}
    assert by_name["add"]["approved"] is True  # approval survives rediscovery
    assert by_name["add"]["active"] is True
    assert by_name["news"]["approved"] is False and by_name["news"]["active"] is True
    assert by_name["ping"]["active"] is False  # retired, history kept

    # Retired tool cannot be invoked (400), but is still listed as inactive.
    ping_id = by_name["ping"]["id"]
    _invoke(client, user, ws, ping_id, expect=400)
    assert _tools(client, user, ws)["ping"]["active"] is False


def test_discover_connection_failure_marks_server_error(client: TestClient, fake_mcp):
    user, _, ws = _setup(client, "mcp-connfail@test.dev")
    server_id = _register(client, user, ws, name="demo").json()["id"]

    fake_mcp["list_error"] = McpConnectionError("spawn failed: no such command")
    _discover(client, user, ws, server_id, expect=502)
    row = client.get(f"/workspaces/{ws}/mcp/servers/{server_id}", headers=user["headers"]).json()
    assert row["status"] == "error" and "spawn failed" in row["last_error"]

    fake_mcp["list_error"] = None
    found = _discover(client, user, ws, server_id).json()
    assert found["status"] == "connected"
    assert client.get(f"/workspaces/{ws}/mcp/servers/{server_id}", headers=user["headers"]).json()[
        "last_error"
    ] is None


# ---- invocation ------------------------------------------------------------


def test_invoke_happy_path_records_tool_call(client: TestClient, fake_mcp):
    user, _, ws = _setup(client, "mcp-invoke@test.dev")
    server_id = _register(client, user, ws, name="demo").json()["id"]
    tool_id = _discover(client, user, ws, server_id).json()["tools"][0]["id"]  # add

    resp = _invoke(client, user, ws, tool_id, {"a": 2, "b": 3})
    out = resp.json()
    assert out["content"] == "sum is 5"
    assert out["is_error"] is False and out["status"] == "ok"
    assert out["latency_ms"] >= 0 and out["tool_call_id"]

    rows = _tool_call_rows()
    assert len(rows) == 1
    call = rows[0]
    assert str(call.id) == out["tool_call_id"]
    assert call.status == "ok" and call.invoked_by == "api" and call.agent_id is None
    assert call.arguments == {"a": 2, "b": 3}
    assert call.result == {"content": "sum is 5", "is_error": False}
    assert str(call.workspace_id) == ws

    history = client.get(f"/workspaces/{ws}/mcp/tool-calls", headers=user["headers"]).json()
    assert len(history) == 1
    assert history[0]["tool_name"] == "add" and history[0]["status"] == "ok"


def test_invoke_schema_mismatch_is_422_and_logged(client: TestClient, fake_mcp):
    user, _, ws = _setup(client, "mcp-badargs@test.dev")
    server_id = _register(client, user, ws, name="demo").json()["id"]
    tool_id = _discover(client, user, ws, server_id).json()["tools"][0]["id"]

    resp = client.post(
        f"/workspaces/{ws}/mcp/tools/{tool_id}/invoke",
        json={"arguments": {"a": "two"}},
        headers=user["headers"],
    )
    assert resp.status_code == 422
    assert "Invalid arguments" in resp.json()["detail"]

    rows = _tool_call_rows()
    assert len(rows) == 1 and rows[0].status == "invalid"
    assert rows[0].arguments == {"a": "two"} and rows[0].latency_ms == 0
    assert rows[0].result and rows[0].result["error"]


def test_invoke_requires_discovery_then_approval(client: TestClient, fake_mcp):
    user, _, ws = _setup(client, "mcp-gates@test.dev")
    server_id = _register(client, user, ws, name="demo").json()["id"]
    tool_id = _discover(client, user, ws, server_id).json()["tools"][0]["id"]

    # Reset status to 'registered' by changing the command -> 409 on invoke.
    client.patch(
        f"/workspaces/{ws}/mcp/servers/{server_id}",
        json={"command": "other-server.py"},
        headers=user["headers"],
    )
    _invoke(client, user, ws, tool_id, expect=409)

    _discover(client, user, ws, server_id)  # connected again
    admin = client.patch(
        f"/workspaces/{ws}/mcp/tools/{tool_id}",
        json={"requires_approval": True},
        headers=user["headers"],
    )
    assert admin.status_code == 200 and admin.json()["requires_approval"] is True
    _invoke(client, user, ws, tool_id, expect=403)

    assert _tool_call_rows() == []  # refused before any MCP call: nothing logged


def test_invoke_transport_failure_is_502_and_logged(client: TestClient, fake_mcp):
    user, _, ws = _setup(client, "mcp-transport@test.dev")
    server_id = _register(client, user, ws, name="demo").json()["id"]
    tool_id = _discover(client, user, ws, server_id).json()["tools"][0]["id"]

    fake_mcp["call_error"] = McpConnectionError("connection refused")
    _invoke(client, user, ws, tool_id, expect=502)

    rows = _tool_call_rows()
    assert len(rows) == 1 and rows[0].status == "error"
    assert "connection refused" in rows[0].result["error"]
    row = client.get(f"/workspaces/{ws}/mcp/servers/{server_id}", headers=user["headers"]).json()
    assert row["status"] == "error" and "connection refused" in row["last_error"]


def test_tool_level_failure_is_200_with_is_error(client: TestClient, fake_mcp):
    user, _, ws = _setup(client, "mcp-toolerr@test.dev")
    server_id = _register(client, user, ws, name="demo").json()["id"]
    tool_id = _discover(client, user, ws, server_id).json()["tools"][0]["id"]

    fake_mcp["outcome"] = ToolOutcome("cannot add those", True)
    out = _invoke(client, user, ws, tool_id, {"a": 1, "b": 2}).json()
    assert out["is_error"] is True and out["status"] == "error"
    rows = _tool_call_rows()
    assert rows[0].status == "error" and rows[0].result["is_error"] is True


def test_tool_calls_are_tenant_scoped_with_limit(client: TestClient, fake_mcp):
    alice, _, alice_ws = _setup(client, "alice-calls@test.dev")
    sid = _register(client, alice, alice_ws, name="demo").json()["id"]
    tid = _discover(client, alice, alice_ws, sid).json()["tools"][0]["id"]
    _invoke(client, alice, alice_ws, tid, {"a": 1, "b": 1})
    _invoke(client, alice, alice_ws, tid, {"a": 2, "b": 2})

    limited = client.get(
        f"/workspaces/{alice_ws}/mcp/tool-calls?limit=1", headers=alice["headers"]
    ).json()
    assert len(limited) == 1  # newest first

    bob, _, bob_ws = _setup(client, "bob-calls@test.dev")
    assert client.get(f"/workspaces/{bob_ws}/mcp/tool-calls", headers=bob["headers"]).json() == []
