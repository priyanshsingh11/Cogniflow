"""Conversation CRUD and the cross-DB message write pattern.

Every message follows: Postgres row (`pending`, payload staged) -> Mongo write
(`_id` = message UUID, idempotent) -> flip `synced` and null the payload, so
Mongo becomes the sole long-term owner of message content. A crash between the
two writes leaves a `pending` row that `reap_stuck_messages` heals from the
staged payload; rows that keep failing are marked `failed` after
`settings.chat_reaper_max_attempts` and keep their payload for inspection.

The reaper runs from a lifespan task now (phase 3b); arq owns it from phase 5.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat import store
from app.config import settings
from app.db.postgres import SessionLocal
from app.llm.gateway import LLMGateway
from app.models import Conversation, Message
from app.rag.answer import AnswerResult, answer_question
from app.schemas.chat import ConversationOut, MessageOut, TurnOut
from app.schemas.knowledge import PassageOut

logger = logging.getLogger(__name__)


# ------------------------------------------------------------ conversations


async def create_conversation(
    session: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID, title: str
) -> Conversation:
    conversation = Conversation(workspace_id=workspace_id, user_id=user_id, title=title)
    session.add(conversation)
    await session.commit()
    return conversation


async def get_conversation(
    session: AsyncSession, workspace_id: uuid.UUID, conversation_id: uuid.UUID
) -> Conversation | None:
    """Workspace-scoped fetch: foreign ids behave like missing ones (404)."""
    result = await session.execute(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.workspace_id == workspace_id
        )
    )
    return result.scalar_one_or_none()


async def list_conversations(session: AsyncSession, workspace_id: uuid.UUID) -> list[Conversation]:
    result = await session.execute(
        select(Conversation)
        .where(Conversation.workspace_id == workspace_id)
        .order_by(Conversation.created_at.desc())
    )
    return list(result.scalars().all())


def conversation_out(conversation: Conversation) -> ConversationOut:
    return ConversationOut(
        id=conversation.id,
        title=conversation.title,
        user_id=conversation.user_id,
        created_at=conversation.created_at,
    )


# --------------------------------------------------------------- chat turns


async def post_message(
    session: AsyncSession,
    gateway: LLMGateway,
    conversation: Conversation,
    content: str,
    top_k: int = 6,
    tier: str | None = None,
) -> TurnOut:
    """Retrieve -> one cited LLM answer -> persist user + assistant messages.

    Atomic on model failure: `answer_question` raises before anything is
    persisted, so a 502 turn leaves no messages behind."""
    answer: AnswerResult = await answer_question(
        session, gateway, conversation.workspace_id, content, top_k, tier
    )

    user_row = await _persist_message(session, conversation, "user", content, None, None)
    citations = [PassageOut.from_passage(p).model_dump(mode="json") for p in answer.citations]
    meta = {"tier": answer.tier, "route_reason": answer.route_reason}
    assistant_row = await _persist_message(
        session, conversation, "assistant", answer.answer, citations, meta
    )

    return TurnOut(
        user_message=MessageOut(
            id=user_row.id,
            role="user",
            content=content,
            citations=[],
            meta=None,
            created_at=user_row.created_at,
        ),
        assistant_message=MessageOut(
            id=assistant_row.id,
            role="assistant",
            content=answer.answer,
            citations=[PassageOut(**c) for c in citations],
            meta=meta,
            created_at=assistant_row.created_at,
        ),
        tier=answer.tier,
        route_reason=answer.route_reason,
    )


async def fetch_history(conversation: Conversation) -> list[MessageOut]:
    """Oldest-first history from Mongo (the owner of message content)."""
    docs = await store.fetch_messages(str(conversation.workspace_id), str(conversation.id))
    return [MessageOut.from_doc(doc) for doc in docs]


async def _persist_message(
    session: AsyncSession,
    conversation: Conversation,
    role: str,
    content: str,
    citations: list | None,
    meta: dict | None,
) -> Message:
    row = Message(
        conversation_id=conversation.id,
        workspace_id=conversation.workspace_id,
        role=role,
        content=content,
        citations=citations,
        meta=meta,
        status="pending",
        attempts=0,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    # Postgres row first, durably, before touching Mongo (cross-DB rule).
    await session.commit()

    try:
        await store.insert_message(_mongo_doc(row))
    except Exception:  # Mongo down: leave `pending`, the reaper heals it
        logger.warning("mongo write failed for message %s; left pending", row.id, exc_info=True)
        return row

    await _mark_synced(session, row)
    return row


async def _mark_synced(session: AsyncSession, row: Message) -> None:
    row.status = "synced"
    row.content = None
    row.citations = None
    row.meta = None
    await session.commit()


def _mongo_doc(row: Message) -> dict:
    return {
        "_id": str(row.id),
        "id": str(row.id),
        "workspace_id": str(row.workspace_id),
        "conversation_id": str(row.conversation_id),
        "role": row.role,
        "content": row.content,
        "citations": row.citations,
        "meta": row.meta,
        "created_at": row.created_at,
    }


# ------------------------------------------------------------------- reaper


async def reap_stuck_messages(
    *,
    stuck_seconds: int | None = None,
    max_attempts: int | None = None,
    batch: int = 100,
) -> int:
    """Retry `pending` rows older than `stuck_seconds` from their staged
    payload. Returns the number of rows recovered (flipped to `synced`)."""
    stuck_seconds = settings.chat_reaper_stuck_seconds if stuck_seconds is None else stuck_seconds
    max_attempts = settings.chat_reaper_max_attempts if max_attempts is None else max_attempts
    cutoff = datetime.now(UTC) - timedelta(seconds=stuck_seconds)

    async with SessionLocal() as session:
        result = await session.execute(
            select(Message)
            .where(Message.status == "pending", Message.created_at < cutoff)
            .order_by(Message.created_at)
            .limit(batch)
        )
        recovered = 0
        for row in result.scalars().all():
            if row.content is None:
                # Pending without payload cannot be rebuilt: give up loudly.
                row.status = "failed"
                row.attempts += 1
                continue
            try:
                await store.insert_message(_mongo_doc(row))
            except Exception:
                row.attempts += 1
                if row.attempts >= max_attempts:
                    row.status = "failed"  # payload kept for inspection
                logger.warning(
                    "reaper could not sync message %s (attempt %d)",
                    row.id,
                    row.attempts,
                    exc_info=True,
                )
                continue
            await _mark_synced(session, row)
            recovered += 1
        await session.commit()
        return recovered


async def reaper_loop(stop: asyncio.Event) -> None:
    """Periodic reaper for the app lifespan (until arq takes it in phase 5)."""
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.chat_reaper_interval_seconds)
            return  # stop requested
        except TimeoutError:
            pass
        try:
            await reap_stuck_messages()
        except Exception:  # never let the loop die
            logger.exception("chat reaper run failed")
