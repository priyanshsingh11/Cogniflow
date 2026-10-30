"""Knowledge API: document upload/list/delete, vector search and cited answers.

Upload flow: validate -> hash-dedupe -> store bytes -> insert row (pending)
-> process in the background (parse/chunk/embed). Retrieval and `ask` only see
chunks of documents whose status is `ready`. The answer itself comes from
`app.rag.answer.answer_question`, shared with chat (phase 3b).
"""

import hashlib
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, require_role
from app.config import settings
from app.db.postgres import get_pg
from app.llm.deps import get_gateway
from app.llm.errors import AllModelsFailedError
from app.llm.gateway import LLMGateway
from app.models import Document, Role
from app.rag.answer import NoIndexedDocumentsError, answer_question
from app.rag.parsing import SUPPORTED_EXTENSIONS, extension_of
from app.rag.retrieval import search as vector_search
from app.rag.service import delete_document, get_document, process_document
from app.schemas.knowledge import AskIn, AskOut, DocumentOut, PassageOut, SearchIn, SearchOut
from app.storage import get_storage

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["knowledge"])
require_viewer = require_role(Role.VIEWER)
require_member = require_role(Role.MEMBER)


# ---------------------------------------------------------------- documents


def _document_out(document: Document) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        filename=document.filename,
        status=document.status,
        size_bytes=document.size_bytes,
        error_message=document.error_message,
        created_at=document.created_at,
    )


@router.post("/documents", response_model=DocumentOut, status_code=201)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    ctx: TenantContext = Depends(require_member),
    session: AsyncSession = Depends(get_pg),
) -> DocumentOut:
    filename = (file.filename or "").strip()
    if extension_of(filename) not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type; allowed: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )

    data = await file.read()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail=f"File exceeds {settings.max_upload_mb} MB")
    if not data:
        raise HTTPException(status_code=422, detail="File is empty")

    content_hash = hashlib.sha256(data).hexdigest()
    existing = await session.execute(
        select(Document.id).where(
            Document.workspace_id == ctx.workspace.id, Document.content_hash == content_hash
        )
    )
    if existing.first() is not None:
        raise HTTPException(status_code=409, detail="This file is already uploaded")

    document = Document(
        workspace_id=ctx.workspace.id,
        filename=filename,
        storage_path="",  # filled after we know the id (key includes it)
        content_hash=content_hash,
        size_bytes=len(data),
        status="pending",
    )
    session.add(document)
    await session.flush()  # assigns id before the storage key is built

    key = f"{ctx.workspace.id}/{document.id}/{filename}"
    document.storage_path = key
    try:
        await get_storage().save(key, data)
    except Exception:
        await session.rollback()
        raise HTTPException(status_code=500, detail="Could not store the file") from None
    await session.commit()

    background_tasks.add_task(process_document, document.id)
    return _document_out(document)


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(
    ctx: TenantContext = Depends(require_viewer),
    session: AsyncSession = Depends(get_pg),
) -> list[DocumentOut]:
    result = await session.execute(
        select(Document)
        .where(Document.workspace_id == ctx.workspace.id)
        .order_by(Document.created_at.desc())
    )
    return [_document_out(d) for d in result.scalars().all()]


@router.get("/documents/{document_id}", response_model=DocumentOut)
async def get_document_endpoint(
    document_id: uuid.UUID,
    ctx: TenantContext = Depends(require_viewer),
    session: AsyncSession = Depends(get_pg),
) -> DocumentOut:
    document = await get_document(session, ctx.workspace.id, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return _document_out(document)


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document_endpoint(
    document_id: uuid.UUID,
    ctx: TenantContext = Depends(require_member),
    session: AsyncSession = Depends(get_pg),
) -> None:
    document = await get_document(session, ctx.workspace.id, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    await delete_document(document.id)


# ----------------------------------------------------------- search and ask


@router.post("/knowledge/search", response_model=SearchOut)
async def search_knowledge(
    payload: SearchIn,
    ctx: TenantContext = Depends(require_member),
    session: AsyncSession = Depends(get_pg),
) -> SearchOut:
    passages = await vector_search(session, ctx.workspace.id, payload.query, payload.top_k)
    return SearchOut(
        query=payload.query,
        passages=[PassageOut.from_passage(p) for p in passages],
    )


@router.post("/knowledge/ask", response_model=AskOut)
async def ask_knowledge(
    payload: AskIn,
    ctx: TenantContext = Depends(require_member),
    session: AsyncSession = Depends(get_pg),
    gateway: LLMGateway = Depends(get_gateway),
) -> AskOut:
    try:
        result = await answer_question(
            session, gateway, ctx.workspace.id, payload.question, payload.top_k, payload.tier
        )
    except NoIndexedDocumentsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AllModelsFailedError as exc:
        raise HTTPException(status_code=502, detail="All models failed") from exc
    return AskOut(
        answer=result.answer,
        citations=[PassageOut.from_passage(p) for p in result.citations],
        tier=result.tier,
        route_reason=result.route_reason,
    )
