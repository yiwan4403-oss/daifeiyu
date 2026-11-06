"""记忆管理（Phase 1 最小版）：保存六类记忆 + FTS5 检索。

后续 Phase 2 在此接口后加入 LLM 仲裁（ADD/UPDATE/DELETE/NOOP）、
五因子显著性、时间衰减与关联图。
"""

import json
import time

KINDS = ("episodic", "semantic", "associative", "emotional", "procedural", "autobiographical")


class MemoryManager:
    def __init__(self, conn) -> None:
        self.conn = conn

    def save(
        self,
        kind: str,
        content: str,
        source: str = "self",
        salience: float = 0.5,
        links: list | None = None,
    ) -> int:
        assert kind in KINDS, f"未知记忆类型: {kind}"
        ts = time.time()
        cur = self.conn.execute(
            "INSERT INTO memories(kind, content, source, salience, ts, links) "
            "VALUES (?,?,?,?,?,?)",
            (kind, content, source, salience, ts, json.dumps(links or [])),
        )
        self.conn.commit()
        return cur.lastrowid

    def search(self, query: str, k: int = 5) -> list[str]:
        """FTS5 优先，失败退化为 LIKE。"""
        try:
            rows = self.conn.execute(
                "SELECT m.content FROM memory_fts f JOIN memories m ON m.rowid = f.rowid "
                "WHERE memory_fts MATCH ? ORDER BY rank LIMIT ?",
                (query, k),
            ).fetchall()
            if rows:
                return [r[0] for r in rows]
        except Exception:
            pass
        like = f"%{query}%"
        rows = self.conn.execute(
            "SELECT content FROM memories WHERE content LIKE ? ORDER BY salience DESC LIMIT ?",
            (like, k),
        ).fetchall()
        return [r[0] for r in rows]

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
