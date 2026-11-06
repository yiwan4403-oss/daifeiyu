"""自传系统：把身份 + 高显著性记忆写成第一人称自传，注入上下文。"""

import asyncio
import time

from core.model_gateway import ModelGateway

AUTOBIO_PROMPT = (
    "根据下面关于你自己的信息，写一段第一人称的自我介绍（100 字内）。"
    "只写这段介绍本身，不要列表、不要标题。"
)


class AutobiographyManager:
    def __init__(self, cfg: dict, components: dict) -> None:
        m = cfg["model"]
        light = cfg.get("task_models", {}).get("light", m["model"])
        self.gateway = ModelGateway(
            {
                "base_url": m["base_url"],
                "api_key_env": m.get("api_key_env", "DEEPSEEK_API_KEY"),
                "model": light,
                "timeout_seconds": int(m.get("timeout_seconds", 60)),
                "max_tokens": 300,
                "temperature": 0.5,
                "retries": 1,
            }
        )
        self.memory = components["memories"]
        self.identity = components["identity"]

    def latest(self) -> str:
        rows = self.memory.conn.execute(
            "SELECT content FROM memories WHERE kind='autobiographical' "
            "AND decay_state != 'lost' ORDER BY id DESC LIMIT 1"
        ).fetchall()
        return rows[0][0] if rows else ""

    def _compose_sync(self) -> str:
        if not getattr(self.gateway, "api_key", ""):
            return ""
        ident = self.identity.get()
        salient = self.memory.conn.execute(
            "SELECT content FROM memories WHERE kind IN ('semantic','episodic','emotional') "
            "AND decay_state != 'lost' ORDER BY salience DESC LIMIT 15"
        ).fetchall()
        body = (
            f"名字：{ident.name}\n性格：{ident.core_persona or '（未设定）'}\n"
            "重要记忆：\n" + "\n".join(f"- {r[0]}" for r in salient)
        )
        try:
            text = self.gateway.chat(AUTOBIO_PROMPT, body).strip()
        except Exception:
            return ""
        if not text:
            return ""
        self.memory.save("autobiographical", text, source="self", salience=0.9)
        return text

    async def refresh_if_stale(self, max_age_hours: float = 24.0) -> str:
        """超过 max_age 小时没写过自传就重写一份。"""
        rows = self.memory.conn.execute(
            "SELECT ts, content FROM memories WHERE kind='autobiographical' "
            "AND decay_state != 'lost' ORDER BY id DESC LIMIT 1"
        ).fetchall()
        if rows and time.time() - rows[0][0] < max_age_hours * 3600:
            return rows[0][1]
        return await asyncio.to_thread(self._compose_sync)
