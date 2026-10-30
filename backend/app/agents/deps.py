"""Tool registry per request.

Tools are built from the caller's workspace (tenancy is baked into the tool
closure), so the runtime never sees a workspace id and cannot be pointed at
another tenant's knowledge or tools. RAG registers `knowledge_search`;
phase 4b adds every approved, active MCP tool as `mcp__<server>__<tool>` —
only `approved AND NOT requires_approval AND active` tools qualify, and each
call goes through `app.mcp.service.invoke_tool` (so it is logged in
`tool_calls` with `invoked_by="agent"` exactly like an API call).
"""

import uuid
from typing import Any

from fastapi import Depends
from sqlalchemy import select

from app.agents.tools import Tool, ToolRegistry
from app.api.deps import TenantContext, require_workspace
from app.db.postgres import SessionLocal
from app.mcp import service
from app.models.mcp import McpServer, McpTool
from app.rag.retrieval import search as vector_search


def _knowledge_search(workspace_id: uuid.UUID):
    async def run(arguments: dict[str, Any]) -> str:
        query = arguments["query"]
        async with SessionLocal() as session:
            passages = await vector_search(session, workspace_id, str(query), top_k=6)
        if not passages:
            return "No relevant passages found in the workspace documents."
        return "\n\n".join(
            f"[{i}] ({p.filename} #{p.chunk_index})\n{p.content}"
            for i, p in enumerate(passages, start=1)
        )

    return run


def _mcp_invoke(workspace_id: uuid.UUID, tool_id: uuid.UUID):
    async def run(arguments: dict[str, Any]) -> str:
        async with SessionLocal() as session:
            outcome = await service.invoke_tool(
                session,
                workspace_id=workspace_id,
                tool_id=tool_id,
                arguments=dict(arguments),
                invoked_by="agent",
            )
        if outcome.is_error:
            return f"Tool failed: {outcome.content}"
        return outcome.content

    return run


def _agent_arguments(tool: McpTool) -> dict[str, str]:
    """Only `required` properties (the runtime treats every listed argument
    as mandatory); optional ones are described in the tool description."""
    schema = tool.input_schema or {}
    required = set(schema.get("required") or [])
    props = schema.get("properties") or {}
    arguments: dict[str, str] = {}
    for name in sorted(required):
        spec = props.get(name) or {}
        arguments[name] = str(spec.get("description") or spec.get("type") or "value")
    return arguments


def _agent_description(tool: McpTool, server_name: str) -> str:
    base = tool.description or f"MCP tool '{tool.name}' from server '{server_name}'."
    schema = tool.input_schema or {}
    required = set(schema.get("required") or [])
    optional = [
        name
        for name in (schema.get("properties") or {})
        if name not in required
    ]
    if optional:
        base += f" Optional arguments: {', '.join(sorted(optional))}."
    return base


async def get_tools(ctx: TenantContext = Depends(require_workspace)) -> ToolRegistry:
    """Workspace-scoped registry (async: MCP tools are loaded from the DB).
    Overridable in tests via app.dependency_overrides[get_tools]."""
    tools = [
        Tool(
            name="knowledge_search",
            description=(
                "Search the workspace's uploaded documents for passages relevant "
                "to a query. Returns numbered passages with their source filename; "
                "use them as evidence."
            ),
            fn=_knowledge_search(ctx.workspace.id),
            arguments={"query": "what to look for in the knowledge base"},
        )
    ]

    async with SessionLocal() as session:
        result = await session.execute(
            select(McpTool, McpServer.name)
            .join(McpServer, McpTool.mcp_server_id == McpServer.id)
            .where(
                McpServer.workspace_id == ctx.workspace.id,
                McpTool.approved.is_(True),
                McpTool.requires_approval.is_(False),
                McpTool.active.is_(True),
            )
            .order_by(McpServer.name, McpTool.name)
        )
        for tool, server_name in result.all():
            tools.append(
                Tool(
                    name=f"mcp__{server_name}__{tool.name}",
                    description=_agent_description(tool, server_name),
                    fn=_mcp_invoke(ctx.workspace.id, tool.id),
                    arguments=_agent_arguments(tool),
                )
            )
    return ToolRegistry(tools)
