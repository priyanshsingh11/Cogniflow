"""Vector retrieval: cosine similarity over document_chunks, tenant-filtered."""

import asyncio
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentChunk
from app.rag.embeddings import get_embedder


@dataclass(frozen=True)
class Passage:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    chunk_index: int
    content: str
    token_count: int
    score: float  # cosine similarity in [0, 1] for normalized vectors


async def search(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    query: str,
    top_k: int = 6,
) -> list[Passage]:
    """Top-k most similar passages from ready documents in this workspace.

    Only chunks whose document has finished indexing are searchable; embeds
    the query with the same model/dimensions as the stored vectors."""
    if top_k < 1:
        return []
    embedder = get_embedder()
    vector = await _embed_query(embedder, query)

    result = await session.execute(
        select(
            DocumentChunk,
            Document.filename,
            DocumentChunk.embedding.cosine_distance(vector).label("distance"),
        )
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(
            DocumentChunk.workspace_id == workspace_id,
            Document.status == "ready",
        )
        .order_by("distance")
        .limit(top_k)
    )
    return [
        Passage(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            filename=filename,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            token_count=chunk.token_count,
            score=max(0.0, 1.0 - float(distance)),
        )
        for chunk, filename, distance in result.all()
    ]


async def _embed_query(embedder, query: str) -> list[float]:
    return await asyncio.to_thread(embedder.embed_query, query)
