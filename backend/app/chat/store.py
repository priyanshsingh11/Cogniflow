"""Mongo persistence for chat messages.

Ownership rule: Mongo documents reference Postgres UUIDs (`workspace_id`,
`conversation_id`, `message_id`), never the reverse — there is no
`mongo_conversation_id` anywhere. Every query is filtered by `workspace_id`
(Authorize in Postgres happens first in the API layer).

Motor clients are bound to the event loop that uses them, and the app runs
across several loops (uvicorn request loop, reaper task, pytest's per-test
loops), so clients are cached per running loop instead of being shared.
"""

import asyncio
from typing import Any
from weakref import WeakKeyDictionary

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

from app.config import settings

COLLECTION = "messages"
DEFAULT_HISTORY_LIMIT = 500

_clients: WeakKeyDictionary[asyncio.AbstractEventLoop, AsyncIOMotorClient] = WeakKeyDictionary()


def _collection():
    loop = asyncio.get_running_loop()
    client = _clients.get(loop)
    if client is None:
        client = AsyncIOMotorClient(settings.mongo_url)
        _clients[loop] = client
    return client[settings.mongo_db][COLLECTION]


async def insert_message(doc: dict[str, Any]) -> None:
    """Idempotent write: `_id` is the Postgres message UUID, so a reaper
    retry after a crash-following-write is a harmless duplicate."""
    try:
        await _collection().insert_one(doc)
    except DuplicateKeyError:
        pass  # already written by a previous attempt -> success


async def fetch_messages(
    workspace_id: str, conversation_id: str, limit: int = DEFAULT_HISTORY_LIMIT
) -> list[dict[str, Any]]:
    """Oldest-first history for ONE conversation in ONE workspace."""
    cursor = (
        _collection()
        .find(
            {"workspace_id": workspace_id, "conversation_id": conversation_id},
            {"_id": 0},
        )
        .sort([("created_at", 1), ("id", 1)])
        .limit(limit)
    )
    return await cursor.to_list(length=limit)
