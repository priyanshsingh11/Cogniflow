"""Built-in specialist agents. A workspace can override any of them by
creating an Agent with the same role (see coordinator resolver)."""

from app.agents.config import AgentConfig

SPECIALISTS: dict[str, AgentConfig] = {
    "research": AgentConfig(
        name="Researcher",
        role="research",
        system_prompt=(
            "You are a research specialist. Gather and organize the relevant facts for the "
            "task. Be accurate, note uncertainty, and never invent sources."
        ),
    ),
    "analysis": AgentConfig(
        name="Analyst",
        role="analysis",
        system_prompt=(
            "You are an analysis specialist. Reason step by step over the provided material, "
            "compare options, and state clear conclusions with the evidence behind them."
        ),
    ),
    "writing": AgentConfig(
        name="Writer",
        role="writing",
        system_prompt=(
            "You are a writing specialist. Produce clear, well-structured text for the "
            "intended reader using only the material you are given."
        ),
    ),
    "review": AgentConfig(
        name="Reviewer",
        role="review",
        system_prompt=(
            "You are a review specialist. Check the work for errors, gaps and unsupported "
            "claims, then list concrete fixes. Be specific and concise."
        ),
    ),
}
