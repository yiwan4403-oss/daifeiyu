"""双日记：生活日记（经历）与内心日记（反思），同日互引，分别注入上下文。"""

import asyncio
import time
from datetime import datetime

from core.model_gateway import ModelGateway

LIFE_PROMPT = (
    "根据下面这些今天发生的事，写一篇生活日记：今天经历了什么、做了什么、遇到了谁。"
    "3 到 5 句，平实记录，不评价、不抒情。只输出日记正文。"
)

INNER_PROMPT = (
    "根据今天的经历和你的情绪，写一篇内心日记：今天你在意什么、产生了什么想法、"
    "对某些事或某些人的看法有没有变化。这是反思，不是摘要——写下你的心路，"
    "可以引用生活日记里的事，但不要复述。3 到 5 句。只输出日记正文。"
)


class Diary:
    def __init__(self, components: dict, cfg: dict) -> None:
        m = cfg["model"]
        light = cfg.get("task_models", {}).get("light", m["model"])
        self.gateway = ModelGateway(
            {
                "base_url": m["base_url"],
                "api_key_env": m.get("api_key_env", "DEEPSEEK_API_KEY"),
                "model": light,
                "timeout_seconds": int(m.get("timeout_seconds", 60)),
                "max_tokens": 400,
                "temperature": 0.5,
                "retries": 1,
            }
        )
        self.memory = components["memories"]
        self.emotion = components.get("emotion")
        self.conn = components["conn"]

    def _today(self) -> str:
        return time.strftime("%Y-%m-%d")

    def exists(self, day: str, kind: str) -> bool:
        row = self.conn.execute(
            "SELECT id FROM memories WHERE kind='autobiographical' "
            "AND json_extract(meta, '$.diary')=? AND json_extract(meta, '$.date')=?",
            (kind, day),
        ).fetchone()
        return row is not None

    def latest(self, kind: str) -> str:
        row = self.conn.execute(
            "SELECT content FROM memories WHERE kind='autobiographical' "
            "AND json_extract(meta, '$.diary')=? AND decay_state != 'lost' "
            "ORDER BY id DESC LIMIT 1",
            (kind,),
        ).fetchone()
        return row[0] if row else ""

    def _day_facts(self, day: str) -> str:
        start = datetime.strptime(day, "%Y-%m-%d").timestamp()
        end = start + 86400
        events = self.conn.execute(
            "SELECT type, actor, payload FROM events WHERE ts>=? AND ts<? ORDER BY id LIMIT 40",
            (start, end),
        ).fetchall()
        acts = self.conn.execute(
            "SELECT kind, summary FROM activities WHERE started_at>=? AND started_at<?",
            (start, end),
        ).fetchall()
        lines = [f"[{t}] {a or ''} {p[:60]}" for t, a, p in events]
        lines += [f"活动：{k}（{s or ''}）" for k, s in acts]
        return "\n".join(lines) or "（今天没什么特别的事）"

    def _write_sync(self, kind: str, prompt: str, body: str, links: list) -> str:
        if not getattr(self.gateway, "api_key", ""):
            return ""
        try:
            text = self.gateway.chat(prompt, body).strip()
        except Exception:
            return ""
        if not text:
            return ""
        mid = self.memory.save(
            "autobiographical",
            text,
            source="self",
            salience=0.75,
            links=links,
            meta={"diary": kind, "date": self._today()},
        )
        return text

    async def daily(self) -> dict:
        day = self._today()
        out = {}
        if not self.exists(day, "life"):
            text = await asyncio.to_thread(
                self._write_sync, "life", LIFE_PROMPT, self._day_facts(day), []
            )
            out["life"] = bool(text)
        if not self.exists(day, "inner"):
            life = self.latest("life")
            emotion = self.emotion.summary() if self.emotion else ""
            body = f"今天的生活日记：\n{life}\n\n我此刻的情绪：{emotion}"
            # 互引：找到 life 日记的 id 作为 links
            row = self.conn.execute(
                "SELECT id FROM memories WHERE json_extract(meta,'$.diary')='life' "
                "AND json_extract(meta,'$.date')=? ORDER BY id DESC LIMIT 1",
                (day,),
            ).fetchone()
            links = [row[0]] if row else []
            await asyncio.to_thread(
                self._write_sync, "inner", INNER_PROMPT, body, links
            )
            out["inner"] = self.latest("inner") != ""
        return out
