import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_request_id
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
    """Stage one llm_calls row per attempt (incl. failures/skips). Caller commits.

    All rows of one invocation share a `call_id` (so the dashboard can count
    logical calls and fallbacks) and the current `request_id` (so they join to
    the structured log lines of the request or job that produced them).
    """
    call_id = uuid.uuid4()
    request_id = get_request_id()
    for a in attempts:
        session.add(
            LLMCall(
                workspace_id=workspace_id,
                agent_id=a.agent_id or agent_id,
                step_run_id=step_run_id,
                call_id=call_id,
                request_id=request_id,
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
