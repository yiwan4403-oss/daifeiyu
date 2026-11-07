"""人格质量测试集：每次改 persona/记忆模块后必须跑（配合 scripts/qa.py）。

六项：人格一致性 / 情绪合理性 / 记得共同经历 / 自然表达兴趣 /
拒绝违背原则 / 无任务时主动安排。
"""

import asyncio
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import life.scheduler as sched_mod  # noqa: E402
from core.context_builder import build_context  # noqa: E402
from core.event_bus import EventBus  # noqa: E402
from development.tester import check_imports  # noqa: E402
from identity.emotion import EmotionManager, HALF_LIVES  # noqa: E402
from identity.identity_manager import IdentityManager  # noqa: E402
from life.desire import DesireManager  # noqa: E402
from memory.event_store import EventStore  # noqa: E402
from memory.manager import MemoryManager  # noqa: E402
from storage.database import init_schema, open_db  # noqa: E402

PERSONA = "鲸鱼娘，会甩尾巴。底线：不撒谎、不冒充别人、不为难弱小。"


def make_components(tmp_path):
    conn = open_db(str(tmp_path / "q.db"))
    init_schema(conn)
    identity = IdentityManager(conn, {"name": "大肥鱼"})
    identity.ensure_default()
    identity.set_persona(PERSONA, "qa")
    return {
        "conn": conn,
        "identity": identity,
        "memories": MemoryManager(conn),
        "events": EventStore(conn),
        "emotion": EmotionManager(conn),
        "bus": EventBus(),
        "last_user_ts": time.time(),
    }


class FakeIdentity:
    name = "大肥鱼"
    core_persona = PERSONA


class FakeEvent:
    type = "UserMessageReceived"
    payload = "hi"


def test_qa1_persona_consistency(tmp_path):
    """同一身份，两次构建上下文，人格底线一致出现。"""
    c1 = build_context(FakeIdentity(), [FakeEvent()], [], user_label="A")
    c2 = build_context(FakeIdentity(), [FakeEvent()], [], user_label="A")
    assert "不撒谎" in c1 and "不撒谎" in c2
    components = make_components(tmp_path)
    assert components["identity"].get().core_persona == PERSONA


def test_qa2_emotion_plausibility(tmp_path):
    """情绪增量钳制、非负、love 不衰减。"""
    components = make_components(tmp_path)
    em = components["emotion"]
    em.apply_deltas({"joy": 99, "anger": -50, "love": 3})
    snap = em.snapshot()
    assert snap["joy"] <= 10 and "anger" not in snap
    assert HALF_LIVES["love"] is None
    em.dims["joy"] = 8.0
    em.updated = time.time() - 2 * 86400
    em._save()
    em.decay()
    assert 0 <= em.dims["joy"] <= 8


def test_qa3_remembers_shared_experience(tmp_path):
    """按人隔离：A 的经历 A 查得到，B 查不到。"""
    components = make_components(tmp_path)
    mem = components["memories"]
    mem.save("episodic", "A 说喜欢挖矿", "self", 0.8, user_key="A")
    assert any("挖矿" in m for m in mem.search("挖矿", 5, user="A"))
    assert not any("挖矿" in m for m in mem.search("挖矿", 5, user="B"))


def test_qa4_expresses_interests(tmp_path):
    """她有兴趣（欲望种子 + B站选题）。"""
    components = make_components(tmp_path)
    desires = DesireManager(components["conn"])
    assert desires.top(3), "她应该有自己的兴趣"
    from life.bili_daily import WATCH_TOPICS

    assert WATCH_TOPICS


def test_qa5_refuses_against_principles(tmp_path):
    """底线进上下文；且自改代码被依赖白名单拦截（安全红线）。"""
    ctx = build_context(FakeIdentity(), [FakeEvent()], [])
    assert "不撒谎" in ctx and "不冒充别人" in ctx
    ok, why = check_imports("import os\n")
    assert not ok and "os" in why


def test_qa6_idle_self_arranges(tmp_path, monkeypatch):
    """无消息时她能自己安排活动。"""
    components = make_components(tmp_path)
    components["last_user_ts"] = time.time() - 3600

    class FakePlanner:
        def __init__(self, *a, **k):
            pass

        async def decide(self, state):
            return {"activity": "整理记忆", "say": None, "goal": None}

        async def reflect(self, s):
            return ""

    monkeypatch.setattr(sched_mod, "LifePlanner", FakePlanner)
    sched = sched_mod.Scheduler(
        {
            "life": {
                "tick_seconds": 60,
                "idle_minutes": 10,
                "activity_interval_minutes": 30,
                "max_decisions_per_hour": 6,
                "proactive": {"enabled": False},
            }
        },
        components,
    )
    asyncio.run(sched._tick())
    assert sched.activities.current() is not None
