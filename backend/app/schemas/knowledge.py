"""Schemas for documents, retrieval and cited answers (phase 3)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.rag.retrieval import Passage


class DocumentOut(BaseModel):
    id: uuid.UUID
    filename: str
    status: str  # pending | processing | ready | failed
    size_bytes: int
    error_message: str | None = None
    created_at: datetime


class SearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=4_000)
    top_k: int = Field(default=6, ge=1, le=20)


class PassageOut(BaseModel):
    document_id: uuid.UUID
    filename: str
    chunk_index: int
    content: str
    score: float

    @classmethod
    def from_passage(cls, p: Passage) -> "PassageOut":
        return cls(
            document_id=p.document_id,
            filename=p.filename,
            chunk_index=p.chunk_index,
            content=p.content,
            score=round(p.score, 4),
        )


class SearchOut(BaseModel):
    query: str
    passages: list[PassageOut]


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=4_000)
    top_k: int = Field(default=6, ge=1, le=20)
    tier: str | None = None  # optional pin, overrides the router


class AskOut(BaseModel):
    answer: str
    citations: list[PassageOut]
    tier: str
    route_reason: str
