import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class StepExecutionContext:
    session: AsyncSession
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    step_run_id: uuid.UUID
    step_name: str
    step_config: dict[str, Any]
    context: dict[str, Any]
    agent_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None


@dataclass
class StepResult:
    output: Any
    status: str = "succeeded"  # succeeded | waiting_approval | skipped
    next_step: str | None = None
    approval_details: dict[str, Any] | None = None
