"""Schemas for conversations, chat messages and turns (phase 3b)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.llm.types import Tier
from app.schemas.knowledge import PassageOut


class ConversationCreate(BaseModel):
    title: str = Field(default="", max_length=255)


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str
    user_id: uuid.UUID  # creator/owner
    created_at: datetime


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    top_k: int = Field(default=6, ge=1, le=20)
    tier: str | None = None  # optional pin, overrides the router

    @field_validator("tier")
    @classmethod
    def _tier(cls, v: str | None) -> str | None:
        if v is not None:
            Tier(v)  # raises ValueError -> 422
        return v


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str  # user | assistant
    content: str | None = None  # None only for corrupted/failed staging rows
    citations: list[PassageOut] = Field(default_factory=list)  # assistant only
    meta: dict | None = None  # assistant only: tier, route_reason
    created_at: datetime

    @classmethod
    def from_doc(cls, doc: dict) -> "MessageOut":
        """From a Mongo message document (the history source of truth)."""
        return cls(
            id=doc["id"],
            role=doc["role"],
            content=doc.get("content"),
            citations=[PassageOut(**c) for c in doc.get("citations") or []],
            meta=doc.get("meta"),
            created_at=doc["created_at"],
        )


class TurnOut(BaseModel):
    user_message: MessageOut
    assistant_message: MessageOut
    tier: str
    route_reason: str
