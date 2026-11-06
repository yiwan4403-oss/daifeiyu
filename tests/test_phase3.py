"""Phase 3 测试：欲望/目标/活动/规划/调度节拍/主动发言闸门。"""

import asyncio
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import life.scheduler as sched_mod  # noqa: E402
from core.event_bus import EventBus  # noqa: E402
from identity.emotion import EmotionManager  # noqa: E402
from identity.identity_manager import IdentityManager  # noqa: E402
from life.activities import ActivityManager  # noqa: E402
from life.desire import DesireManager  # noqa: E402
from life.goals import GoalManager  # noqa: E402
from life.scheduler import Scheduler  # noqa: E402
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
        "bus": EventBus(),
        "emotion": EmotionManager(conn),
        "last_user_ts": time.time(),
    }


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
        "budget": {"daily_usd": 1.0, "usd_per_mtok_in": 0.28, "usd_per_mtok_out": 1.68},
        "life": {
            "tick_seconds": 60,
            "idle_minutes": 10,
            "activity_interval_minutes": 30,
            "max_decisions_per_hour": 6,
            "reflect_every_activities": 2,
            "proactive": {
                "enabled": True,
                "start_hour": 0,
                "end_hour": 24,
                "min_gap_minutes": 1,
            },
        },
    }


def test_desire_and_goal(tmp_path):
    components = make_components(tmp_path)
    desires = DesireManager(components["conn"])
    top = desires.top(3)
    assert top, "种子欲望应存在"
    name = top[0][0]
    before = dict(top)[name]
    desires.feed(name, -0.3)
    after = dict(desires.top(5))[name]
    assert after < before

    goals = GoalManager(components["conn"])
    gid = goals.create("学会红石电路", priority=1)
    assert goals.list_active(5)[0]["text"] == "学会红石电路"
    goals.set_status(gid, "done")
    assert goals.count_active() == 0


def test_activity_lifecycle(tmp_path):
    components = make_components(tmp_path)
    acts = ActivityManager(components["conn"])
    acts.start("整理记忆")
    assert acts.current()["kind"] == "整理记忆"
    acts.start("休息")
    assert acts.current()["kind"] == "休息"
    acts.end("睡了一会儿")
    assert acts.current() is None
    assert "休息" in acts.today_summary()


def test_scheduler_idle_tick(tmp_path, monkeypatch):
    components = make_components(tmp_path)
    components["last_user_ts"] = time.time() - 3600
    cfg = make_cfg()

    class FakePlanner:
        def __init__(self, *a, **k):
            pass

        async def decide(self, state):
            return {"activity": "整理记忆", "say": "在吗", "goal": "学会红石"}

        async def reflect(self, s):
            return "整理记忆让我更清醒"

    monkeypatch.setattr(sched_mod, "LifePlanner", FakePlanner)
    got = []
    components["bus"].subscribe("proactive", got.append)
    sched = Scheduler(cfg, components)
    asyncio.run(sched._tick())

    count = components["conn"].execute(
        "SELECT COUNT(*) FROM activities WHERE kind='整理记忆'"
    ).fetchone()[0]
    assert count == 1
    assert any(g["text"] == "学会红石" for g in sched.goals.list_active(5))
    assert got == ["在吗"]
    assert components["events"].recent(5)[-1].type == "ActivityStarted"

    # 活动间隔未到：再 tick 不新增
    asyncio.run(sched._tick())
    count2 = components["conn"].execute(
        "SELECT COUNT(*) FROM activities WHERE kind='整理记忆'"
    ).fetchone()[0]
    assert count2 == 1


def test_scheduler_not_idle(tmp_path, monkeypatch):
    components = make_components(tmp_path)
    components["last_user_ts"] = time.time()  # 刚聊过
    cfg = make_cfg()

    class FakePlanner:
        def __init__(self, *a, **k):
            pass

        async def decide(self, state):
            raise AssertionError("不该被调用")

        async def reflect(self, s):
            return ""

    monkeypatch.setattr(sched_mod, "LifePlanner", FakePlanner)
    sched = Scheduler(cfg, components)
    asyncio.run(sched._tick())  # 不抛错即可
    assert sched.activities.current() is None


def test_proactive_gap_gate(tmp_path, monkeypatch):
    components = make_components(tmp_path)
    components["last_user_ts"] = time.time() - 3600
    cfg = make_cfg()

    class FakePlanner:
        def __init__(self, *a, **k):
            pass

        async def decide(self, state):
            return {"activity": "发呆", "say": "又是我"}

        async def reflect(self, s):
            return ""

    monkeypatch.setattr(sched_mod, "LifePlanner", FakePlanner)
    got = []
    components["bus"].subscribe("proactive", got.append)
    sched = Scheduler(cfg, components)
    asyncio.run(sched._tick())
    assert got == ["又是我"]
    sched._last_activity_ts = 0.0  # 绕过活动间隔，只看发言闸门
    asyncio.run(sched._tick())
    assert got == ["又是我"]  # 1 分钟内不重复主动
