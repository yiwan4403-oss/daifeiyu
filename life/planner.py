"""生活规划器：低频 LLM 决策（现在想做什么 / 要不要主动说话 / 要不要立新目标）。"""

import asyncio

from core.model_gateway import ModelGateway

PLAN_PROMPT = (
    "你是 Resident 的生活规划器。根据当前状态，选择现在要做的一件事。\n"
    "可用活动：发呆、整理记忆、写日记、想想某个朋友、休息、学点新东西、等朋友来聊天。\n"
    '输出 JSON：{"activity": "整理记忆", "say": null, "goal": null}。\n'
    "- activity 必须从可用活动里选一个\n"
    "- say：如果想主动跟朋友说句话，写 20 字以内；不想就 null\n"
    "- goal：如果冒出一个值得长期做的事，一句话描述；没有就 null\n"
    "只输出 JSON，不要解释。"
)

REFLECT_PROMPT = (
    "根据你最近的经历，用一句话（40 字内）写下你对自己的观察或经验总结。只输出这句话。"
)


class LifePlanner:
    def __init__(self, cfg: dict, components: dict) -> None:
        m = cfg["model"]
        light = cfg.get("task_models", {}).get("light", m["model"])
        self.gateway = ModelGateway(
            {
                "base_url": m["base_url"],
                "api_key_env": m.get("api_key_env", "DEEPSEEK_API_KEY"),
                "model": light,
                "timeout_seconds": int(m.get("timeout_seconds", 60)),
                "max_tokens": 200,
                "temperature": 0.4,
                "retries": 1,
            }
        )
        self.components = components

    def decide_sync(self, state_text: str) -> dict:
        if not getattr(self.gateway, "api_key", ""):
            return {}
        import json
        import re

        try:
            raw = self.gateway.chat(PLAN_PROMPT, state_text)
        except Exception:
            return {}
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return {}
        try:
            data = json.loads(m.group(0))
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}
        return data

    async def decide(self, state_text: str) -> dict:
        return await asyncio.to_thread(self.decide_sync, state_text)

    def reflect_sync(self, activities_summary: str) -> str:
        if not getattr(self.gateway, "api_key", ""):
            return ""
        try:
            return self.gateway.chat(REFLECT_PROMPT, activities_summary).strip()
        except Exception:
            return ""

    async def reflect(self, activities_summary: str) -> str:
        return await asyncio.to_thread(self.reflect_sync, activities_summary)
