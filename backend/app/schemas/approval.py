import datetime
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field


class ApprovalDecideIn(BaseModel):
    action: Literal["approve", "reject"]
    reason: str | None = Field(default=None, max_length=2000)


class ApprovalOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    workflow_run_id: uuid.UUID | None = None
    step_run_id: uuid.UUID | None = None
    decided_by: uuid.UUID | None = None
    status: str
    reason: str | None = None
    description: str | None = None
    details: dict[str, Any] | None = None
    requested_at: datetime.datetime
    decided_at: datetime.datetime | None = None
    created_at: datetime.datetime

    model_config = {"from_attributes": True}
