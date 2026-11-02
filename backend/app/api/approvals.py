import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    TenantContext,
    get_pg,
    require_member,
    require_viewer,
)
from app.models.workflow import Approval, StepRun, WorkflowRun
from app.schemas.approval import ApprovalDecideIn, ApprovalOut
from app.worker.queue import enqueue_job

router = APIRouter(prefix="/workspaces/{workspace_id}/approvals", tags=["approvals"])


@router.get("", response_model=list[ApprovalOut])
async def list_approvals(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    ctx: TenantContext = Depends(require_viewer),
    session: AsyncSession = Depends(get_pg),
) -> list[ApprovalOut]:
    stmt = (
        select(Approval)
        .where(Approval.workspace_id == ctx.workspace.id)
        .order_by(Approval.requested_at.desc())
        .limit(limit)
    )
    if status is not None:
        stmt = stmt.where(Approval.status == status)

    approvals = list((await session.execute(stmt)).scalars().all())
    return [ApprovalOut.model_validate(a) for a in approvals]


@router.get("/{approval_id}", response_model=ApprovalOut)
async def get_approval(
    approval_id: uuid.UUID,
    ctx: TenantContext = Depends(require_viewer),
    session: AsyncSession = Depends(get_pg),
) -> ApprovalOut:
    appr = await session.get(Approval, approval_id)
    if appr is None or appr.workspace_id != ctx.workspace.id:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return ApprovalOut.model_validate(appr)


@router.post("/{approval_id}/decide", response_model=ApprovalOut)
async def decide_approval(
    approval_id: uuid.UUID,
    payload: ApprovalDecideIn,
    ctx: TenantContext = Depends(require_member),
    session: AsyncSession = Depends(get_pg),
) -> ApprovalOut:
    appr = await session.get(Approval, approval_id)
    if appr is None or appr.workspace_id != ctx.workspace.id:
        raise HTTPException(status_code=404, detail="Approval request not found")

    if appr.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Approval has already been decided with status '{appr.status}'",
        )

    now = datetime.datetime.now(datetime.UTC)
    appr.status = "approved" if payload.action == "approve" else "rejected"
    appr.decided_by = ctx.user.id if ctx.user else None
    appr.decided_at = now
    appr.reason = payload.reason

    if payload.action == "approve":
        if appr.workflow_run_id and appr.step_run_id:
            step_run = await session.get(StepRun, appr.step_run_id)
            wf_run = await session.get(WorkflowRun, appr.workflow_run_id)

            if step_run and step_run.status == "waiting_approval":
                step_run.status = "pending"
            if wf_run and wf_run.status == "waiting_approval":
                wf_run.status = "queued"

            await session.commit()
            await session.refresh(appr)

            # Resume the workflow run via the worker queue
            if wf_run:
                await enqueue_job("execute_workflow_run", str(wf_run.id))
        else:
            await session.commit()
            await session.refresh(appr)

    else:  # reject
        if appr.workflow_run_id and appr.step_run_id:
            step_run = await session.get(StepRun, appr.step_run_id)
            wf_run = await session.get(WorkflowRun, appr.workflow_run_id)

            if step_run:
                step_run.status = "failed"
                step_run.error = f"Approval rejected: {payload.reason or 'No reason provided'}"
                step_run.finished_at = now
            if wf_run:
                st_name = step_run.step_name if step_run else "unknown"
                wf_run.status = "failed"
                wf_run.error = f"Step '{st_name}' approval rejected"
                wf_run.finished_at = now

        await session.commit()
        await session.refresh(appr)

    return ApprovalOut.model_validate(appr)
