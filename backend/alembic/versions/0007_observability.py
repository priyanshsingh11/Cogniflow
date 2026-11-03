"""audit_logs, llm_calls call_id/request_id, mcp_servers credentials_enc

Revision ID: 0007_observability
Revises: 0006_workflows_runs_approvals
Create Date: 2026-11-02

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "0007_observability"
down_revision: str | None = "0006_workflows_runs_approvals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    # 1. audit_logs — append-only. workspace/org/actor use SET NULL so the
    #    trail survives tenant teardown (ids are also kept in `metadata`).
    op.create_table(
        "audit_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "actor_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("entity_type", sa.String(60), nullable=True),
        sa.Column("entity_id", sa.String(64), nullable=True),
        sa.Column("metadata", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        _created_at(),
    )
    op.create_index(
        "ix_audit_logs_workspace_created", "audit_logs", ["workspace_id", "created_at"]
    )
    op.create_index("ix_audit_logs_org_created", "audit_logs", ["org_id", "created_at"])
    op.create_index("ix_audit_logs_actor_created", "audit_logs", ["actor_id", "created_at"])
    op.create_index("ix_audit_logs_action_created", "audit_logs", ["action", "created_at"])

    # 2. llm_calls — call_id groups the attempts of one gateway invocation
    #    (fallback rate), request_id joins rows to structured log lines.
    op.add_column("llm_calls", sa.Column("call_id", UUID(as_uuid=True), nullable=True))
    op.add_column("llm_calls", sa.Column("request_id", sa.String(64), nullable=True))
    op.create_index("ix_llm_calls_call_id", "llm_calls", ["call_id"])

    # 3. mcp_servers — per-server credentials (headers/env) encrypted at rest.
    op.add_column(
        "mcp_servers",
        sa.Column("credentials_enc", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("mcp_servers", "credentials_enc")
    op.drop_index("ix_llm_calls_call_id", table_name="llm_calls")
    op.drop_column("llm_calls", "request_id")
    op.drop_column("llm_calls", "call_id")
    op.drop_index("ix_audit_logs_action_created", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_created", table_name="audit_logs")
    op.drop_index("ix_audit_logs_org_created", table_name="audit_logs")
    op.drop_index("ix_audit_logs_workspace_created", table_name="audit_logs")
    op.drop_table("audit_logs")
