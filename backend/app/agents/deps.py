"""Tool registry per request.

Tools are built from the caller's workspace (tenancy is baked into the tool
closure), so the runtime never sees a workspace id and cannot be pointed at
another tenant's knowledge. RAG registers `knowledge_search` here; MCP (phase 4)
adds its tools the same way.
"""

import uuid
from typing import Any

from fastapi import Depends

from app.agents.tools import Tool, ToolRegistry
from app.api.deps import TenantContext, require_workspace
from app.db.postgres import SessionLocal
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


def get_tools(ctx: TenantContext = Depends(require_workspace)) -> ToolRegistry:
    """Workspace-scoped registry. Overridable in tests via
    app.dependency_overrides[get_tools]."""
    return ToolRegistry(
        [
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
    )
