import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_membership
from app.db.postgres import get_pg
from app.models import Membership, Organization, Role, User, Workspace
from app.schemas.org import MemberAdd, MemberOut, OrgCreate, OrgOut, WorkspaceCreate, WorkspaceOut

router = APIRouter(prefix="/organizations", tags=["organizations"])


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "org"
    return f"{base}-{uuid.uuid4().hex[:8]}"


async def _require_org_role(
    org_id: uuid.UUID, user: User, session: AsyncSession, minimum: Role
) -> Membership:
    """Org-level counterpart of require_workspace/require_role (path param org_id)."""
    membership = await get_membership(user, org_id, session)
    if membership is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if Role.rank(Role(membership.role)) < Role.rank(minimum):
        raise HTTPException(
            status_code=403,
            detail=f"Requires {minimum.value} role or higher",
        )
    return membership


@router.get("", response_model=list[OrgOut])
async def list_orgs(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_pg)
) -> list[OrgOut]:
    result = await session.execute(
        select(Organization, Membership.role)
        .join(Membership, Membership.org_id == Organization.id)
        .where(Membership.user_id == user.id)
        .order_by(Organization.created_at)
    )
    return [
        OrgOut(
            id=org.id,
            name=org.name,
            slug=org.slug,
            role=Role(role),
            created_at=org.created_at,
        )
        for org, role in result.all()
    ]


@router.post("", status_code=201, response_model=OrgOut)
async def create_org(
    payload: OrgCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_pg),
) -> OrgOut:
    org = Organization(name=payload.name, slug=_slugify(payload.name))
    session.add(org)
    await session.flush()
    session.add(Membership(user_id=user.id, org_id=org.id, role=Role.OWNER.value))
    await session.commit()
    return OrgOut(
        id=org.id, name=org.name, slug=org.slug, role=Role.OWNER, created_at=org.created_at
    )


@router.get("/{org_id}/members", response_model=list[MemberOut])
async def list_members(
    org_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_pg),
) -> list[MemberOut]:
    await _require_org_role(org_id, user, session, Role.VIEWER)
    result = await session.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.org_id == org_id)
        .order_by(Membership.created_at)
    )
    return [
        MemberOut(
            user_id=member_user.id,
            email=member_user.email,
            display_name=member_user.display_name,
            role=Role(membership.role),
            joined_at=membership.created_at,
        )
        for membership, member_user in result.all()
    ]


@router.post("/{org_id}/members", status_code=201, response_model=MemberOut)
async def add_member(
    org_id: uuid.UUID,
    payload: MemberAdd,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_pg),
) -> MemberOut:
    actor_membership = await _require_org_role(org_id, user, session, Role.ADMIN)
    actor_rank = Role.rank(Role(actor_membership.role))

    # Nobody may grant a role at or above their own rank: only owners can
    # grant admin, and nobody can grant owner through this endpoint.
    granted_rank = Role.rank(payload.role)
    if granted_rank >= actor_rank:
        raise HTTPException(status_code=403, detail="Cannot grant a role at or above your own")

    result = await session.execute(select(User).where(User.email == payload.email.lower()))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="No user with that email")

    existing = await get_membership(target, org_id, session)
    if existing is not None:
        raise HTTPException(status_code=409, detail="Already a member")

    membership = Membership(user_id=target.id, org_id=org_id, role=payload.role.value)
    session.add(membership)
    await session.commit()
    return MemberOut(
        user_id=target.id,
        email=target.email,
        display_name=target.display_name,
        role=payload.role,
        joined_at=membership.created_at,
    )


@router.get("/{org_id}/workspaces", response_model=list[WorkspaceOut])
async def list_workspaces(
    org_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_pg),
) -> list[WorkspaceOut]:
    membership = await _require_org_role(org_id, user, session, Role.VIEWER)
    result = await session.execute(
        select(Workspace).where(Workspace.org_id == org_id).order_by(Workspace.created_at)
    )
    role = Role(membership.role)
    return [
        WorkspaceOut(id=w.id, org_id=w.org_id, name=w.name, role=role, created_at=w.created_at)
        for w in result.scalars().all()
    ]


@router.post("/{org_id}/workspaces", status_code=201, response_model=WorkspaceOut)
async def create_workspace(
    org_id: uuid.UUID,
    payload: WorkspaceCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_pg),
) -> WorkspaceOut:
    membership = await _require_org_role(org_id, user, session, Role.MEMBER)
    workspace = Workspace(org_id=org_id, name=payload.name)
    session.add(workspace)
    await session.commit()
    return WorkspaceOut(
        id=workspace.id,
        org_id=workspace.org_id,
        name=workspace.name,
        role=Role(membership.role),
        created_at=workspace.created_at,
    )
