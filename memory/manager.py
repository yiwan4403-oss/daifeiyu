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
        meta: dict | None = None,
        user_key: str = "",
    ) -> int:
        assert kind in KINDS, f"未知记忆类型: {kind}"
        ts = time.time()
        cur = self.conn.execute(
            "INSERT INTO memories(kind, content, source, salience, ts, links, meta, user_key) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (kind, content, source, salience, ts, json.dumps(links or []),
             json.dumps(meta or {}, ensure_ascii=False), user_key),
        )
        mid = cur.lastrowid
        self.conn.execute(
            "INSERT INTO memory_fts(rowid, content) VALUES (?,?)", (mid, content)
        )
        self.conn.commit()
        return mid

    def _fts_sync(self, mid: int, content: str) -> None:
        self.conn.execute("DELETE FROM memory_fts WHERE rowid=?", (mid,))
        self.conn.execute("INSERT INTO memory_fts(rowid, content) VALUES (?,?)", (mid, content))

    def apply_op(self, op: str, content: str, target=None, user_key: str = "") -> bool:
        """ADD/UPDATE/DELETE：先查重，再落库；DELETE 不物理删，标记 lost 保留原档。"""
        if op == "ADD":
            row = self.conn.execute(
                "SELECT id FROM memories WHERE content=? AND decay_state!='lost'",
                (content,),
            ).fetchone()
            if row:
                return False  # 已存在
            self.save(
                "semantic", content, source="llm",
                salience=self._salience(content), user_key=user_key,
            )
            return True
        if op == "UPDATE":
            row_id = target if isinstance(target, int) else None
            if row_id is None:
                row = self.conn.execute(
                    "SELECT id FROM memories WHERE content=? AND decay_state!='lost'",
                    (content,),
                ).fetchone()
                row_id = row[0] if row else None
            if row_id is None:
                return self.apply_op("ADD", content)
            self.conn.execute(
                "UPDATE memories SET content=?, source='llm', ts=?, decay_state='active' WHERE id=?",
                (content, time.time(), row_id),
            )
            self._fts_sync(row_id, content)
            self.conn.commit()
            return True
        if op == "DELETE":
            if isinstance(target, int):
                self.conn.execute(
                    "UPDATE memories SET decay_state='lost' WHERE id=?", (target,)
                )
                self.conn.execute("DELETE FROM memory_fts WHERE rowid=?", (target,))
                self.conn.commit()
                return True
            rows = self.conn.execute(
                "SELECT id FROM memories WHERE content=? AND decay_state!='lost'",
                (content,),
            ).fetchall()
            for (mid,) in rows:
                self.conn.execute(
                    "UPDATE memories SET decay_state='lost' WHERE id=?", (mid,)
                )
                self.conn.execute("DELETE FROM memory_fts WHERE rowid=?", (mid,))
            self.conn.commit()
            return bool(rows)
        return False

    def _salience(self, content: str) -> float:
        """五因子显著性（v1 简化）：情绪 0.3 + 自我相关 0.2 + 基础 0.5。"""
        emotional = 0.3 if any(w in content for w in EMOTION_WORDS) else 0.0
        self_related = 0.2 if any(w in content for w in ("大肥鱼", "主人", "我")) else 0.0
        return min(1.0, 0.5 + emotional + self_related)

    def consolidate(self) -> None:
        """衰减状态机：active→fade→lost；30 天内豁免。借 companion-emergence 阈值。"""
        now = time.time()
        rows = self.conn.execute(
            "SELECT id, salience, decay_state, ts, last_access FROM memories"
        ).fetchall()
        for mid, sal, state, ts, last_access in rows:
            if state == "lost":
                continue
            if ts and now - ts < 30 * 86400:
                continue  # 30 天豁免
            if state == "active" and sal < 0.25:
                self.conn.execute(
                    "UPDATE memories SET decay_state='fade' WHERE id=?", (mid,)
                )
            elif state == "fade":
                if sal < 0.10:
                    self.conn.execute(
                        "UPDATE memories SET decay_state='lost' WHERE id=?", (mid,)
                    )
                else:
                    self.conn.execute(
                        "UPDATE memories SET salience=salience*0.9 WHERE id=?", (mid,)
                    )
        self.conn.commit()

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]

    def search(self, query: str, k: int = 5, user: str | None = None) -> list[str]:
        """FTS5 优先，失败退化为 LIKE；排除已遗忘（lost）。

        user 给出时：优先返回该玩家的记忆 + 全局记忆（user_key 为空）。
        """
        if user:
            sql = (
                "SELECT m.content FROM memory_fts f JOIN memories m ON m.rowid = f.rowid "
                "WHERE memory_fts MATCH ? AND m.decay_state != 'lost' "
                "AND (m.user_key = '' OR m.user_key = ?) ORDER BY rank LIMIT ?"
            )
            args = (query, user, k)
        else:
            sql = (
                "SELECT m.content FROM memory_fts f JOIN memories m ON m.rowid = f.rowid "
                "WHERE memory_fts MATCH ? AND m.decay_state != 'lost' "
                "ORDER BY rank LIMIT ?"
            )
            args = (query, k)
        try:
            rows = self.conn.execute(sql, args).fetchall()
            if rows:
                return [r[0] for r in rows]
        except Exception:
            pass
        like = f"%{query}%"
        if user:
            rows = self.conn.execute(
                "SELECT content FROM memories WHERE content LIKE ? AND decay_state != 'lost' "
                "AND (user_key = '' OR user_key = ?) ORDER BY salience DESC LIMIT ?",
                (like, user, k),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT content FROM memories WHERE content LIKE ? AND decay_state != 'lost' "
                "ORDER BY salience DESC LIMIT ?",
                (like, k),
            ).fetchall()
        return [r[0] for r in rows]


EMOTION_WORDS = (
    "喜欢", "讨厌", "生气", "高兴", "难过", "害怕", "开心", "烦", "恨",
    "爱", "伤心", "激动", "失望", "惊喜",
)
