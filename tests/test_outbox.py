"""Outbox 测试：幂等、状态机、崩溃恢复。"""

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from security.outbox import Outbox  # noqa: E402
from storage.database import init_schema, open_db  # noqa: E402


def test_outbox_idempotent_and_claim(tmp_path):
    conn = open_db(str(tmp_path / "o.db"))
    init_schema(conn)
    box = Outbox(conn)
    t1 = box.enqueue("qq_send", "qq:1:2026-11-07:abc123", {"uid": "1", "text": "hi"})
    t2 = box.enqueue("qq_send", "qq:1:2026-11-07:abc123", {"uid": "1", "text": "hi"})
    assert t1 == t2  # 幂等

    task = box.claim(t1)
    assert task is not None and task["action"] == "qq_send"
    assert box.claim(t1) is None  # 已被认领

    box.finish(t1, True)
    # 完成后再入队同 key：done 不拦截，但 claim 不到（状态 done）
    t3 = box.enqueue("qq_send", "qq:1:2026-11-07:abc123", {})
    assert box.claim(t3) is None


def test_outbox_same_text_twice_not_swallowed(tmp_path):
    """同内容两次发送必须各自入队（去重键带 nonce）。"""
    conn = open_db(str(tmp_path / "o3.db"))
    init_schema(conn)
    box = Outbox(conn)
    a = box.enqueue("qq_send", "qq:1:reply:2026-11-08:111", {"text": "哈喽"})
    b = box.enqueue("qq_send", "qq:1:reply:2026-11-08:222", {"text": "哈喽"})
    assert a != b
    assert box.claim(a) is not None
    assert box.claim(b) is not None


def test_outbox_recover_stale_executing(tmp_path):
    conn = open_db(str(tmp_path / "o2.db"))
    init_schema(conn)
    box = Outbox(conn)
    t = box.enqueue("install_plugin", "install:dice:1.0.0", {})
    box.claim(t)
    # 模拟崩溃：executing 停在 10 分钟前
    conn.execute("UPDATE outbox SET updated_at=? WHERE id=?", (time.time() - 600, t))
    conn.commit()
    assert box.recover(stale_seconds=300) == 1
    task = box.claim(t)
    assert task is not None
    box.finish(t, True)
