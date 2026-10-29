"""Direct gateway access for a workspace: a smoke-test/playground endpoint.

Agent runs (phase 2b) call the same gateway; this endpoint exists so routing,
fallback and llm_calls logging can be exercised and inspected end to end.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, require_role
from app.db.postgres import get_pg
from app.llm.deps import get_gateway
from app.llm.errors import AllModelsFailedError
from app.llm.gateway import LLMGateway
from app.llm.recording import record_attempts
from app.llm.types import Message, RoutingHints, Tier
from app.models import Role

router = APIRouter(prefix="/workspaces/{workspace_id}/llm", tags=["llm"])
require_member = require_role(Role.MEMBER)


class MessageIn(BaseModel):
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str = Field(min_length=1, max_length=100_000)


class ChatIn(BaseModel):
    messages: list[MessageIn] = Field(min_length=1)
    step_type: str | None = None
    tier: Tier | None = None  # optional pin, overrides the router
    max_tokens: int | None = Field(default=None, ge=1, le=8192)
    temperature: float | None = Field(default=None, ge=0, le=2)


class AttemptOut(BaseModel):
    attempt_no: int
    tier: str
    provider: str
    model: str
    status: str
    error_type: str | None
    latency_ms: int


class ChatOut(BaseModel):
    content: str
    tier: str
    route_reason: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    attempts: list[AttemptOut]


@router.post("/chat", response_model=ChatOut)
async def chat(
    payload: ChatIn,
    ctx: TenantContext = Depends(require_member),
    session: AsyncSession = Depends(get_pg),
    gateway: LLMGateway = Depends(get_gateway),
) -> ChatOut:
    hints = RoutingHints(
        step_type=payload.step_type,
        pinned_tier=payload.tier,
        params={"max_tokens": payload.max_tokens, "temperature": payload.temperature},
    )
    messages = [Message(m.role, m.content) for m in payload.messages]
    try:
        result = await gateway.complete(messages, hints)
    except AllModelsFailedError as exc:
        record_attempts(
            session, exc.attempts, workspace_id=ctx.workspace.id, route_reason="all models failed"
        )
        await session.commit()
        raise HTTPException(status_code=502, detail="All models failed") from exc

    record_attempts(
        session, result.attempts, workspace_id=ctx.workspace.id, route_reason=result.route_reason
    )
    await session.commit()
    return ChatOut(
        content=result.response.content,
        tier=result.tier,
        route_reason=result.route_reason,
        provider=result.response.provider,
        model=result.response.model,
        prompt_tokens=result.response.prompt_tokens,
        completion_tokens=result.response.completion_tokens,
        attempts=[
            AttemptOut(
                attempt_no=a.attempt_no,
                tier=a.tier,
                provider=a.provider,
                model=a.model,
                status=a.status,
                error_type=a.error_type,
                latency_ms=a.latency_ms,
            )
            for a in result.attempts
        ],
    )
