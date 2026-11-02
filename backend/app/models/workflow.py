import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPkMixin


class Workflow(Base, UUIDPkMixin, TimestampMixin):
    """A workflow definition in a workspace (phases 5 & 6)."""

    __tablename__ = "workflows"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_workflows_workspace_name"),
        Index("ix_workflows_workspace_created", "workspace_id", "created_at"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_versions.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )


class WorkflowVersion(Base, UUIDPkMixin, TimestampMixin):
    """An immutable version of a workflow's graph and steps."""

    __tablename__ = "workflow_versions"
    __table_args__ = (
        UniqueConstraint("workflow_id", "version", name="uq_workflow_versions_wf_version"),
        Index("ix_workflow_versions_wf_version", "workflow_id", "version"),
    )

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    graph: Mapped[dict] = mapped_column(JSONB, default=dict)


class WorkflowStep(Base, UUIDPkMixin, TimestampMixin):
    """One step in a workflow version."""

    __tablename__ = "workflow_steps"
    __table_args__ = (
        UniqueConstraint("workflow_version_id", "name", name="uq_workflow_steps_version_name"),
        Index("ix_workflow_steps_version_position", "workflow_version_id", "position"),
    )

    workflow_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_versions.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # llm | knowledge_search | mcp_tool | condition | agent | coordinator | approval
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    config: Mapped[dict] = mapped_column(JSONB, default=dict)


class WorkflowRun(Base, UUIDPkMixin, TimestampMixin):
    """Durable record of a workflow execution in Postgres."""

    __tablename__ = "workflow_runs"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "idempotency_key", name="uq_workflow_runs_workspace_idempotency"
        ),
        Index("ix_workflow_runs_workspace_created", "workspace_id", "created_at"),
        Index("ix_workflow_runs_workflow_created", "workflow_id", "created_at"),
        Index("ix_workflow_runs_status", "status"),
    )

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    workflow_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_versions.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(30), default="queued"
    )  # queued | running | waiting_approval | succeeded | failed | cancelled
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    queue_job_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    input: Mapped[dict] = mapped_column(JSONB, default=dict)
    output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class StepRun(Base, UUIDPkMixin, TimestampMixin):
    """Execution of one step within a workflow run, with leases and retries."""

    __tablename__ = "step_runs"
    __table_args__ = (
        UniqueConstraint(
            "workflow_run_id", "step_name", "attempt", name="uq_step_runs_run_step_attempt"
        ),
        Index("ix_step_runs_run_created", "workflow_run_id", "created_at"),
        Index("ix_step_runs_status_lease", "status", "lease_expires_at"),
    )

    workflow_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False
    )
    workflow_step_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_steps.id", ondelete="SET NULL"), nullable=True
    )
    step_name: Mapped[str] = mapped_column(String(100), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(
        String(30), default="pending"
    )  # pending | running | waiting_approval | succeeded | failed | skipped
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    trace_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    input: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    lease_worker_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lease_expires_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Approval(Base, UUIDPkMixin, TimestampMixin):
    """Human approval sign-off record (Phase 6)."""

    __tablename__ = "approvals"
    __table_args__ = (
        Index("ix_approvals_workspace_status", "workspace_id", "status"),
        Index("ix_approvals_run_created", "workflow_run_id", "created_at"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    workflow_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=True
    )
    step_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("step_runs.id", ondelete="CASCADE"), nullable=True
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending | approved | rejected | expired
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    requested_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.UTC)
    )
    decided_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
