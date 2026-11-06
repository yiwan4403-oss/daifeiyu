"""插件 SDK：Resident 扩展能力的统一契约。"""

from dataclasses import dataclass, field


@dataclass
class ToolSpec:
    name: str
    description: str
    params: str = "{}"  # JSON 描述参数


@dataclass
class Manifest:
    id: str
    name: str
    version: str
    description: str = ""
    capabilities: list = field(default_factory=list)
    tools: list = field(default_factory=list)  # ToolSpec
    permissions: list = field(default_factory=list)
    python: str = ">=3.10"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "capabilities": list(self.capabilities),
            "tools": [
                {"name": t.name, "description": t.description, "params": t.params}
                for t in self.tools
            ],
            "permissions": list(self.permissions),
            "python": self.python,
        }


class PluginContext:
    """插件可用的受控上下文：不给数据库直连，只给受控 API。"""

    def __init__(self, components: dict, registry, plugin_id: str) -> None:
        self.components = components
        self.registry = registry
        self.plugin_id = plugin_id

    def memory(self):
        return self.components["memories"]

    def say(self, text: str) -> None:
        self.components["bus"].publish("proactive", f"[插件 {self.plugin_id}] {text}")


class Plugin:
    """插件基类：manifest 声明能力，tool(name) 返回可调用函数。"""

    manifest: Manifest

    def __init__(self, ctx: PluginContext | None = None) -> None:
        self.ctx = ctx

    def health(self) -> str:
        return "ok"

    def tool(self, name: str):
        """按名字返回工具函数；找不到返回 None。"""
        return None
