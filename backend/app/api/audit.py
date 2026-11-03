"""Audit log read API (phase 8): admins answer "who did what, when".

Two scopes:
- workspace: every action recorded against one workspace (workflow edits,
  runs, approvals, MCP changes, document deletes, workspace renames...).
- organization: org-level actions (member additions) plus the sign-in
  history of the org's members — account events carry no workspace.

Writes happen next to the change they describe (``app.core.audit``).
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, get_current_user, require_role
from app.db.postgres import get_pg
from app.models import AuditLog, Membership, Role, User
from app.schemas.audit import AuditLogOut

router = APIRouter(tags=["audit"])
require_workspace_admin = require_role(Role.ADMIN)


def _out(row: AuditLog, actor_email: str | None) -> AuditLogOut:
    return AuditLogOut(
        id=row.id,
        action=row.action,
        actor_id=row.actor_id,
        actor_email=actor_email,
        workspace_id=row.workspace_id,
        org_id=row.org_id,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        metadata=row.metadata_json or {},
        created_at=row.created_at,
    )


@router.get("/workspaces/{workspace_id}/audit-logs", response_model=list[AuditLogOut])
async def list_workspace_audit_logs(
    action: str | None = Query(default=None, description="Exact action, e.g. workflow.updated"),
    actor_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx: TenantContext = Depends(require_workspace_admin),
    session: AsyncSession = Depends(get_pg),
) -> list[AuditLogOut]:
    stmt = (
        select(AuditLog, User.email)
        .outerjoin(User, User.id == AuditLog.actor_id)
        .where(AuditLog.workspace_id == ctx.workspace.id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if actor_id:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    rows = (await session.execute(stmt)).all()
    return [_out(row, email) for row, email in rows]


@router.get("/organizations/{org_id}/audit-logs", response_model=list[AuditLogOut])
async def list_org_audit_logs(
    org_id: uuid.UUID,
    action: str | None = Query(default=None),
    scope: str = Query(
        default="all",
        description=(
            "'all' = org + workspace + member sign-ins; "
            "'account' = no workspace (sign-ins, member changes)"
        ),
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_pg),
) -> list[AuditLogOut]:
    from app.api.organizations import _require_org_role

    await _require_org_role(org_id, user, session, Role.ADMIN)

    member_ids = select(Membership.user_id).where(Membership.org_id == org_id)
    org_scope = or_(
        AuditLog.org_id == org_id,
        # Account events (sign-ins) have no org: show the ones by
        # this org's members.
        and_(
            AuditLog.workspace_id.is_(None),
            AuditLog.org_id.is_(None),
            AuditLog.actor_id.in_(member_ids),
        ),
    )
    if scope == "account":
        org_scope = and_(AuditLog.workspace_id.is_(None), org_scope)
    stmt = (
        select(AuditLog, User.email)
        .outerjoin(User, User.id == AuditLog.actor_id)
        .where(org_scope)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if action:
        stmt = stmt.where(AuditLog.action == action)
    rows = (await session.execute(stmt)).all()
    return [_out(row, email) for row, email in rows]
