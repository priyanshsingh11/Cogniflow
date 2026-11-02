from collections.abc import Callable
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.models.workflow import WorkflowStep


class WorkflowState(TypedDict, total=False):
    run_id: str
    workspace_id: str
    input: dict[str, Any]
    steps: dict[str, Any]
    current_step: str
    next_step: str | None
    status: str  # running | waiting_approval | succeeded | failed
    error: str | None
    waiting_approval_step: str | None
    waiting_approval_details: dict[str, Any] | None


def compile_workflow_graph(
    steps: list[WorkflowStep],
    execute_step_callback: Callable[[WorkflowStep, WorkflowState], Any],
) -> Any:
    """Build a LangGraph StateGraph from the ordered workflow steps."""
    if not steps:
        raise ValueError("Cannot compile a workflow with no steps")

    # Sort by position
    sorted_steps = sorted(steps, key=lambda s: s.position)
    step_map = {s.name: s for s in sorted_steps}

    builder = StateGraph(WorkflowState)

    # 1. Add nodes
    for step in sorted_steps:

        async def node_fn(state: WorkflowState, s: WorkflowStep = step) -> WorkflowState:
            # If already paused for approval or failed, do not execute
            if state.get("status") in ("waiting_approval", "failed"):
                return state

            result_state = await execute_step_callback(s, state)
            return result_state

        builder.add_node(step.name, node_fn)

    # 2. Add edges
    # START -> first step
    builder.add_edge(START, sorted_steps[0].name)

    for i, step in enumerate(sorted_steps):
        is_last = i == len(sorted_steps) - 1

        if step.type == "condition":
            default_next = sorted_steps[i + 1].name if not is_last else None
            then_step = step.config.get("then_step") or default_next
            else_step = step.config.get("else_step") or default_next

            def make_router(t_step: str | None, e_step: str | None, d_next: str | None):
                def condition_router(state: WorkflowState) -> str:
                    if state.get("status") in ("waiting_approval", "failed"):
                        return END
                    nxt = state.get("next_step")
                    if nxt and nxt in step_map:
                        return nxt
                    if d_next and d_next in step_map:
                        return d_next
                    return END

                return condition_router

            path_map = {}
            if then_step and then_step in step_map:
                path_map[then_step] = then_step
            if else_step and else_step in step_map:
                path_map[else_step] = else_step
            if default_next and default_next in step_map:
                path_map[default_next] = default_next
            path_map[END] = END

            builder.add_conditional_edges(
                step.name,
                make_router(then_step, else_step, default_next),
                path_map,
            )
        else:
            # Check explicit next_step in config
            explicit_next = step.config.get("next_step")
            if explicit_next and explicit_next in step_map:
                builder.add_edge(step.name, explicit_next)
            elif not is_last:
                next_step = sorted_steps[i + 1]
                builder.add_edge(step.name, next_step.name)
            else:
                builder.add_edge(step.name, END)

    return builder.compile()
