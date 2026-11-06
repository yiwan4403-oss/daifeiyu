"""持续进化（Phase 6 v1）：健康检查、运行指标、经验学习、自我维护。"""

import time


class Metrics:
    def __init__(self, conn) -> None:
        self.conn = conn

    def snapshot(self) -> dict:
        usage = self.conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(in_tokens),0), COALESCE(SUM(out_tokens),0), "
            "COALESCE(SUM(cost_est),0) FROM model_usage"
        ).fetchone()
        memories = self.conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        events = self.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        activities = self.conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
        return {
            "llm_calls": usage[0],
            "tokens_in": usage[1],
            "tokens_out": usage[2],
            "cost_usd": round(usage[3] or 0.0, 4),
            "memories": memories,
            "events": events,
            "activities": activities,
        }


class SelfMaintenance:
    """定期：插件健康检查（异常自动禁用并记 audit）、指标快照、经验沉淀。"""

    def __init__(self, components: dict) -> None:
        self.components = components
        self.conn = components["conn"]
        self.metrics = Metrics(self.conn)
        self._last_run = 0.0
        self.interval = 6 * 3600  # 6 小时一次

    def _audit(self, actor, action, resource, result, detail=""):
        self.conn.execute(
            "INSERT INTO audit(ts, actor, action, resource, result, detail) VALUES (?,?,?,?,?,?)",
            (time.time(), actor, action, resource, result, detail),
        )
        self.conn.commit()

    async def run_once(self) -> dict:
        report: dict = {"plugins": {}}
        dev = self.components.get("dev")
        if dev is not None:
            for pid in dev.loaded():
                try:
                    version, plugin = dev.loader._loaded[pid]
                    health = plugin.health()
                    report["plugins"][pid] = {"version": version, "health": health}
                    self._audit("self", "health_check", pid, "ok", health)
                except Exception as exc:
                    dev.loader.disable(pid)
                    self._audit("self", "health_check", pid, "disabled", str(exc))
                    report["plugins"][pid] = {"version": "?", "health": f"异常已禁用: {exc}"}
        # 经验沉淀：把指标观察写进 procedural 记忆（不调 LLM，纯规则）
        m = self.metrics.snapshot()
        note = (
            f"运行指标：{m['llm_calls']} 次模型调用，{m['tokens_in'] + m['tokens_out']} tokens，"
            f"约 {m['cost_usd']} USD；记忆 {m['memories']} 条，事件 {m['events']} 条，"
            f"活动 {m['activities']} 次。"
        )
        self.components["memories"].save(
            "procedural", note, source="self", salience=0.4
        )
        report["metrics"] = self.metrics.snapshot()
        self._last_run = time.time()
        return report

    async def maybe_run(self) -> dict | None:
        if time.time() - self._last_run < self.interval:
            return None
        return await self.run_once()
