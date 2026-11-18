"""workflow_triggers (schedule + webhook), workflow_runs.trigger_id

Revision ID: 0008_workflow_triggers
Revises: 0007_observability
Create Date: 2026-11-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "0008_workflow_triggers"
down_revision: str | None = "0007_observability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workflow_triggers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workflow_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("cron", sa.String(120), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("input", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("secret_hash", sa.String(64), nullable=True),
        sa.Column("secret_prefix", sa.String(12), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_workflow_triggers_workflow", "workflow_triggers", ["workflow_id"])
    op.create_index(
        "ix_workflow_triggers_due", "workflow_triggers", ["type", "enabled", "next_run_at"]
    )
    op.create_index(
        "uq_workflow_triggers_secret_hash", "workflow_triggers", ["secret_hash"], unique=True
    )
    op.add_column(
        "workflow_runs",
        sa.Column(
            "trigger_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workflow_triggers.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("workflow_runs", "trigger_id")
    op.drop_table("workflow_triggers")
