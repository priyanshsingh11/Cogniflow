"""Document processing pipeline: load bytes -> parse -> chunk -> embed -> store.

Runs in-process after the upload response (FastAPI BackgroundTasks); the arq
worker in phase 5 can call ``process_document`` unchanged. The document row is
committed first with status ``pending`` (Postgres-first rule), then flipped to
``processing`` -> ``ready`` / ``failed``; a failed row keeps ``error_message``.
"""

import asyncio
import uuid

from sqlalchemy import delete, select

from app.config import settings
from app.db.postgres import SessionLocal
from app.models import Document, DocumentChunk
from app.rag.chunking import chunk_text, token_count
from app.rag.embeddings import get_embedder
from app.rag.parsing import DocumentParseError, extract_text
from app.storage import get_storage


async def process_document(document_id: uuid.UUID) -> None:
    async with SessionLocal() as session:
        document = await session.get(Document, document_id)
        if document is None:
            return  # deleted while queued
        document.status = "processing"
        await session.commit()

        try:
            data = await get_storage().load(document.storage_path)
            text = extract_text(document.filename, data)
            chunks = chunk_text(text)
            if not chunks:
                raise DocumentParseError("No text to index")
            if len(chunks) > settings.rag_max_chunks_per_doc:
                raise DocumentParseError(
                    f"Document splits into {len(chunks)} chunks "
                    f"(limit {settings.rag_max_chunks_per_doc})"
                )

            embedder = get_embedder()
            # CPU-bound ONNX inference; keep the event loop free.
            vectors = await asyncio.to_thread(embedder.embed, chunks)

            # Reprocessing (a retry) must not duplicate: start from scratch.
            await session.execute(
                delete(DocumentChunk).where(DocumentChunk.document_id == document.id)
            )
            session.add_all(
                DocumentChunk(
                    document_id=document.id,
                    workspace_id=document.workspace_id,
                    chunk_index=i,
                    content=content,
                    embedding=vector,
                    token_count=token_count(content),
                )
                for i, (content, vector) in enumerate(zip(chunks, vectors, strict=True))
            )
            document.status = "ready"
            document.error_message = None
        except Exception as exc:  # any failure marks the row, never the worker
            document.status = "failed"
            document.error_message = str(exc) or exc.__class__.__name__
        await session.commit()


async def delete_document(document_id: uuid.UUID) -> bool:
    """Remove a document row (chunks cascade) and its stored bytes.

    Returns False when the document does not exist (caller maps that to 404)."""
    async with SessionLocal() as session:
        document = await session.get(Document, document_id)
        if document is None:
            return False
        storage_path = document.storage_path
        await session.delete(document)
        await session.commit()
    await get_storage().delete(storage_path)
    return True


async def get_document(session, workspace_id: uuid.UUID, document_id: uuid.UUID) -> Document | None:
    """Workspace-scoped fetch: foreign ids behave like missing ones (404)."""
    result = await session.execute(
        select(Document).where(
            Document.id == document_id, Document.workspace_id == workspace_id
        )
    )
    return result.scalar_one_or_none()
