"""QQ 适配器：OneBot v11 反向 WebSocket（Resident 作 server）。

QQ 机器人框架（NapCat/LLOneBot/Lagrange 等，配置 reverse-ws 指向本机端口）
主动连过来；消息事件进事件总线；发消息必须经过 L2 审批。
"""

import asyncio
import json
import time

from adapters.base import Adapter
from websockets.asyncio.server import serve


def _parse_message(message) -> tuple[str, list[str]]:
    """OneBot message：字符串直接返回；数组按段提取文本与图片 url。"""
    if isinstance(message, str):
        return message, []
    if not isinstance(message, list):
        return str(message), []
    texts, images = [], []
    for seg in message:
        if not isinstance(seg, dict):
            continue
        stype = seg.get("type")
        data = seg.get("data") or {}
        if stype == "text":
            texts.append(str(data.get("text", "")))
        elif stype == "image":
            url = data.get("url") or data.get("file") or ""  # url 缺失时退回本地路径
            if url:
                images.append(url)
            texts.append("[图片]")
        elif stype == "face":
            texts.append("[表情]")
        elif stype == "at":
            texts.append(f"@{data.get('qq', '')}")
        else:
            texts.append(f"[{stype}]")
    return "".join(texts), images


class OneBotAdapter(Adapter):
    name = "qq"

    def __init__(self, components: dict, cfg: dict | None = None) -> None:
        self.components = components
        cfg = cfg or {}
        self.host = cfg.get("host", "127.0.0.1")
        self.port = int(cfg.get("port", 6700))
        self.min_send_interval = float(cfg.get("min_send_interval_seconds", 5))
        self.conns: set = set()
        self._pending_actions: dict[str, asyncio.Future] = {}
        self._approved_actions: dict[int, object] = {}
        self._server = None
        self._last_send = 0.0
        self._send_lock = asyncio.Lock()

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
                    await self._on_message(data)
                elif data.get("echo") and data["echo"] in self._pending_actions:
                    fut = self._pending_actions.pop(data["echo"])
                    if not fut.done():
                        fut.set_result(data)
                else:
                    print(f"[qq] 收到未识别帧：{str(data)[:200]}")
        finally:
            self.conns.discard(ws)

    async def _on_message(self, data: dict) -> None:
        msg_type = data.get("message_type", "")
        scope = "private" if msg_type == "private" else "group"
        sender = data.get("sender") or {}
        user_id = str(sender.get("user_id", "?"))
        text, images = _parse_message(data.get("message", ""))
        self.components["events"].append(
            "UserMessageReceived", scope, "user", user_id, text
        )
        rel = self.components.get("relationships")
        if rel is not None:
            rel.touch(user_id)
        handler = self.components.get("on_user_message")
        if handler is not None:
            try:
                await handler(scope, user_id, text, images)
            except Exception as exc:
                print(f"[qq] 处理消息失败：{exc}")

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
        # 串行化 + 重试：NapCat 偶发慢响应，避免把消息标成失败
        async with self._send_lock:
            last_exc = None
            for _ in range(2):
                try:
                    return await self._send_once(user_id, text)
                except ConnectionError as exc:
                    last_exc = exc
                    await asyncio.sleep(2)
            raise last_exc or ConnectionError("发送失败")

    async def _send_once(self, user_id: str, text: str) -> str:
        # 发送限速（风控缓解）：两次发送至少间隔 min_send_interval 秒
        now = time.time()
        wait = self.min_send_interval - (now - self._last_send)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_send = time.time()
        echo = f"resident{int(time.time() * 1000)}"
        fut = asyncio.get_running_loop().create_future()
        self._pending_actions[echo] = fut
        payload = json.dumps(
            {
                "action": "send_private_msg",
                "params": {
                    "user_id": int(user_id),
                    "message": [{"type": "text", "data": {"text": text}}],
                },
                "echo": echo,
            }
        )
        print(f"[qq] 发送动作：{payload[:120]}")
        for ws in list(self.conns):
            await ws.send(payload)
        try:
            await asyncio.wait_for(fut, timeout=30)
        except asyncio.TimeoutError:
            self._pending_actions.pop(echo, None)
            raise ConnectionError("OneBot 未响应")
        return "sent"

    async def set_avatar(self, image_path: str) -> str:
        """设置 QQ 头像（NapCat set_qq_avatar）。image_path 为本地绝对路径。"""
        import os

        if not os.path.isfile(image_path):
            raise FileNotFoundError(image_path)
        if not self.conns:
            raise ConnectionError("没有 OneBot 连接")
        echo = f"avatar{int(time.time() * 1000)}"
        fut = asyncio.get_running_loop().create_future()
        self._pending_actions[echo] = fut
        payload = json.dumps(
            {
                "action": "set_qq_avatar",
                "params": {"file": os.path.abspath(image_path)},
                "echo": echo,
            }
        )
        print(f"[qq] 设置头像：{payload[:120]}")
        for ws in list(self.conns):
            await ws.send(payload)
        try:
            await asyncio.wait_for(fut, timeout=20)
        except asyncio.TimeoutError:
            self._pending_actions.pop(echo, None)
            raise ConnectionError("OneBot 未响应")
        return "sent"
