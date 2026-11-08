"""Windows 适配器：L3 下不限制路径（可配禁区），低权限按白名单。"""

import os

from adapters.base import Adapter


class WindowsAdapter(Adapter):
    name = "windows"

    def __init__(self, allowed_dirs: list | None = None, deny_dirs: list | None = None) -> None:
        self.allowed_dirs = [os.path.abspath(d) for d in (allowed_dirs or ["workspace", "data"])]
        self.deny_dirs = [os.path.abspath(d) for d in (deny_dirs or []) if d]
        self.unrestricted = False  # L3 时由 cli 置 True

    def capabilities(self) -> list[str]:
        return ["file_list", "file_read", "file_write", "run_command"]

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def _check(self, path: str) -> str:
        target = os.path.abspath(path)
        for d in self.deny_dirs:
            if target == d or target.startswith(d + os.sep):
                raise PermissionError(f"路径在禁区中: {path}")
        if self.unrestricted:
            return target
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

    def _allowed(self, action: str) -> bool:
        perm = getattr(self, "permissions", None)
        return True if perm is None else perm.allowed(action)

    def write_file(self, path: str, content: str) -> str:
        if not self._allowed("write_file"):
            return "[拒绝] 当前权限等级不允许写入文件"
        try:
            target = self._check(path)
        except PermissionError as exc:
            return f"[拒绝] {exc}"
        try:
            with open(target, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as exc:
            return f"[错误] {exc}"
        return f"[写入] {len(content)} 字符 → {target}"

    def run_command(self, cmd: str, timeout: int = 60) -> str:
        if not self._allowed("run_command"):
            return "[拒绝] 当前权限等级不允许执行命令"
        import subprocess

        try:
            proc = subprocess.run(
                ["cmd", "/c", cmd],
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            return "[超时] 命令执行超过限制"
        except Exception as exc:
            return f"[错误] {exc}"
        out = (proc.stdout or "")[-3000:]
        err = (proc.stderr or "")[-1000:]
        return f"[退出码 {proc.returncode}]\n{out}\n{err}".strip()
