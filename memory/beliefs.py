"""Belief 分层与演化：observation → hypothesis → knowledge → view。

新证据可修正观点；每次变化写 belief_history（旧判断与原因永不删除）。
模型输出不得自动标 verified；升级到 knowledge/view 需要证据。
"""

import json
import time

STAGES = ("observation", "hypothesis", "knowledge", "view")


class BeliefManager:
    def __init__(self, conn) -> None:
        self.conn = conn

    def add(
        self,
        content: str,
        source: str,
        verified: int = 0,
        confidence: float = 0.5,
        stage: str = "observation",
        evidence: list | None = None,
    ) -> int:
        assert verified in (0, 1)
        assert stage in STAGES
        cur = self.conn.execute(
            "INSERT INTO beliefs(content, source, verified, confidence, stage, evidence, ts, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                content,
                source,
                verified,
                confidence,
                stage,
                json.dumps(evidence or [], ensure_ascii=False),
                time.time(),
                time.time(),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def get(self, belief_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT id, content, source, verified, confidence, stage, evidence FROM beliefs WHERE id=?",
            (belief_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "content": row[1],
            "source": row[2],
            "verified": row[3],
            "confidence": row[4],
            "stage": row[5],
            "evidence": json.loads(row[6] or "[]"),
        }

    def evolve(
        self,
        belief_id: int,
        new_stage: str,
        reason: str,
        new_content: str = "",
        evidence: list | None = None,
    ) -> bool:
        """升/降级或修正：写历史，再更新。"""
        assert new_stage in STAGES
        old = self.get(belief_id)
        if old is None:
            return False
        content = new_content or old["content"]
        now = time.time()
        self.conn.execute(
            "INSERT INTO belief_history(belief_id, old_stage, new_stage, old_content, "
            "new_content, reason, ts) VALUES (?,?,?,?,?,?,?)",
            (belief_id, old["stage"], new_stage, old["content"], content, reason, now),
        )
        merged = list(old["evidence"])
        for e in evidence or []:
            if e not in merged:
                merged.append(e)
        self.conn.execute(
            "UPDATE beliefs SET stage=?, content=?, evidence=?, updated_at=? WHERE id=?",
            (new_stage, content, json.dumps(merged, ensure_ascii=False), now, belief_id),
        )
        self.conn.commit()
        return True

    def verify(self, belief_id: int, ok: bool = True) -> None:
        """人工/权威核实：verified 标记。"""
        self.conn.execute(
            "UPDATE beliefs SET verified=?, updated_at=? WHERE id=?",
            (1 if ok else 0, time.time(), belief_id),
        )
        self.conn.commit()

    def history(self, belief_id: int, k: int = 10) -> list[dict]:
        rows = self.conn.execute(
            "SELECT old_stage, new_stage, old_content, new_content, reason, ts "
            "FROM belief_history WHERE belief_id=? ORDER BY id DESC LIMIT ?",
            (belief_id, k),
        ).fetchall()
        return [
            {
                "old_stage": r[0],
                "new_stage": r[1],
                "old_content": r[2],
                "new_content": r[3],
                "reason": r[4],
                "ts": r[5],
            }
            for r in rows
        ]

    def list_stage(self, stage: str, k: int = 10) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, content, source, verified, confidence FROM beliefs "
            "WHERE stage=? ORDER BY updated_at DESC LIMIT ?",
            (stage, k),
        ).fetchall()
        return [
            {"id": r[0], "content": r[1], "source": r[2], "verified": r[3], "confidence": r[4]}
            for r in rows
        ]

    def list_unverified(self, k: int = 10) -> list[dict]:
        return self.list_stage("observation", k) + self.list_stage("hypothesis", k)

    def list_verified(self, k: int = 10) -> list[str]:
        rows = self.conn.execute(
            "SELECT content FROM beliefs WHERE stage IN ('knowledge','view') ORDER BY ts DESC LIMIT ?",
            (k,),
        ).fetchall()
        return [r[0] for r in rows]
