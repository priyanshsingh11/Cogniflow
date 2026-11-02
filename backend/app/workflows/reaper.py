import datetime
import logging

from sqlalchemy import select

from app.config import settings
from app.db.postgres import SessionLocal
from app.models.workflow import StepRun, WorkflowRun

logger = logging.getLogger(__name__)


async def reap_stuck_runs() -> int:
    """Find step runs and workflow runs with expired leases (e.g. crashed workers)

    and reset them to pending for retry or mark them failed if max attempts reached.
    """
    now = datetime.datetime.now(datetime.UTC)
    reaped_count = 0

    async with SessionLocal() as session:
        # Find step runs whose lease expired
        stmt = (
            select(StepRun, WorkflowRun)
            .join(WorkflowRun, StepRun.workflow_run_id == WorkflowRun.id)
            .where(
                StepRun.status == "running",
                StepRun.lease_expires_at.is_not(None),
                StepRun.lease_expires_at < now,
                WorkflowRun.status == "running",
            )
        )
        results = (await session.execute(stmt)).all()

        for step_run, workflow_run in results:
            reaped_count += 1
            if step_run.attempt < settings.workflow_reaper_max_attempts:
                logger.warning(
                    "Reaping stuck step_run %s (attempt %s/%s), resetting to pending",
                    step_run.id,
                    step_run.attempt,
                    settings.workflow_reaper_max_attempts,
                )
                step_run.attempt += 1
                step_run.status = "pending"
                step_run.lease_worker_id = None
                step_run.lease_expires_at = None
                workflow_run.status = "queued"

                # Re-enqueue
                from app.worker.queue import enqueue_job

                await enqueue_job("execute_workflow_run", str(workflow_run.id))
            else:
                logger.error(
                    "Step_run %s exceeded max attempts %s; marking run failed",
                    step_run.id,
                    settings.workflow_reaper_max_attempts,
                )
                step_run.status = "failed"
                step_run.error = "Worker lease expired; max retry attempts reached"
                step_run.finished_at = now
                step_run.lease_worker_id = None
                step_run.lease_expires_at = None

                workflow_run.status = "failed"
                workflow_run.error = f"Step '{step_run.step_name}' lease expired"
                workflow_run.finished_at = now

        await session.commit()

    return reaped_count
