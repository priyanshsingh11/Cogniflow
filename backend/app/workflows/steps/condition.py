from typing import Any

from app.workflows.steps.base import StepExecutionContext, StepResult
from app.workflows.template import render_template


def _evaluate_predicate(field_val: Any, op: str, target_val: Any) -> bool:
    if op in ("==", "eq"):
        return field_val == target_val
    if op in ("!=", "neq"):
        return field_val != target_val
    if op in (">", "gt"):
        return float(field_val) > float(target_val)
    if op in (">=", "gte"):
        return float(field_val) >= float(target_val)
    if op in ("<", "lt"):
        return float(field_val) < float(target_val)
    if op in ("<=", "lte"):
        return float(field_val) <= float(target_val)
    if op == "in":
        return field_val in target_val
    if op == "not in":
        return field_val not in target_val
    if op == "contains":
        return target_val in field_val
    if op == "is_empty":
        return not bool(field_val)
    if op == "not_empty":
        return bool(field_val)
    return bool(field_val)


async def execute_condition_step(ctx: StepExecutionContext) -> StepResult:
    config = ctx.step_config
    then_step = config.get("then_step")
    else_step = config.get("else_step")
    expression = config.get("expression")
    predicate = config.get("predicate")

    result = False

    if expression is not None:
        rendered = render_template(expression, ctx.context)
        if isinstance(rendered, bool):
            result = rendered
        elif isinstance(rendered, str):
            lower = rendered.strip().lower()
            if lower in ("true", "1", "yes"):
                result = True
            elif lower in ("false", "0", "no", "", "none"):
                result = False
            else:
                result = bool(rendered.strip())
        else:
            result = bool(rendered)

    elif predicate and isinstance(predicate, dict):
        field_path = predicate.get("field", "")
        op = predicate.get("op", "==")
        target_val = render_template(predicate.get("value"), ctx.context)

        # Resolve field_path in context
        parts = field_path.split(".")
        cur: Any = ctx.context
        for part in parts:
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                cur = None
                break
        result = _evaluate_predicate(cur, op, target_val)

    next_step = then_step if result else else_step
    return StepResult(
        output={"result": result, "next_step": next_step},
        next_step=next_step,
    )
