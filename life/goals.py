"""目标管理：希望达到什么结果（可暂停/取消/完成）。"""

import time


class GoalManager:
    def __init__(self, conn) -> None:
        self.conn = conn

    def create(self, text: str, desire_id: int | None = None, priority: int = 0) -> int:
        cur = self.conn.execute(
            "INSERT INTO goals(text, desire_id, priority, status, created_at) "
            "VALUES (?,?,?,'pending',?)",
            (text, desire_id, priority, time.time()),
        )
        self.conn.commit()
        return cur.lastrowid

    def list_active(self, k: int = 10) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, text, priority FROM goals WHERE status IN ('pending','active') "
            "ORDER BY priority DESC, id ASC LIMIT ?",
            (k,),
        ).fetchall()
        return [{"id": r[0], "text": r[1], "priority": r[2]} for r in rows]

    def set_status(self, goal_id: int, status: str) -> None:
        assert status in ("pending", "active", "paused", "done", "failed")
        self.conn.execute("UPDATE goals SET status=? WHERE id=?", (status, goal_id))
        self.conn.commit()

    def count_active(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM goals WHERE status IN ('pending','active')"
        ).fetchone()[0]
