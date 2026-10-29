from app.agents.tools import ToolRegistry


def get_tools() -> ToolRegistry:
    """Tool registry for agent runs. Empty until RAG (phase 3) and MCP (phase 4)
    register tools; overridable in tests via app.dependency_overrides."""
    return ToolRegistry()
