"""Rules-based tier choice. Automatic, deterministic and free (no extra LLM call).

Quality escalation (a bad answer moves up a tier) lives in the gateway; this
only picks where to START.
"""

from dataclasses import dataclass

from app.llm.types import Message, RoutingHints, Tier

SMALL_STEPS = {"classify", "extract", "format", "route", "condition"}
LARGE_STEPS = {"plan", "reason", "analyze", "analysis", "review"}

MEDIUM_TOKENS = 6_000
LARGE_TOKENS = 24_000
MEDIUM_DOCS = 1
LARGE_DOCS = 5


@dataclass
class RouteDecision:
    tier: Tier
    reason: str


def estimate_tokens(messages: list[Message]) -> int:
    """Cheap estimate (~4 chars/token); good enough for tier thresholds."""
    return sum(len(m.content) for m in messages) // 4


def route(messages: list[Message], hints: RoutingHints) -> RouteDecision:
    if hints.pinned_tier is not None:
        return RouteDecision(hints.pinned_tier, f"agent pinned tier={hints.pinned_tier.value}")

    if hints.step_type in LARGE_STEPS:
        tier, reasons = Tier.LARGE, [f"step_type={hints.step_type}"]
    elif hints.step_type in SMALL_STEPS:
        tier, reasons = Tier.SMALL, [f"step_type={hints.step_type}"]
    else:
        tier, reasons = Tier.MEDIUM, [f"step_type={hints.step_type or 'default'}"]

    def bump(to: Tier, why: str) -> None:
        nonlocal tier
        if to.rank > tier.rank:
            tier = to
            reasons.append(why)

    tokens = estimate_tokens(messages)
    if tokens >= LARGE_TOKENS:
        bump(Tier.LARGE, f"~{tokens} tokens")
    elif tokens >= MEDIUM_TOKENS:
        bump(Tier.MEDIUM, f"~{tokens} tokens")
    if hints.num_documents >= LARGE_DOCS:
        bump(Tier.LARGE, f"{hints.num_documents} documents")
    elif hints.num_documents >= MEDIUM_DOCS:
        bump(Tier.MEDIUM, f"{hints.num_documents} document(s)")

    return RouteDecision(tier, "; ".join(reasons))
