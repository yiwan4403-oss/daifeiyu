"""上下文构建：身份 + 情绪 + 关系 + 自传 + 信念 + 相关记忆 + 最近事件。"""


def build_context(
    identity,
    recent_events: list,
    related_memories: list,
    emotion_summary: str = "",
    relationship: str = "",
    autobiography: str = "",
    beliefs: list | None = None,
    user_label: str = "",
    inner_diary: str = "",
) -> str:
    parts = [f"你是 {identity.name}。", identity.core_persona or ""]
    if user_label:
        parts.append(f"现在跟你说话的人是：{user_label}（不同的人要分开对待，别把别人的事算到他头上）。")
    if inner_diary:
        parts.append(f"你最近的内心日记（你的想法，可作参考）：{inner_diary[:160]}。")
    if autobiography:
        parts.append(f"你对自己的认知（自传）：{autobiography[:200]}")
    if emotion_summary:
        parts.append(f"你现在的情绪：{emotion_summary}。")
    if relationship:
        parts.append(f"与当前对话者的关系：{relationship}。")
    if beliefs:
        parts.append("你确认过的事实：\n" + "\n".join(f"- {b}" for b in beliefs[:8]))
    if related_memories:
        parts.append("相关记忆：\n" + "\n".join(f"- {m}" for m in related_memories))
    if recent_events:
        parts.append(
            "最近发生：\n" + "\n".join(f"- [{e.type}] {e.payload[:80]}" for e in recent_events)
        )
    parts.append("用自然、简短的中文回答，一两句话。")
    return "\n".join(p for p in parts if p)
