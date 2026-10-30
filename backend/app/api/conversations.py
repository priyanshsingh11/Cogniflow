"""Conversations & chat: create/list/get threads, post a message (retrieval +
one cited LLM call), fetch history from Mongo.

Reads are viewer+, writes member+; conversations are workspace-scoped so a
foreign conversation id is a 404 on every path (existence never leaks).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, require_role
from app.chat import service
from app.db.postgres import get_pg
from app.llm.deps import get_gateway
from app.llm.errors import AllModelsFailedError
from app.llm.gateway import LLMGateway
from app.models import Role
from app.rag.answer import NoIndexedDocumentsError
from app.schemas.chat import ConversationCreate, ConversationOut, MessageIn, MessageOut, TurnOut

router = APIRouter(prefix="/workspaces/{workspace_id}/conversations", tags=["conversations"])
require_viewer = require_role(Role.VIEWER)
require_member = require_role(Role.MEMBER)


async def _load(session: AsyncSession, ctx: TenantContext, conversation_id: uuid.UUID):
    conversation = await service.get_conversation(session, ctx.workspace.id, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.post("", response_model=ConversationOut, status_code=201)
async def create_conversation(
    payload: ConversationCreate,
    ctx: TenantContext = Depends(require_member),
    session: AsyncSession = Depends(get_pg),
) -> ConversationOut:
    conversation = await service.create_conversation(
        session, ctx.workspace.id, ctx.user.id, payload.title
    )
    return service.conversation_out(conversation)


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    ctx: TenantContext = Depends(require_viewer),
    session: AsyncSession = Depends(get_pg),
) -> list[ConversationOut]:
    rows = await service.list_conversations(session, ctx.workspace.id)
    return [service.conversation_out(c) for c in rows]


@router.get("/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: uuid.UUID,
    ctx: TenantContext = Depends(require_viewer),
    session: AsyncSession = Depends(get_pg),
) -> ConversationOut:
    conversation = await _load(session, ctx, conversation_id)
    return service.conversation_out(conversation)


@router.post("/{conversation_id}/messages", response_model=TurnOut)
async def post_message(
    conversation_id: uuid.UUID,
    payload: MessageIn,
    ctx: TenantContext = Depends(require_member),
    session: AsyncSession = Depends(get_pg),
    gateway: LLMGateway = Depends(get_gateway),
) -> TurnOut:
    conversation = await _load(session, ctx, conversation_id)
    try:
        return await service.post_message(
            session, gateway, conversation, payload.content, payload.top_k, payload.tier
        )
    except NoIndexedDocumentsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AllModelsFailedError as exc:
        # Atomic turn: nothing was persisted (answer_question raised first).
        raise HTTPException(status_code=502, detail="All models failed") from exc


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
async def get_messages(
    conversation_id: uuid.UUID,
    ctx: TenantContext = Depends(require_viewer),
    session: AsyncSession = Depends(get_pg),
) -> list[MessageOut]:
    conversation = await _load(session, ctx, conversation_id)
    return await service.fetch_history(conversation)
