import asyncio

import pytest

from app.agents.config import AgentConfig
from app.agents.coordinator import PlanError, parse_plan, run_coordinator
from app.agents.runtime import AgentRunError, parse_tool_call, run_agent
from app.agents.tools import Tool, ToolRegistry
from app.llm.errors import RateLimitError
from app.llm.gateway import LLMGateway
from tests.fakes import FakeProvider
from tests.test_llm_gateway import _no_sleep, _registry

TOOL = '{"tool": "echo", "arguments": {"text": "hi"}}'
CUSTOM = AgentConfig(name="Tester", role="custom", system_prompt="be brief")  # -> medium tier (m1)


def _gw(g: FakeProvider, o: FakeProvider | None = None) -> LLMGateway:
    return LLMGateway({"g": g, "o": o or FakeProvider("o", {})}, _registry(), sleep=_no_sleep)


def _echo_registry(**kw) -> tuple[ToolRegistry, list]:
    calls: list = []

    async def echo(args):
        calls.append(args)
        return f"echo:{args['text']}"

    return ToolRegistry([Tool("echo", "echoes text", echo, {"text": "what to echo"}, **kw)]), calls


def _run(gateway, config=CUSTOM, text="go", **kw):
    return asyncio.run(run_agent(gateway, config, text, **kw))


# ---- parse_tool_call -------------------------------------------------------


def test_parse_tool_call():
    assert parse_tool_call("just an answer") is None
    assert parse_tool_call(TOOL) == {"tool": "echo", "arguments": {"text": "hi"}}
    assert parse_tool_call(f"```json\n{TOOL}\n```")["tool"] == "echo"
    assert parse_tool_call('{"answer": 1}') is None  # JSON but not a tool call
    assert parse_tool_call(f"Sure! {TOOL}") is None  # prose around it = final answer
    assert parse_tool_call('{"tool": "x", "arguments": "oops"}') == {"tool": "x", "arguments": {}}


# ---- runtime ---------------------------------------------------------------


def test_single_call_without_tools():
    g = FakeProvider("g", {"m1": ["  the answer  "]})
    result = _run(_gw(g))
    assert result.output == "the answer" and result.status == "completed"
    assert result.steps == [] and result.models_used == ["g:m1"]


def test_tool_loop_runs_tool_then_answers():
    tools, calls = _echo_registry()
    g = FakeProvider("g", {"m1": [TOOL, "final: echo:hi"]})
    result = _run(_gw(g), tools=tools)
    assert result.output == "final: echo:hi" and result.status == "completed"
    assert calls == [{"text": "hi"}]
    assert [(s.kind, s.tool, s.result) for s in result.steps] == [("tool", "echo", "echo:hi")]


def test_tools_are_not_parsed_when_none_registered():
    g = FakeProvider("g", {"m1": [TOOL]})
    result = _run(_gw(g))  # no registry -> the JSON is just the answer
    assert result.output == TOOL and result.steps == []


def test_unknown_tool_and_missing_args_become_tool_errors():
    tools, calls = _echo_registry()
    bad = ['{"tool": "nope", "arguments": {}}', '{"tool": "echo", "arguments": {}}', "done"]
    result = _run(_gw(FakeProvider("g", {"m1": bad})), tools=tools)
    assert [s.kind for s in result.steps] == ["tool_error", "tool_error"]
    assert (
        "Unknown tool" in result.steps[0].result and "Missing arguments" in result.steps[1].result
    )
    assert calls == [] and result.output == "done"


def test_tool_requiring_approval_is_refused_not_run():
    tools, calls = _echo_registry(requires_approval=True)
    g = FakeProvider("g", {"m1": [TOOL, "ok"]})
    result = _run(_gw(g), tools=tools)
    assert calls == [] and "requires human approval" in result.steps[0].result


def test_tool_exception_is_reported_not_raised():
    async def boom(args):
        raise ValueError("secret detail")

    tools = ToolRegistry([Tool("echo", "x", boom, {"text": "t"})])
    result = _run(_gw(FakeProvider("g", {"m1": [TOOL, "recovered"]})), tools=tools)
    assert result.steps[0].kind == "tool_error" and "ValueError" in result.steps[0].result
    assert "secret detail" not in result.steps[0].result  # details don't leak to the model
    assert result.output == "recovered"


def test_step_limit_stops_runaway_tool_loop():
    tools, calls = _echo_registry()
    result = _run(_gw(FakeProvider("g", {"m1": [TOOL]})), tools=tools, max_steps=3)
    assert result.status == "step_limit" and len(result.steps) == 3 and len(calls) == 3


def test_all_models_failed_raises_with_agent_id_on_attempts():
    err = RateLimitError("429")
    g = FakeProvider("g", {m: [err] for m in ("m1", "l1")})
    o = FakeProvider("o", {m: [err] for m in ("m2", "l2", "free")})
    config = AgentConfig(name="A", role="custom", system_prompt="", id=__import__("uuid").uuid4())
    with pytest.raises(AgentRunError) as info:
        _run(_gw(g, o), config)
    assert info.value.attempts and all(a.agent_id == config.id for a in info.value.attempts)


def test_agent_pins_are_honoured():
    g = FakeProvider("g", {})
    pinned = AgentConfig(name="P", role="custom", system_prompt="", tier_pin="large")
    _run(_gw(g), pinned)
    assert g.calls == ["l1"]


# ---- coordinator -----------------------------------------------------------

PLAN_RW = (
    '{"steps": [{"role": "research", "task": "find facts"}, {"role": "writing", "task": "write"}]}'
)
PLAN_RA = '{"steps": [{"role": "research", "task": "find"}, {"role": "analysis", "task": "judge"}]}'


async def _default_resolver(role: str) -> AgentConfig:
    from app.agents.specialists import SPECIALISTS

    return SPECIALISTS[role]


def _coord(gateway, goal="do the thing", resolve=_default_resolver):
    return asyncio.run(run_coordinator(gateway, goal, resolve))


def test_parse_plan_validation():
    assert parse_plan(PLAN_RW, 5) == [
        {"role": "research", "task": "find facts"},
        {"role": "writing", "task": "write"},
    ]
    assert len(parse_plan(PLAN_RW, 1)) == 1  # capped
    for bad in (
        "no json",
        '{"steps": []}',
        '{"steps": [{"role": "hacker", "task": "x"}]}',
        '{"steps": [{"role": "research"}]}',
        '{"steps": "x"}',
    ):
        assert isinstance(parse_plan(bad, 5), str)


def test_coordinator_plans_delegates_and_uses_last_writing_step_as_final():
    g = FakeProvider("g", {"l1": [PLAN_RW], "m1": ["the facts", "the report"]})
    result = _coord(_gw(g))
    assert result.status == "completed" and result.final == "the report"
    assert [s.role for s in result.steps] == ["research", "writing"]
    assert [s.agent for s in result.steps] == ["Researcher", "Writer"]
    assert len(result.attempts) == 3  # plan + 2 steps


def test_coordinator_adds_writer_synthesis_when_plan_does_not_end_in_writing():
    g = FakeProvider("g", {"l1": [PLAN_RA, "analysis out"], "m1": ["facts", "polished final"]})
    result = _coord(_gw(g))
    assert result.final == "polished final"
    assert [s.role for s in result.steps] == ["research", "analysis", "writing"]
    assert result.steps[-1].task == "final synthesis"


def test_invalid_plan_escalates_past_the_planner_tier():
    # l1 (large tier) returns junk -> rest of large tier skipped -> last_resort ("free") plans.
    g = FakeProvider("g", {"l1": ["I will think about it"], "m1": ["facts", "report"]})
    o = FakeProvider("o", {"free": [PLAN_RW]})
    result = _coord(_gw(g, o))
    assert result.status == "completed" and o.calls == ["free"]


def test_unplannable_goal_raises_plan_error():
    err = RateLimitError("429")
    g = FakeProvider("g", {"l1": [err]})
    o = FakeProvider("o", {"l2": [err], "free": [err]})
    with pytest.raises(PlanError) as info:
        _coord(_gw(g, o))
    assert info.value.attempts


def test_step_failure_returns_partial_results_with_failed_status():
    err = RateLimitError("429")
    g = FakeProvider("g", {"l1": [PLAN_RW, err], "m1": [err]})
    o = FakeProvider("o", {m: [err] for m in ("m2", "l2", "free")})
    result = _coord(_gw(g, o))
    assert result.status == "failed" and result.final == ""
    assert [s.status for s in result.steps] == ["failed"]  # stopped at the first failure


def test_coordinator_uses_resolver_overrides():
    custom = AgentConfig(
        name="Custom Researcher", role="research", system_prompt="x", tier_pin="small"
    )

    async def resolve(role: str) -> AgentConfig:
        return custom if role == "research" else await _default_resolver(role)

    g = FakeProvider("g", {"l1": [PLAN_RW], "s1": ["facts"], "m1": ["report"]})
    result = _coord(_gw(g), resolve=resolve)
    assert result.steps[0].agent == "Custom Researcher" and "s1" in g.calls
