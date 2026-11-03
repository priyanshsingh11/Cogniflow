"""`/metrics` — Prometheus text endpoint (phase 8 extra).

Global aggregates only (no tenant identifiers), so it stays open like
`/health`: process counters from `app.core.metrics`, live row counts from
Postgres, and the arq queue depth from Redis. One scrape = run success
rate, queue pressure and model attempt outcomes.
"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import metrics as process_metrics
from app.db.postgres import get_pg
from app.db.redis import redis
from app.models import LLMCall, WorkflowRun

router = APIRouter(tags=["metrics"])

_QUEUE_KEY = "arq:queue"


def _counter(name: str, help_text: str, samples: list[tuple[dict[str, str], float]]) -> list[str]:
    lines = [f"# HELP {name} {help_text}", f"# TYPE {name} counter"]
    for labels, value in samples:
        label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        lines.append(f"{name}{{{label_str}}} {value}" if label_str else f"{name} {value}")
    return lines


def _gauge(name: str, help_text: str, value: float) -> list[str]:
    return [f"# HELP {name} {help_text}", f"# TYPE {name} gauge", f"{name} {value}"]


@router.get("/metrics")
async def metrics(session: AsyncSession = Depends(get_pg)) -> Response:
    run_rows = (
        await session.execute(
            select(WorkflowRun.status, func.count(WorkflowRun.id)).group_by(WorkflowRun.status)
        )
    ).all()
    llm_rows = (
        await session.execute(
            select(LLMCall.status, func.count(LLMCall.id)).group_by(LLMCall.status)
        )
    ).all()

    succeeded = dict(run_rows).get("succeeded", 0)
    failed = dict(run_rows).get("failed", 0)
    decided = succeeded + failed

    try:
        queue_depth = await redis.zcard(_QUEUE_KEY)
    except Exception:
        queue_depth = -1  # Redis unreachable; the gauge says so explicitly

    extra: list[str] = []
    extra += _counter(
        "cogniflow_runs_total",
        "Workflow runs by status (all workspaces, Postgres rows).",
        [({"status": status}, count) for status, count in run_rows],
    )
    extra += _gauge(
        "cogniflow_run_success_ratio",
        "succeeded / (succeeded + failed) over all recorded runs.",
        round(succeeded / decided, 4) if decided else 0.0,
    )
    extra += _gauge(
        "cogniflow_queue_depth",
        "Jobs waiting in the arq queue (-1 if Redis is unreachable).",
        queue_depth,
    )
    extra += _counter(
        "cogniflow_llm_calls_total",
        "Model attempts by status (all workspaces, Postgres rows).",
        [({"status": status}, count) for status, count in llm_rows],
    )

    body = process_metrics.render(extra_lines=extra)
    return Response(content=body, media_type="text/plain; version=0.0.4; charset=utf-8")
