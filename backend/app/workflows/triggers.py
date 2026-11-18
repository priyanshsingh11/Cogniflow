"""Trigger plumbing shared by the API, the webhook endpoint and the worker (phase 10).

`launch_run` is the single place a trigger turns into a queued WorkflowRun;
idempotency keys make double fires (restarts, overlapping workers, webhook
retries) harmless.
"""

import datetime
import hashlib
import logging
import secrets
import uuid
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.db.postgres import SessionLocal
from app.models.trigger import WorkflowTrigger
from app.models.workflow import Workflow, WorkflowRun
from app.models.workspace import Workspace
from app.worker.queue import enqueue_job

logger = logging.getLogger(__name__)

MAX_BATCH = 100


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def new_secret() -> str:
    return secrets.token_urlsafe(32)


def validate_cron(expr: str, tz: str) -> str | None:
    """Return an error message, or None when the expression and zone are valid."""
    if len(expr.split()) != 5:
        return "cron must have exactly 5 fields (minute hour day month weekday)"
    if not croniter.is_valid(expr):
        return "invalid cron expression"
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        return f"unknown timezone '{tz}'"
    return None


def next_fire(expr: str, tz: str, after: datetime.datetime) -> datetime.datetime:
    """Next occurrence strictly after `after`, evaluated in `tz`, returned in UTC."""
    local = after.astimezone(ZoneInfo(tz))
    nxt = croniter(expr, local).get_next(datetime.datetime)
    return nxt.astimezone(datetime.UTC)


async def launch_run(
    session: AsyncSession,
    *,
    workflow: Workflow,
    trigger: WorkflowTrigger,
    run_input: dict[str, Any],
    idempotency_key: str | None,
) -> tuple[WorkflowRun, bool]:
    """Create + enqueue a run for `trigger`. Returns (run, created); an existing
    run with the same idempotency key is returned untouched (created=False)."""
    if workflow.current_version_id is None:
        raise ValueError("Workflow has no active version to run")

    if idempotency_key:
        existing = (
            await session.execute(
                select(WorkflowRun).where(
                    WorkflowRun.workspace_id == workflow.workspace_id,
                    WorkflowRun.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing, False

    run = WorkflowRun(
        workflow_id=workflow.id,
        workflow_version_id=workflow.current_version_id,
        workspace_id=workflow.workspace_id,
        triggered_by=None,
        trigger_id=trigger.id,
        status="queued",
        idempotency_key=idempotency_key,
        input=run_input,
    )
    session.add(run)
    try:
        await session.commit()
    except IntegrityError:  # lost a race on the idempotency key
        await session.rollback()
        existing = (
            await session.execute(
                select(WorkflowRun).where(
                    WorkflowRun.workspace_id == workflow.workspace_id,
                    WorkflowRun.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one()
        return existing, False
    await session.refresh(run)

    workspace = await session.get(Workspace, workflow.workspace_id)
    record_audit(
        session,
        action="run.triggered",
        workspace_id=workflow.workspace_id,
        org_id=workspace.org_id if workspace else None,
        entity_type="workflow_run",
        entity_id=run.id,
        metadata={
            "workflow_id": str(workflow.id),
            "trigger_id": str(trigger.id),
            "trigger_type": trigger.type,
            "idempotency_key": idempotency_key,
        },
    )
    await session.commit()

    job_id = await enqueue_job("execute_workflow_run", str(run.id))
    if job_id:
        run.queue_job_id = job_id
        await session.commit()
        await session.refresh(run)
    return run, True


async def fire_due_triggers(now: datetime.datetime | None = None) -> int:
    """Start every enabled schedule whose `next_run_at` has passed. Returns runs created.

    After downtime a schedule fires once (not once per missed tick) and then
    jumps to its next future occurrence. The key `schedule:<id>:<due time>`
    makes a repeat fire of the same tick a no-op.
    """
    now = now or datetime.datetime.now(datetime.UTC)
    async with SessionLocal() as session:
        ids = list(
            (
                await session.execute(
                    select(WorkflowTrigger.id)
                    .where(
                        WorkflowTrigger.type == "schedule",
                        WorkflowTrigger.enabled.is_(True),
                        WorkflowTrigger.next_run_at <= now,
                    )
                    .order_by(WorkflowTrigger.next_run_at)
                    .limit(MAX_BATCH)
                )
            ).scalars()
        )

    created = 0
    for trigger_id in ids:
        async with SessionLocal() as session:
            trigger = (
                await session.execute(
                    select(WorkflowTrigger)
                    .where(WorkflowTrigger.id == trigger_id)
                    .with_for_update(skip_locked=True)
                )
            ).scalar_one_or_none()
            if (
                trigger is None
                or not trigger.enabled
                or trigger.next_run_at is None
                or trigger.next_run_at > now
                or not trigger.cron
            ):
                continue
            due = trigger.next_run_at
            tid, cron, tz = trigger.id, trigger.cron, trigger.timezone
            workflow = await session.get(Workflow, trigger.workflow_id)
            try:
                if workflow is not None and workflow.current_version_id is not None:
                    _, made = await launch_run(
                        session,
                        workflow=workflow,
                        trigger=trigger,
                        run_input=dict(trigger.input or {}),
                        idempotency_key=f"schedule:{tid}:{due.isoformat()}",
                    )
                    created += int(made)
                else:
                    logger.warning("Schedule %s skipped: workflow missing or has no version", tid)
                trigger.last_run_at = now
                trigger.next_run_at = next_fire(cron, tz, now)
                await session.commit()
            except Exception:
                await session.rollback()
                logger.exception("Schedule %s failed to fire; will retry next minute", tid)
    return created


def new_trigger_id() -> uuid.UUID:  # small seam for tests
    return uuid.uuid4()
