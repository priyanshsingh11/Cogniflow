import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import Role


class OrgCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class OrgOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    role: Role | None = None  # caller's role, filled when listing own orgs
    created_at: datetime


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class WorkspaceOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    role: Role | None = None  # caller's role in the owning org
    created_at: datetime


class MemberAdd(BaseModel):
    email: EmailStr
    role: Role = Role.MEMBER


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: EmailStr
    display_name: str
    role: Role
    joined_at: datetime
