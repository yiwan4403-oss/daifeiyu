"""PydanticAI 编排层：工具循环 + 任务分级模型 + 预算护栏。

PydanticAI 只承担 loop 与 tooling；身份、记忆、生活状态全部来自 deps。
"""

import os
import time
from dataclasses import dataclass

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from core.context_builder import build_context


class BudgetError(Exception):
    pass


@dataclass
class ResidentDeps:
    identity: object
    memory: object
    events: object
    arbiter: object
    emotion: object = None
    relationships: object = None
    autobiography: object = None
    beliefs: object = None


def _remember_tool(ctx: RunContext[ResidentDeps], text: str) -> str:
    """把值得长期记住的事实写进记忆。"""
    ctx.deps.memory.save("semantic", text, source="self", salience=0.7)
    return "记住了"


def _recall_tool(ctx: RunContext[ResidentDeps], query: str) -> str:
    """检索自己的记忆。"""
    hits = ctx.deps.memory.search(query, 3)
    return "\n".join(hits) if hits else "没想起相关的事"


class ResidentAgent:
    def __init__(self, cfg: dict, components: dict) -> None:
        m = cfg["model"]
        self.base_url = m["base_url"]
        self.api_key = os.environ.get(m.get("api_key_env", "DEEPSEEK_API_KEY"), "")
        self.max_tokens = int(m.get("max_tokens", 300))
        self.temperature = float(m.get("temperature", 0.9))
        self.tier_models = {
            "chat": m["model"],
            "reason": m["model"],
            "light": m["model"],
        }
        self.tier_models.update(cfg.get("task_models", {}))
        self.budget = cfg.get("budget", {})
        self.conn = components["conn"]
        self.deps = ResidentDeps(
            identity=components["identity"],
            memory=components["memories"],
            events=components["events"],
            arbiter=components.get("arbiter"),
            emotion=components.get("emotion"),
            relationships=components.get("relationships"),
            autobiography=components.get("autobiography"),
            beliefs=components.get("beliefs"),
        )
        self._spent_today = 0.0
        self._current_user = "user"

    def _make(self, tier: str) -> OpenAIChatModel:
        return OpenAIChatModel(
            self.tier_models.get(tier, self.tier_models["chat"]),
            provider=OpenAIProvider(base_url=self.base_url, api_key=self.api_key),
        )

    def _system(self, ctx: RunContext[ResidentDeps]) -> str:
        d = ctx.deps
        query = getattr(ctx, "prompt", None) or ""
        ident = d.identity.get()
        related = d.memory.search(query, 5)
        recent = d.events.recent(20)
        emotion_summary = d.emotion.summary() if d.emotion else ""
        relationship = d.relationships.summary(self._current_user) if d.relationships else ""
        autobiography = d.autobiography.latest() if d.autobiography else ""
        beliefs = d.beliefs.list_verified(8) if d.beliefs else []
        return build_context(
            ident, recent, related,
            emotion_summary=emotion_summary,
            relationship=relationship,
            autobiography=autobiography,
            beliefs=beliefs,
        )

    def _check_budget(self) -> None:
        cap = float(self.budget.get("daily_usd", 0.0))
        if cap <= 0:
            return
        if self._spent_today >= cap:
            raise BudgetError(f"今日预算已用完（{cap} USD），明天再来。")

    def _record_usage(self, usage, tier: str) -> None:
        try:
            # v2 中 result.usage 是属性；拿到的是 RunUsage 对象
            totals = usage.totals()
            tin = getattr(totals, "input", 0) or 0
            tout = getattr(totals, "output", 0) or 0
        except Exception:
            tin = tout = 0
        usd = (
            tin / 1_000_000 * float(self.budget.get("usd_per_mtok_in", 0.0))
            + tout / 1_000_000 * float(self.budget.get("usd_per_mtok_out", 0.0))
        )
        self._spent_today += usd
        self.conn.execute(
            "INSERT INTO model_usage(ts, task_class, model, in_tokens, out_tokens, cost_est, ok) "
            "VALUES (?,?,?,?,?,?,1)",
            (time.time(), tier, self.tier_models.get(tier, ""), tin, tout, usd),
        )
        self.conn.commit()

    async def chat(self, user_text: str, tier: str = "chat") -> str:
        self._check_budget()
        agent = Agent(
            self._make(tier),
            deps_type=ResidentDeps,
            instructions=self._system,
            tools=[_remember_tool, _recall_tool],
            retries=1,
        )
        try:
            result = await agent.run(user_text, deps=self.deps)
        except Exception as exc:
            if "401" in str(exc) or "Authentication" in str(exc):
                return "[网关错误] API Key 无效或未配置"
            raise
        self._record_usage(result.usage, tier)
        out = result.output
        return out.strip() if isinstance(out, str) else str(out)
