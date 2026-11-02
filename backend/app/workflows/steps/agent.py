import uuid

from app.agents.config import AgentConfig
from app.agents.deps import get_tools
from app.agents.runtime import run_agent
from app.api.deps import TenantContext
from app.llm.deps import get_gateway
from app.llm.recording import record_attempts
from app.models.agent import Agent
from app.models.enums import Role
from app.models.workspace import Workspace
from app.workflows.steps.base import StepExecutionContext, StepResult
from app.workflows.template import render_template


async def execute_agent_step(ctx: StepExecutionContext) -> StepResult:
    config = ctx.step_config
    agent_id_raw = config.get("agent_id") or ctx.agent_id
    raw_input = config.get("input", "")
    max_steps = int(config.get("max_steps", 5))

    if not agent_id_raw:
        raise ValueError(f"Agent step '{ctx.step_name}' missing agent_id in configuration")

    agent_uuid = uuid.UUID(str(agent_id_raw))
    agent_row = await ctx.session.get(Agent, agent_uuid)
    if agent_row is None or agent_row.workspace_id != ctx.workspace_id:
        raise ValueError(f"Agent '{agent_uuid}' not found in workspace")

    rendered_input = str(render_template(raw_input, ctx.context))

    agent_config = AgentConfig(
        id=agent_row.id,
        name=agent_row.name,
        role=agent_row.role,
        system_prompt=agent_row.system_prompt,
        tier_pin=agent_row.tier_pin,
        model_pin=agent_row.model_pin,
        params=agent_row.params or {},
    )

    t_ctx = TenantContext(
        user=None,  # type: ignore[arg-type]
        workspace=Workspace(id=ctx.workspace_id),
        org=None,  # type: ignore[arg-type]
        membership=None,  # type: ignore[arg-type]
        role=Role.MEMBER,
    )
    tools = await get_tools(t_ctx)

    gateway = get_gateway()
    result = await run_agent(
        gateway=gateway,
        config=agent_config,
        user_input=rendered_input,
        tools=tools,
        max_steps=max_steps,
    )

    record_attempts(
        ctx.session,
        result.attempts,
        workspace_id=ctx.workspace_id,
        route_reason=f"workflow:{ctx.step_name}",
        agent_id=agent_row.id,
        step_run_id=ctx.step_run_id,
    )
    await ctx.session.flush()

    return StepResult(
        output={
            "output": result.output,
            "status": result.status,
            "steps": [
                {
                    "kind": s.kind,
                    "tool": s.tool,
                    "arguments": s.arguments,
                    "result": s.result,
                }
                for s in result.steps
            ],
            "models_used": result.models_used,
        }
    )
