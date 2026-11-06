import json
import os
import sys
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.context_builder import build_context  # noqa: E402
from core.event_bus import EventBus  # noqa: E402
from core.model_gateway import GatewayError, ModelGateway  # noqa: E402
from identity.identity_manager import IdentityManager  # noqa: E402
from memory.event_store import EventStore  # noqa: E402
from memory.manager import MemoryManager  # noqa: E402
from storage.database import init_schema, open_db  # noqa: E402


def test_identity_persists_across_restart(tmp_path):
    db = str(tmp_path / "r.db")
    conn = open_db(db)
    init_schema(conn)
    ident = IdentityManager(conn, {"name": "大肥鱼"})
    ident.ensure_default()
    assert ident.get().name == "大肥鱼"
    ident.set_persona("一条鲸鱼娘，会甩尾巴", "测试", "human")
    conn.close()

    # 模拟重启：新连接、新 manager，身份仍在
    conn2 = open_db(db)
    ident2 = IdentityManager(conn2, {"name": "大肥鱼"})
    got = ident2.get()
    assert got.core_persona == "一条鲸鱼娘，会甩尾巴"


def test_event_store_roundtrip(tmp_path):
    conn = open_db(str(tmp_path / "e.db"))
    init_schema(conn)
    events = EventStore(conn)
    events.append("UserMessageReceived", "private", "user", "user", "你好")
    recent = events.recent(10)
    assert recent[-1].type == "UserMessageReceived"
    assert recent[-1].payload == "你好"


def test_memory_save_and_search(tmp_path):
    conn = open_db(str(tmp_path / "m.db"))
    init_schema(conn)
    mem = MemoryManager(conn)
    mem.save("episodic", "用户说过他喜欢挖矿", "self", 0.8)
    mem.save("semantic", "服务器里末影人身上有金苹果", "self", 0.9)
    hits = mem.search("挖矿", 5)
    assert any("挖矿" in h for h in hits)


def test_event_bus_delivery():
    bus = EventBus()
    got = []
    bus.subscribe("user_message", lambda p: got.append(p))
    bus.publish("user_message", "hello")
    assert got == ["hello"]


def test_context_builder():
    class FakeIdentity:
        name = "大肥鱼"
        core_persona = "鲸鱼娘"

    class FakeEvent:
        type = "UserMessageReceived"
        payload = "早上好"

    ctx = build_context(FakeIdentity(), [FakeEvent()], ["用户喜欢挖矿"])
    assert "大肥鱼" in ctx
    assert "鲸鱼娘" in ctx
    assert "挖矿" in ctx


class FakeResp:
    def __init__(self, data: dict):
        self._data = json.dumps(data).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._data


def test_gateway_chat(monkeypatch, tmp_path):
    def fake_urlopen(req, timeout):
        return FakeResp(
            {
                "choices": [{"message": {"content": "你好呀"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    gw = ModelGateway(
        {
            "base_url": "http://mock",
            "api_key_env": "DEEPSEEK_API_KEY",
            "model": "deepseek-flash",
            "timeout_seconds": 5,
            "max_tokens": 100,
            "temperature": 0.9,
        }
    )
    assert gw.chat("system", "hi") == "你好呀"
    assert gw.usage[-1]["in"] == 10


def test_gateway_missing_key():
    gw = ModelGateway(
        {
            "base_url": "http://mock",
            "api_key_env": "NO_SUCH_ENV_VAR",
            "model": "m",
            "timeout_seconds": 5,
            "max_tokens": 10,
            "temperature": 0.5,
        }
    )
    with pytest.raises(GatewayError):
        gw.chat("s", "u")
