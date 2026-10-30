import uuid

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPkMixin


class Conversation(Base, UUIDPkMixin, TimestampMixin):
    """A chat thread in a workspace. Postgres is the anchor; the messages
    themselves live in Mongo (referencing this UUID, never the reverse)."""

    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_workspace_created", "workspace_id", "created_at"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(String(255), default="")


class Message(Base, UUIDPkMixin, TimestampMixin):
    """Cross-DB staging row for one chat message (pending -> Mongo -> synced).

    The payload (content/citations/meta) is staged here only while the row is
    `pending`; once Mongo acknowledges, the row flips to `synced` and the
    payload is nulled — Mongo is the long-term owner of the message. A reaper
    retries stale `pending` rows from the staged payload (idempotent: Mongo
    `_id` = this row's id) and marks rows `failed` after max attempts, keeping
    their payload for inspection."""

    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
        Index("ix_messages_status_created", "status", "created_at"),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))  # denormalized
    role: Mapped[str] = mapped_column(String(20))  # user | assistant
    content: Mapped[str | None] = mapped_column(Text, nullable=True)  # nulled after sync
    citations: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # tier, route_reason
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|synced|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)  # reaper write attempts
