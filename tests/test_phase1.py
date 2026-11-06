"""Phase 1 测试：仲裁、去重、显著性、衰减、系统提示词、预算、断点续接。"""

import asyncio
import json
import os
import sys
import types
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import memory.arbiter as arbiter_mod  # noqa: E402
from core.agent import BudgetError, ResidentAgent  # noqa: E402
from identity.identity_manager import IdentityManager  # noqa: E402
from memory.event_store import EventStore  # noqa: E402
from memory.manager import MemoryManager  # noqa: E402
from storage.database import init_schema, open_db  # noqa: E402


def make_components(tmp_path):
    conn = open_db(str(tmp_path / "r.db"))
    init_schema(conn)
    identity = IdentityManager(conn, {"name": "大肥鱼"})
    identity.ensure_default()
    return {
        "conn": conn,
        "identity": identity,
        "events": EventStore(conn),
        "memories": MemoryManager(conn),
    }


def make_cfg():
    return {
        "resident": {"name": "大肥鱼", "data_dir": "data"},
        "model": {
            "base_url": "http://mock",
            "api_key_env": "DEEPSEEK_API_KEY",
            "model": "deepseek-flash",
            "timeout_seconds": 5,
            "max_tokens": 100,
            "temperature": 0.9,
        },
        "task_models": {"chat": "deepseek-flash", "light": "deepseek-flash"},
        "budget": {"daily_usd": 1.0, "usd_per_mtok_in": 0.28, "usd_per_mtok_out": 1.68},
    }


def test_arbiter_decide_and_apply(tmp_path, monkeypatch):
    components = make_components(tmp_path)
    cfg = make_cfg()

    class FakeGateway:
        api_key = "sk-test"

        def __init__(self, *a, **k):
            pass

        def chat(self, system, user):
            return '{"ops":[{"op":"ADD","content":"玩家 e好耶p 喜欢挖矿"}],"emotion":{"joy":1}}'

    monkeypatch.setattr(arbiter_mod, "ModelGateway", FakeGateway)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    arb = arbiter_mod.MemoryArbiter(cfg, components)
    result = asyncio.run(arb.apply("我喜欢挖矿", "知道了"))
    assert result["ops"] and result["ops"][0]["op"] == "ADD"
    assert result["emotion"] == {"joy": 1}
    assert "挖矿" in components["memories"].search("挖矿", 5)[0]


def test_apply_op_dedupe_and_delete(tmp_path):
    components = make_components(tmp_path)
    mem = components["memories"]
    assert mem.apply_op("ADD", "玩家喜欢挖矿") is True
    assert mem.apply_op("ADD", "玩家喜欢挖矿") is False  # md5 级查重（同内容）
    mem.apply_op("DELETE", "玩家喜欢挖矿")
    assert all("挖矿" not in c for c in mem.search("挖矿", 10))


def test_salience_factors(tmp_path):
    components = make_components(tmp_path)
    mem = components["memories"]
    assert mem._salience("我喜欢大肥鱼") >= 0.7   # 情绪 + 自我相关
    assert mem._salience("明天可能下雨") == 0.5


def test_consolidate_decay_states(tmp_path):
    components = make_components(tmp_path)
    mem = components["memories"]
    conn = components["conn"]
    mid = mem.save("semantic", "旧事", "self", salience=0.20)
    # 旧记忆（>30 天）
    conn.execute("UPDATE memories SET ts=? WHERE id=?", (time.time() - 40 * 86400, mid))
    conn.commit()
    mem.consolidate()
    state = conn.execute("SELECT decay_state FROM memories WHERE id=?", (mid,)).fetchone()[0]
    assert state == "fade"
    conn.execute("UPDATE memories SET salience=0.05 WHERE id=?", (mid,))
    conn.commit()
    mem.consolidate()
    state = conn.execute("SELECT decay_state FROM memories WHERE id=?", (mid,)).fetchone()[0]
    assert state == "lost"


def test_system_prompt_includes_identity_and_memory(tmp_path):
    components = make_components(tmp_path)
    components["memories"].save("semantic", "用户喜欢挖矿", "self", 0.8)
    cfg = make_cfg()
    agent = ResidentAgent(cfg, components)
    ctx = types.SimpleNamespace(deps=agent.deps, prompt="挖矿")
    sys_prompt = agent._system(ctx)
    assert "大肥鱼" in sys_prompt
    assert "挖矿" in sys_prompt


def test_budget_guard(tmp_path):
    components = make_components(tmp_path)
    cfg = make_cfg()
    agent = ResidentAgent(cfg, components)
    agent._spent_today = 1.0  # 达到上限
    with pytest.raises(BudgetError):
        agent._check_budget()


def test_restart_continuity_phase1(tmp_path):
    db = str(tmp_path / "c.db")
    conn = open_db(db)
    init_schema(conn)
    ident = IdentityManager(conn, {"name": "大肥鱼"})
    ident.ensure_default()
    events = EventStore(conn)
    mem = MemoryManager(conn)
    events.append("UserMessageReceived", "private", "user", "user", "你好")
    mem.save("episodic", "用户说：你好；我回：你好呀", "self", 0.5)
    conn.close()

    conn2 = open_db(db)
    ident2 = IdentityManager(conn2, {"name": "大肥鱼"})
    assert ident2.get().name == "大肥鱼"
    assert EventStore(conn2).recent(5)[-1].payload == "你好"
    assert MemoryManager(conn2).count() == 1
    conn2.close()
