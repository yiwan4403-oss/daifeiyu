"""Resident 最小可运行骨架（Phase 1 起点）。

运行：
    python main.py --init   # 初始化数据目录与身份
    python main.py          # 前台聊天循环（stdin）

退出方式：输入 exit 或 Ctrl+C，状态在每次回复后落盘。
"""

import argparse
import json
import os
import sys

import yaml

from core.context_builder import build_context
from core.event_bus import EventBus
from core.model_gateway import ModelGateway, GatewayError
from identity.identity_manager import IdentityManager
from memory.event_store import EventStore
from memory.manager import MemoryManager
from storage.database import init_schema, open_db


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def make_components(cfg: dict) -> dict:
    data_dir = os.path.abspath(cfg["resident"]["data_dir"])
    os.makedirs(data_dir, exist_ok=True)
    db_path = os.path.join(data_dir, "resident.db")
    conn = open_db(db_path)
    init_schema(conn)
    bus = EventBus()
    gateway = ModelGateway(cfg["model"])
    identity = IdentityManager(conn, cfg["resident"])
    events = EventStore(conn)
    memories = MemoryManager(conn)
    return {
        "conn": conn,
        "bus": bus,
        "gateway": gateway,
        "identity": identity,
        "events": events,
        "memories": memories,
    }


def run_loop(components: dict) -> None:
    bus = components["bus"]
    gateway = components["gateway"]
    identity = components["identity"]
    events = components["events"]
    memories = components["memories"]

    print(f"[resident] {identity.get().name} 已启动（输入 exit 退出）")
    while True:
        try:
            line = input("你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        if line.lower() in ("exit", "quit"):
            break

        events.append(
            event_type="UserMessageReceived",
            scope="private",
            source="user",
            actor="user",
            payload=line,
        )
        bus.publish("user_message", line)

        ctx = build_context(identity.get(), events.recent(20), memories.search(line, 5))
        try:
            reply = gateway.chat(ctx, line)
        except GatewayError as exc:
            reply = f"[网关错误] {exc}"

        print(f"她 > {reply}")

        events.append(
            event_type="ResidentReplied",
            scope="private",
            source="self",
            actor=identity.get().name,
            payload=reply,
        )
        memories.save(
            kind="episodic",
            content=f"用户说：{line}；我回：{reply}",
            source="self",
            salience=0.5,
        )
        identity.touch()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--init", action="store_true", help="初始化数据目录与身份")
    args = ap.parse_args()

    cfg = load_config(args.config)
    components = make_components(cfg)

    if args.init:
        components["identity"].ensure_default()
        print("[resident] 已初始化：", components["identity"].get())
        return 0

    components["identity"].ensure_default()
    run_loop(components)
    components["conn"].close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
