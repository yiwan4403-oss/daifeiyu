"""CLI 适配器：本地聊天窗口（标准输入输出）。"""

import asyncio

from core.agent import BudgetError, ResidentAgent
from memory.arbiter import MemoryArbiter


async def run_cli(components: dict, cfg: dict) -> None:
    arbiter = components.get("arbiter") or MemoryArbiter(cfg, components)
    components["arbiter"] = arbiter
    agent = ResidentAgent(cfg, components)
    ident = components["identity"].get()
    print(f"[resident] {ident.name} 已启动（输入 exit 退出）")
    while True:
        try:
            line = (await asyncio.to_thread(input, "你 > ")).strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        if line.lower() in ("exit", "quit"):
            break

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
            "episodic",
            f"用户说：{line}；我回：{reply}",
            source="self",
            salience=0.4,
        )
        await arbiter.apply(line, reply)
        components["identity"].touch()

    components["memories"].consolidate()
    components["conn"].close()
