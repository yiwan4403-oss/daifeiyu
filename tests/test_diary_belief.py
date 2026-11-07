"""双日记测试：生活/内心分离、同日互引、反思产物（fake LLM）。"""

import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import life.diary as diary_mod  # noqa: E402
from identity.emotion import EmotionManager  # noqa: E402
from identity.identity_manager import IdentityManager  # noqa: E402
from memory.event_store import EventStore  # noqa: E402
from memory.manager import MemoryManager  # noqa: E402
from storage.database import init_schema, open_db  # noqa: E402


def make_components(tmp_path):
    conn = open_db(str(tmp_path / "d.db"))
    init_schema(conn)
    identity = IdentityManager(conn, {"name": "大肥鱼"})
    identity.ensure_default()
    components = {
        "conn": conn,
        "identity": identity,
        "memories": MemoryManager(conn),
        "events": EventStore(conn),
        "emotion": EmotionManager(conn),
    }
    components["events"].append("UserMessageReceived", "private", "user", "123", "今天好累")
    return components


def make_cfg():
    return {
        "model": {
            "base_url": "http://mock",
            "api_key_env": "DEEPSEEK_API_KEY",
            "model": "deepseek-flash",
            "timeout_seconds": 5,
            "max_tokens": 100,
            "temperature": 0.9,
        },
        "task_models": {"light": "deepseek-flash"},
    }


def test_diary_life_and_inner_separate(tmp_path, monkeypatch):
    components = make_components(tmp_path)

    class FakeGateway:
        api_key = "sk-test"

        def __init__(self, *a, **k):
            pass

        def chat(self, prompt, body):
            if "内心日记" in prompt:
                return "我发现自己在没人说话时会有点安静，可能想找点新事情做。"
            return "今天和 123 聊了几句，整理了一下记忆。"

    monkeypatch.setattr(diary_mod, "ModelGateway", FakeGateway)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

    diary = diary_mod.Diary(components, make_cfg())
    result = asyncio.run(diary.daily())
    assert result.get("life") is True
    assert result.get("inner") is True

    life = diary.latest("life")
    inner = diary.latest("inner")
    assert "聊了几句" in life
    assert "有点安静" in inner  # 内心日记是反思，不是复述

    # 同日互引：inner 的 links 指向 life 日记
    conn = components["conn"]
    inner_id = conn.execute(
        "SELECT id FROM memories WHERE json_extract(meta,'$.diary')='inner' ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    life_id = conn.execute(
        "SELECT id FROM memories WHERE json_extract(meta,'$.diary')='life' ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    links = conn.execute("SELECT links FROM memories WHERE id=?", (inner_id,)).fetchone()[0]
    assert str(life_id) in links

    # 幂等：再跑一天不会重复写
    asyncio.run(diary.daily())
    count = conn.execute(
        "SELECT COUNT(*) FROM memories WHERE json_extract(meta,'$.diary') IN ('life','inner')"
    ).fetchone()[0]
    assert count == 2
