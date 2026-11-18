"""Workflow triggers: admin CRUD under a workflow, plus the public webhook
endpoint that starts a run (phase 10)."""

import datetime
import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, require_role
from app.config import settings
from app.core.audit import record_audit
from app.core.ratelimit import client_ip, enforce
from app.db.postgres import get_pg
from app.models import Role
from app.models.trigger import WorkflowTrigger
from app.models.workflow import Workflow
from app.schemas.trigger import HookOut, TriggerCreate, TriggerOut, TriggerPatch
from app.workflows.triggers import (
    hash_secret,
    launch_run,
    new_secret,
    next_fire,
    validate_cron,
)

router = APIRouter(
    prefix="/workspaces/{workspace_id}/workflows/{workflow_id}/triggers", tags=["triggers"]
)
hooks_router = APIRouter(tags=["triggers"])
require_viewer = require_role(Role.VIEWER)
require_admin = require_role(Role.ADMIN)

MAX_TRIGGERS_PER_WORKFLOW = 10
MAX_HOOK_BODY_BYTES = 64 * 1024


def _out(trigger: WorkflowTrigger, secret: str | None = None) -> TriggerOut:
    out = TriggerOut.model_validate(trigger)
    if secret:
        out.secret = secret
        out.webhook_path = f"/hooks/{secret}"
    return out


async def _workflow(session: AsyncSession, ctx: TenantContext, workflow_id: uuid.UUID) -> Workflow:
    wf = await session.get(Workflow, workflow_id)
    if wf is None or wf.workspace_id != ctx.workspace.id:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf


async def _trigger(
    session: AsyncSession, ctx: TenantContext, workflow_id: uuid.UUID, trigger_id: uuid.UUID
) -> WorkflowTrigger:
    trig = await session.get(WorkflowTrigger, trigger_id)
    if trig is None or trig.workflow_id != workflow_id or trig.workspace_id != ctx.workspace.id:
        raise HTTPException(status_code=404, detail="Trigger not found")
    return trig


def _audit(session, ctx, action, trig, extra=None):
    record_audit(
        session,
        action=action,
        actor_id=ctx.user.id,
        workspace_id=ctx.workspace.id,
        org_id=ctx.org.id,
        entity_type="workflow_trigger",
        entity_id=trig.id,
        metadata={"workflow_id": str(trig.workflow_id), "type": trig.type, **(extra or {})},
    )


@router.get("", response_model=list[TriggerOut])
async def list_triggers(
    workflow_id: uuid.UUID,
    ctx: TenantContext = Depends(require_viewer),
    session: AsyncSession = Depends(get_pg),
) -> list[TriggerOut]:
    await _workflow(session, ctx, workflow_id)
    rows = await session.execute(
        select(WorkflowTrigger)
        .where(WorkflowTrigger.workflow_id == workflow_id)
        .order_by(WorkflowTrigger.created_at)
    )
    return [_out(t) for t in rows.scalars()]


@router.post("", response_model=TriggerOut, status_code=201)
async def create_trigger(
    workflow_id: uuid.UUID,
    payload: TriggerCreate,
    ctx: TenantContext = Depends(require_admin),
    session: AsyncSession = Depends(get_pg),
) -> TriggerOut:
    await _workflow(session, ctx, workflow_id)
    count = (
        await session.execute(
            select(func.count(WorkflowTrigger.id)).where(WorkflowTrigger.workflow_id == workflow_id)
        )
    ).scalar_one()
    if count >= MAX_TRIGGERS_PER_WORKFLOW:
        raise HTTPException(
            status_code=409, detail=f"At most {MAX_TRIGGERS_PER_WORKFLOW} triggers per workflow"
        )

    trig = WorkflowTrigger(
        workspace_id=ctx.workspace.id,
        workflow_id=workflow_id,
        type=payload.type,
        enabled=payload.enabled,
        cron=payload.cron,
        timezone=payload.timezone,
        input=payload.input,
        created_by=ctx.user.id,
    )
    secret: str | None = None
    if payload.type == "schedule":
        trig.next_run_at = next_fire(payload.cron or "", payload.timezone, _now())
    else:
        secret = new_secret()
        trig.secret_hash = hash_secret(secret)
        trig.secret_prefix = secret[:6]
    session.add(trig)
    await session.flush()
    _audit(session, ctx, "trigger.created", trig, {"cron": trig.cron})
    await session.commit()
    await session.refresh(trig)
    return _out(trig, secret)


@router.patch("/{trigger_id}", response_model=TriggerOut)
async def update_trigger(
    workflow_id: uuid.UUID,
    trigger_id: uuid.UUID,
    payload: TriggerPatch,
    ctx: TenantContext = Depends(require_admin),
    session: AsyncSession = Depends(get_pg),
) -> TriggerOut:
    trig = await _trigger(session, ctx, workflow_id, trigger_id)
    if trig.type == "webhook" and (payload.cron or payload.timezone or payload.input is not None):
        raise HTTPException(status_code=422, detail="Only 'enabled' applies to webhook triggers")
    if payload.input is not None:
        trig.input = payload.input
    if payload.timezone is not None:
        trig.timezone = payload.timezone
    if payload.cron is not None:
        trig.cron = payload.cron
    if trig.type == "schedule":
        if err := validate_cron(trig.cron or "", trig.timezone):
            raise HTTPException(status_code=422, detail=err)
    if payload.enabled is not None:
        trig.enabled = payload.enabled
    if trig.type == "schedule" and (
        payload.cron is not None or payload.timezone is not None or payload.enabled
    ):
        # Re-arm from now: edits (and re-enabling) never fire a stale past tick.
        trig.next_run_at = next_fire(trig.cron or "", trig.timezone, _now())
    _audit(session, ctx, "trigger.updated", trig, payload.model_dump(exclude_unset=True))
    await session.commit()
    await session.refresh(trig)
    return _out(trig)


@router.post("/{trigger_id}/rotate", response_model=TriggerOut)
async def rotate_secret(
    workflow_id: uuid.UUID,
    trigger_id: uuid.UUID,
    ctx: TenantContext = Depends(require_admin),
    session: AsyncSession = Depends(get_pg),
) -> TriggerOut:
    trig = await _trigger(session, ctx, workflow_id, trigger_id)
    if trig.type != "webhook":
        raise HTTPException(status_code=422, detail="Only webhook triggers have a secret")
    secret = new_secret()
    trig.secret_hash = hash_secret(secret)
    trig.secret_prefix = secret[:6]
    _audit(session, ctx, "trigger.secret_rotated", trig)
    await session.commit()
    await session.refresh(trig)
    return _out(trig, secret)


@router.delete("/{trigger_id}", status_code=204)
async def delete_trigger(
    workflow_id: uuid.UUID,
    trigger_id: uuid.UUID,
    ctx: TenantContext = Depends(require_admin),
    session: AsyncSession = Depends(get_pg),
) -> None:
    trig = await _trigger(session, ctx, workflow_id, trigger_id)
    _audit(session, ctx, "trigger.deleted", trig)
    await session.delete(trig)
    await session.commit()


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


@hooks_router.post("/hooks/{token}", response_model=HookOut, status_code=202)
async def fire_webhook(
    token: str, request: Request, session: AsyncSession = Depends(get_pg)
) -> HookOut:
    """Public: the secret in the path is the credential. The JSON body becomes the
    run input (a non-object body is wrapped as {"payload": ...}). An optional
    `Idempotency-Key` header makes sender retries safe."""
    await enforce("hook_ip", client_ip(request), settings.rl_webhook_ip_per_min, 60)

    trig = (
        await session.execute(
            select(WorkflowTrigger).where(
                WorkflowTrigger.secret_hash == hash_secret(token),
                WorkflowTrigger.type == "webhook",
                WorkflowTrigger.enabled.is_(True),
            )
        )
    ).scalar_one_or_none()
    if trig is None:
        raise HTTPException(status_code=404, detail="Unknown webhook")
    await enforce("webhook", str(trig.id), settings.rl_webhook_per_min, 60)

    raw = await request.body()
    if len(raw) > MAX_HOOK_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Body too large (64 KB max)")
    run_input: dict[str, Any] = {}
    if raw.strip():
        try:
            body = json.loads(raw)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Body must be valid JSON") from exc
        run_input = body if isinstance(body, dict) else {"payload": body}

    wf = await session.get(Workflow, trig.workflow_id)
    if wf is None or wf.current_version_id is None:
        raise HTTPException(status_code=409, detail="Workflow has no active version to run")

    sender_key = request.headers.get("idempotency-key")
    key = f"webhook:{trig.id}:{sender_key[:200]}" if sender_key else None
    run, created = await launch_run(
        session, workflow=wf, trigger=trig, run_input=run_input, idempotency_key=key
    )
    trig.last_run_at = _now()
    await session.commit()
    return HookOut(run_id=run.id, status=run.status, duplicate=not created)
