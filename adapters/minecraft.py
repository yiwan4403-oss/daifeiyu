"""Minecraft 适配器骨架：协议已定，等待服务器地址与机器人账号接入。

接入时实现 start()：连入服务器，把聊天事件写入 components['events']，
动作（say/move）作为工具经 L2 审批执行。
"""

from adapters.base import Adapter


class MinecraftAdapter(Adapter):
    name = "minecraft"

    def __init__(self, components: dict, cfg: dict | None = None) -> None:
        self.components = components
        self.cfg = cfg or {}

    def capabilities(self) -> list[str]:
        return ["minecraft_say"]

    def start(self) -> None:
        raise NotImplementedError(
            "Minecraft 适配器待接入：需要服务器地址与机器人账号（见 adapters/README.md）"
        )

    def stop(self) -> None:
        pass
