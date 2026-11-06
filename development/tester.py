"""依赖白名单与测试执行：程序化安全门。"""

import ast
import os
import subprocess

DEFAULT_ALLOWED_IMPORTS = {
    "json", "random", "math", "datetime", "re", "typing", "collections",
    "extensions.sdk",
}

FORBIDDEN_IMPORTS = {"os", "sys", "subprocess", "socket", "shutil", "requests",
                     "urllib", "pathlib", "importlib", "ctypes", "builtins"}


def _module_allowed(module: str, allowed: set) -> bool:
    """按最长前缀匹配：extensions.sdk 在白名单时，from extensions.sdk import … 放行。"""
    parts = module.split(".")
    for i in range(len(parts), 0, -1):
        if ".".join(parts[:i]) in allowed:
            return True
    return False


def check_imports(code: str, allowed: set | None = None) -> tuple[bool, str]:
    allowed = allowed or set()
    allowed |= DEFAULT_ALLOWED_IMPORTS
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return False, f"语法错误: {exc}"
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name.split(".")[0]
                if name in FORBIDDEN_IMPORTS or not _module_allowed(alias.name, allowed):
                    problems.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            name = node.module or ""
            if name and (name.split(".")[0] in FORBIDDEN_IMPORTS or not _module_allowed(name, allowed)):
                problems.append(name)
    if problems:
        return False, "禁止的 import: " + ", ".join(sorted(set(problems)))
    return True, ""


class Tester:
    def __init__(self, timeout_seconds: int = 60, project_root: str | None = None) -> None:
        self.timeout = timeout_seconds
        self.project_root = project_root or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..")
        )

    def run(self, sandbox_dir: str) -> tuple[bool, str]:
        test_file = os.path.join(sandbox_dir, "test_plugin.py")
        if not os.path.isfile(test_file):
            return False, "缺少 test_plugin.py：没有测试不许安装"
        plugin_file = os.path.join(sandbox_dir, "plugin.py")
        if not os.path.isfile(plugin_file):
            return False, "缺少 plugin.py"
        env = dict(os.environ)
        env["PYTHONPATH"] = self.project_root + os.pathsep + env.get("PYTHONPATH", "")
        try:
            proc = subprocess.run(
                ["python", "-m", "pytest", "test_plugin.py", "-q"],
                cwd=sandbox_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            return False, "测试超时"
        ok = proc.returncode == 0
        tail = (proc.stdout or "")[-800:] + (proc.stderr or "")[-400:]
        return ok, tail
