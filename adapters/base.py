"""适配器统一协议：外部世界 → 事件进；动作出。"""

from abc import ABC, abstractmethod


class Adapter(ABC):
    """一个适配器 = 一个外部环境。核心不依赖任何具体适配器。"""

    name: str = "base"

    @abstractmethod
    def capabilities(self) -> list[str]:
        """适配器提供的能力名。"""

    @abstractmethod
    def start(self) -> None:
        """建立连接/启动监听（阻塞的启动放后台任务）。"""

    @abstractmethod
    def stop(self) -> None:
        """关闭连接。"""
