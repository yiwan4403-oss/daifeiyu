"""能力注册表：插件提供的能力与工具索引；一个能力可由多个插件提供。"""

import threading


class CapabilityRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._capabilities: dict[str, list[str]] = {}   # capability -> [plugin_id]
        self._tools: dict[str, tuple[str, object]] = {}  # tool_name -> (plugin_id, handler)

    def register_plugin(self, plugin_id: str, manifest, handlers: dict) -> None:
        with self._lock:
            for cap in manifest.capabilities:
                self._capabilities.setdefault(cap, [])
                if plugin_id not in self._capabilities[cap]:
                    self._capabilities[cap].append(plugin_id)
            for name, handler in handlers.items():
                self._tools[name] = (plugin_id, handler)

    def unregister_plugin(self, plugin_id: str) -> None:
        with self._lock:
            for cap, owners in list(self._capabilities.items()):
                if plugin_id in owners:
                    owners.remove(plugin_id)
                if not owners:
                    del self._capabilities[cap]
            for name, (owner, _) in list(self._tools.items()):
                if owner == plugin_id:
                    del self._tools[name]

    def has_capability(self, capability: str) -> bool:
        with self._lock:
            return bool(self._capabilities.get(capability))

    def capabilities(self) -> list[str]:
        with self._lock:
            return sorted(self._capabilities.keys())

    def tools(self) -> list[str]:
        with self._lock:
            return sorted(self._tools.keys())

    def get_tool(self, name: str):
        with self._lock:
            hit = self._tools.get(name)
            return hit[1] if hit else None
