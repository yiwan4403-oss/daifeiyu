"""Phase 2 测试：情绪衰减、关系、信念、自传、升级后的上下文。"""

import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import memory.autobiography as autobiography_mod  # noqa: E402
from identity.emotion import EmotionManager  # noqa: E402
from identity.relationships import RelationshipManager  # noqa: E402
from memory.beliefs import BeliefManager  # noqa: E402
from storage.database import init_schema, open_db  # noqa: E402
from core.context_builder import build_context  # noqa: E402
from identity.identity_manager import IdentityManager  # noqa: E402


def make_components(tmp_path):
    conn = open_db(str(tmp_path / "r.db"))
    init_schema(conn)
    identity = IdentityManager(conn, {"name": "大肥鱼"})
    identity.ensure_default()
    return {"conn": conn, "identity": identity}


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


def test_emotion_decay_math(tmp_path):
    components = make_components(tmp_path)
    em = EmotionManager(components["conn"])
    em.dims["joy"] = 8.0
    em.dims["love"] = 5.0
    em.updated = __import__("time").time() - 2 * 86400  # 2 天前
    em._save()
    em.decay()
    # joy 半衰期 0.5 天，2 天 → 8 * 0.5^4 = 0.5
    assert abs(em.dims["joy"] - 0.5) < 0.01
    # love 不衰减
    assert em.dims["love"] == 5.0


def test_emotion_apply_deltas_and_snapshot(tmp_path):
    components = make_components(tmp_path)
    em = EmotionManager(components["conn"])
    em.apply_deltas({"joy": 3, "unknown_key": 99, "anger": -5})
    snap = em.snapshot()
    assert snap["joy"] == 3.0
    assert "unknown_key" not in snap
    assert "anger" not in snap  # 负增量钳到 0 后消失


def test_relationship_familiarity_grows(tmp_path):
    components = make_components(tmp_path)
    rel = RelationshipManager(components["conn"])
    r1 = rel.touch("e好耶p", affinity_delta=0.05, note="喜欢挖矿")
    r2 = rel.touch("e好耶p")
    assert r2["familiarity"] > r1["familiarity"]
    assert r1["affinity"] == 0.05
    assert "喜欢挖矿" in r2["known"]


def test_belief_layers(tmp_path):
    components = make_components(tmp_path)
    b = BeliefManager(components["conn"])
    bid = b.add("模型自己推测的事", source="llm", verified=0)
    assert bid in [x["id"] for x in b.list_unverified()]
    # 未升级到 knowledge/view 前不算“确认过的事实”
    b.verify(bid, ok=True)
    assert b.list_verified() == []
    # 演化：observation → hypothesis → knowledge，历史留痕
    b.evolve(bid, "hypothesis", "有一些证据", evidence=["看到一次"])
    assert b.get(bid)["stage"] == "hypothesis"
    b.evolve(bid, "knowledge", "多次验证通过", evidence=["又看到两次"])
    assert b.list_verified() == ["模型自己推测的事"]
    hist = b.history(bid)
    assert hist[0]["old_stage"] == "hypothesis" and hist[0]["new_stage"] == "knowledge"
    assert len(hist) == 2


def test_autobiography_compose(tmp_path, monkeypatch):
    components = make_components(tmp_path)
    from memory.manager import MemoryManager

    components["memories"] = MemoryManager(components["conn"])
    components["memories"].save("semantic", "我喜欢挖矿", "self", 0.9)
    cfg = make_cfg()

    class FakeGateway:
        api_key = "sk-test"

        def __init__(self, *a, **k):
            pass

        def chat(self, system, user):
            return "我是一条鲸鱼娘，喜欢挖矿和陪朋友聊天。"

    monkeypatch.setattr(autobiography_mod, "ModelGateway", FakeGateway)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    auto = autobiography_mod.AutobiographyManager(cfg, components)
    text = asyncio.run(auto.refresh_if_stale(24.0))
    assert "鲸鱼娘" in text
    assert auto.latest() == text


def test_context_includes_phase2_extras(tmp_path):
    class FakeIdentity:
        name = "大肥鱼"
        core_persona = "鲸鱼娘"

    class FakeEvent:
        type = "UserMessageReceived"
        payload = "hi"

    ctx = build_context(
        FakeIdentity(),
        [FakeEvent()],
        ["相关记忆"],
        emotion_summary="joy3",
        relationship="e好耶p：朋友",
        autobiography="我是鲸鱼娘",
        beliefs=["玩家喜欢挖矿"],
    )
    assert "joy3" in ctx
    assert "e好耶p：朋友" in ctx
    assert "我是鲸鱼娘" in ctx
    assert "玩家喜欢挖矿" in ctx
