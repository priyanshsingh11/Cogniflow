import logging
import uuid
from typing import Any

from app.chat.service import reap_stuck_messages as run_chat_reaper
from app.rag.service import process_document as run_process_document
from app.workflows.executor import execute_run
from app.workflows.reaper import reap_stuck_runs as run_stuck_runs_reaper

logger = logging.getLogger(__name__)


async def execute_workflow_run(ctx: dict[str, Any] | None, run_id: str) -> dict[str, Any]:
    """Background task to execute a workflow run durably."""
    logger.info("Starting workflow run execution: %s", run_id)
    run_uuid = uuid.UUID(run_id)
    worker_id = ctx.get("job_id") if ctx else None
    run = await execute_run(run_uuid, worker_id=worker_id)
    return {"status": run.status, "run_id": str(run.id)}


async def process_document(ctx: dict[str, Any] | None, document_id: str) -> None:
    """Moved from in-process BackgroundTasks to arq worker (Phase 5)."""
    logger.info("Processing document: %s", document_id)
    doc_uuid = uuid.UUID(document_id)
    await run_process_document(doc_uuid)


async def reap_stuck_messages(ctx: dict[str, Any] | None = None) -> int:
    """Moved from in-process FastAPI loop to arq worker (Phase 5)."""
    logger.info("Running chat message reaper task")
    return await run_chat_reaper()


async def reap_stuck_runs(ctx: dict[str, Any] | None = None) -> int:
    """Reaper for stuck workflow runs and expired step leases."""
    logger.info("Running workflow run lease reaper task")
    return await run_stuck_runs_reaper()

