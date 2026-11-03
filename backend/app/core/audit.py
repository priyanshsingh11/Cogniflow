"""Audit recording helper (phase 8).

Mirrors ``app.llm.recording``: stage the row, the caller commits — so an
event lands in the same transaction as the change it describes (a rollback
discards both). Callers whose path raises (failed login) commit explicitly
before raising.
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


def record_audit(
    session: AsyncSession,
    *,
    action: str,
    actor_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    org_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    """Stage one audit row. Caller commits."""
    row = AuditLog(
        action=action,
        actor_id=actor_id,
        workspace_id=workspace_id,
        org_id=org_id,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        metadata_json=metadata or {},
    )
    session.add(row)
    return row
