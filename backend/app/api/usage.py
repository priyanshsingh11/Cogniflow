"""Usage & cost dashboard API (phase 8).

One endpoint aggregates what the raw tables already record:
- `llm_calls` — model attempts: tokens, latency, status, tier, model, agent.
- `tool_calls` — MCP invocations.
- `workflow_runs` / `step_runs` — run outcomes and step durations.

`call_id` groups the attempts of one gateway invocation, so the report can
speak in logical *calls* (and how often the router fell back) instead of raw
attempts. Costs are summed from `llm_calls.cost_usd` — $0 while only free
models are configured, but the field and aggregation are real.
"""

from datetime import UTC, datetime, time, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Date, case, cast, distinct, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, require_role
from app.db.postgres import get_pg
from app.models import Agent, LLMCall, Role, StepRun, ToolCall, Workflow, WorkflowRun
from app.schemas.usage import (
    AgentUsage,
    DayUsage,
    ModelUsage,
    RecentError,
    SlowStep,
    SlowWorkflow,
    TierUsage,
    UsageReport,
    UsageTotals,
)

router = APIRouter(prefix="/workspaces/{workspace_id}/usage", tags=["usage"])
require_viewer = require_role(Role.VIEWER)

_ERROR_STATUSES = ("error", "invalid_output")


@router.get("", response_model=UsageReport)
async def usage_report(
    days: int = Query(default=30, ge=1, le=90),
    ctx: TenantContext = Depends(require_viewer),
    session: AsyncSession = Depends(get_pg),
) -> UsageReport:
    ws = ctx.workspace.id
    today = datetime.now(UTC).date()
    start_day = today - timedelta(days=days - 1)
    since = datetime.combine(start_day, time.min, tzinfo=UTC)

    call_key = func.coalesce(LLMCall.call_id, LLMCall.id)

    # --- logical calls: one row per gateway invocation -------------------
    per_call = (
        select(
            call_key.label("k"),
            func.count().label("attempts"),
            func.bool_or(LLMCall.status == "success").label("ok"),
        )
        .where(LLMCall.workspace_id == ws, LLMCall.created_at >= since)
        .group_by(call_key)
        .subquery()
    )
    call_stats = (
        await session.execute(
            select(
                func.count(per_call.c.k),
                func.sum(case((per_call.c.ok.is_(False), 1), else_=0)),
                func.sum(case((per_call.c.attempts > 1, 1), else_=0)),
            )
        )
    ).one()
    total_calls = call_stats[0] or 0
    failed_calls = int(call_stats[1] or 0)
    fallback_calls = int(call_stats[2] or 0)

    # --- attempt-level totals --------------------------------------------
    totals_row = (
        await session.execute(
            select(
                func.count(LLMCall.id),
                func.coalesce(func.sum(LLMCall.prompt_tokens), 0),
                func.coalesce(func.sum(LLMCall.completion_tokens), 0),
                func.coalesce(func.sum(LLMCall.cost_usd), 0),
                func.coalesce(func.avg(LLMCall.latency_ms), 0.0),
                func.coalesce(
                    func.percentile_cont(0.95).within_group(LLMCall.latency_ms), 0.0
                ),
                func.coalesce(
                    func.sum(case((LLMCall.status.in_(_ERROR_STATUSES), 1), else_=0)), 0
                ),
            ).where(LLMCall.workspace_id == ws, LLMCall.created_at >= since)
        )
    ).one()
    attempts, prompt_tokens, completion_tokens, cost, avg_lat, p95_lat, error_attempts = (
        totals_row
    )

    # --- tool calls -------------------------------------------------------
    tool_row = (
        await session.execute(
            select(
                func.count(ToolCall.id),
                func.coalesce(
                    func.sum(case((ToolCall.status != "ok", 1), else_=0)), 0
                ),
            ).where(ToolCall.workspace_id == ws, ToolCall.created_at >= since)
        )
    ).one()

    # --- runs -------------------------------------------------------------
    run_rows = (
        await session.execute(
            select(WorkflowRun.status, func.count(WorkflowRun.id))
            .where(WorkflowRun.workspace_id == ws, WorkflowRun.created_at >= since)
            .group_by(WorkflowRun.status)
        )
    ).all()
    runs_by_status = dict(run_rows)
    runs = sum(runs_by_status.values())
    succeeded = runs_by_status.get("succeeded", 0)
    failed = runs_by_status.get("failed", 0)
    decided = succeeded + failed

    # --- breakdowns -------------------------------------------------------
    tier_rows = (
        await session.execute(
            select(
                LLMCall.tier,
                func.count(distinct(call_key)),
                func.count(LLMCall.id),
                func.coalesce(func.sum(LLMCall.prompt_tokens + LLMCall.completion_tokens), 0),
                func.coalesce(
                    func.sum(case((LLMCall.status.in_(_ERROR_STATUSES), 1), else_=0)), 0
                ),
                func.coalesce(func.avg(LLMCall.latency_ms), 0.0),
            )
            .where(LLMCall.workspace_id == ws, LLMCall.created_at >= since)
            .group_by(LLMCall.tier)
            .order_by(func.count(LLMCall.id).desc())
        )
    ).all()

    model_rows = (
        await session.execute(
            select(
                LLMCall.provider,
                LLMCall.model,
                func.count(LLMCall.id),
                func.coalesce(func.sum(LLMCall.prompt_tokens + LLMCall.completion_tokens), 0),
                func.coalesce(
                    func.sum(case((LLMCall.status.in_(_ERROR_STATUSES), 1), else_=0)), 0
                ),
                func.coalesce(func.avg(LLMCall.latency_ms), 0.0),
            )
            .where(LLMCall.workspace_id == ws, LLMCall.created_at >= since)
            .group_by(LLMCall.provider, LLMCall.model)
            .order_by(func.count(LLMCall.id).desc())
        )
    ).all()

    agent_rows = (
        await session.execute(
            select(
                LLMCall.agent_id,
                Agent.name,
                func.count(LLMCall.id),
                func.coalesce(func.sum(LLMCall.prompt_tokens + LLMCall.completion_tokens), 0),
                func.coalesce(
                    func.sum(case((LLMCall.status.in_(_ERROR_STATUSES), 1), else_=0)), 0
                ),
            )
            .outerjoin(Agent, Agent.id == LLMCall.agent_id)
            .where(LLMCall.workspace_id == ws, LLMCall.created_at >= since)
            .group_by(LLMCall.agent_id, Agent.name)
            .order_by(func.count(LLMCall.id).desc())
        )
    ).all()

    day_col = cast(LLMCall.created_at, Date).label("day")
    day_rows = (
        await session.execute(
            select(
                day_col,
                func.count(distinct(call_key)),
                func.count(LLMCall.id),
                func.coalesce(func.sum(LLMCall.prompt_tokens + LLMCall.completion_tokens), 0),
                func.coalesce(
                    func.sum(case((LLMCall.status.in_(_ERROR_STATUSES), 1), else_=0)), 0
                ),
                func.coalesce(func.avg(LLMCall.latency_ms), 0.0),
            )
            .where(LLMCall.workspace_id == ws, LLMCall.created_at >= since)
            .group_by(day_col)
            .order_by(day_col)
        )
    ).all()

    # --- slowest steps / workflows ---------------------------------------
    step_dur = extract("epoch", StepRun.finished_at - StepRun.started_at)
    slow_step_rows = (
        await session.execute(
            select(StepRun, Workflow.name, step_dur)
            .join(WorkflowRun, StepRun.workflow_run_id == WorkflowRun.id)
            .join(Workflow, WorkflowRun.workflow_id == Workflow.id)
            .where(
                WorkflowRun.workspace_id == ws,
                StepRun.created_at >= since,
                StepRun.started_at.is_not(None),
                StepRun.finished_at.is_not(None),
            )
            .order_by(step_dur.desc())
            .limit(10)
        )
    ).all()

    run_dur = extract("epoch", WorkflowRun.finished_at - WorkflowRun.started_at)
    slow_wf_rows = (
        await session.execute(
            select(
                Workflow.id,
                Workflow.name,
                func.count(WorkflowRun.id),
                func.avg(run_dur),
                func.max(run_dur),
            )
            .join(Workflow, WorkflowRun.workflow_id == Workflow.id)
            .where(
                WorkflowRun.workspace_id == ws,
                WorkflowRun.created_at >= since,
                WorkflowRun.started_at.is_not(None),
                WorkflowRun.finished_at.is_not(None),
            )
            .group_by(Workflow.id, Workflow.name)
            .order_by(func.avg(run_dur).desc())
            .limit(10)
        )
    ).all()

    # --- recent errors (merged, newest first) -----------------------------
    llm_error_rows = list(
        (
            await session.execute(
                select(LLMCall)
                .where(
                    LLMCall.workspace_id == ws,
                    LLMCall.status == "error",
                    LLMCall.created_at >= since,
                )
                .order_by(LLMCall.created_at.desc())
                .limit(10)
            )
        ).scalars()
    )
    run_error_rows = list(
        (
            await session.execute(
                select(WorkflowRun)
                .where(
                    WorkflowRun.workspace_id == ws,
                    WorkflowRun.status == "failed",
                    WorkflowRun.created_at >= since,
                )
                .order_by(WorkflowRun.created_at.desc())
                .limit(10)
            )
        ).scalars()
    )
    recent_errors = [
        RecentError(
            kind="llm_call",
            created_at=call.created_at,
            message=call.error_type or "Model call failed",
            entity_id=call.id,
            context={
                "provider": call.provider,
                "model": call.model,
                "tier": call.tier,
                "request_id": call.request_id,
            },
        )
        for call in llm_error_rows
    ] + [
        RecentError(
            kind="run",
            created_at=run.created_at,
            message=run.error or "Run failed",
            entity_id=run.id,
            context={"workflow_id": str(run.workflow_id)},
        )
        for run in run_error_rows
    ]
    recent_errors.sort(key=lambda e: e.created_at, reverse=True)
    recent_errors = recent_errors[:15]

    # --- zero-fill the daily series for the chart -------------------------
    by_day_map = {
        row[0]: row
        for row in day_rows
    }
    by_day: list[DayUsage] = []
    day = start_day
    while day <= today:
        row = by_day_map.get(day)
        by_day.append(
            DayUsage(
                day=day,
                calls=row[1] if row else 0,
                attempts=row[2] if row else 0,
                tokens=int(row[3]) if row else 0,
                errors=int(row[4]) if row else 0,
                avg_latency_ms=round(float(row[5]), 1) if row else 0.0,
            )
        )
        day += timedelta(days=1)

    return UsageReport(
        days=days,
        since=since,
        totals=UsageTotals(
            llm_calls=total_calls,
            llm_attempts=attempts,
            prompt_tokens=int(prompt_tokens),
            completion_tokens=int(completion_tokens),
            total_tokens=int(prompt_tokens) + int(completion_tokens),
            cost_usd=float(cost),
            failed_calls=failed_calls,
            fallback_calls=fallback_calls,
            fallback_rate=round(fallback_calls / total_calls, 4) if total_calls else 0.0,
            failure_rate=round(failed_calls / total_calls, 4) if total_calls else 0.0,
            avg_latency_ms=round(float(avg_lat), 1),
            p95_latency_ms=round(float(p95_lat), 1),
            tool_calls=tool_row[0] or 0,
            tool_call_errors=int(tool_row[1] or 0),
            runs=runs,
            runs_succeeded=succeeded,
            runs_failed=failed,
            run_success_rate=round(succeeded / decided, 4) if decided else 0.0,
        ),
        by_tier=[
            TierUsage(
                tier=tier,
                calls=calls,
                attempts=attempts_n,
                tokens=int(tokens),
                errors=int(errors),
                avg_latency_ms=round(float(lat), 1),
            )
            for tier, calls, attempts_n, tokens, errors, lat in tier_rows
        ],
        by_model=[
            ModelUsage(
                provider=provider,
                model=model,
                attempts=attempts_n,
                tokens=int(tokens),
                errors=int(errors),
                avg_latency_ms=round(float(lat), 1),
            )
            for provider, model, attempts_n, tokens, errors, lat in model_rows
        ],
        by_agent=[
            AgentUsage(
                agent_id=agent_id,
                agent_name=name,
                attempts=attempts_n,
                tokens=int(tokens),
                errors=int(errors),
            )
            for agent_id, name, attempts_n, tokens, errors in agent_rows
        ],
        by_day=by_day,
        slowest_steps=[
            SlowStep(
                step_run_id=sr.id,
                workflow_run_id=sr.workflow_run_id,
                workflow_name=wf_name,
                step_name=sr.step_name,
                status=sr.status,
                duration_ms=int(float(seconds) * 1000),
                finished_at=sr.finished_at,
            )
            for sr, wf_name, seconds in slow_step_rows
        ],
        slowest_workflows=[
            SlowWorkflow(
                workflow_id=wf_id,
                workflow_name=name,
                runs=count,
                avg_duration_ms=int(float(avg) * 1000),
                max_duration_ms=int(float(maximum) * 1000),
            )
            for wf_id, name, count, avg, maximum in slow_wf_rows
        ],
        recent_errors=recent_errors,
    )
