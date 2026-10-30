"""mcp servers, mcp tools, tool calls

Revision ID: 0005_mcp_tables
Revises: 0004_conversations_messages
Create Date: 2026-10-30

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "0005_mcp_tables"
down_revision: str | None = "0004_conversations_messages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "mcp_servers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("transport", sa.String(20), nullable=False),  # stdio | http
        sa.Column("url_or_command", sa.Text(), nullable=False),  # command or endpoint URL
        sa.Column("args", JSONB(), nullable=True),  # stdio argv, [] means none
        sa.Column("secret_ref", sa.String(255), nullable=True),  # phase 11: credentials
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="registered"
        ),  # registered|connected|error
        sa.Column("last_error", sa.Text(), nullable=True),
        _created_at(),
        sa.UniqueConstraint("workspace_id", "name", name="uq_mcp_servers_workspace_name"),
    )
    op.create_index(
        "ix_mcp_servers_workspace_created", "mcp_servers", ["workspace_id", "created_at"]
    )

    op.create_table(
        "mcp_tools",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "mcp_server_id",
            UUID(as_uuid=True),
            sa.ForeignKey("mcp_servers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),  # shown to the model
        sa.Column("input_schema", JSONB(), nullable=False, server_default="{}"),
        sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        _created_at(),
        sa.UniqueConstraint("mcp_server_id", "name", name="uq_mcp_tools_server_name"),
    )

    op.create_table(
        "tool_calls",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        # No FK yet: step_runs arrives with the workflow engine (phase 5),
        # same deferral as llm_calls.step_run_id.
        sa.Column("step_run_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "mcp_tool_id",
            UUID(as_uuid=True),
            sa.ForeignKey("mcp_tools.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),  # denormalized
        sa.Column(
            "agent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("invoked_by", sa.String(20), nullable=False, server_default="api"),
        sa.Column("arguments", JSONB(), nullable=True),
        sa.Column("result", JSONB(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),  # ok | error | invalid
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        _created_at(),
    )
    op.create_index("ix_tool_calls_workspace_created", "tool_calls", ["workspace_id", "created_at"])
    op.create_index("ix_tool_calls_tool_created", "tool_calls", ["mcp_tool_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_tool_calls_tool_created", table_name="tool_calls")
    op.drop_index("ix_tool_calls_workspace_created", table_name="tool_calls")
    op.drop_table("tool_calls")
    op.drop_table("mcp_tools")
    op.drop_index("ix_mcp_servers_workspace_created", table_name="mcp_servers")
    op.drop_table("mcp_servers")
