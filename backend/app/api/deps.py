"""Auth and tenancy dependencies.

Every tenant-scoped route composes two checks:

1. ``require_workspace(workspace_id)`` — resolves the workspace from the path,
   loads the caller's membership in the owning org (404 if the workspace
   doesn't exist OR the caller isn't a member, so foreign workspaces are
   indistinguishable from nonexistent ones), and returns a ``TenantContext``
   carrying workspace, org, membership and role.

2. ``require_role(min_role)`` — a factory wrapping require_workspace with a
   privilege check (owner > admin > member > viewer).

Roles are decided by org membership; a workspace is always scoped to exactly
one org, so workspace access = org membership in the workspace's org.
"""

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.postgres import get_pg
from app.models import Membership, Organization, Role, User, Workspace

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class TenantContext:
    """Everything a tenant-scoped handler needs about 'where am I'."""

    user: User
    workspace: Workspace
    org: Organization
    membership: Membership
    role: Role

    def has_role(self, minimum: Role) -> bool:
        return Role.rank(self.role) >= Role.rank(minimum)


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_pg),
) -> User:
    if credentials is None:
        raise _unauthorized()
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise _unauthorized("Invalid or expired token")
    user = await session.get(User, user_id)
    if user is None:
        raise _unauthorized("User no longer exists")
    return user


async def get_membership(
    user: User, org_id: UUID, session: AsyncSession
) -> Membership | None:
    result = await session.execute(
        select(Membership).where(Membership.user_id == user.id, Membership.org_id == org_id)
    )
    return result.scalar_one_or_none()


async def require_workspace(
    workspace_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_pg),
) -> TenantContext:
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    membership = await get_membership(user, workspace.org_id, session)
    if membership is None:
        # Same 404 as a nonexistent workspace: don't leak existence of
        # workspaces in other tenants.
        raise HTTPException(status_code=404, detail="Workspace not found")

    org = await session.get(Organization, workspace.org_id)
    assert org is not None  # FK guarantees the org exists
    return TenantContext(
        user=user,
        workspace=workspace,
        org=org,
        membership=membership,
        role=Role(membership.role),
    )


def require_role(minimum: Role) -> Callable[..., TenantContext]:
    """Dependency factory: require_workspace + privilege >= `minimum`."""

    async def dependency(
        workspace_id: UUID,
        ctx: TenantContext = Depends(require_workspace),
    ) -> TenantContext:
        if not ctx.has_role(minimum):
            raise HTTPException(
                status_code=403,
                detail=f"Requires {minimum.value} role or higher (you are {ctx.role.value})",
            )
        return ctx

    return dependency
