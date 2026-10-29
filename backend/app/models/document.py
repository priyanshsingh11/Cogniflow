import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPkMixin

# Matches app.rag.embeddings.EMBEDDING_DIM; migration 0003 must agree.
EMBEDDING_DIM = 384


class Document(Base, UUIDPkMixin, TimestampMixin):
    """An uploaded knowledge file. Bytes live in storage (local folder / R2);
    text and vectors live in Postgres via DOCUMENT_CHUNKS."""

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("workspace_id", "content_hash", name="uq_documents_ws_hash"),
        Index("ix_documents_workspace_created", "workspace_id", "created_at"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(String(512))
    # sha256 hex: deduplicates re-uploads within a workspace.
    content_hash: Mapped[str] = mapped_column(String(64))
    # pending | processing | ready | failed
    status: Mapped[str] = mapped_column(String(20), default="pending")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def is_ready(self) -> bool:
        return self.status == "ready"


class DocumentChunk(Base, UUIDPkMixin):
    """One embeddable passage of a document. workspace_id is denormalized so
    retrieval is a single-table tenant filter plus a join for status."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_chunks_doc_index"),
        Index("ix_document_chunks_workspace", "workspace_id"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    token_count: Mapped[int] = mapped_column(Integer, default=0)
