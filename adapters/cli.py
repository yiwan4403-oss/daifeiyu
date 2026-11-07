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


async def _handle_command(dev, components: dict, line: str) -> str:
    parts = line.split()
    cmd = parts[0].lower()
    if cmd == "/plugins":
        return (
            f"已加载插件：{dev.loaded() or '无'}\n"
            f"能力：{dev.capabilities() or '无'}\n"
            f"工具：{dev.tools() or '无'}"
        )
    if cmd == "/pending":
        pend = dev.pending()
        if not pend:
            return "没有待审批项"
        return "\n".join(f"[{p['id']}] {p['action']} → {p['resource']}：{p['request']}" for p in pend)
    if cmd == "/approve" and len(parts) == 2:
        result = dev.approve(int(parts[1]), True)
        qq = (components.get("adapters") or {}).get("qq")
        if qq is not None:
            await qq.dispatch(int(parts[1]))
        return str(result)
    if cmd == "/reject" and len(parts) == 2:
        result = dev.approve(int(parts[1]), False)
        return str(result)
    if cmd == "/rollback" and len(parts) == 2:
        return str(dev.rollback(parts[1]))
    if cmd == "/qq" and len(parts) >= 2:
        qq = (components.get("adapters") or {}).get("qq")
        if qq is None:
            return "QQ 适配器未启用"
        if parts[1].lower() == "avatar" and len(parts) == 3:
            try:
                await qq.set_avatar(parts[2])
                return "头像已设置"
            except Exception as exc:
                return f"[头像设置失败] {exc}"
        return "用法：/qq avatar <本地图片绝对路径>"
    if cmd == "/bili" and len(parts) >= 2:
        bili = (components.get("adapters") or {}).get("bilibili")
        if bili is None:
            return "B站适配器未启用"
        sub = parts[1].lower()
        if sub == "login":
            r = bili.login_start()
            if "error" in r:
                return str(r)
            print(f"[bili] 用手机 B站App 扫码：{r['url']}")
            return "二维码已生成。扫完后敲 /bili poll"
        if sub == "poll":
            return str(bili.login_poll())
        if sub == "me":
            return bili.me()
        if sub == "dm" and len(parts) == 2:
            return bili.dm_status()
        if sub == "dm" and len(parts) >= 3:
            return str(bili.send_dm(" ".join(parts[2:])))
        return "用法：/bili login|poll|me|dm|dm <内容>"
    return "命令：/plugins /pending /approve <id> /reject <id> /rollback <插件id> /bili login|poll|me|dm"


async def run_cli(components: dict, cfg: dict) -> None:
    components.setdefault("emotion", EmotionManager(components["conn"]))
    components.setdefault("relationships", RelationshipManager(components["conn"]))
    components.setdefault("beliefs", BeliefManager(components["conn"]))
    components.setdefault("autobiography", AutobiographyManager(cfg, components))
    components["last_user_ts"] = time.time()

    from adapters.bilibili import BilibiliAdapter
    from adapters.browser import BrowserAdapter
    from adapters.windows import WindowsAdapter
    from development.mcp_client import MCPHub
    from development.pipeline import DevPipeline
    from development.self_maintenance import SelfMaintenance
    from extensions.registry import CapabilityRegistry

    components.setdefault("registry", CapabilityRegistry())
    components["dev"] = DevPipeline(cfg, components)
    dev = components["dev"]
    auto_loaded = dev.auto_load()
    if auto_loaded:
        print(f"[plugins] 已自动加载：{auto_loaded}")

    components["adapters"] = {
        "browser": BrowserAdapter(),
        "windows": WindowsAdapter(cfg.get("windows", {}).get("allowed_dirs", ["workspace", "data"])),
        "bilibili": BilibiliAdapter(cfg.get("bilibili", {})),
    }
    qq_cfg = cfg.get("qq", {})
    if qq_cfg.get("enabled"):
        from adapters.qq import OneBotAdapter

        qq_adapter = OneBotAdapter(components, qq_cfg)
        qq_adapter.start()
        components["adapters"]["qq"] = qq_adapter
        print(f"[qq] OneBot 反向 WS 监听 {qq_cfg.get('host')}:{qq_cfg.get('port')}")

    from security.outbox import Outbox

    components["outbox"] = Outbox(components["conn"])
    components["outbox"].recover()
    mcp_hub = MCPHub((cfg.get("mcp") or {}).get("servers", []))
    await mcp_hub.start_all()
    components["mcp"] = mcp_hub

    maintenance = SelfMaintenance(components)

    async def maintenance_loop():
        while True:
            await asyncio.sleep(3600)
            try:
                report = await maintenance.maybe_run()
                if report:
                    print(f"[life] 自我维护完成：{report['metrics']}")
                # 双日记：21 点后写今天的（生活 + 内心，同日互引）
                now = time.localtime()
                if now.tm_hour >= 21:
                    result = await components["diary"].daily()
                    if result:
                        print(f"[life] 日记已写：{result}")
            except Exception as exc:
                print(f"[life] 自我维护失败：{exc}")

    maint_task = asyncio.create_task(maintenance_loop())

    arbiter = components.get("arbiter") or MemoryArbiter(cfg, components)
    arbiter.bind_emotion(components["emotion"])
    components["arbiter"] = arbiter

    auto = components["autobiography"]
    narrative = await auto.refresh_if_stale(24.0)
    if narrative:
        print(f"[resident] 自传已更新（{len(narrative)} 字）")

    agent = ResidentAgent(cfg, components)
    ident = components["identity"].get()

    qq_cfg = cfg.get("qq", {})
    qq_owner_ids = [str(x) for x in (qq_cfg.get("owner_ids") or [])]
    qq_auto_reply = bool(qq_cfg.get("auto_reply", True))
    components["qq_owner_ids"] = qq_owner_ids

    from life.bili_daily import BiliDaily
    from life.diary import Diary

    components["bili_daily"] = BiliDaily(components, cfg)
    components["diary"] = Diary(components, cfg)

    async def qq_send_safe(uid: str, text: str, kind: str = "reply") -> bool:
        """所有对外发送经 outbox：幂等，防重启重复发。"""
        import hashlib

        outbox = components["outbox"]
        qq_adapter = components["adapters"].get("qq")
        if qq_adapter is None:
            return False
        key = f"qq:{uid}:{time.strftime('%Y-%m-%d')}:{hashlib.md5(text.encode('utf-8')).hexdigest()[:10]}"
        tid = outbox.enqueue("qq_send", key, {"uid": uid, "text": text, "kind": kind})
        task = outbox.claim(tid)
        if task is None:
            return False  # 已在执行/已完成
        try:
            await qq_adapter.send_private(uid, text)
            outbox.finish(tid, True)
            return True
        except Exception as exc:
            outbox.finish(tid, False, str(exc))
            return False

    async def handle_user_message(scope: str, uid: str, text: str, images=None) -> None:
        """外部入口（QQ 等）来的消息：按人建上下文、记忆打归属、自动回复。"""
        components["last_user_ts"] = time.time()
        if scope != "private":
            return  # 群聊暂不自动回，避免刷屏
        qq_adapter = components["adapters"].get("qq")
        is_owner = uid in qq_owner_ids

        # owner 在 QQ 里可以下命令（/plugins /pending /approve …）
        if is_owner and text.startswith("/"):
            try:
                if text.strip().lower() == "/health":
                    result = str(await maintenance.run_once())
                else:
                    result = await _handle_command(dev, components, text)
            except Exception as exc:
                result = f"[命令失败] {exc}"
            if qq_adapter is not None:
                await qq_send_safe(uid, result[:1500], kind="command")
            print(f"[qq] {uid} 命令：{text} → {result[:80]}")
            return

        try:
            reply = await agent.chat(text, "chat", user_key=uid, images=images)
        except Exception as exc:
            reply = f"[错误] {exc}"
        components["memories"].save(
            "episodic",
            f"{uid}（QQ）说：{text}；我回：{reply}",
            source="self",
            salience=0.4,
            user_key=uid,
        )
        await arbiter.apply(text, reply, user_key=uid)
        if qq_adapter is not None:
            ok = await qq_send_safe(uid, reply, kind="reply")
            if ok:
                print(f"[qq] {uid}：{text} → 已回复：{reply[:40]}")
            else:
                print(f"[qq] {uid}：{text} → 回复已入队（幂等），未实际发送")

    components["on_user_message"] = handle_user_message

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

            if line.startswith("/"):
                if line.strip().lower() == "/health":
                    print(await maintenance.run_once())
                    continue
                print(await _handle_command(dev, components, line))
                continue

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
        maint_task.cancel()
        try:
            await asyncio.gather(sched_task, maint_task, return_exceptions=True)
        except Exception:
            pass
        await mcp_hub.stop_all()

    components["emotion"].decay()
    components["memories"].consolidate()
    components["conn"].close()
