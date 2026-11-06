"""关系系统：多维（familiarity/trust/affinity）+ 关系事件，交互自动更新。"""

import json
import time


class RelationshipManager:
    def __init__(self, conn) -> None:
        self.conn = conn

    def get(self, name: str) -> dict:
        row = self.conn.execute(
            "SELECT familiarity, trust, affinity, status, known_json, unverified_json, updated_at "
            "FROM relationships WHERE name=? AND scope='private'",
            (name,),
        ).fetchone()
        if row is None:
            self.conn.execute(
                "INSERT INTO relationships(name, scope, familiarity, trust, affinity, status, "
                "known_json, unverified_json, updated_at) VALUES (?,?,0,0,0,'',?,?,?)",
                (name, "private", "[]", "[]", time.time()),
            )
            self.conn.commit()
            row = (0.0, 0.0, 0.0, "", "[]", "[]", time.time())
        return {
            "name": name,
            "familiarity": row[0],
            "trust": row[1],
            "affinity": row[2],
            "status": row[3],
            "known": json.loads(row[4] or "[]"),
            "unverified": json.loads(row[5] or "[]"),
            "updated_at": row[6],
        }

    def touch(self, name: str, affinity_delta: float = 0.0, trust_delta: float = 0.0, note: str = "") -> dict:
        rel = self.get(name)
        now = time.time()
        familiarity = min(1.0, rel["familiarity"] + 0.02)  # 每次交互 +0.02
        affinity = max(-1.0, min(1.0, rel["affinity"] + affinity_delta))
        trust = max(0.0, min(1.0, rel["trust"] + trust_delta))
        known = rel["known"]
        if note and note not in known:
            known = (known + [note])[-50:]
        self.conn.execute(
            "UPDATE relationships SET familiarity=?, trust=?, affinity=?, status=?, "
            "known_json=?, updated_at=? WHERE name=? AND scope='private'",
            (familiarity, trust, affinity, rel["status"], json.dumps(known, ensure_ascii=False), now, name),
        )
        self.conn.commit()
        rel.update(familiarity=familiarity, trust=trust, affinity=affinity, known=known, updated_at=now)
        return rel

    def add_unverified(self, name: str, claim: str) -> None:
        rel = self.get(name)
        items = rel["unverified"]
        if claim not in items:
            items.append(claim)
        self.conn.execute(
            "UPDATE relationships SET unverified_json=? WHERE name=? AND scope='private'",
            (json.dumps(items, ensure_ascii=False), name),
        )
        self.conn.commit()

    def summary(self, name: str) -> str:
        rel = self.get(name)
        stage = (
            "陌生" if rel["familiarity"] < 0.1
            else "眼熟" if rel["familiarity"] < 0.3
            else "朋友" if rel["familiarity"] < 0.6
            else "亲近" if rel["familiarity"] < 0.85
            else "很熟"
        )
        return (
            f"{name}：{stage}（熟悉 {rel['familiarity']:.2f}，信任 {rel['trust']:.2f}，"
            f"好感 {rel['affinity']:+.2f}）"
        )
