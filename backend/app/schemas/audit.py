"""Schemas for the audit log read API (phase 8)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AuditLogOut(BaseModel):
    id: uuid.UUID
    action: str
    actor_id: uuid.UUID | None = None
    actor_email: str | None = None
    workspace_id: uuid.UUID | None = None
    org_id: uuid.UUID | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
