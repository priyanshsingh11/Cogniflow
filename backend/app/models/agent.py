import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPkMixin


class Agent(Base, UUIDPkMixin, TimestampMixin):
    """A saved agent configuration. tier_pin/model_pin are optional overrides of
    the automatic router; leave both null to let the router decide."""

    __tablename__ = "agents"
    __table_args__ = (UniqueConstraint("workspace_id", "name", name="uq_agent_workspace_name"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50))  # research|analysis|writing|review|custom
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    tier_pin: Mapped[str | None] = mapped_column(String(20), nullable=True)
    model_pin: Mapped[str | None] = mapped_column(String(255), nullable=True)  # "provider:model"
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
