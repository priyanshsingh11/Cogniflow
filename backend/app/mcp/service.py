"""MCP registry, discovery and invocation (phase 4).

Tenancy: every query is workspace-scoped (roles enforced in `api/mcp.py`).
Every invocation attempt is recorded in `tool_calls` — `ok`, `error`
(transport or tool failure) and `invalid` (arguments that fail the stored
schema) — parity with `llm_calls` recording.

Domain errors are raised here and mapped to HTTP codes at the API edge, so
the agent tool wiring (4b) can reuse this module without FastAPI.
"""

import time
import uuid
from dataclasses import dataclass
from typing import Any

import jsonschema
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp import client
from app.models.mcp import McpServer, McpTool, ToolCall


class ToolNotFound(Exception):
    """No such tool in this workspace (foreign ids behave like missing ones)."""


class ToolRetiredError(Exception):
    """The server no longer exposes this tool (kept for call history)."""


class ServerNotConnectedError(Exception):
    """Discovery has not run (or the last attempt failed)."""


class ApprovalRequiredError(Exception):
    """Sensitive tool: refused until the phase-6 approval flow exists."""


class ArgumentsInvalidError(Exception):
    """Arguments do not satisfy the tool's stored input schema."""


class InvokeFailedError(Exception):
    """Transport-level failure while calling the server."""


@dataclass(frozen=True)
class InvokeOutcome:
    tool_call_id: uuid.UUID
    content: str
    is_error: bool
    latency_ms: int
    status: str  # ok | error


# ----------------------------------------------------------------- servers


async def get_server(
    session: AsyncSession, workspace_id: uuid.UUID, server_id: uuid.UUID
) -> McpServer | None:
    result = await session.execute(
        select(McpServer).where(
            McpServer.id == server_id, McpServer.workspace_id == workspace_id
        )
    )
    return result.scalar_one_or_none()


async def list_servers(session: AsyncSession, workspace_id: uuid.UUID) -> list[McpServer]:
    result = await session.execute(
        select(McpServer)
        .where(McpServer.workspace_id == workspace_id)
        .order_by(McpServer.created_at)
    )
    return list(result.scalars().all())


async def create_server(
    session: AsyncSession, workspace_id: uuid.UUID, payload
) -> McpServer:
    """Builds and stages the row (unique name enforced by the DB -> 409 at
    the API edge via IntegrityError)."""
    server = McpServer(
        workspace_id=workspace_id,
        name=payload.name,
        transport=payload.transport,
        url_or_command=(payload.command or "").strip()
        if payload.transport == "stdio"
        else payload.url,
        args=list(payload.args or []) if payload.transport == "stdio" else None,
        status="registered",
    )
    session.add(server)
    return server


async def update_server(session: AsyncSession, server: McpServer, payload) -> McpServer:
    """Applies the patch; any connection-relevant change resets status to
    `registered` so the next call must re-discover."""
    if payload.name is not None:
        server.name = payload.name
    config_changed = False
    if payload.command is not None:
        server.url_or_command = payload.command.strip()
        config_changed = True
    if payload.args is not None:
        server.args = list(payload.args)
        config_changed = True
    if payload.url is not None:
        server.url_or_command = payload.url
        config_changed = True
    if config_changed:
        server.status = "registered"
        server.last_error = None
    await session.commit()
    return server


async def delete_server(session: AsyncSession, server: McpServer) -> None:
    # Cascades to mcp_tools and (via mcp_tools) to this server's tool_calls.
    await session.delete(server)
    await session.commit()


# ------------------------------------------------------------------- tools


async def get_tool(
    session: AsyncSession, workspace_id: uuid.UUID, tool_id: uuid.UUID
) -> tuple[McpTool, McpServer] | None:
    result = await session.execute(
        select(McpTool, McpServer)
        .join(McpServer, McpTool.mcp_server_id == McpServer.id)
        .where(McpTool.id == tool_id, McpServer.workspace_id == workspace_id)
    )
    return result.first()


async def list_tools_rows(
    session: AsyncSession, workspace_id: uuid.UUID, server_id: uuid.UUID | None = None
) -> list[tuple[McpTool, str]]:
    """(tool, server_name) pairs, newest servers' tools last."""
    stmt = (
        select(McpTool, McpServer.name)
        .join(McpServer, McpTool.mcp_server_id == McpServer.id)
        .where(McpServer.workspace_id == workspace_id)
    )
    if server_id is not None:
        stmt = stmt.where(McpTool.mcp_server_id == server_id)
    stmt = stmt.order_by(McpServer.name, McpTool.name)
    result = await session.execute(stmt)
    return [(tool, server_name) for tool, server_name in result.all()]


async def update_tool(session: AsyncSession, tool: McpTool, payload) -> McpTool:
    if payload.approved is not None:
        tool.approved = payload.approved
    if payload.requires_approval is not None:
        tool.requires_approval = payload.requires_approval
    await session.commit()
    return tool


# --------------------------------------------------------------- discovery


async def discover(session: AsyncSession, server: McpServer) -> list[McpTool]:
    """Connect, list tools, upsert. New tools start `approved=false`;
    tools the server no longer exposes become `active=false` (history kept).
    Raises client.McpConnectionError after marking the server `error`."""
    try:
        found = await client.list_tools(server)
    except client.McpConnectionError as exc:
        server.status = "error"
        server.last_error = str(exc)[:4_000]
        await session.commit()
        raise

    existing_result = await session.execute(
        select(McpTool).where(McpTool.mcp_server_id == server.id)
    )
    existing = {tool.name: tool for tool in existing_result.scalars()}
    seen: set[str] = set()

    for discovery in found:
        schema = _safe_schema(discovery.input_schema)
        seen.add(discovery.name)
        row = existing.get(discovery.name)
        if row is not None:
            row.description = discovery.description or None
            row.input_schema = schema
            row.active = True
        else:
            session.add(
                McpTool(
                    mcp_server_id=server.id,
                    name=discovery.name,
                    description=discovery.description or None,
                    input_schema=schema,
                    approved=False,
                    requires_approval=False,
                    active=True,
                )
            )
    for name, row in existing.items():
        if name not in seen:
            row.active = False

    server.status = "connected"
    server.last_error = None
    await session.commit()

    rows = await session.execute(
        select(McpTool).where(McpTool.mcp_server_id == server.id).order_by(McpTool.name)
    )
    return list(rows.scalars().all())


def _safe_schema(schema: Any) -> dict:
    """Store the schema only if it is a valid JSON Schema; otherwise fall back
    to `{}` (permissive) rather than blocking a usable tool."""
    if not isinstance(schema, dict) or not schema:
        return {}
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
    except jsonschema.exceptions.SchemaError:
        return {}
    return schema


# ------------------------------------------------------------------ invoke


async def invoke_tool(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    tool_id: uuid.UUID,
    arguments: dict[str, Any],
    invoked_by: str = "api",
    agent_id: uuid.UUID | None = None,
) -> InvokeOutcome:
    """validate -> MCP call -> record. Domain errors (see above) instead of
    HTTPException so agents can reuse this directly."""
    pair = await get_tool(session, workspace_id, tool_id)
    if pair is None:
        raise ToolNotFound(f"Tool {tool_id} not found")
    tool, server = pair
    if not tool.active:
        raise ToolRetiredError(f"Tool '{tool.name}' is no longer exposed by its server")
    if tool.requires_approval:
        raise ApprovalRequiredError(
            f"Tool '{tool.name}' requires human approval (not yet available; phase 6)"
        )
    if server.status != "connected":
        raise ServerNotConnectedError(
            f"Server '{server.name}' is not connected (status: {server.status}); "
            "run discovery first"
        )

    try:
        jsonschema.validate(instance=arguments, schema=tool.input_schema or {})
    except jsonschema.exceptions.ValidationError as exc:
        record_tool_call(
            session,
            workspace_id=workspace_id,
            mcp_tool_id=tool.id,
            arguments=arguments,
            result={"error": exc.message},
            status="invalid",
            latency_ms=0,
            invoked_by=invoked_by,
            agent_id=agent_id,
        )
        await session.commit()
        raise ArgumentsInvalidError(exc.message) from exc
    except jsonschema.exceptions.SchemaError:
        pass  # unschematized stored schema: discovery sanitized it; call anyway

    started = time.monotonic()
    try:
        outcome = await client.call_tool(server, tool.name, arguments)
    except client.McpConnectionError as exc:
        latency_ms = int((time.monotonic() - started) * 1_000)
        server.status = "error"
        server.last_error = str(exc)[:4_000]
        record_tool_call(
            session,
            workspace_id=workspace_id,
            mcp_tool_id=tool.id,
            arguments=arguments,
            result={"error": str(exc)},
            status="error",
            latency_ms=latency_ms,
            invoked_by=invoked_by,
            agent_id=agent_id,
        )
        await session.commit()
        raise InvokeFailedError(str(exc)) from exc

    latency_ms = int((time.monotonic() - started) * 1_000)
    status = "error" if outcome.is_error else "ok"
    call_id = record_tool_call(
        session,
        workspace_id=workspace_id,
        mcp_tool_id=tool.id,
        arguments=arguments,
        result={"content": outcome.content, "is_error": outcome.is_error},
        status=status,
        latency_ms=latency_ms,
        invoked_by=invoked_by,
        agent_id=agent_id,
    )
    await session.commit()
    return InvokeOutcome(
        tool_call_id=call_id,
        content=outcome.content,
        is_error=outcome.is_error,
        latency_ms=latency_ms,
        status=status,
    )


def record_tool_call(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    mcp_tool_id: uuid.UUID,
    arguments: dict[str, Any] | None,
    result: dict[str, Any] | None,
    status: str,
    latency_ms: int,
    invoked_by: str,
    agent_id: uuid.UUID | None = None,
    step_run_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Stage one tool_calls row. Caller commits."""
    row = ToolCall(
        workspace_id=workspace_id,
        mcp_tool_id=mcp_tool_id,
        agent_id=agent_id,
        step_run_id=step_run_id,
        invoked_by=invoked_by,
        arguments=arguments,
        result=result,
        status=status,
        latency_ms=latency_ms,
    )
    session.add(row)
    return row.id


async def list_tool_calls(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    limit: int = 50,
    tool_id: uuid.UUID | None = None,
) -> list[tuple[ToolCall, str]]:
    """Newest first: (call, tool_name)."""
    stmt = (
        select(ToolCall, McpTool.name)
        .join(McpTool, ToolCall.mcp_tool_id == McpTool.id)
        .where(ToolCall.workspace_id == workspace_id)
    )
    if tool_id is not None:
        stmt = stmt.where(ToolCall.mcp_tool_id == tool_id)
    stmt = stmt.order_by(ToolCall.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return [(call, tool_name) for call, tool_name in result.all()]
