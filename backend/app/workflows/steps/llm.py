from app.llm.deps import get_gateway
from app.llm.recording import record_attempts
from app.llm.types import Message, RoutingHints
from app.workflows.steps.base import StepExecutionContext, StepResult
from app.workflows.template import render_template


async def execute_llm_step(ctx: StepExecutionContext) -> StepResult:
    config = ctx.step_config
    prompt_raw = config.get("prompt", "")
    system_raw = config.get("system_prompt", "")
    tier = config.get("tier")
    model = config.get("model")
    step_type = config.get("step_type", "execute")

    rendered_prompt = str(render_template(prompt_raw, ctx.context))
    rendered_system = str(render_template(system_raw, ctx.context))

    messages: list[Message] = []
    if rendered_system:
        messages.append(Message(role="system", content=rendered_system))
    messages.append(Message(role="user", content=rendered_prompt))

    hints = RoutingHints(
        step_type=step_type,
        pinned_tier=tier,
        pinned_model=model,
    )

    gateway = get_gateway()
    result = await gateway.complete(messages, hints)

    record_attempts(
        ctx.session,
        result.attempts,
        workspace_id=ctx.workspace_id,
        route_reason=result.route_reason,
        agent_id=ctx.agent_id,
        step_run_id=ctx.step_run_id,
    )
    await ctx.session.flush()

    return StepResult(
        output={
            "content": result.response.content,
            "provider": result.response.provider,
            "model": result.response.model,
            "tier": result.tier,
            "route_reason": result.route_reason,
        }
    )
