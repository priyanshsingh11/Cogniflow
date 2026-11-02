from sqlalchemy import select

from app.agents.config import AgentConfig
from app.agents.coordinator import PlanError, run_coordinator
from app.agents.deps import get_tools
from app.agents.specialists import SPECIALISTS
from app.api.deps import TenantContext
from app.llm.deps import get_gateway
from app.llm.recording import record_attempts
from app.models.agent import Agent
from app.models.enums import Role
from app.models.workspace import Workspace
from app.workflows.steps.base import StepExecutionContext, StepResult
from app.workflows.template import render_template


async def execute_coordinator_step(ctx: StepExecutionContext) -> StepResult:
    config = ctx.step_config
    goal_raw = config.get("goal", "")
    max_steps = int(config.get("max_steps", 5))

    rendered_goal = str(render_template(goal_raw, ctx.context))

    async def resolve(role: str) -> AgentConfig:
        row = (
            await ctx.session.execute(
                select(Agent)
                .where(Agent.workspace_id == ctx.workspace_id, Agent.role == role)
                .order_by(Agent.created_at)
                .limit(1)
            )
        ).scalar_one_or_none()
        return AgentConfig.from_row(row) if row else SPECIALISTS[role]

    t_ctx = TenantContext(
        user=None,  # type: ignore[arg-type]
        workspace=Workspace(id=ctx.workspace_id),
        org=None,  # type: ignore[arg-type]
        membership=None,  # type: ignore[arg-type]
        role=Role.MEMBER,
    )
    tools = await get_tools(t_ctx)
    gateway = get_gateway()

    try:
        result = await run_coordinator(
            gateway,
            rendered_goal,
            resolve,
            tools=tools,
            max_steps=max_steps,
        )
    except PlanError as exc:
        record_attempts(
            ctx.session,
            exc.attempts,
            workspace_id=ctx.workspace_id,
            route_reason="coordinator:planning failed",
            step_run_id=ctx.step_run_id,
        )
        await ctx.session.flush()
        raise ValueError(f"Coordinator could not plan the goal: {exc}") from exc

    record_attempts(
        ctx.session,
        result.attempts,
        workspace_id=ctx.workspace_id,
        route_reason="coordinator:execution",
        step_run_id=ctx.step_run_id,
    )
    await ctx.session.flush()

    return StepResult(
        output={
            "output": result.final,
            "status": result.status,
            "plan": result.plan,
            "steps": [
                {
                    "role": s.role,
                    "task": s.task,
                    "agent": s.agent,
                    "status": s.status,
                    "output": s.output,
                }
                for s in result.steps
            ],
        }
    )
