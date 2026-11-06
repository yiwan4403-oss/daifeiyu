"""上下文构建：身份 + 最近事件 + 相关记忆 → system 文本。"""


def build_context(identity, recent_events: list, related_memories: list) -> str:
    parts = [f"你是 {identity.name}。", identity.core_persona or ""]
    if related_memories:
        parts.append("相关记忆：\n" + "\n".join(f"- {m}" for m in related_memories))
    if recent_events:
        parts.append(
            "最近发生：\n" + "\n".join(f"- [{e.type}] {e.payload[:80]}" for e in recent_events)
        )
    parts.append("用自然、简短的中文回答，一两句话。")
    return "\n".join(p for p in parts if p)
