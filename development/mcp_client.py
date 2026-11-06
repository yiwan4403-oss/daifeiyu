"""MCP 客户端（stdio）：把外部工具标准化接入。结果一律 untrusted。"""

import asyncio
import json
from contextlib import AsyncExitStack

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


class MCPServerError(Exception):
    pass


class MCPServerConn:
    def __init__(self, name: str, command: str, args: list | None = None) -> None:
        self.name = name
        self.command = command
        self.args = args or []
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._tools: list[str] = []

    async def connect(self) -> list[str]:
        import os

        params = StdioServerParameters(
            command=self.command, args=self.args, env=dict(os.environ)
        )
        self._stack = AsyncExitStack()
        try:
            read, write = await self._stack.enter_async_context(stdio_client(params))
            self._session = await self._stack.enter_async_context(ClientSession(read, write))
            await self._session.initialize()
            res = await self._session.list_tools()
        except Exception as exc:
            await self.close()
            raise MCPServerError(f"{self.name} 连接失败: {exc}") from exc
        self._tools = [t.name for t in res.tools]
        return self._tools

    @property
    def tools(self) -> list[str]:
        return list(self._tools)

    async def call(self, tool_name: str, arguments: dict) -> str:
        if self._session is None:
            raise MCPServerError(f"{self.name} 未连接")
        try:
            result = await self._session.call_tool(tool_name, arguments or {})
        except Exception as exc:
            raise MCPServerError(f"调用 {tool_name} 失败: {exc}") from exc
        parts = []
        for item in getattr(result, "content", []):
            text = getattr(item, "text", None)
            parts.append(text if text is not None else str(item))
        return ("\n".join(parts))[:4000]

    async def close(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None
            self._session = None


class MCPHub:
    """管理多个 MCP server；工具结果一律标注 untrusted。"""

    def __init__(self, servers_cfg: list | None = None) -> None:
        self._conns: dict[str, MCPServerConn] = {}
        self._cfg = servers_cfg or []

    async def start_all(self) -> list[str]:
        started = []
        for item in self._cfg:
            if not isinstance(item, dict) or not item.get("name") or not item.get("command"):
                continue
            conn = MCPServerConn(
                item["name"], item["command"], list(item.get("args") or [])
            )
            try:
                await conn.connect()
            except MCPServerError as exc:
                print(f"[mcp] {exc}")
                continue
            self._conns[item["name"]] = conn
            started.append(item["name"])
        return started

    async def stop_all(self) -> None:
        for conn in list(self._conns.values()):
            await conn.close()
        self._conns.clear()

    def names(self) -> list[str]:
        return list(self._conns.keys())

    def list_tools(self) -> dict[str, list[str]]:
        return {name: conn.tools for name, conn in self._conns.items()}

    async def call(self, server: str, tool: str, arguments: dict) -> str:
        conn = self._conns.get(server)
        if conn is None:
            raise MCPServerError(f"未知 MCP server: {server}")
        return await conn.call(tool, arguments)
