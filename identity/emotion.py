"""情绪系统：26 维 + 逐情绪半衰期衰减（companion-emergence 公式）。

衰减：new = old · (1/2)^(Δt / half_life)；< 0.01 视为消失。
love / belonging 不衰减。所有数值是内部状态模拟，不代表主观体验。
"""

import json
import time

# 半衰期（天）。core 快（小时级），complex 中速，body 最快；
# 初值可调，来源：companion-emergence 报告的取值区间（0.125–730 天）。
HALF_LIVES: dict[str, float | None] = {
    # core (11)
    "joy": 0.5, "sadness": 1.0, "anger": 0.75, "fear": 0.75,
    "surprise": 0.25, "disgust": 1.0, "trust": 7.0, "anticipation": 1.0,
    "calm": 0.5, "excitement": 0.5, "boredom": 0.5,
    # complex (11)
    "love": None, "belonging": None, "pride": 3.0, "shame": 2.0,
    "guilt": 2.0, "envy": 3.0, "gratitude": 2.0, "loneliness": 1.5,
    "nostalgia": 7.0, "hope": 5.0, "curiosity": 1.0,
    # body (4)
    "tiredness": 0.125, "hunger": 0.125, "pain": 0.25, "arousal": 0.125,
}

MIN_VALUE = 0.01


class EmotionManager:
    def __init__(self, conn) -> None:
        self.conn = conn
        row = conn.execute("SELECT dims, updated_at FROM emotion_state WHERE id=1").fetchone()
        if row is None:
            self.dims = {k: 0.0 for k in HALF_LIVES}
            self.updated = time.time()
            conn.execute(
                "INSERT INTO emotion_state(id, dims, updated_at) VALUES (1, ?, ?)",
                (json.dumps(self.dims), self.updated),
            )
            conn.commit()
        else:
            self.dims = json.loads(row[0])
            self.updated = float(row[1] or time.time())

    def _save(self) -> None:
        self.conn.execute(
            "UPDATE emotion_state SET dims=?, updated_at=? WHERE id=1",
            (json.dumps(self.dims), self.updated),
        )
        self.conn.commit()

    def decay(self) -> None:
        """按经过的时间衰减；不衰减的维度跳过；<MIN 删除。"""
        now = time.time()
        dt_days = (now - self.updated) / 86400.0
        if dt_days <= 0:
            return
        for name, half in HALF_LIVES.items():
            if half is None:
                continue
            old = float(self.dims.get(name, 0.0))
            if old == 0.0:
                continue
            new = old * (0.5 ** (dt_days / half))
            self.dims[name] = new if new >= MIN_VALUE else 0.0
        self.updated = now
        self._save()

    def apply_deltas(self, deltas: dict) -> None:
        """施加情绪增量（LLM 评估结果），幅度钳制在 [-10, 10]。"""
        self.decay()
        for name, delta in deltas.items():
            if name not in HALF_LIVES:
                continue
            try:
                delta = float(delta)
            except (TypeError, ValueError):
                continue
            delta = max(-10.0, min(10.0, delta))
            self.dims[name] = max(0.0, min(10.0, float(self.dims.get(name, 0.0)) + delta))
        self._save()

    def snapshot(self) -> dict:
        self.decay()
        return {k: round(v, 2) for k, v in self.dims.items() if v >= MIN_VALUE}

    def summary(self, top: int = 4) -> str:
        snap = self.snapshot()
        if not snap:
            return "情绪平稳"
        ranked = sorted(snap.items(), key=lambda kv: kv[1], reverse=True)[:top]
        return "、".join(f"{k}{v}" for k, v in ranked)
