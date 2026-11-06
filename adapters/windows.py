"""Windows 适配器 v1：白名单目录内的只读文件操作。写操作留待 L2 审批。"""

import os

from adapters.base import Adapter


class WindowsAdapter(Adapter):
    name = "windows"

    def __init__(self, allowed_dirs: list | None = None) -> None:
        self.allowed_dirs = [os.path.abspath(d) for d in (allowed_dirs or ["workspace", "data"])]

    def capabilities(self) -> list[str]:
        return ["file_list", "file_read"]

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def _check(self, path: str) -> str:
        target = os.path.abspath(path)
        for d in self.allowed_dirs:
            if target == d or target.startswith(d + os.sep):
                return target
        raise PermissionError(f"路径不在白名单内: {path}")

    def list_dir(self, path: str) -> str:
        try:
            target = self._check(path)
        except PermissionError as exc:
            return f"[拒绝] {exc}"
        try:
            names = sorted(os.listdir(target))[:100]
        except Exception as exc:
            return f"[错误] {exc}"
        return "\n".join(names) if names else "（空目录）"

    def read_file(self, path: str, max_bytes: int = 20_000) -> str:
        try:
            target = self._check(path)
        except PermissionError as exc:
            return f"[拒绝] {exc}"
        if not os.path.isfile(target):
            return "[错误] 不是文件"
        try:
            with open(target, "rb") as f:
                data = f.read(max_bytes + 1)
        except Exception as exc:
            return f"[错误] {exc}"
        text = data[:max_bytes].decode("utf-8", errors="replace")
        return f"[本地文件] {text}"
