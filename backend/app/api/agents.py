"""Agents CRUD (admin edits, any member of the org can read/run) and run endpoints
for a single agent or the coordinator (master agent)."""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.config import ROLES, AgentConfig
from app.agents.coordinator import PlanError, run_coordinator
from app.agents.deps import get_tools
from app.agents.runtime import AgentRunError, run_agent
from app.agents.specialists import SPECIALISTS
from app.agents.tools import ToolRegistry
from app.api.deps import TenantContext, require_role, require_workspace
from app.db.postgres import get_pg
from app.llm.deps import get_gateway
from app.llm.gateway import LLMGateway
from app.llm.recording import record_attempts
from app.llm.types import ModelRef, Tier
from app.models import Agent, Role

router = APIRouter(prefix="/workspaces/{workspace_id}/agents", tags=["agents"])
coordinator_router = APIRouter(prefix="/workspaces/{workspace_id}/coordinator", tags=["agents"])
require_member = require_role(Role.MEMBER)
require_admin = require_role(Role.ADMIN)


class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    role: str
    system_prompt: str = Field(default="", max_length=20_000)
    tier_pin: str | None = None
    model_pin: str | None = None  # "provider:model"
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("role")
    @classmethod
    def _role(cls, v: str) -> str:
        if v not in ROLES:
            raise ValueError(f"role must be one of {list(ROLES)}")
        return v

    @field_validator("tier_pin")
    @classmethod
    def _tier(cls, v: str | None) -> str | None:
        if v is not None:
            Tier(v)  # raises ValueError -> 422
        return v

    @field_validator("model_pin")
    @classmethod
    def _model(cls, v: str | None) -> str | None:
        if v is not None:
            ModelRef.parse(v)
        return v


class AgentPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    role: str | None = None
    system_prompt: str | None = Field(default=None, max_length=20_000)
    tier_pin: str | None = None
    model_pin: str | None = None
    params: dict[str, Any] | None = None

    _role = field_validator("role")(AgentIn._role.__func__)
    _tier = field_validator("tier_pin")(AgentIn._tier.__func__)
    _model = field_validator("model_pin")(AgentIn._model.__func__)


class AgentOut(BaseModel):
    id: uuid.UUID
    name: str
    role: str
    system_prompt: str
    tier_pin: str | None
    model_pin: str | None
    params: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


async def _get_agent(session: AsyncSession, ctx: TenantContext, agent_id: uuid.UUID) -> Agent:
    agent = await session.get(Agent, agent_id)
    # Scope to the caller's workspace: foreign agents look nonexistent.
    if agent is None or agent.workspace_id != ctx.workspace.id:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.get("", response_model=list[AgentOut])
async def list_agents(
    ctx: TenantContext = Depends(require_workspace), session: AsyncSession = Depends(get_pg)
) -> list[Agent]:
    result = await session.execute(
        select(Agent).where(Agent.workspace_id == ctx.workspace.id).order_by(Agent.created_at)
    )
    return list(result.scalars())


@router.post("", response_model=AgentOut, status_code=201)
async def create_agent(
    payload: AgentIn,
    ctx: TenantContext = Depends(require_admin),
    session: AsyncSession = Depends(get_pg),
) -> Agent:
    agent = Agent(workspace_id=ctx.workspace.id, **payload.model_dump())
    session.add(agent)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="An agent with this name already exists"
        ) from exc
    return agent


@router.get("/{agent_id}", response_model=AgentOut)
async def get_agent(
    agent_id: uuid.UUID,
    ctx: TenantContext = Depends(require_workspace),
    session: AsyncSession = Depends(get_pg),
) -> Agent:
    return await _get_agent(session, ctx, agent_id)


@router.patch("/{agent_id}", response_model=AgentOut)
async def update_agent(
    agent_id: uuid.UUID,
    payload: AgentPatch,
    ctx: TenantContext = Depends(require_admin),
    session: AsyncSession = Depends(get_pg),
) -> Agent:
    agent = await _get_agent(session, ctx, agent_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(agent, key, value)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="An agent with this name already exists"
        ) from exc
    return agent


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(
    agent_id: uuid.UUID,
    ctx: TenantContext = Depends(require_admin),
    session: AsyncSession = Depends(get_pg),
) -> None:
    await session.delete(await _get_agent(session, ctx, agent_id))
    await session.commit()


# ---- runs ------------------------------------------------------------------


class RunIn(BaseModel):
    input: str = Field(min_length=1, max_length=50_000)


class ToolStepOut(BaseModel):
    kind: str
    tool: str
    arguments: dict[str, Any]
    result: str


class RunOut(BaseModel):
    output: str
    status: str
    steps: list[ToolStepOut]
    models_used: list[str]
    llm_calls: int


@router.post("/{agent_id}/run", response_model=RunOut)
async def run_agent_endpoint(
    agent_id: uuid.UUID,
    payload: RunIn,
    ctx: TenantContext = Depends(require_member),
    session: AsyncSession = Depends(get_pg),
    gateway: LLMGateway = Depends(get_gateway),
    tools: ToolRegistry = Depends(get_tools),
) -> RunOut:
    agent = await _get_agent(session, ctx, agent_id)
    try:
        result = await run_agent(gateway, AgentConfig.from_row(agent), payload.input, tools=tools)
    except AgentRunError as exc:
        record_attempts(
            session, exc.attempts, workspace_id=ctx.workspace.id, route_reason="agent run failed"
        )
        await session.commit()
        raise HTTPException(status_code=502, detail="All models failed") from exc
    record_attempts(session, result.attempts, workspace_id=ctx.workspace.id, route_reason="")
    await session.commit()
    return RunOut(
        output=result.output,
        status=result.status,
        steps=[ToolStepOut(**s.__dict__) for s in result.steps],
        models_used=result.models_used,
        llm_calls=len(result.attempts),
    )


class CoordinatorIn(BaseModel):
    goal: str = Field(min_length=1, max_length=20_000)


class PlanStepOut(BaseModel):
    role: str
    task: str


class CoordStepOut(BaseModel):
    role: str
    task: str
    agent: str
    status: str
    output: str


class CoordinatorOut(BaseModel):
    status: str
    plan: list[PlanStepOut]
    steps: list[CoordStepOut]
    final: str
    llm_calls: int


@coordinator_router.post("/run", response_model=CoordinatorOut)
async def run_coordinator_endpoint(
    payload: CoordinatorIn,
    ctx: TenantContext = Depends(require_member),
    session: AsyncSession = Depends(get_pg),
    gateway: LLMGateway = Depends(get_gateway),
    tools: ToolRegistry = Depends(get_tools),
) -> CoordinatorOut:
    async def resolve(role: str) -> AgentConfig:
        """Workspace agent for this role if one exists, else the built-in."""
        row = (
            await session.execute(
                select(Agent)
                .where(Agent.workspace_id == ctx.workspace.id, Agent.role == role)
                .order_by(Agent.created_at)
                .limit(1)
            )
        ).scalar_one_or_none()
        return AgentConfig.from_row(row) if row else SPECIALISTS[role]

    try:
        result = await run_coordinator(gateway, payload.goal, resolve, tools=tools)
    except PlanError as exc:
        record_attempts(
            session, exc.attempts, workspace_id=ctx.workspace.id, route_reason="planning failed"
        )
        await session.commit()
        raise HTTPException(status_code=502, detail="Coordinator could not plan the goal") from exc
    record_attempts(session, result.attempts, workspace_id=ctx.workspace.id, route_reason="")
    await session.commit()
    return CoordinatorOut(
        status=result.status,
        plan=[PlanStepOut(**p) for p in result.plan],
        steps=[CoordStepOut(**s.__dict__) for s in result.steps],
        final=result.final,
        llm_calls=len(result.attempts),
    )
