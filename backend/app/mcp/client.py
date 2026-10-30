"""Thin async wrapper over the official MCP client SDK (v2).

Connect-per-request by design: initialize -> operate -> close, no session
pool until arq owns background work (phase 5+). Tenancy never happens here —
the service layer resolves workspace-scoped rows before a server object
reaches this module.

Two operations, both bounded by `settings.mcp_timeout_seconds`:
- `list_tools`  (discovery)
- `call_tool`   (invocation, normalized to plain text)
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult

from app.config import settings
from app.models.mcp import McpServer


class McpConnectionError(Exception):
    """The server could not be reached (spawn failure, timeout, transport)."""


class DiscoveredTool:
    """What discovery cares about, decoupled from SDK types (fakes return this)."""

    __slots__ = ("name", "description", "input_schema")

    def __init__(self, name: str, description: str, input_schema: dict) -> None:
        self.name = name
        self.description = description
        self.input_schema = input_schema


class ToolOutcome:
    """Normalized tool result: plain text + error flag."""

    __slots__ = ("content", "is_error")

    def __init__(self, content: str, is_error: bool) -> None:
        self.content = content
        self.is_error = is_error


@asynccontextmanager
async def _connect(server: McpServer):
    """Initialized ClientSession, or McpConnectionError (incl. on timeout or
    any transport failure while the caller operates on the session)."""
    try:
        async with asyncio.timeout(settings.mcp_timeout_seconds):
            if server.transport == "stdio":
                params = StdioServerParameters(
                    command=server.url_or_command, args=list(server.args or [])
                )
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        yield session
            else:
                async with streamable_http_client(server.url_or_command) as (
                    read,
                    write,
                    _,
                ):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        yield session
    except McpConnectionError:
        raise
    except Exception as exc:  # spawn/timeout/transport failures, SDK internals
        raise McpConnectionError(f"MCP server '{server.name}' failed: {exc}") from exc


async def list_tools(server: McpServer) -> list[DiscoveredTool]:
    """Tools the server currently exposes. Raises McpConnectionError."""
    async with _connect(server) as session:
        result = await session.list_tools()
    tools: list[DiscoveredTool] = []
    for tool in result.tools:
        schema = tool.input_schema if isinstance(tool.input_schema, dict) else {}
        tools.append(DiscoveredTool(tool.name, tool.description or "", schema))
    return tools


async def call_tool(server: McpServer, name: str, arguments: dict[str, Any]) -> ToolOutcome:
    """Invoke one tool. Tool-level failures come back as `is_error=True`;
    transport-level failures raise McpConnectionError (caller logs them)."""
    async with _connect(server) as session:
        result = await session.call_tool(name, arguments or {})
    if not isinstance(result, CallToolResult):
        raise McpConnectionError(f"MCP server '{server.name}' returned an unexpected reply")
    return ToolOutcome(content=_normalize(result), is_error=bool(result.is_error))


def _normalize(result: CallToolResult) -> str:
    """Text blocks joined; other blocks summarised; capped at
    `mcp_max_result_bytes` (decoded leniently so the cap never breaks)."""
    parts: list[str] = []
    for block in result.content:
        kind = getattr(block, "type", "unknown")
        if kind == "text" and getattr(block, "text", None):
            parts.append(block.text)
        else:
            parts.append(f"[{kind} omitted]")
    text = "\n".join(parts)
    limit = settings.mcp_max_result_bytes
    encoded = text.encode()
    if len(encoded) > limit:
        return encoded[:limit].decode(errors="ignore") + "\n…[truncated]"
    return text
