"""Resident 最小可运行骨架（Phase 1）。

运行：
    python main.py --init   # 初始化数据目录与身份
    python main.py          # CLI 聊天（exit 退出）
"""

import argparse
import asyncio
import os
import sys

import yaml

from core.event_bus import EventBus
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
    conn = open_db(os.path.join(data_dir, "resident.db"))
    init_schema(conn)
    return {
        "conn": conn,
        "bus": EventBus(),
        "identity": IdentityManager(conn, cfg["resident"]),
        "events": EventStore(conn),
        "memories": MemoryManager(conn),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--init", action="store_true", help="初始化数据目录与身份")
    args = ap.parse_args()

    cfg = load_config(args.config)
    components = make_components(cfg)
    components["identity"].ensure_default()

    if args.init:
        print("[resident] 已初始化：", components["identity"].get())
        components["conn"].close()
        return 0

    from adapters.cli import run_cli

    asyncio.run(run_cli(components, cfg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
