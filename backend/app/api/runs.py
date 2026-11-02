import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    TenantContext,
    get_pg,
    require_member,
    require_viewer,
)
from app.models.llm_call import LLMCall
from app.models.mcp import ToolCall
from app.models.workflow import StepRun, Workflow, WorkflowRun
from app.schemas.workflow import RunTriggerIn, StepRunOut, WorkflowRunOut
from app.worker.queue import enqueue_job

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["runs"])


async def _load_run_out(session: AsyncSession, run: WorkflowRun) -> WorkflowRunOut:
    stmt = select(StepRun).where(StepRun.workflow_run_id == run.id).order_by(StepRun.created_at)
    step_runs = list((await session.execute(stmt)).scalars().all())

    step_runs_out: list[StepRunOut] = []
    for sr in step_runs:
        llm_count_stmt = select(func.count(LLMCall.id)).where(LLMCall.step_run_id == sr.id)
        llm_count = (await session.execute(llm_count_stmt)).scalar() or 0

        tool_count_stmt = select(func.count(ToolCall.id)).where(ToolCall.step_run_id == sr.id)
        tool_count = (await session.execute(tool_count_stmt)).scalar() or 0

        step_runs_out.append(
            StepRunOut(
                id=sr.id,
                workflow_run_id=sr.workflow_run_id,
                workflow_step_id=sr.workflow_step_id,
                step_name=sr.step_name,
                attempt=sr.attempt,
                status=sr.status,
                idempotency_key=sr.idempotency_key,
                input=sr.input,
                output=sr.output,
                error=sr.error,
                started_at=sr.started_at,
                finished_at=sr.finished_at,
                created_at=sr.created_at,
                llm_calls_count=llm_count,
                tool_calls_count=tool_count,
            )
        )

    return WorkflowRunOut(
        id=run.id,
        workflow_id=run.workflow_id,
        workflow_version_id=run.workflow_version_id,
        workspace_id=run.workspace_id,
        conversation_id=run.conversation_id,
        triggered_by=run.triggered_by,
        status=run.status,
        idempotency_key=run.idempotency_key,
        queue_job_id=run.queue_job_id,
        input=run.input or {},
        output=run.output,
        error=run.error,
        started_at=run.started_at,
        finished_at=run.finished_at,
        created_at=run.created_at,
        step_runs=step_runs_out,
    )


@router.post(
    "/workflows/{workflow_id}/runs",
    response_model=WorkflowRunOut,
    status_code=201,
)
async def trigger_workflow_run(
    workflow_id: uuid.UUID,
    payload: RunTriggerIn,
    ctx: TenantContext = Depends(require_member),
    session: AsyncSession = Depends(get_pg),
) -> WorkflowRunOut:
    wf = await session.get(Workflow, workflow_id)
    if wf is None or wf.workspace_id != ctx.workspace.id:
        raise HTTPException(status_code=404, detail="Workflow not found")

    if wf.current_version_id is None:
        raise HTTPException(status_code=400, detail="Workflow has no active version to run")

    # Idempotency check: if an idempotency key was provided and already exists, return existing run
    if payload.idempotency_key:
        existing_stmt = select(WorkflowRun).where(
            WorkflowRun.workspace_id == ctx.workspace.id,
            WorkflowRun.idempotency_key == payload.idempotency_key,
        )
        existing_run = (await session.execute(existing_stmt)).scalar_one_or_none()
        if existing_run is not None:
            return await _load_run_out(session, existing_run)

    run = WorkflowRun(
        workflow_id=wf.id,
        workflow_version_id=wf.current_version_id,
        workspace_id=ctx.workspace.id,
        triggered_by=ctx.user.id if ctx.user else None,
        status="queued",
        idempotency_key=payload.idempotency_key,
        input=payload.input,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)

    job_id = await enqueue_job("execute_workflow_run", str(run.id))
    if job_id:
        run.queue_job_id = job_id
        await session.commit()
        await session.refresh(run)

    return await _load_run_out(session, run)


@router.get(
    "/workflows/{workflow_id}/runs",
    response_model=list[WorkflowRunOut],
)
async def list_workflow_runs(
    workflow_id: uuid.UUID,
    ctx: TenantContext = Depends(require_viewer),
    session: AsyncSession = Depends(get_pg),
) -> list[WorkflowRunOut]:
    wf = await session.get(Workflow, workflow_id)
    if wf is None or wf.workspace_id != ctx.workspace.id:
        raise HTTPException(status_code=404, detail="Workflow not found")

    stmt = (
        select(WorkflowRun)
        .where(
            WorkflowRun.workspace_id == ctx.workspace.id,
            WorkflowRun.workflow_id == workflow_id,
        )
        .order_by(WorkflowRun.created_at.desc())
    )
    runs = list((await session.execute(stmt)).scalars().all())
    return [await _load_run_out(session, r) for r in runs]


@router.get("/runs", response_model=list[WorkflowRunOut])
async def list_workspace_runs(
    limit: int = Query(default=50, ge=1, le=100),
    status: str | None = Query(default=None),
    ctx: TenantContext = Depends(require_viewer),
    session: AsyncSession = Depends(get_pg),
) -> list[WorkflowRunOut]:
    stmt = (
        select(WorkflowRun)
        .where(WorkflowRun.workspace_id == ctx.workspace.id)
        .order_by(WorkflowRun.created_at.desc())
        .limit(limit)
    )
    if status is not None:
        stmt = stmt.where(WorkflowRun.status == status)

    runs = list((await session.execute(stmt)).scalars().all())
    return [await _load_run_out(session, r) for r in runs]


@router.get("/runs/{run_id}", response_model=WorkflowRunOut)
async def get_run_details(
    run_id: uuid.UUID,
    ctx: TenantContext = Depends(require_viewer),
    session: AsyncSession = Depends(get_pg),
) -> WorkflowRunOut:
    run = await session.get(WorkflowRun, run_id)
    if run is None or run.workspace_id != ctx.workspace.id:
        raise HTTPException(status_code=404, detail="Run not found")
    return await _load_run_out(session, run)


@router.post("/runs/{run_id}/cancel", response_model=WorkflowRunOut)
async def cancel_run(
    run_id: uuid.UUID,
    ctx: TenantContext = Depends(require_member),
    session: AsyncSession = Depends(get_pg),
) -> WorkflowRunOut:
    run = await session.get(WorkflowRun, run_id)
    if run is None or run.workspace_id != ctx.workspace.id:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.status in ("queued", "running", "waiting_approval"):
        run.status = "cancelled"
        run.finished_at = datetime.datetime.now(datetime.UTC)
        await session.commit()
        await session.refresh(run)

    return await _load_run_out(session, run)
