"""MCP layer: register servers, discover their tools, validate + invoke them,
and expose every attempt through `tool_calls`.

Server config is admin+; discovery/invocation member+; reads viewer+.
Foreign ids are 404 on every path (existence never leaks).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, require_role
from app.db.postgres import get_pg
from app.mcp import client, service
from app.models import Role
from app.schemas.mcp import (
    DiscoverOut,
    InvokeIn,
    InvokeOut,
    ServerCreate,
    ServerOut,
    ServerPatch,
    ToolCallOut,
    ToolOut,
    ToolPatch,
)

router = APIRouter(prefix="/workspaces/{workspace_id}/mcp", tags=["mcp"])
require_viewer = require_role(Role.VIEWER)
require_member = require_role(Role.MEMBER)
require_admin = require_role(Role.ADMIN)


async def _load_server(
    session: AsyncSession, ctx: TenantContext, server_id: uuid.UUID
):
    server = await service.get_server(session, ctx.workspace.id, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="MCP server not found")
    return server


def _server_out(server) -> ServerOut:
    return ServerOut(
        id=server.id,
        name=server.name,
        transport=server.transport,
        url_or_command=server.url_or_command,
        args=server.args,
        status=server.status,
        last_error=server.last_error,
        created_at=server.created_at,
    )


# ----------------------------------------------------------------- servers


@router.post("/servers", response_model=ServerOut, status_code=201)
async def create_server(
    payload: ServerCreate,
    ctx: TenantContext = Depends(require_admin),
    session: AsyncSession = Depends(get_pg),
) -> ServerOut:
    server = await service.create_server(session, ctx.workspace.id, payload)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="An MCP server with this name already exists"
        ) from exc
    return _server_out(server)


@router.get("/servers", response_model=list[ServerOut])
async def list_servers(
    ctx: TenantContext = Depends(require_viewer),
    session: AsyncSession = Depends(get_pg),
) -> list[ServerOut]:
    return [_server_out(s) for s in await service.list_servers(session, ctx.workspace.id)]


@router.get("/servers/{server_id}", response_model=ServerOut)
async def get_server(
    server_id: uuid.UUID,
    ctx: TenantContext = Depends(require_viewer),
    session: AsyncSession = Depends(get_pg),
) -> ServerOut:
    return _server_out(await _load_server(session, ctx, server_id))


@router.patch("/servers/{server_id}", response_model=ServerOut)
async def patch_server(
    server_id: uuid.UUID,
    payload: ServerPatch,
    ctx: TenantContext = Depends(require_admin),
    session: AsyncSession = Depends(get_pg),
) -> ServerOut:
    server = await _load_server(session, ctx, server_id)
    if payload.command is not None or payload.args is not None:
        if server.transport != "stdio":
            raise HTTPException(
                status_code=422, detail="command/args only apply to stdio servers"
            )
    if payload.url is not None:
        if server.transport != "http" or not payload.url.startswith(("http://", "https://")):
            raise HTTPException(
                status_code=422,
                detail="'url' only applies to http servers and must start with http(s)://",
            )
    return _server_out(await service.update_server(session, server, payload))


@router.delete("/servers/{server_id}", status_code=204)
async def delete_server(
    server_id: uuid.UUID,
    ctx: TenantContext = Depends(require_admin),
    session: AsyncSession = Depends(get_pg),
) -> None:
    server = await _load_server(session, ctx, server_id)
    await service.delete_server(session, server)


@router.post("/servers/{server_id}/discover", response_model=DiscoverOut)
async def discover(
    server_id: uuid.UUID,
    ctx: TenantContext = Depends(require_member),
    session: AsyncSession = Depends(get_pg),
) -> DiscoverOut:
    server = await _load_server(session, ctx, server_id)
    try:
        tools = await service.discover(session, server)
    except client.McpConnectionError as exc:
        raise HTTPException(
            status_code=502, detail=f"Could not reach MCP server: {exc}"
        ) from exc
    return DiscoverOut(
        server_id=server.id,
        status=server.status,
        tools=[ToolOut.from_row(t, server.name) for t in tools],
    )


# ------------------------------------------------------------------- tools


@router.get("/tools", response_model=list[ToolOut])
async def list_tools(
    server_id: uuid.UUID | None = Query(default=None),
    ctx: TenantContext = Depends(require_viewer),
    session: AsyncSession = Depends(get_pg),
) -> list[ToolOut]:
    rows = await service.list_tools_rows(session, ctx.workspace.id, server_id)
    return [ToolOut.from_row(tool, name) for tool, name in rows]


@router.patch("/tools/{tool_id}", response_model=ToolOut)
async def patch_tool(
    tool_id: uuid.UUID,
    payload: ToolPatch,
    ctx: TenantContext = Depends(require_admin),
    session: AsyncSession = Depends(get_pg),
) -> ToolOut:
    pair = await service.get_tool(session, ctx.workspace.id, tool_id)
    if pair is None:
        raise HTTPException(status_code=404, detail="MCP tool not found")
    tool, server = pair
    tool = await service.update_tool(session, tool, payload)
    return ToolOut.from_row(tool, server.name)


@router.post("/tools/{tool_id}/invoke", response_model=InvokeOut)
async def invoke_tool(
    tool_id: uuid.UUID,
    payload: InvokeIn,
    ctx: TenantContext = Depends(require_member),
    session: AsyncSession = Depends(get_pg),
) -> InvokeOut:
    try:
        outcome = await service.invoke_tool(
            session,
            workspace_id=ctx.workspace.id,
            tool_id=tool_id,
            arguments=payload.arguments,
            invoked_by="api",
        )
    except service.ToolNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except service.ToolRetiredError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except service.ServerNotConnectedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except service.ApprovalRequiredError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except service.ArgumentsInvalidError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid arguments: {exc}") from exc
    except service.InvokeFailedError as exc:
        raise HTTPException(status_code=502, detail=f"MCP server call failed: {exc}") from exc
    return InvokeOut(
        tool_call_id=outcome.tool_call_id,
        content=outcome.content,
        is_error=outcome.is_error,
        latency_ms=outcome.latency_ms,
        status=outcome.status,
    )


@router.get("/tool-calls", response_model=list[ToolCallOut])
async def list_tool_calls(
    limit: int = Query(default=50, ge=1, le=200),
    tool_id: uuid.UUID | None = Query(default=None),
    ctx: TenantContext = Depends(require_viewer),
    session: AsyncSession = Depends(get_pg),
) -> list[ToolCallOut]:
    rows = await service.list_tool_calls(
        session, ctx.workspace.id, limit=limit, tool_id=tool_id
    )
    return [ToolCallOut.from_row(call, name) for call, name in rows]
