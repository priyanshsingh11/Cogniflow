"""Deterministic in-repo MCP server used for demos and the opt-in live test.

Run it (this is exactly what a registered `stdio` server does):

    python backend/mcp_servers/demo.py

No network, no side effects — the tools are pure functions so tests can
assert exact outputs.
"""

from mcp.server.mcpserver import MCPServer

server = MCPServer("cogniflow-demo")


@server.tool()
def add(a: float, b: float) -> float:
    """Add two numbers and return the sum."""
    return a + b


@server.tool()
def word_count(text: str) -> int:
    """Count the words in the given text."""
    return len(text.split())


@server.tool()
def get_current_time() -> str:
    """Return the current UTC time in ISO-8601 format."""
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


if __name__ == "__main__":
    server.run(transport="stdio")
