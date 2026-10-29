import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.types import Attempt
from app.models.llm_call import LLMCall


def record_attempts(
    session: AsyncSession,
    attempts: list[Attempt],
    *,
    workspace_id: uuid.UUID,
    route_reason: str,
    agent_id: uuid.UUID | None = None,
    step_run_id: uuid.UUID | None = None,
) -> None:
    """Stage one llm_calls row per attempt (incl. failures/skips). Caller commits."""
    for a in attempts:
        session.add(
            LLMCall(
                workspace_id=workspace_id,
                agent_id=a.agent_id or agent_id,
                step_run_id=step_run_id,
                provider=a.provider,
                model=a.model,
                tier=a.tier,
                route_reason=a.route_reason or route_reason,
                attempt_no=a.attempt_no,
                status=a.status,
                error_type=a.error_type,
                prompt_tokens=a.prompt_tokens,
                completion_tokens=a.completion_tokens,
                latency_ms=a.latency_ms,
            )
        )
