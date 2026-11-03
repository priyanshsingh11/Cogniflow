"""Schemas for the usage & cost dashboard API (phase 8)."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class UsageTotals(BaseModel):
    llm_calls: int  # logical gateway calls (one per invocation)
    llm_attempts: int  # individual model attempts incl. failures/skips
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float  # $0 while only free models are configured
    failed_calls: int  # logical calls where no attempt succeeded
    fallback_calls: int  # logical calls that needed more than one attempt
    fallback_rate: float  # fallback_calls / llm_calls
    failure_rate: float  # failed_calls / llm_calls
    avg_latency_ms: float  # per attempt
    p95_latency_ms: float
    tool_calls: int
    tool_call_errors: int
    runs: int
    runs_succeeded: int
    runs_failed: int
    run_success_rate: float  # succeeded / (succeeded + failed)


class TierUsage(BaseModel):
    tier: str
    calls: int
    attempts: int
    tokens: int
    errors: int
    avg_latency_ms: float


class ModelUsage(BaseModel):
    provider: str
    model: str
    attempts: int
    tokens: int
    errors: int
    avg_latency_ms: float


class AgentUsage(BaseModel):
    agent_id: uuid.UUID | None = None  # None = unattributed (playground/chat)
    agent_name: str | None = None
    attempts: int
    tokens: int
    errors: int


class DayUsage(BaseModel):
    day: date
    calls: int  # logical calls started that day
    attempts: int
    tokens: int
    errors: int
    avg_latency_ms: float


class SlowStep(BaseModel):
    step_run_id: uuid.UUID
    workflow_run_id: uuid.UUID
    workflow_name: str
    step_name: str
    status: str
    duration_ms: int
    finished_at: datetime | None = None


class SlowWorkflow(BaseModel):
    workflow_id: uuid.UUID
    workflow_name: str
    runs: int
    avg_duration_ms: int
    max_duration_ms: int


class RecentError(BaseModel):
    kind: str  # llm_call | run
    created_at: datetime
    message: str
    entity_id: uuid.UUID | None = None
    context: dict = Field(default_factory=dict)  # model/tier or workflow_id


class UsageReport(BaseModel):
    days: int
    since: datetime
    totals: UsageTotals
    by_tier: list[TierUsage]
    by_model: list[ModelUsage]
    by_agent: list[AgentUsage]
    by_day: list[DayUsage]  # zero-filled across the whole range
    slowest_steps: list[SlowStep]
    slowest_workflows: list[SlowWorkflow]
    recent_errors: list[RecentError]
