import logging
import uuid
from typing import Any

from app.chat.service import reap_stuck_messages as run_chat_reaper
from app.core.logging import reset_request_id, set_request_id
from app.rag.service import process_document as run_process_document
from app.workflows.executor import execute_run
from app.workflows.reaper import reap_stuck_runs as run_stuck_runs_reaper

logger = logging.getLogger(__name__)


def _begin_job(request_id: str | None):
    """Adopt the enqueuer's request id (or mint one for cron jobs) so every
    log line of this job carries it; returns the token to reset afterwards."""
    return set_request_id(request_id or uuid.uuid4().hex)


async def execute_workflow_run(
    ctx: dict[str, Any] | None, run_id: str, request_id: str | None = None
) -> dict[str, Any]:
    """Background task to execute a workflow run durably."""
    token = _begin_job(request_id)
    try:
        logger.info("Starting workflow run execution: %s", run_id)
        run_uuid = uuid.UUID(run_id)
        worker_id = ctx.get("job_id") if ctx else None
        run = await execute_run(run_uuid, worker_id=worker_id)
        return {"status": run.status, "run_id": str(run.id)}
    finally:
        reset_request_id(token)


async def process_document(
    ctx: dict[str, Any] | None, document_id: str, request_id: str | None = None
) -> None:
    """Moved from in-process BackgroundTasks to arq worker (Phase 5)."""
    token = _begin_job(request_id)
    try:
        logger.info("Processing document: %s", document_id)
        doc_uuid = uuid.UUID(document_id)
        await run_process_document(doc_uuid)
    finally:
        reset_request_id(token)


async def reap_stuck_messages(
    ctx: dict[str, Any] | None = None, request_id: str | None = None
) -> int:
    """Moved from in-process FastAPI loop to arq worker (Phase 5)."""
    token = _begin_job(request_id)
    try:
        logger.info("Running chat message reaper task")
        return await run_chat_reaper()
    finally:
        reset_request_id(token)


async def reap_stuck_runs(
    ctx: dict[str, Any] | None = None, request_id: str | None = None
) -> int:
    """Reaper for stuck workflow runs and expired step leases."""
    token = _begin_job(request_id)
    try:
        logger.info("Running workflow run lease reaper task")
        return await run_stuck_runs_reaper()
    finally:
        reset_request_id(token)
