"""QQ 适配器：OneBot v11 反向 WebSocket（Resident 作 server）。

QQ 机器人框架（NapCat/LLOneBot/Lagrange 等，配置 reverse-ws 指向本机端口）
主动连过来；消息事件进事件总线；发消息必须经过 L2 审批。
"""

import asyncio
import json
import time

from adapters.base import Adapter
from websockets.asyncio.server import serve


class OneBotAdapter(Adapter):
    name = "qq"

    def __init__(self, components: dict, cfg: dict | None = None) -> None:
        self.components = components
        cfg = cfg or {}
        self.host = cfg.get("host", "127.0.0.1")
        self.port = int(cfg.get("port", 6700))
        self.conns: set = set()
        self._pending_actions: dict[str, asyncio.Future] = {}
        self._approved_actions: dict[int, object] = {}  # approval_id -> coroutine
        self._server = None

    def capabilities(self) -> list[str]:
        return ["qq_send"]

    # ---- 生命周期 ----
    def start(self) -> None:
        self._task = asyncio.create_task(self._serve())

    async def _serve(self) -> None:
        self._server = await serve(self._handler, self.host, self.port)

    def stop(self) -> None:
        pass

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        for ws in list(self.conns):
            await ws.close()
        self.conns.clear()

    # ---- 事件入站 ----
    async def _handler(self, ws) -> None:
        self.conns.add(ws)
        try:
            async for raw in ws:
                try:
                    data = json.loads(raw)
                except Exception:
                    continue
                if data.get("post_type") == "message":
                    self._on_message(data)
                elif data.get("echo") and data["echo"] in self._pending_actions:
                    fut = self._pending_actions.pop(data["echo"])
                    if not fut.done():
                        fut.set_result(data)
        finally:
            self.conns.discard(ws)

    def _on_message(self, data: dict) -> None:
        msg_type = data.get("message_type", "")
        scope = "private" if msg_type == "private" else "group"
        sender = data.get("sender") or {}
        user_id = str(sender.get("user_id", "?"))
        text = str(data.get("message", ""))
        self.components["events"].append(
            "UserMessageReceived", scope, "user", user_id, text
        )
        rel = self.components.get("relationships")
        if rel is not None:
            rel.touch(user_id)

    # ---- 发消息（审批后由 CLI 调用 dispatch） ----
    def register_send(self, approval_id: int, coro) -> None:
        self._approved_actions[approval_id] = coro

    async def dispatch(self, approval_id: int) -> bool:
        coro = self._approved_actions.pop(approval_id, None)
        if coro is None:
            return False
        await coro()
        return True

    async def send_private(self, user_id: str, text: str) -> str:
        if not self.conns:
            raise ConnectionError("没有 OneBot 连接")
        echo = f"resident{int(time.time() * 1000)}"
        fut = asyncio.get_running_loop().create_future()
        self._pending_actions[echo] = fut
        payload = json.dumps(
            {
                "action": "send_private_msg",
                "params": {"user_id": int(user_id), "message": text},
                "echo": echo,
            }
        )
        for ws in list(self.conns):
            await ws.send(payload)
        try:
            await asyncio.wait_for(fut, timeout=10)
        except asyncio.TimeoutError:
            self._pending_actions.pop(echo, None)
            raise ConnectionError("OneBot 未响应")
        return "sent"
