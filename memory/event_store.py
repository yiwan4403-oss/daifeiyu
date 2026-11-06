"""原始事件存储：只增，永不只存总结。"""

import time
from dataclasses import dataclass


@dataclass
class Event:
    type: str
    scope: str
    source: str
    actor: str
    payload: str
    ts: float


class EventStore:
    def __init__(self, conn) -> None:
        self.conn = conn

    def append(
        self,
        event_type: str,
        scope: str = "private",
        source: str = "user",
        actor: str = "",
        payload: str = "",
    ) -> int:
        ts = time.time()
        payload = "".join(
            c for c in payload if c in "\n\t" or (ord(c) >= 32 and ord(c) < 0xD800)
        )  # 规范化：去控制字符/孤立代理（防 GBK 乱码入库）
        cur = self.conn.execute(
            "INSERT INTO events(ts, type, scope, source, actor, payload) VALUES (?,?,?,?,?,?)",
            (ts, event_type, scope, source, actor, payload),
        )
        self.conn.commit()
        return cur.lastrowid

    def recent(self, n: int = 20) -> list[Event]:
        rows = self.conn.execute(
            "SELECT type, scope, source, actor, payload, ts FROM events ORDER BY id DESC LIMIT ?",
            (n,),
        ).fetchall()
        return [
            Event(type=r[0], scope=r[1], source=r[2], actor=r[3], payload=r[4], ts=r[5])
            for r in reversed(rows)
        ]
