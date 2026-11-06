"""CLI 适配器：本地聊天窗口（标准输入输出），带自主生活调度。"""

import asyncio
import time

from core.agent import BudgetError, ResidentAgent
from identity.emotion import EmotionManager
from identity.relationships import RelationshipManager
from life.scheduler import Scheduler
from memory.arbiter import MemoryArbiter
from memory.autobiography import AutobiographyManager
from memory.beliefs import BeliefManager

PRAISE = ("厉害", "谢谢", "可爱", "喜欢", "靠谱", "辛苦", "棒")
INSULT = ("傻", "蠢", "废物", "垃圾", "滚", "闭嘴", "杂种", "去死")


def _affinity_delta(text: str) -> float:
    d = 0.0
    d += 0.05 * sum(1 for w in PRAISE if w in text)
    d -= 0.08 * sum(1 for w in INSULT if w in text)
    return max(-0.2, min(0.2, d))


async def run_cli(components: dict, cfg: dict) -> None:
    components.setdefault("emotion", EmotionManager(components["conn"]))
    components.setdefault("relationships", RelationshipManager(components["conn"]))
    components.setdefault("beliefs", BeliefManager(components["conn"]))
    components.setdefault("autobiography", AutobiographyManager(cfg, components))
    components["last_user_ts"] = time.time()

    arbiter = components.get("arbiter") or MemoryArbiter(cfg, components)
    arbiter.bind_emotion(components["emotion"])
    components["arbiter"] = arbiter

    auto = components["autobiography"]
    narrative = await auto.refresh_if_stale(24.0)
    if narrative:
        print(f"[resident] 自传已更新（{len(narrative)} 字）")

    agent = ResidentAgent(cfg, components)
    ident = components["identity"].get()

    def on_proactive(text):
        print(f"她（主动）> {text}")

    components["bus"].subscribe("proactive", on_proactive)
    scheduler = Scheduler(cfg, components)
    sched_task = asyncio.create_task(scheduler.run())

    print(f"[resident] {ident.name} 已启动（输入 exit 退出；她会自己过日子）")
    try:
        while True:
            try:
                line = (await asyncio.to_thread(input, "你 > ")).strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not line:
                continue
            if line.lower() in ("exit", "quit"):
                break
            components["last_user_ts"] = time.time()

            components["events"].append("UserMessageReceived", "private", "user", "user", line)
            try:
                reply = await agent.chat(line, "chat")
            except BudgetError as exc:
                reply = str(exc)
            except Exception as exc:
                reply = f"[错误] {exc}"
            print(f"她 > {reply}")

            components["events"].append("ResidentReplied", "private", "self", ident.name, reply)
            components["memories"].save(
                "episodic", f"用户说：{line}；我回：{reply}", source="self", salience=0.4
            )
            result = await arbiter.apply(line, reply)
            components["relationships"].touch("user", affinity_delta=_affinity_delta(line))
            if result.get("ops"):
                for op in result["ops"]:
                    if op["op"] == "ADD" and op.get("content"):
                        components["relationships"].add_unverified("user", op["content"])
            components["identity"].touch()
    finally:
        scheduler.stop.set()
        sched_task.cancel()
        try:
            await sched_task
        except (asyncio.CancelledError, Exception):
            pass

    components["emotion"].decay()
    components["memories"].consolidate()
    components["conn"].close()
