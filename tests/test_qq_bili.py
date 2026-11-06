"""QQ（OneBot 反向 WS）与 Bilibili 适配器测试。"""

import asyncio
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from adapters.bilibili import BilibiliAdapter  # noqa: E402
from adapters.qq import OneBotAdapter  # noqa: E402
from identity.identity_manager import IdentityManager  # noqa: E402
from memory.event_store import EventStore  # noqa: E402
from memory.manager import MemoryManager  # noqa: E402
from storage.database import init_schema, open_db  # noqa: E402

QQ_PORT = 18760


def make_components(tmp_path):
    conn = open_db(str(tmp_path / "r.db"))
    init_schema(conn)
    identity = IdentityManager(conn, {"name": "大肥鱼"})
    identity.ensure_default()
    from core.event_bus import EventBus
    from identity.emotion import EmotionManager
    from identity.relationships import RelationshipManager

    return {
        "conn": conn,
        "identity": identity,
        "events": EventStore(conn),
        "memories": MemoryManager(conn),
        "bus": EventBus(),
        "emotion": EmotionManager(conn),
        "relationships": RelationshipManager(conn),
    }


def test_qq_reverse_ws_roundtrip(tmp_path):
    async def run():
        components = make_components(tmp_path)
        adapter = OneBotAdapter(components, {"host": "127.0.0.1", "port": QQ_PORT})
        server_task = asyncio.create_task(adapter._serve())
        await asyncio.sleep(0.4)

        from websockets.asyncio.client import connect

        async with connect(f"ws://127.0.0.1:{QQ_PORT}") as ws:
            # 事件入站：OneBot 私聊消息
            await ws.send(
                json.dumps(
                    {
                        "post_type": "message",
                        "message_type": "private",
                        "sender": {"user_id": 123},
                        "message": "你好",
                    }
                )
            )
            await asyncio.sleep(0.3)
            events = components["events"].recent(5)
            assert events[-1].type == "UserMessageReceived"
            assert events[-1].scope == "private"
            assert events[-1].actor == "123"

            # 动作出站：send_private 收到 action 后回 echo
            send_task = asyncio.create_task(adapter.send_private("123", "回你"))
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            action = json.loads(raw)
            assert action["action"] == "send_private_msg"
            await ws.send(json.dumps({"echo": action["echo"], "status": "ok"}))
            result = await asyncio.wait_for(send_task, timeout=5)
            assert result == "sent"

        server_task.cancel()
        try:
            await server_task
        except (asyncio.CancelledError, Exception):
            pass
        await adapter.close()
        components["conn"].close()

    asyncio.run(run())


def test_qq_send_requires_approval_chain(tmp_path):
    components = make_components(tmp_path)
    adapter = OneBotAdapter(components, {"host": "127.0.0.1", "port": QQ_PORT + 1})

    from security.permission import ApprovalManager

    approvals = ApprovalManager()
    pid = approvals.submit("给 QQ 用户 123 发消息：hi", resource="qq:123", action="qq_send")

    called = {}

    async def do_send():
        called["sent"] = True

    adapter.register_send(pid, do_send)
    assert approvals.pending()
    approvals.decide(pid, True)
    asyncio.run(adapter.dispatch(pid))
    assert called.get("sent") is True
    components["conn"].close()


def test_bilibili_search_mocked(tmp_path, monkeypatch):
    class FakeResp:
        def __init__(self, payload):
            self._p = json.dumps(payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return self._p

    import urllib.request

    payload = {
        "code": 0,
        "data": {
            "result": [
                {"title": "红石教程", "bvid": "BV1xx411c7mD", "play": 12345},
            ]
        },
    }
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: FakeResp(payload))
    b = BilibiliAdapter({"min_interval_seconds": 0})
    out = b.search("红石")
    assert "BV1xx411c7mD" in out
    assert "untrusted" in out


def test_bilibili_video_info_mocked(tmp_path, monkeypatch):
    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(
                {
                    "code": 0,
                    "data": {
                        "title": "测试视频",
                        "desc": "简介内容",
                        "owner": {"name": "up主"},
                        "stat": {"view": 100, "like": 5},
                    },
                }
            ).encode("utf-8")

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: FakeResp())
    b = BilibiliAdapter({"min_interval_seconds": 0})
    out = b.video_info("BV1xx411c7mD")
    assert "测试视频" in out and "up主" in out


def test_governor_budgets_and_backoff():
    from adapters.bilibili import BiliGovernor

    gov = BiliGovernor(
        {"read_per_hour": 3, "read_per_day": 5, "request_interval_seconds": 0}
    )
    for _ in range(3):
        assert gov.allow_read() == ""
        gov.record_read()
    assert "预算" in gov.allow_read()  # 超出 3/时
    gov.record_throttle_hit()
    assert "暂停" in gov.allow_read()  # 退避中
    assert "暂停" in gov.allow_write()


def test_login_flow_mocked(tmp_path, monkeypatch):
    import types
    import urllib.request

    cred = str(tmp_path / "bili.json")

    class FakeResp:
        def __init__(self, url, payload, set_cookie=None):
            self._url = url
            self._p = json.dumps(payload).encode("utf-8")
            self.headers = types.SimpleNamespace(get_all=lambda k: set_cookie or [])

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n=-1):
            return self._p

    def fake_urlopen(req, timeout):
        url = req.full_url
        if "generate" in url:
            return FakeResp(url, {"code": 0, "data": {"qrcode_key": "KEY1", "url": "http://qr"}})
        if "poll" in url:
            return FakeResp(url, {"data": {"code": 0}})
        if "nav" in url:
            return FakeResp(
                url,
                {"data": {"isLogin": True, "uname": "她", "mid": 123}},
                set_cookie=["SESSDATA=abc; Path=/;", "bili_jct=xyz; Path=/;", "buvid3=uv; Path=/;"],
            )
        return FakeResp(url, {})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    b = BilibiliAdapter({"min_interval_seconds": 0}, credentials_path=cred)
    start = b.login_start()
    assert start["qrcode_key"] == "KEY1"
    poll = b.login_poll()
    assert poll["status"] == "success"
    assert b.logged_in
    assert os.path.isfile(cred)
