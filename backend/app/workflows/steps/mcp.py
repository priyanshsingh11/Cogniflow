import uuid

from sqlalchemy import select

from app.mcp import service as mcp_service
from app.models.mcp import McpServer, McpTool
from app.models.workflow import Approval
from app.workflows.steps.base import StepExecutionContext, StepResult
from app.workflows.template import render_template


async def execute_mcp_step(ctx: StepExecutionContext) -> StepResult:
    config = ctx.step_config
    tool_id_raw = config.get("tool_id")
    tool_name = config.get("tool_name")
    raw_arguments = config.get("arguments", {})

    rendered_arguments = render_template(raw_arguments, ctx.context)
    if not isinstance(rendered_arguments, dict):
        rendered_arguments = {}

    # 1. Resolve tool
    tool: McpTool | None = None
    if tool_id_raw:
        tid = uuid.UUID(str(tool_id_raw))
        pair = await mcp_service.get_tool(ctx.session, ctx.workspace_id, tid)
        if pair:
            tool, _ = pair
    elif tool_name:
        # Search by tool name in workspace
        stmt = (
            select(McpTool)
            .join(McpServer, McpTool.mcp_server_id == McpServer.id)
            .where(
                McpServer.workspace_id == ctx.workspace_id,
                McpTool.name == str(tool_name),
                McpTool.active.is_(True),
            )
        )
        res = await ctx.session.execute(stmt)
        tool = res.scalar_one_or_none()

    if tool is None:
        raise ValueError(f"MCP tool not found: id={tool_id_raw}, name={tool_name}")

    # 2. Check human approval requirement
    if tool.requires_approval or config.get("require_approval", False):
        # Check if already approved for this step_run
        stmt = select(Approval).where(
            Approval.step_run_id == ctx.step_run_id,
            Approval.status == "approved",
        )
        appr_res = await ctx.session.execute(stmt)
        approval_row = appr_res.scalar_one_or_none()

        if approval_row is None:
            # Need human approval
            return StepResult(
                status="waiting_approval",
                output=None,
                approval_details={
                    "tool_id": str(tool.id),
                    "tool_name": tool.name,
                    "arguments": rendered_arguments,
                    "description": f"Human approval required to run tool '{tool.name}'",
                },
            )

        # Approved: execute with approval bypass
        outcome = await mcp_service.invoke_tool(
            ctx.session,
            workspace_id=ctx.workspace_id,
            tool_id=tool.id,
            arguments=rendered_arguments,
            invoked_by="workflow",
            step_run_id=ctx.step_run_id,
            approval_id=approval_row.id,
        )
    else:
        outcome = await mcp_service.invoke_tool(
            ctx.session,
            workspace_id=ctx.workspace_id,
            tool_id=tool.id,
            arguments=rendered_arguments,
            invoked_by="workflow",
            step_run_id=ctx.step_run_id,
        )

    return StepResult(
        output={
            "tool_id": str(tool.id),
            "tool_name": tool.name,
            "arguments": rendered_arguments,
            "content": outcome.content,
            "is_error": outcome.is_error,
            "status": outcome.status,
            "tool_call_id": str(outcome.tool_call_id),
        }
    )
