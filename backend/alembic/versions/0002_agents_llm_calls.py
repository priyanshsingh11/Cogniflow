"""agents and llm_calls

Revision ID: 0002_agents_llm_calls
Revises: 0001_initial_auth
Create Date: 2026-10-29

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "0002_agents_llm_calls"
down_revision: str | None = "0001_initial_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("system_prompt", sa.Text, nullable=False, server_default=""),
        sa.Column("tier_pin", sa.String(20), nullable=True),
        sa.Column("model_pin", sa.String(255), nullable=True),
        sa.Column("params", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        _created_at(),
        sa.UniqueConstraint("workspace_id", "name", name="uq_agent_workspace_name"),
    )
    op.create_index("ix_agents_workspace_id", "agents", ["workspace_id"])

    op.create_table(
        "llm_calls",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("step_run_id", UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("tier", sa.String(20), nullable=False),
        sa.Column("route_reason", sa.Text, nullable=False, server_default=""),
        sa.Column("attempt_no", sa.Integer, nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("error_type", sa.String(255), nullable=True),
        sa.Column("prompt_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer, nullable=False, server_default="0"),
        _created_at(),
    )
    op.create_index(
        "ix_llm_calls_workspace_created", "llm_calls", ["workspace_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_llm_calls_workspace_created", table_name="llm_calls")
    op.drop_table("llm_calls")
    op.drop_index("ix_agents_workspace_id", table_name="agents")
    op.drop_table("agents")
