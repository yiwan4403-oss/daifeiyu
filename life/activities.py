"""活动管理：当前正在做什么（同一时间只有一个活动）。"""

import time


class ActivityManager:
    def __init__(self, conn) -> None:
        self.conn = conn

    def current(self) -> dict | None:
        row = self.conn.execute(
            "SELECT id, kind, started_at FROM activities WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return {"id": row[0], "kind": row[1], "started_at": row[2]} if row else None

    def start(self, kind: str) -> int:
        cur = self.conn.execute(
            "UPDATE activities SET ended_at=? WHERE ended_at IS NULL", (time.time(),)
        )
        self.conn.execute(
            "INSERT INTO activities(kind, started_at) VALUES (?,?)", (kind, time.time())
        )
        self.conn.commit()
        return self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def end(self, summary: str = "") -> None:
        self.conn.execute(
            "UPDATE activities SET ended_at=?, summary=? WHERE ended_at IS NULL",
            (time.time(), summary),
        )
        self.conn.commit()

    def today_summary(self) -> str:
        rows = self.conn.execute(
            "SELECT kind, started_at, ended_at, summary FROM activities "
            "WHERE started_at > ? ORDER BY started_at DESC LIMIT 20",
            (time.time() - 86400,),
        ).fetchall()
        return "; ".join(
            f"{r[0]}({int((r[2] or time.time()) - r[1]) // 60}分钟)" for r in rows
        ) or "今天还没做什么"
