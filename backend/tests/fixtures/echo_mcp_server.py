"""Tiny stdio MCP server for the opt-in live test (tests/test_mcp_live.py)."""

from mcp.server.mcpserver import MCPServer

server = MCPServer("echo")


@server.tool()
def add(a: float, b: float) -> str:
    """Add two numbers."""
    return f"sum is {a + b:g}"


if __name__ == "__main__":
    server.run("stdio")
