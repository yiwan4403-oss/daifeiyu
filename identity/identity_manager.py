"""身份管理：核心身份严格保护，变更留历史。"""

import json
import time
from dataclasses import dataclass


@dataclass
class Identity:
    name: str
    core_persona: str = ""
    preferences: dict = None

    def __post_init__(self):
        if self.preferences is None:
            self.preferences = {}


class IdentityManager:
    def __init__(self, conn, cfg: dict) -> None:
        self.conn = conn
        self.default_name = cfg.get("name", "Resident")
        self._cache: Identity | None = None

    def ensure_default(self) -> None:
        cur = self.conn.execute("SELECT name, core_persona, preferences_json FROM identity WHERE id=1")
        row = cur.fetchone()
        if row is None:
            now = time.strftime("%Y-%m-%dT%H:%M:%S")
            self.conn.execute(
                "INSERT INTO identity(id, name, core_persona, preferences_json, created_at, updated_at) "
                "VALUES (1, ?, '', '{}', ?, ?)",
                (self.default_name, now, now),
            )
            self.conn.commit()

    def get(self) -> Identity:
        if self._cache is not None:
            return self._cache
        cur = self.conn.execute("SELECT name, core_persona, preferences_json FROM identity WHERE id=1")
        row = cur.fetchone()
        if row is None:
            self.ensure_default()
            cur = self.conn.execute("SELECT name, core_persona, preferences_json FROM identity WHERE id=1")
            row = cur.fetchone()
        ident = Identity(
            name=row[0],
            core_persona=row[1],
            preferences=json.loads(row[2] or "{}"),
        )
        self._cache = ident
        return ident

    def set_persona(self, new_persona: str, reason: str, approved_by: str = "human") -> None:
        """基础性格有限变化：留历史。核心身份（name）修改需 L3 人工确认。"""
        old = self.get().core_persona
        now = time.time()
        self.conn.execute(
            "INSERT INTO persona_history(ts, field, old_value, new_value, reason, approved_by) "
            "VALUES (?,?,?,?,?,?)",
            (now, "core_persona", old, new_persona, reason, approved_by),
        )
        self.conn.execute(
            "UPDATE identity SET core_persona=?, updated_at=? WHERE id=1",
            (new_persona, time.strftime("%Y-%m-%dT%H:%M:%S")),
        )
        self.conn.commit()
        self._cache = None

    def touch(self) -> None:
        self.conn.execute(
            "UPDATE identity SET updated_at=? WHERE id=1",
            (time.strftime("%Y-%m-%dT%H:%M:%S"),),
        )
        self.conn.commit()
