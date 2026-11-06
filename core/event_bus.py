"""事件总线：模块间解耦的唯一通道。Phase 1 为同步实现。"""

import threading
from collections import defaultdict


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list] = defaultdict(list)
        self._lock = threading.Lock()

    def subscribe(self, event: str, handler) -> None:
        with self._lock:
            self._subs[event].append(handler)

    def publish(self, event: str, payload=None) -> None:
        with self._lock:
            handlers = list(self._subs[event])
        for handler in handlers:
            try:
                handler(payload)
            except Exception:
                # 单个订阅者异常不阻断事件传播（记日志占位）
                pass
