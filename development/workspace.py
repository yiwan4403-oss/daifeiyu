"""开发工作区：草稿与沙箱目录管理。"""

import os


class DevWorkspace:
    def __init__(self, data_dir: str) -> None:
        self.workspace = os.path.join(data_dir, "..", "workspace")
        self.sandbox = os.path.join(data_dir, "..", "sandbox")
        for d in (self.workspace, self.sandbox):
            os.makedirs(d, exist_ok=True)

    def sandbox_dir(self, plugin_id: str) -> str:
        d = os.path.join(self.sandbox, plugin_id)
        os.makedirs(d, exist_ok=True)
        return d

    def write_generated(self, plugin_id: str, files: dict) -> str:
        """files: {文件名: 内容}，写入沙箱。返回目录路径。"""
        d = self.sandbox_dir(plugin_id)
        for name, content in files.items():
            safe = os.path.basename(name)
            with open(os.path.join(d, safe), "w", encoding="utf-8") as f:
                f.write(content)
        return d

    def clean(self, plugin_id: str) -> None:
        import shutil

        shutil.rmtree(self.sandbox_dir(plugin_id), ignore_errors=True)
