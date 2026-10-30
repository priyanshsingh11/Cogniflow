import uuid

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPkMixin


class McpServer(Base, UUIDPkMixin, TimestampMixin):
    """An MCP server registered in one workspace (phase 4).

    `url_or_command` holds the stdio command or the HTTP endpoint URL; `args`
    is the stdio argv. `status` reflects the last discovery attempt.
    """

    __tablename__ = "mcp_servers"
    __table_args__ = (Index("ix_mcp_servers_workspace_created", "workspace_id", "created_at"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(120))
    transport: Mapped[str] = mapped_column(String(20))  # stdio | http
    url_or_command: Mapped[str] = mapped_column(Text)
    args: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    secret_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)  # phase 11
    status: Mapped[str] = mapped_column(String(20), default="registered")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class McpTool(Base, UUIDPkMixin, TimestampMixin):
    """A tool discovered on a server. `approved` gates agent/workflow use;
    `requires_approval` (phase 6) is refused today; `active` marks tools the
    server no longer exposes — retired without losing `tool_calls` history."""

    __tablename__ = "mcp_tools"
    __table_args__ = (UniqueConstraint("mcp_server_id", "name", name="uq_mcp_tools_server_name"),)

    mcp_server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mcp_servers.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_schema: Mapped[dict] = mapped_column(JSONB, default=dict)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ToolCall(Base, UUIDPkMixin, TimestampMixin):
    """One invocation attempt of an MCP tool (parity with `llm_calls`):
    ok, error (transport or tool failure) or invalid (schema mismatch)."""

    __tablename__ = "tool_calls"
    __table_args__ = (
        Index("ix_tool_calls_workspace_created", "workspace_id", "created_at"),
        Index("ix_tool_calls_tool_created", "mcp_tool_id", "created_at"),
    )

    # No FK yet: step_runs arrives with the workflow engine (phase 5),
    # same deferral as llm_calls.step_run_id.
    step_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    mcp_tool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mcp_tools.id", ondelete="CASCADE")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))  # denormalized
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    invoked_by: Mapped[str] = mapped_column(String(20), default="api")  # api|agent|workflow
    arguments: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20))  # ok | error | invalid
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
