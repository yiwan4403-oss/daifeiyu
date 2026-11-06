"""测试用 MCP echo server（stdio）。"""

import asyncio

from mcp.server.mcpserver import MCPServer


def echo(text: str) -> str:
    return f"echo:{text}"


async def main() -> None:
    server = MCPServer("echo-server", title="Echo")
    server.add_tool(echo, name="echo", description="回显文本")
    await server.run_stdio_async()


if __name__ == "__main__":
    asyncio.run(main())
