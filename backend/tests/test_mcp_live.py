"""Opt-in: real MCP SDK round trip against a local stdio server.
Run with: RUN_LIVE_MCP=1 uv run pytest tests/test_mcp_live.py -s"""

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.test_mcp_api import _discover, _invoke, _register, _setup

pytestmark = pytest.mark.skipif(not os.getenv("RUN_LIVE_MCP"), reason="set RUN_LIVE_MCP=1")

SERVER = str(Path(__file__).parent / "fixtures" / "echo_mcp_server.py")


def test_live_stdio_discovery_and_invoke(client: TestClient):
    user, _, ws = _setup(client, "mcp-live@test.dev")
    server_id = _register(client, user, ws, name="echo", args=[SERVER]).json()["id"]
    tools = _discover(client, user, ws, server_id).json()["tools"]
    assert [t["name"] for t in tools] == ["add"]

    tool_id = tools[0]["id"]
    out = _invoke(client, user, ws, tool_id, {"a": 2, "b": 3}).json()
    assert out["status"] == "ok" and "5" in out["content"], out
    assert sys.executable  # server was spawned with the test interpreter
