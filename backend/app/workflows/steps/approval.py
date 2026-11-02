from sqlalchemy import select

from app.models.workflow import Approval
from app.workflows.steps.base import StepExecutionContext, StepResult
from app.workflows.template import render_template


async def execute_approval_step(ctx: StepExecutionContext) -> StepResult:
    config = ctx.step_config
    desc_raw = config.get("description", "Human approval required to proceed")
    details_raw = config.get("details", {})

    # Check if this step run was already approved (when resumed)
    stmt = select(Approval).where(
        Approval.step_run_id == ctx.step_run_id,
        Approval.status == "approved",
    )
    res = await ctx.session.execute(stmt)
    existing_approval = res.scalar_one_or_none()

    if existing_approval is not None:
        decided_by_str = str(existing_approval.decided_by) if existing_approval.decided_by else None
        decided_at_str = (
            existing_approval.decided_at.isoformat() if existing_approval.decided_at else None
        )
        return StepResult(
            status="succeeded",
            output={
                "approved": True,
                "decided_by": decided_by_str,
                "reason": existing_approval.reason,
                "decided_at": decided_at_str,
            },
        )

    rendered_desc = str(render_template(desc_raw, ctx.context))
    rendered_details = render_template(details_raw, ctx.context)
    if not isinstance(rendered_details, dict):
        rendered_details = {}

    return StepResult(
        status="waiting_approval",
        output=None,
        approval_details={
            "description": rendered_desc,
            "details": rendered_details,
        },
    )
