"""主动投递策略测试：免打扰、每日额度。"""

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from life import proactive as policy  # noqa: E402
from security.outbox import Outbox  # noqa: E402
from storage.database import init_schema, open_db  # noqa: E402

CFG = {"enabled": True, "max_per_day": 2, "quiet_start_hour": 23, "quiet_end_hour": 8}


def test_quiet_hours():
    assert policy.quiet_now(CFG, 23) is True
    assert policy.quiet_now(CFG, 2) is True
    assert policy.quiet_now(CFG, 7) is True
    assert policy.quiet_now(CFG, 8) is False
    assert policy.quiet_now(CFG, 15) is False


def test_daily_cap(tmp_path):
    conn = open_db(str(tmp_path / "p.db"))
    init_schema(conn)
    box = Outbox(conn)
    allowed, why = policy.can_send(conn, CFG, hour=15)
    assert allowed, why
    for i in range(2):
        tid = box.enqueue("proactive_qq", f"k{i}", {"text": str(i)})
        box.claim(tid)
        box.finish(tid, True)
    allowed, why = policy.can_send(conn, CFG, hour=15)
    assert not allowed and "额度" in why


def test_disabled_and_quiet_block(tmp_path):
    conn = open_db(str(tmp_path / "p2.db"))
    init_schema(conn)
    assert policy.can_send(conn, {**CFG, "enabled": False}, hour=15)[0] is False
    assert policy.can_send(conn, CFG, hour=2)[0] is False
