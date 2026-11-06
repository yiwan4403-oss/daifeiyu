"""欲望系统：为什么想做（区别于 Goal/Task/Activity）。"""

import time

SEEDS = (
    ("想和朋友们聊天", "social", 0.6),
    ("整理自己的记忆", "self", 0.5),
    ("学点新东西", "growth", 0.6),
    ("好好休息", "rest", 0.4),
)


class DesireManager:
    def __init__(self, conn) -> None:
        self.conn = conn
        self._seed()

    def _seed(self) -> None:
        if self.conn.execute("SELECT COUNT(*) FROM desires").fetchone()[0]:
            return
        for name, source, strength in SEEDS:
            self.conn.execute(
                "INSERT INTO desires(name, strength, source, created_at) VALUES (?,?,?,?)",
                (name, strength, source, time.time()),
            )
        self.conn.commit()

    def add(self, name: str, strength: float = 0.5, source: str = "self") -> int:
        cur = self.conn.execute(
            "INSERT INTO desires(name, strength, source, created_at) VALUES (?,?,?,?)",
            (name, max(0.0, min(1.0, strength)), source, time.time()),
        )
        self.conn.commit()
        return cur.lastrowid

    def top(self, k: int = 3) -> list[tuple[str, float]]:
        rows = self.conn.execute(
            "SELECT name, strength FROM desires ORDER BY strength DESC LIMIT ?", (k,)
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def feed(self, name: str, amount: float = -0.3) -> None:
        """满足一次欲望：强度下降；其他欲望随时间略涨。"""
        self.conn.execute(
            "UPDATE desires SET strength = MAX(0, MIN(1, strength + ?)) WHERE name=?",
            (amount, name),
        )
        self.conn.execute(
            "UPDATE desires SET strength = MIN(1, strength + 0.05) WHERE name != ?",
            (name,),
        )
        self.conn.commit()
