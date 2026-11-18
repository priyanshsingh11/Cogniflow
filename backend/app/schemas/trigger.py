"""Schemas for workflow triggers (phase 10)."""

import datetime
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.workflows.triggers import validate_cron


class TriggerCreate(BaseModel):
    type: Literal["schedule", "webhook"]
    cron: str | None = Field(default=None, max_length=120)
    timezone: str = Field(default="UTC", max_length=64)
    input: dict[str, Any] = Field(default_factory=dict)  # default run input (schedules)
    enabled: bool = True

    @model_validator(mode="after")
    def _check(self) -> "TriggerCreate":
        if self.type == "schedule":
            if not self.cron:
                raise ValueError("schedule triggers need 'cron'")
            self.cron = " ".join(self.cron.split())
            if err := validate_cron(self.cron, self.timezone):
                raise ValueError(err)
        else:
            self.cron = None
            self.input = {}
        return self


class TriggerPatch(BaseModel):
    enabled: bool | None = None
    cron: str | None = Field(default=None, max_length=120)
    timezone: str | None = Field(default=None, max_length=64)
    input: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _something(self) -> "TriggerPatch":
        if all(v is None for v in (self.enabled, self.cron, self.timezone, self.input)):
            raise ValueError("nothing to update")
        if self.cron is not None:
            self.cron = " ".join(self.cron.split())
        return self


class TriggerOut(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    type: str
    enabled: bool
    cron: str | None = None
    timezone: str
    input: dict[str, Any] = Field(default_factory=dict)
    next_run_at: datetime.datetime | None = None
    last_run_at: datetime.datetime | None = None
    secret_prefix: str | None = None
    secret: str | None = None  # returned once, on create/rotate only
    webhook_path: str | None = None  # same: "/hooks/<secret>"
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class HookOut(BaseModel):
    run_id: uuid.UUID
    status: str
    duplicate: bool = False
