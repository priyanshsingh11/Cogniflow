"""workflows, workflow_versions, workflow_steps, workflow_runs, step_runs, approvals

Revision ID: 0006_workflows_runs_approvals
Revises: 0005_mcp_tables
Create Date: 2026-11-02

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "0006_workflows_runs_approvals"
down_revision: str | None = "0005_mcp_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    # 1. workflows
    op.create_table(
        "workflows",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("current_version_id", UUID(as_uuid=True), nullable=True),
        _created_at(),
        sa.UniqueConstraint("workspace_id", "name", name="uq_workflows_workspace_name"),
    )
    op.create_index(
        "ix_workflows_workspace_created", "workflows", ["workspace_id", "created_at"]
    )

    # 2. workflow_versions
    op.create_table(
        "workflow_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workflow_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("graph", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        _created_at(),
        sa.UniqueConstraint("workflow_id", "version", name="uq_workflow_versions_wf_version"),
    )
    op.create_index(
        "ix_workflow_versions_wf_version", "workflow_versions", ["workflow_id", "version"]
    )

    # Add FK from workflows.current_version_id -> workflow_versions.id
    op.create_foreign_key(
        "fk_workflows_current_version_id",
        "workflows",
        "workflow_versions",
        ["current_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 3. workflow_steps
    op.create_table(
        "workflow_steps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workflow_version_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workflow_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        # types: llm, knowledge_search, mcp_tool, condition, agent, coordinator, approval
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column(
            "agent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("config", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        _created_at(),
        sa.UniqueConstraint("workflow_version_id", "name", name="uq_workflow_steps_version_name"),
    )
    op.create_index(
        "ix_workflow_steps_version_position",
        "workflow_steps",
        ["workflow_version_id", "position"],
    )

    # 4. workflow_runs
    op.create_table(
        "workflow_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workflow_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workflow_version_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workflow_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "triggered_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(30), nullable=False, server_default="queued"),
        sa.Column("idempotency_key", sa.String(255), nullable=True),
        sa.Column("queue_job_id", sa.String(255), nullable=True),
        sa.Column("input", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("output", JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        sa.UniqueConstraint(
            "workspace_id", "idempotency_key", name="uq_workflow_runs_workspace_idempotency"
        ),
    )
    op.create_index(
        "ix_workflow_runs_workspace_created", "workflow_runs", ["workspace_id", "created_at"]
    )
    op.create_index(
        "ix_workflow_runs_workflow_created", "workflow_runs", ["workflow_id", "created_at"]
    )
    op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"])

    # 5. step_runs
    op.create_table(
        "step_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workflow_run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workflow_step_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workflow_steps.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("step_name", sa.String(100), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("idempotency_key", sa.String(255), nullable=True),
        sa.Column("trace_ref", sa.String(255), nullable=True),
        sa.Column("input", JSONB(), nullable=True),
        sa.Column("output", JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("lease_worker_id", sa.String(100), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        sa.UniqueConstraint(
            "workflow_run_id", "step_name", "attempt", name="uq_step_runs_run_step_attempt"
        ),
    )
    op.create_index(
        "ix_step_runs_run_created", "step_runs", ["workflow_run_id", "created_at"]
    )
    op.create_index(
        "ix_step_runs_status_lease", "step_runs", ["status", "lease_expires_at"]
    )

    # 6. approvals (Phase 6)
    op.create_table(
        "approvals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workflow_run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "step_run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("step_runs.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "decided_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("details", JSONB(), nullable=True),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
    )
    op.create_index(
        "ix_approvals_workspace_status", "approvals", ["workspace_id", "status"]
    )
    op.create_index(
        "ix_approvals_run_created", "approvals", ["workflow_run_id", "created_at"]
    )

    # 7. Wire foreign keys deferred in migrations 0002 and 0005
    op.create_foreign_key(
        "fk_llm_calls_step_run_id",
        "llm_calls",
        "step_runs",
        ["step_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_tool_calls_step_run_id",
        "tool_calls",
        "step_runs",
        ["step_run_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_tool_calls_step_run_id", "tool_calls", type_="foreignkey")
    op.drop_constraint("fk_llm_calls_step_run_id", "llm_calls", type_="foreignkey")

    op.drop_index("ix_approvals_run_created", table_name="approvals")
    op.drop_index("ix_approvals_workspace_status", table_name="approvals")
    op.drop_table("approvals")

    op.drop_index("ix_step_runs_status_lease", table_name="step_runs")
    op.drop_index("ix_step_runs_run_created", table_name="step_runs")
    op.drop_table("step_runs")

    op.drop_index("ix_workflow_runs_status", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_workflow_created", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_workspace_created", table_name="workflow_runs")
    op.drop_table("workflow_runs")

    op.drop_index("ix_workflow_steps_version_position", table_name="workflow_steps")
    op.drop_table("workflow_steps")

    op.drop_constraint("fk_workflows_current_version_id", "workflows", type_="foreignkey")
    op.drop_index("ix_workflow_versions_wf_version", table_name="workflow_versions")
    op.drop_table("workflow_versions")

    op.drop_index("ix_workflows_workspace_created", table_name="workflows")
    op.drop_table("workflows")
