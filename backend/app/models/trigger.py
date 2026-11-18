import datetime
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPkMixin


class WorkflowTrigger(Base, UUIDPkMixin, TimestampMixin):
    """Starts a workflow without a person clicking Run (phase 10).

    type=schedule: `cron` (5 fields) evaluated in `timezone`; the worker fires it
    when `next_run_at` passes. type=webhook: callers POST to /hooks/<secret>;
    only the sha256 of the secret is stored.
    """

    __tablename__ = "workflow_triggers"
    __table_args__ = (
        Index("ix_workflow_triggers_workflow", "workflow_id"),
        Index("ix_workflow_triggers_due", "type", "enabled", "next_run_at"),
        Index("uq_workflow_triggers_secret_hash", "secret_hash", unique=True),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # schedule | webhook
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    cron: Mapped[str | None] = mapped_column(String(120), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    input: Mapped[dict] = mapped_column(JSONB, default=dict)  # default run input (schedules)
    secret_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    secret_prefix: Mapped[str | None] = mapped_column(String(12), nullable=True)
    next_run_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_run_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
