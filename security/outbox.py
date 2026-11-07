"""Outbox：外部副作用动作的持久化队列（幂等 + 状态机 + 崩溃恢复）。"""

import json
import time


class Outbox:
    """所有外部动作（发 QQ、装插件、发私信…）先落表再执行。

    - dedupe_key 唯一：同一动作重复入队只产生一行，防重复执行
    - 状态机：pending → executing → done / failed
    - recover()：崩溃遗留的 executing 行复位为 pending（超时未完成视为中断）
    """

    def __init__(self, conn) -> None:
        self.conn = conn

    def enqueue(self, action: str, dedupe_key: str, payload: dict | None = None) -> int:
        """返回任务 id；若已存在同 dedupe_key 且未完成，返回已有 id（幂等）。"""
        now = time.time()
        row = self.conn.execute(
            "SELECT id FROM outbox WHERE dedupe_key=?",
            (dedupe_key,),
        ).fetchone()
        if row:
            return row[0]  # 幂等：任何状态下同一 key 只有一行
        cur = self.conn.execute(
            "INSERT INTO outbox(dedupe_key, action, payload, status, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?)",
            (
                dedupe_key,
                action,
                json.dumps(payload or {}, ensure_ascii=False),
                "pending",
                now,
                now,
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def claim(self, task_id: int) -> dict | None:
        """取一个 pending 任务并置为 executing。"""
        row = self.conn.execute(
            "SELECT id, action, payload FROM outbox WHERE id=? AND status='pending'",
            (task_id,),
        ).fetchone()
        if row is None:
            return None
        self.conn.execute(
            "UPDATE outbox SET status='executing', attempts=attempts+1, updated_at=? WHERE id=?",
            (time.time(), task_id),
        )
        self.conn.commit()
        try:
            payload = json.loads(row[2] or "{}")
        except Exception:
            payload = {}
        return {"id": row[0], "action": row[1], "payload": payload}

    def finish(self, task_id: int, ok: bool, detail: str = "") -> None:
        self.conn.execute(
            "UPDATE outbox SET status=?, detail=?, updated_at=? WHERE id=?",
            ("done" if ok else "failed", detail, time.time(), task_id),
        )
        self.conn.commit()

    def pending(self, k: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, action, payload, status, attempts FROM outbox "
            "WHERE status IN ('pending','failed') ORDER BY id LIMIT ?",
            (k,),
        ).fetchall()
        return [
            {"id": r[0], "action": r[1], "payload": r[2], "status": r[3], "attempts": r[4]}
            for r in rows
        ]

    def recover(self, stale_seconds: float = 300) -> int:
        """重启时：executing 且超过 stale_seconds 未更新的任务复位为 pending。"""
        cutoff = time.time() - stale_seconds
        cur = self.conn.execute(
            "UPDATE outbox SET status='pending' WHERE status='executing' AND updated_at < ?",
            (cutoff,),
        )
        self.conn.commit()
        return cur.rowcount
