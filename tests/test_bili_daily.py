"""B 站生物钟测试：挑选、分享额度、沉默衰减、窗口判定。"""

import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.event_bus import EventBus  # noqa: E402
from identity.identity_manager import IdentityManager  # noqa: E402
from life.bili_daily import BiliDaily  # noqa: E402
from memory.event_store import EventStore  # noqa: E402
from memory.manager import MemoryManager  # noqa: E402
from storage.database import init_schema, open_db  # noqa: E402


class FakeBili:
    def __init__(self, items):
        self._items = items

    def search_items(self, query, k=5):
        return self._items[:k]


def make_components(tmp_path, owner_ids=None, seed_event_ts=None):
    conn = open_db(str(tmp_path / "r.db"))
    init_schema(conn)
    identity = IdentityManager(conn, {"name": "大肥鱼"})
    identity.ensure_default()
    components = {
        "conn": conn,
        "identity": identity,
        "events": EventStore(conn),
        "memories": MemoryManager(conn),
        "bus": EventBus(),
        "qq_owner_ids": set(owner_ids or []),
    }
    if seed_event_ts is not None:
        eid = components["events"].append(
            "UserMessageReceived", "private", "user", "123", "hi"
        )
        conn.execute("UPDATE events SET ts=? WHERE id=?", (seed_event_ts, eid))
        conn.commit()
    return components


def make_cfg(tmp_path):
    return {
        "resident": {"data_dir": str(tmp_path / "data")},
        "bili_daily": {
            "window_start_hour": 0,
            "window_end_hour": 24,
            "max_share_per_day": 3,
            "deep_read": 3,
            "skip_chance": 0.0,
            "topics": ["测试"],
        },
    }


def test_run_session_writes_and_shares(tmp_path):
    import time

    components = make_components(tmp_path, owner_ids=["123"], seed_event_ts=time.time())
    components["adapters"] = {
        "bilibili": FakeBili(
            [
                {"title": "红石进阶", "bvid": "BV1", "play": 999},
                {"title": "建筑教程", "bvid": "BV2", "play": 500},
            ]
        )
    }
    got = []
    components["bus"].subscribe("proactive", got.append)
    cfg = make_cfg(tmp_path)
    bd = BiliDaily(components, cfg)
    summary = asyncio.run(bd.run_session())
    assert "红石进阶" in summary
    assert any("红石进阶" in m for m in components["memories"].search("红石", 5))
    assert got and "红石进阶" in got[0]
    assert bd._state["shared"] == 1


def test_silence_decay_quota(tmp_path):
    import time

    # 7 天没互动 → 0
    components = make_components(
        tmp_path, owner_ids=["123"], seed_event_ts=time.time() - 8 * 86400
    )
    bd = BiliDaily(components, make_cfg(tmp_path))
    assert bd._quota() == 0
    # 3 天没互动 → 2
    components2 = make_components(
        tmp_path, owner_ids=["123"], seed_event_ts=time.time() - 4 * 86400
    )
    bd2 = BiliDaily(components2, make_cfg(tmp_path))
    assert bd2._quota() == 2
    # 刚互动 → 3
    components3 = make_components(tmp_path, owner_ids=["123"])
    components3["events"].append("UserMessageReceived", "private", "user", "123", "hi")
    bd3 = BiliDaily(components3, make_cfg(tmp_path))
    assert bd3._quota() == 3


def test_maybe_wake_outside_window(tmp_path):
    components = make_components(tmp_path)
    components["adapters"] = {"bilibili": FakeBili([])}
    cfg = make_cfg(tmp_path)
    cfg["bili_daily"]["window_start_hour"] = 23
    cfg["bili_daily"]["window_end_hour"] = 24
    bd = BiliDaily(components, cfg)
    from datetime import datetime

    if 23 <= datetime.now().hour < 24:
        # 恰好在窗口内时跳过该断言
        return
    assert bd.maybe_wake() is False
