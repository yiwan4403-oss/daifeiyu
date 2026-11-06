"""记忆仲裁 + 情绪评估：LLM 一次调用输出记忆操作与情绪增量。"""

import asyncio
import json
import re

from core.model_gateway import ModelGateway

OPS_PROMPT = (
    "你是记忆与情绪仲裁器。根据本轮对话，输出一个 JSON 对象：\n"
    '{"ops": [...], "emotion": {...}}\n'
    "ops 每项形如 {\"op\": \"ADD|UPDATE|DELETE\", \"content\": \"...\", \"target\": null}：\n"
    "- 用户明确告知关于自己或世界的事实 → ADD\n"
    "- 与已有记忆矛盾 → UPDATE（target 填旧记忆 id）或先 DELETE 再 ADD\n"
    "- 闲聊、客套、无信息量 → 不输出该项\n"
    "- 内容写成一句陈述，带主语；最多 3 条\n"
    "emotion 是这场对话引起的情绪增量，键只能用：joy, sadness, anger, fear, surprise, "
    "disgust, trust, anticipation, calm, excitement, boredom, love, belonging, pride, shame, "
    "guilt, envy, gratitude, loneliness, nostalgia, hope, curiosity, tiredness, hunger, pain, "
    "arousal；值为 -10 到 10 的数字；没有明显情绪变化就给空对象 {}。\n"
    "只输出 JSON，不要解释。"
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
                "max_tokens": 500,
                "temperature": 0.2,
                "retries": 1,
            }
        )
        self.memory = components["memories"]

    def decide_sync(self, user_text: str, reply: str) -> dict:
        if not getattr(self.gateway, "api_key", ""):
            return {"ops": [], "emotion": {}}
        existing = self.memory.search(user_text, 4)
        body = (
            f"本轮对话：\n用户：{user_text}\n我：{reply}\n"
            "已有相关记忆：\n" + "\n".join(f"- {t}" for t in existing)
        )
        try:
            raw = self.gateway.chat(OPS_PROMPT, body)
        except Exception:
            return {"ops": [], "emotion": {}}
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return {"ops": [], "emotion": {}}
        try:
            data = json.loads(m.group(0))
        except Exception:
            return {"ops": [], "emotion": {}}
        ops = [
            o for o in data.get("ops", [])
            if isinstance(o, dict) and o.get("op") in ("ADD", "UPDATE", "DELETE")
        ][:3]
        emotion = data.get("emotion")
        if not isinstance(emotion, dict):
            emotion = {}
        return {"ops": ops, "emotion": emotion}

    async def apply(self, user_text: str, reply: str) -> dict:
        result = await asyncio.to_thread(self.decide_sync, user_text, reply)
        for op in result["ops"]:
            content = str(op.get("content", "")).strip()
            if op["op"] in ("ADD", "UPDATE") and not content:
                continue
            self.memory.apply_op(op["op"], content, target=op.get("target"))
        emotion = result["emotion"]
        if emotion:
            em = self.__dict__.get("_emotion")
            if em is None:
                return result
            em.apply_deltas(emotion)
        return result

    def bind_emotion(self, emotion) -> None:
        self._emotion = emotion
