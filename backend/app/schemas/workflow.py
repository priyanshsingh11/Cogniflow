import datetime
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

StepType = Literal[
    "llm",
    "knowledge_search",
    "mcp_tool",
    "condition",
    "agent",
    "coordinator",
    "approval",
]


class WorkflowStepCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: StepType
    position: int = 0
    agent_id: uuid.UUID | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    next_step: str | None = None


class WorkflowStepOut(BaseModel):
    id: uuid.UUID
    workflow_version_id: uuid.UUID
    name: str
    position: int
    type: str
    agent_id: uuid.UUID | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class WorkflowVersionCreate(BaseModel):
    steps: list[WorkflowStepCreate] = Field(..., min_length=1)
    graph: dict[str, Any] | None = None


class WorkflowVersionOut(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    version: int
    graph: dict[str, Any] = Field(default_factory=dict)
    steps: list[WorkflowStepOut] = Field(default_factory=list)
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class WorkflowCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    steps: list[WorkflowStepCreate] = Field(..., min_length=1)
    graph: dict[str, Any] | None = None


class WorkflowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None


class WorkflowOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: str | None = None
    current_version_id: uuid.UUID | None = None
    current_version: WorkflowVersionOut | None = None
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


# ------------------------------------------------------------------- runs


class RunTriggerIn(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=255)


class StepRunOut(BaseModel):
    id: uuid.UUID
    workflow_run_id: uuid.UUID
    workflow_step_id: uuid.UUID | None = None
    step_name: str
    attempt: int
    status: str
    idempotency_key: str | None = None
    input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    error: str | None = None
    started_at: datetime.datetime | None = None
    finished_at: datetime.datetime | None = None
    created_at: datetime.datetime
    llm_calls_count: int = 0
    tool_calls_count: int = 0

    model_config = {"from_attributes": True}


class WorkflowRunOut(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    workflow_version_id: uuid.UUID
    workspace_id: uuid.UUID
    conversation_id: uuid.UUID | None = None
    triggered_by: uuid.UUID | None = None
    status: str
    idempotency_key: str | None = None
    queue_job_id: str | None = None
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] | None = None
    error: str | None = None
    started_at: datetime.datetime | None = None
    finished_at: datetime.datetime | None = None
    created_at: datetime.datetime
    step_runs: list[StepRunOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}

