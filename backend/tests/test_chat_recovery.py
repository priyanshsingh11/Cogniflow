"""Cross-DB recovery: the `pending` Postgres rows the message write leaves
behind (crash between Postgres and Mongo) are healed by the reaper from their
staged payload; repeated failures become `failed`.

All DB/Mongo work runs in ONE asyncio.run per step with the app engine
disposed before and after, so no pooled connection ever crosses event loops
(TestClient's portal loop owns the engine between steps).
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.chat import store
from app.chat.service import reap_stuck_messages
from app.models import Conversation, Message
from tests.test_tenancy import _first_org_and_workspace, _signup

CITATION = {
    "document_id": str(uuid.uuid4()),
    "filename": "runbook.txt",
    "chunk_index": 0,
    "content": "restart the worker",
    "score": 0.75,
}


def _run_db(coro):
    async def go():
        from app.db.postgres import engine

        await engine.dispose()  # drop any TestClient-loop connections first
        try:
            return await coro()
        finally:
            await engine.dispose()  # ... and leave none behind for teardown

    return asyncio.run(go())


def _setup(client: TestClient, email: str):
    user = _signup(client, email, email.split("@")[0].title())
    _, ws = _first_org_and_workspace(client, user)
    return user["user_id"], ws


def _seed(
    user_id: str,
    ws_id: str,
    *,
    content: str | None = "staged payload",
    citations: list | None = None,
    meta: dict | None = None,
    status: str = "pending",
    attempts: int = 0,
    age_minutes: int = 60,
):
    """Insert a conversation + message row directly, simulating a write that
    crashed mid-flight (or simply aged). Returns their ids."""

    async def go():
        from app.db.postgres import SessionLocal

        async with SessionLocal() as session:
            conversation = Conversation(
                workspace_id=uuid.UUID(ws_id), user_id=uuid.UUID(user_id), title="thread"
            )
            session.add(conversation)
            await session.flush()
            row = Message(
                conversation_id=conversation.id,
                workspace_id=uuid.UUID(ws_id),
                role="assistant",
                content=content,
                citations=citations,
                meta=meta,
                status=status,
                attempts=attempts,
                created_at=datetime.now(UTC) - timedelta(minutes=age_minutes),
            )
            session.add(row)
            await session.commit()
            return str(conversation.id), str(row.id)

    return _run_db(go)


async def _reap(**kw) -> int:
    # Shrink the stuck threshold so tests don't wait a minute for new rows.
    return await reap_stuck_messages(stuck_seconds=5, **kw)


def _history(conversation_id: str, ws_id: str) -> list[dict]:
    return asyncio.run(store.fetch_messages(ws_id, conversation_id))


def _row(message_id: str):
    async def go():
        from app.db.postgres import SessionLocal

        async with SessionLocal() as session:
            return await session.get(Message, uuid.UUID(message_id))

    return _run_db(go)


def test_stale_pending_row_is_recovered_into_mongo(client: TestClient):
    user_id, ws = _setup(client, "reap-stale@test.dev")
    conv_id, row_id = _seed(
        user_id,
        ws,
        content="The answer cites [1].",
        citations=[CITATION],
        meta={"tier": "medium", "route_reason": "step_type=qa"},
        age_minutes=60,
    )

    assert _run_db(_reap) == 1

    row = _row(row_id)
    assert row.status == "synced"
    assert row.content is None and row.citations is None and row.meta is None  # nulled
    assert row.attempts == 0

    history = _history(conv_id, ws)
    assert len(history) == 1
    doc = history[0]
    assert doc["id"] == row_id and doc["content"] == "The answer cites [1]."
    assert doc["citations"][0]["filename"] == "runbook.txt"
    assert doc["meta"]["tier"] == "medium"


def test_fresh_pending_row_is_left_alone(client: TestClient):
    user_id, ws = _setup(client, "reap-fresh@test.dev")
    conv_id, row_id = _seed(user_id, ws, content="still being written", age_minutes=0)

    assert _run_db(_reap) == 0  # below the stuck threshold: untouched
    assert _row(row_id).status == "pending"
    assert _row(row_id).content == "still being written"
    assert _history(conv_id, ws) == []


def test_crash_after_mongo_write_is_idempotent(client: TestClient):
    """Row committed, Mongo written, crash before the flip: the retry must
    not duplicate the message (Mongo `_id` = message id)."""
    user_id, ws = _setup(client, "reap-dup@test.dev")
    conv_id, row_id = _seed(user_id, ws, content="written already", age_minutes=60)

    async def prewrite():
        await store.insert_message(
            {
                "_id": row_id,
                "id": row_id,
                "workspace_id": ws,
                "conversation_id": conv_id,
                "role": "assistant",
                "content": "written already",
                "citations": None,
                "meta": None,
                "created_at": datetime.now(UTC),
            }
        )

    asyncio.run(prewrite())

    assert _run_db(_reap) == 1  # flip still happens...
    assert _row(row_id).status == "synced"
    history = _history(conv_id, ws)
    assert len(history) == 1  # ...but the message is stored exactly once


def test_repeated_mongo_failures_become_failed(client: TestClient, monkeypatch):
    user_id, ws = _setup(client, "reap-fail@test.dev")
    _, row_id = _seed(user_id, ws, content="doomed payload", attempts=2, age_minutes=60)

    async def down(doc):
        raise ConnectionError("mongo down")

    monkeypatch.setattr(store, "insert_message", down)

    assert _run_db(_reap) == 0
    row = _row(row_id)
    assert row.status == "failed" and row.attempts == 3  # max attempts reached
    assert row.content == "doomed payload"  # payload kept for inspection


def test_transient_failure_counts_an_attempt_then_recovers(client: TestClient, monkeypatch):
    user_id, ws = _setup(client, "reap-retry@test.dev")
    _, row_id = _seed(user_id, ws, content="eventually consistent", age_minutes=60)

    async def down(doc):
        raise ConnectionError("blip")

    monkeypatch.setattr(store, "insert_message", down)
    assert _run_db(_reap) == 0
    row = _row(row_id)
    assert row.status == "pending" and row.attempts == 1  # still retryable

    monkeypatch.undo()  # mongo is back
    assert _run_db(_reap) == 1
    row = _row(row_id)
    assert row.status == "synced" and row.content is None


def test_pending_row_without_payload_is_given_up_on(client: TestClient):
    user_id, ws = _setup(client, "reap-empty@test.dev")
    _, row_id = _seed(user_id, ws, content=None, age_minutes=60)

    assert _run_db(_reap) == 0
    row = _row(row_id)
    assert row.status == "failed"  # cannot be rebuilt without staged content
    assert row.content is None
