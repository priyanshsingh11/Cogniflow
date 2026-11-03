import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.ratelimit import limit_login, limit_signup
from app.core.audit import record_audit
from app.core.security import create_access_token, hash_password, verify_password
from app.db.postgres import get_pg
from app.models import Membership, Organization, Role, User, Workspace
from app.schemas.auth import LoginRequest, SignupRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "org"
    return f"{base}-{uuid.uuid4().hex[:8]}"


@router.post("/signup", status_code=201, response_model=TokenResponse)
async def signup(
    payload: SignupRequest,
    _rate_limit: None = Depends(limit_signup),
    session: AsyncSession = Depends(get_pg),
) -> TokenResponse:
    """Create user + personal org + 'Default' workspace; owner membership."""
    existing = await session.execute(select(User).where(User.email == payload.email.lower()))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
    )
    session.add(user)
    await session.flush()  # assign user.id

    org = Organization(name=f"{payload.display_name}'s Org", slug=_slugify(payload.display_name))
    session.add(org)
    await session.flush()

    session.add(Membership(user_id=user.id, org_id=org.id, role=Role.OWNER.value))
    session.add(Workspace(org_id=org.id, name="Default"))
    record_audit(
        session,
        action="auth.signup",
        actor_id=user.id,
        org_id=org.id,
        entity_type="user",
        entity_id=user.id,
        metadata={"email": user.email},
    )
    await session.commit()

    return TokenResponse(
        access_token=create_access_token(user.id), user=UserOut.model_validate(user)
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    _rate_limit: None = Depends(limit_login),
    session: AsyncSession = Depends(get_pg),
) -> TokenResponse:
    email = payload.email.lower()
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        # Failed attempts are audited too (brute-force visibility). For an
        # unknown email there is no actor, so the row stays out of org views.
        record_audit(
            session,
            action="auth.login_failed",
            actor_id=user.id if user is not None else None,
            entity_type="user",
            entity_id=user.id if user is not None else None,
            metadata={"email": email},
        )
        await session.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password")

    record_audit(
        session,
        action="auth.login",
        actor_id=user.id,
        entity_type="user",
        entity_id=user.id,
        metadata={"email": user.email},
    )
    await session.commit()
    return TokenResponse(
        access_token=create_access_token(user.id), user=UserOut.model_validate(user)
    )


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)
