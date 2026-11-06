"""Belief 分层：来源 + 验证状态。模型输出不得自动标 verified。"""

import time


class BeliefManager:
    def __init__(self, conn) -> None:
        self.conn = conn

    def add(self, content: str, source: str, verified: int = 0, confidence: float = 0.5) -> int:
        """source: user / external / self / llm / hypothesis。
        verified=1 只能来自人工确认或外部权威核实，LLM 输出默认 0。"""
        assert verified in (0, 1)
        cur = self.conn.execute(
            "INSERT INTO beliefs(content, source, verified, confidence, ts, updated_at) "
            "VALUES (?,?,?,?,?,?)",
            (content, source, verified, confidence, time.time(), time.time()),
        )
        self.conn.commit()
        return cur.lastrowid

    def verify(self, belief_id: int, ok: bool = True) -> None:
        self.conn.execute(
            "UPDATE beliefs SET verified=?, updated_at=? WHERE id=?",
            (1 if ok else 0, time.time(), belief_id),
        )
        self.conn.commit()

    def list_unverified(self, k: int = 10) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, content, source FROM beliefs WHERE verified=0 ORDER BY ts DESC LIMIT ?",
            (k,),
        ).fetchall()
        return [{"id": r[0], "content": r[1], "source": r[2]} for r in rows]

    def list_verified(self, k: int = 10) -> list[str]:
        rows = self.conn.execute(
            "SELECT content FROM beliefs WHERE verified=1 ORDER BY ts DESC LIMIT ?",
            (k,),
        ).fetchall()
        return [r[0] for r in rows]
