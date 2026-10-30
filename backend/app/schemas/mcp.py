"""Schemas for MCP servers, tools, discovery and invocation (phase 4)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

_NAME_PATTERN = r"^[a-zA-Z0-9_\- ]+$"


class ServerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120, pattern=_NAME_PATTERN)
    transport: Literal["stdio", "http"]
    command: str | None = None  # stdio: executable
    args: list[str] | None = Field(default=None, max_length=64)  # stdio: argv
    url: str | None = None  # http: endpoint

    @model_validator(mode="after")
    def _check_config(self) -> "ServerCreate":
        if self.transport == "stdio":
            if not (self.command and self.command.strip()):
                raise ValueError("stdio servers need 'command'")
            self.url = None
        else:
            if not self.url or not self.url.startswith(("http://", "https://")):
                raise ValueError("http servers need a valid 'url' starting with http(s)://")
            self.command = None
            self.args = None
        return self


class ServerPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120, pattern=_NAME_PATTERN)
    command: str | None = None
    args: list[str] | None = Field(default=None, max_length=64)
    url: str | None = None

    @model_validator(mode="after")
    def _something_to_update(self) -> "ServerPatch":
        if all(v is None for v in (self.name, self.command, self.args, self.url)):
            raise ValueError("nothing to update")
        return self


class ServerOut(BaseModel):
    id: uuid.UUID
    name: str
    transport: str
    url_or_command: str
    args: list[str] | None = None
    status: str  # registered | connected | error
    last_error: str | None = None
    created_at: datetime


class ToolOut(BaseModel):
    id: uuid.UUID
    server_id: uuid.UUID = Field(validation_alias="mcp_server_id")
    server_name: str
    name: str
    description: str | None = None
    input_schema: dict = Field(default_factory=dict)
    approved: bool
    requires_approval: bool
    active: bool

    @classmethod
    def from_row(cls, tool, server_name: str) -> "ToolOut":
        return cls(
            id=tool.id,
            mcp_server_id=tool.mcp_server_id,
            server_name=server_name,
            name=tool.name,
            description=tool.description,
            input_schema=tool.input_schema or {},
            approved=tool.approved,
            requires_approval=tool.requires_approval,
            active=tool.active,
        )


class ToolPatch(BaseModel):
    approved: bool | None = None
    requires_approval: bool | None = None

    @model_validator(mode="after")
    def _something_to_update(self) -> "ToolPatch":
        if self.approved is None and self.requires_approval is None:
            raise ValueError("nothing to update")
        return self


class DiscoverOut(BaseModel):
    server_id: uuid.UUID
    status: str  # connected
    tools: list[ToolOut]


class InvokeIn(BaseModel):
    arguments: dict = Field(default_factory=dict)


class InvokeOut(BaseModel):
    tool_call_id: uuid.UUID
    content: str
    is_error: bool
    latency_ms: int
    status: str  # ok | error (tool-level failure is a 200 + status=error)


class ToolCallOut(BaseModel):
    id: uuid.UUID
    tool_id: uuid.UUID = Field(validation_alias="mcp_tool_id")
    tool_name: str
    invoked_by: str  # api | agent | workflow
    agent_id: uuid.UUID | None = None
    arguments: dict | None = None
    result: dict | None = None
    status: str  # ok | error | invalid
    latency_ms: int
    created_at: datetime

    @classmethod
    def from_row(cls, call, tool_name: str) -> "ToolCallOut":
        return cls(
            id=call.id,
            mcp_tool_id=call.mcp_tool_id,
            tool_name=tool_name,
            invoked_by=call.invoked_by,
            agent_id=call.agent_id,
            arguments=call.arguments,
            result=call.result,
            status=call.status,
            latency_ms=call.latency_ms,
            created_at=call.created_at,
        )
