"""Workspace-scoped routes — the tenant-isolation pattern all later phases reuse.

Handlers never look up the workspace id themselves; they receive a
TenantContext from require_workspace / require_role, which guarantees the
caller is a member of the owning org (or gets a 404) and, where needed,
holds at least the minimum role (or gets a 403).
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, require_role, require_workspace
from app.core.audit import record_audit
from app.db.postgres import get_pg
from app.models import Role
from app.schemas.org import WorkspaceOut

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

# Module-level singletons keep B008 quiet and make route signatures clean.
require_member = require_role(Role.MEMBER)
require_admin = require_role(Role.ADMIN)


class WorkspaceRename(BaseModel):
    name: str = Field(min_length=1, max_length=255)


@router.get("/{workspace_id}", response_model=WorkspaceOut)
async def get_workspace(ctx: TenantContext = Depends(require_workspace)) -> WorkspaceOut:
    """Any member of the owning org can read a workspace; returns caller's role."""
    return WorkspaceOut(
        id=ctx.workspace.id,
        org_id=ctx.workspace.org_id,
        name=ctx.workspace.name,
        role=ctx.role,
        created_at=ctx.workspace.created_at,
    )


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(
    ctx: TenantContext = Depends(require_admin),
    session: AsyncSession = Depends(get_pg),
) -> None:
    """Admin+ of the owning org may delete a workspace."""
    # Audit first: workspace_id becomes NULL on delete (SET NULL), the org
    # link and metadata keep the event visible and attributable. Flush the
    # row before the DELETE so the insert never races the FK constraint.
    record_audit(
        session,
        action="workspace.deleted",
        actor_id=ctx.user.id,
        workspace_id=ctx.workspace.id,
        org_id=ctx.org.id,
        entity_type="workspace",
        entity_id=ctx.workspace.id,
        metadata={"name": ctx.workspace.name, "workspace_id": str(ctx.workspace.id)},
    )
    await session.flush()
    await session.delete(ctx.workspace)
    await session.commit()


@router.post("/{workspace_id}/rename", response_model=WorkspaceOut)
async def rename_workspace(
    payload: WorkspaceRename,
    ctx: TenantContext = Depends(require_member),
    session: AsyncSession = Depends(get_pg),
) -> WorkspaceOut:
    """Member+ may rename; viewers get 403. Demonstrates require_role(MEMBER)."""
    old_name = ctx.workspace.name
    ctx.workspace.name = payload.name.strip()
    record_audit(
        session,
        action="workspace.renamed",
        actor_id=ctx.user.id,
        workspace_id=ctx.workspace.id,
        org_id=ctx.org.id,
        entity_type="workspace",
        entity_id=ctx.workspace.id,
        metadata={"from": old_name, "to": ctx.workspace.name},
    )
    await session.commit()
    return WorkspaceOut(
        id=ctx.workspace.id,
        org_id=ctx.workspace.org_id,
        name=ctx.workspace.name,
        role=ctx.role,
        created_at=ctx.workspace.created_at,
    )
