import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    TenantContext,
    get_pg,
    require_admin,
    require_member,
    require_viewer,
)
from app.core.audit import record_audit
from app.models.workflow import Workflow, WorkflowStep, WorkflowVersion
from app.schemas.workflow import (
    WorkflowCreate,
    WorkflowOut,
    WorkflowStepOut,
    WorkflowUpdate,
    WorkflowVersionCreate,
    WorkflowVersionOut,
)

router = APIRouter(prefix="/workspaces/{workspace_id}/workflows", tags=["workflows"])


async def _load_workflow(
    session: AsyncSession,
    ctx: TenantContext,
    workflow_id: uuid.UUID,
) -> Workflow:
    wf = await session.get(Workflow, workflow_id)
    if wf is None or wf.workspace_id != ctx.workspace.id:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf


async def _load_version_out(
    session: AsyncSession,
    version: WorkflowVersion,
) -> WorkflowVersionOut:
    stmt = (
        select(WorkflowStep)
        .where(WorkflowStep.workflow_version_id == version.id)
        .order_by(WorkflowStep.position)
    )
    steps = list((await session.execute(stmt)).scalars().all())
    return WorkflowVersionOut(
        id=version.id,
        workflow_id=version.workflow_id,
        version=version.version,
        graph=version.graph or {},
        steps=[WorkflowStepOut.model_validate(s) for s in steps],
        created_at=version.created_at,
    )


async def _load_workflow_out(
    session: AsyncSession,
    wf: Workflow,
) -> WorkflowOut:
    current_ver_out: WorkflowVersionOut | None = None
    if wf.current_version_id is not None:
        ver = await session.get(WorkflowVersion, wf.current_version_id)
        if ver is not None:
            current_ver_out = await _load_version_out(session, ver)

    return WorkflowOut(
        id=wf.id,
        workspace_id=wf.workspace_id,
        name=wf.name,
        description=wf.description,
        current_version_id=wf.current_version_id,
        current_version=current_ver_out,
        created_at=wf.created_at,
    )


@router.post("", response_model=WorkflowOut, status_code=201)
async def create_workflow(
    payload: WorkflowCreate,
    ctx: TenantContext = Depends(require_member),
    session: AsyncSession = Depends(get_pg),
) -> WorkflowOut:
    wf = Workflow(
        workspace_id=ctx.workspace.id,
        name=payload.name,
        description=payload.description,
    )
    session.add(wf)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Workflow with name '{payload.name}' already exists in this workspace",
        ) from exc

    # Create initial version (v1)
    version = WorkflowVersion(
        workflow_id=wf.id,
        version=1,
        graph=payload.graph or {},
    )
    session.add(version)
    await session.flush()

    for idx, s in enumerate(payload.steps):
        step_row = WorkflowStep(
            workflow_version_id=version.id,
            name=s.name,
            position=s.position if s.position is not None else idx,
            type=s.type,
            agent_id=s.agent_id,
            config=s.config,
        )
        session.add(step_row)

    wf.current_version_id = version.id
    record_audit(
        session,
        action="workflow.created",
        actor_id=ctx.user.id,
        workspace_id=ctx.workspace.id,
        org_id=ctx.org.id,
        entity_type="workflow",
        entity_id=wf.id,
        metadata={"name": wf.name},
    )
    await session.commit()
    await session.refresh(wf)

    return await _load_workflow_out(session, wf)


@router.get("", response_model=list[WorkflowOut])
async def list_workflows(
    ctx: TenantContext = Depends(require_viewer),
    session: AsyncSession = Depends(get_pg),
) -> list[WorkflowOut]:
    stmt = (
        select(Workflow)
        .where(Workflow.workspace_id == ctx.workspace.id)
        .order_by(Workflow.created_at.desc())
    )
    workflows = list((await session.execute(stmt)).scalars().all())
    return [await _load_workflow_out(session, wf) for wf in workflows]


@router.get("/{workflow_id}", response_model=WorkflowOut)
async def get_workflow(
    workflow_id: uuid.UUID,
    ctx: TenantContext = Depends(require_viewer),
    session: AsyncSession = Depends(get_pg),
) -> WorkflowOut:
    wf = await _load_workflow(session, ctx, workflow_id)
    return await _load_workflow_out(session, wf)


@router.patch("/{workflow_id}", response_model=WorkflowOut)
async def update_workflow(
    workflow_id: uuid.UUID,
    payload: WorkflowUpdate,
    ctx: TenantContext = Depends(require_member),
    session: AsyncSession = Depends(get_pg),
) -> WorkflowOut:
    wf = await _load_workflow(session, ctx, workflow_id)
    changes: dict = {}
    if payload.name is not None:
        changes["name"] = payload.name
        wf.name = payload.name
    if payload.description is not None:
        changes["description"] = payload.description
        wf.description = payload.description
    if changes:
        record_audit(
            session,
            action="workflow.updated",
            actor_id=ctx.user.id,
            workspace_id=ctx.workspace.id,
            org_id=ctx.org.id,
            entity_type="workflow",
            entity_id=wf.id,
            metadata=changes,
        )

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Workflow with name '{payload.name}' already exists in this workspace",
        ) from exc

    return await _load_workflow_out(session, wf)


@router.delete("/{workflow_id}", status_code=204)
async def delete_workflow(
    workflow_id: uuid.UUID,
    ctx: TenantContext = Depends(require_admin),
    session: AsyncSession = Depends(get_pg),
) -> None:
    wf = await _load_workflow(session, ctx, workflow_id)
    record_audit(
        session,
        action="workflow.deleted",
        actor_id=ctx.user.id,
        workspace_id=ctx.workspace.id,
        org_id=ctx.org.id,
        entity_type="workflow",
        entity_id=wf.id,
        metadata={"name": wf.name},
    )
    await session.delete(wf)
    await session.commit()


# ------------------------------------------------------------------- versions


@router.post("/{workflow_id}/versions", response_model=WorkflowVersionOut, status_code=201)
async def create_version(
    workflow_id: uuid.UUID,
    payload: WorkflowVersionCreate,
    ctx: TenantContext = Depends(require_member),
    session: AsyncSession = Depends(get_pg),
) -> WorkflowVersionOut:
    wf = await _load_workflow(session, ctx, workflow_id)

    max_v_stmt = select(func.max(WorkflowVersion.version)).where(
        WorkflowVersion.workflow_id == wf.id
    )
    cur_max = (await session.execute(max_v_stmt)).scalar() or 0
    next_ver = cur_max + 1

    version = WorkflowVersion(
        workflow_id=wf.id,
        version=next_ver,
        graph=payload.graph or {},
    )
    session.add(version)
    await session.flush()

    for idx, s in enumerate(payload.steps):
        step_row = WorkflowStep(
            workflow_version_id=version.id,
            name=s.name,
            position=s.position if s.position is not None else idx,
            type=s.type,
            agent_id=s.agent_id,
            config=s.config,
        )
        session.add(step_row)

    wf.current_version_id = version.id
    record_audit(
        session,
        action="workflow.version_created",
        actor_id=ctx.user.id,
        workspace_id=ctx.workspace.id,
        org_id=ctx.org.id,
        entity_type="workflow",
        entity_id=wf.id,
        metadata={"workflow_name": wf.name, "version": next_ver, "steps": len(payload.steps)},
    )
    await session.commit()

    return await _load_version_out(session, version)


@router.get("/{workflow_id}/versions", response_model=list[WorkflowVersionOut])
async def list_versions(
    workflow_id: uuid.UUID,
    ctx: TenantContext = Depends(require_viewer),
    session: AsyncSession = Depends(get_pg),
) -> list[WorkflowVersionOut]:
    wf = await _load_workflow(session, ctx, workflow_id)
    stmt = (
        select(WorkflowVersion)
        .where(WorkflowVersion.workflow_id == wf.id)
        .order_by(WorkflowVersion.version.desc())
    )
    versions = list((await session.execute(stmt)).scalars().all())
    return [await _load_version_out(session, v) for v in versions]


@router.get("/{workflow_id}/versions/{version_num}", response_model=WorkflowVersionOut)
async def get_version(
    workflow_id: uuid.UUID,
    version_num: int,
    ctx: TenantContext = Depends(require_viewer),
    session: AsyncSession = Depends(get_pg),
) -> WorkflowVersionOut:
    wf = await _load_workflow(session, ctx, workflow_id)
    stmt = select(WorkflowVersion).where(
        WorkflowVersion.workflow_id == wf.id,
        WorkflowVersion.version == version_num,
    )
    ver = (await session.execute(stmt)).scalar_one_or_none()
    if ver is None:
        raise HTTPException(status_code=404, detail=f"Version {version_num} not found")
    return await _load_version_out(session, ver)
