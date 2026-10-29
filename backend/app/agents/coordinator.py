"""Master agent: plans a goal into specialist sub-tasks and runs them in order.

1. Plan  - a LARGE-tier call returns JSON {"steps":[{"role","task"}]}; invalid
           plans fail the gateway validator, which escalates to a stronger model.
2. Run   - each sub-task goes to the specialist for that role (workspace
           override if one exists, else the built-in), via the router.
3. Final - if the last step isn't writing, the writer synthesizes the answer.
A failing sub-task stops the run and returns the partial results.
"""

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.agents.config import AgentConfig
from app.agents.runtime import AgentRunError, run_agent
from app.agents.specialists import SPECIALISTS
from app.agents.tools import ToolRegistry
from app.llm.errors import AllModelsFailedError
from app.llm.gateway import LLMGateway
from app.llm.types import Attempt, Message, RoutingHints

Resolver = Callable[[str], Awaitable[AgentConfig]]

PLANNER_PROMPT = """You are a planning coordinator. Break the user's goal into 1-{max_steps} \
sequential sub-tasks, using the FEWEST steps that achieve the goal (simple goals need 1-2).
Assign each to one specialist role: {roles}.
Reply with ONLY JSON: {{"steps": [{{"role": "<role>", "task": "<what to do>"}}]}}"""

_CONTEXT_CHARS = 6000


class PlanError(Exception):
    def __init__(self, message: str, attempts: list[Attempt]) -> None:
        super().__init__(message)
        self.attempts = attempts


@dataclass
class StepResult:
    role: str
    task: str
    agent: str
    status: str  # completed | step_limit | failed
    output: str


@dataclass
class CoordinatorResult:
    status: str  # completed | failed
    plan: list[dict[str, str]]
    steps: list[StepResult]
    final: str
    attempts: list[Attempt] = field(default_factory=list)


def parse_plan(content: str, max_steps: int) -> list[dict[str, str]] | str:
    """Return the validated step list, or a short reason string if invalid."""
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if match is None:
        return "no JSON object in plan"
    try:
        data = json.loads(match.group(0))
        raw_steps = data["steps"]
    except (ValueError, KeyError, TypeError):
        return "plan is not valid JSON with a 'steps' list"
    if not isinstance(raw_steps, list) or not raw_steps:
        return "plan has no steps"
    steps = []
    for item in raw_steps[:max_steps]:
        if not isinstance(item, dict):
            return "plan step is not an object"
        role, task = item.get("role"), item.get("task")
        if role not in SPECIALISTS:
            return f"unknown role {role!r}"
        if not isinstance(task, str) or not task.strip():
            return "plan step has no task"
        steps.append({"role": role, "task": task.strip()})
    return steps


async def run_coordinator(
    gateway: LLMGateway,
    goal: str,
    resolve: Resolver,
    *,
    tools: ToolRegistry | None = None,
    max_steps: int = 5,
) -> CoordinatorResult:
    attempts: list[Attempt] = []

    def plan_validator(content: str) -> str | None:
        parsed = parse_plan(content, max_steps)
        return parsed if isinstance(parsed, str) else None

    planner = [
        Message("system", PLANNER_PROMPT.format(max_steps=max_steps, roles=", ".join(SPECIALISTS))),
        Message("user", goal),
    ]
    try:
        planned = await gateway.complete(
            planner, RoutingHints(step_type="plan"), validator=plan_validator
        )
    except AllModelsFailedError as exc:
        raise PlanError("coordinator could not produce a plan", exc.attempts) from exc
    attempts.extend(planned.attempts)
    plan = parse_plan(planned.response.content, max_steps)
    assert isinstance(plan, list)  # the validator guaranteed this

    results: list[StepResult] = []
    for step in plan:
        config = await resolve(step["role"])
        prompt = f"Overall goal: {goal}\n\nYour task: {step['task']}"
        if results:
            prior = "\n\n".join(f"[{r.role}] {r.output}" for r in results)[-_CONTEXT_CHARS:]
            prompt += f"\n\nResults from earlier steps:\n{prior}"
        try:
            run = await run_agent(gateway, config, prompt, tools=tools)
        except AgentRunError as exc:
            attempts.extend(exc.attempts)
            results.append(StepResult(step["role"], step["task"], config.name, "failed", ""))
            return CoordinatorResult("failed", plan, results, "", attempts)
        attempts.extend(run.attempts)
        results.append(StepResult(step["role"], step["task"], config.name, run.status, run.output))

    if plan[-1]["role"] == "writing":
        return CoordinatorResult("completed", plan, results, results[-1].output, attempts)

    writer = await resolve("writing")
    joined = "\n\n".join(f"[{r.role}] {r.output}" for r in results)[-_CONTEXT_CHARS * 2 :]
    synthesis = (
        "Write the final answer to the goal using these results.\n\n"
        f"Goal: {goal}\n\nResults:\n{joined}"
    )
    try:
        final = await run_agent(gateway, writer, synthesis)
    except AgentRunError as exc:
        attempts.extend(exc.attempts)
        return CoordinatorResult("failed", plan, results, "", attempts)
    attempts.extend(final.attempts)
    results.append(
        StepResult("writing", "final synthesis", writer.name, final.status, final.output)
    )
    return CoordinatorResult("completed", plan, results, final.output, attempts)
