"""记忆仲裁：LLM 决定 ADD/UPDATE/DELETE/NOOP（借 Mem0 思路，决策可查不黑盒）。"""

import asyncio
import json
import re

from core.model_gateway import ModelGateway

OPS_PROMPT = (
    "你是记忆仲裁器。根据本轮对话决定要写入哪些长期记忆。\n"
    "只输出 JSON 数组，每项形如 {\"op\": \"ADD\", \"content\": \"...\", \"target\": null}。\n"
    "规则：\n"
    "- 用户明确告知关于自己或世界的事实 → ADD\n"
    "- 与已有记忆矛盾 → UPDATE（target 填旧记忆 id）或先 DELETE 再 ADD\n"
    "- 闲聊、客套、无信息量 → NOOP（不输出该项）\n"
    "- 内容写成一句陈述，带主语，不带\"用户说\"这类包装\n"
    "- 最多 3 条。"
)


class MemoryArbiter:
    def __init__(self, cfg: dict, components: dict) -> None:
        m = cfg["model"]
        light = cfg.get("task_models", {}).get("light", m["model"])
        self.gateway = ModelGateway(
            {
                "base_url": m["base_url"],
                "api_key_env": m.get("api_key_env", "DEEPSEEK_API_KEY"),
                "model": light,
                "timeout_seconds": int(m.get("timeout_seconds", 60)),
                "max_tokens": 400,
                "temperature": 0.2,
                "retries": 1,
            }
        )
        self.memory = components["memories"]

    def decide_sync(self, user_text: str, reply: str) -> list[dict]:
        if not self.gateway.api_key:
            return []
        existing = self.memory.search(user_text, 4)
        body = (
            f"本轮对话：\n用户：{user_text}\n我：{reply}\n"
            "已有相关记忆：\n" + "\n".join(f"- [{i}] {t}" for i, t in enumerate(existing))
        )
        try:
            raw = self.gateway.chat(OPS_PROMPT, body)
        except Exception:
            return []
        m = re.search(r"\[[\s\S]*\]", raw)
        if not m:
            return []
        try:
            ops = json.loads(m.group(0))
        except Exception:
            return []
        out = []
        for op in ops:
            if isinstance(op, dict) and op.get("op") in ("ADD", "UPDATE", "DELETE"):
                if op.get("content") or op.get("target") is not None:
                    out.append(op)
        return out[:3]

    async def apply(self, user_text: str, reply: str) -> list[dict]:
        ops = await asyncio.to_thread(self.decide_sync, user_text, reply)
        applied = []
        for op in ops:
            content = str(op.get("content", "")).strip()
            if op["op"] in ("ADD", "UPDATE") and not content:
                continue
            ok = self.memory.apply_op(op["op"], content, target=op.get("target"))
            if ok:
                applied.append(op)
        return applied
