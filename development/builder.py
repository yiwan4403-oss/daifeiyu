"""版本化装配：沙箱产物 → plugins/<id>/v<version>/。"""

import os
import shutil

from extensions.manifest import ManifestError, load_manifest


class Builder:
    def __init__(self, plugins_dir: str) -> None:
        self.plugins_dir = plugins_dir
        os.makedirs(plugins_dir, exist_ok=True)

    def assemble(self, plugin_id: str, sandbox_dir: str) -> str:
        """把沙箱内容拷进版本目录；manifest 校验通过才算数。返回版本目录。"""
        manifest = load_manifest(os.path.join(sandbox_dir, "manifest.yaml"))
        if manifest.id != plugin_id:
            raise ValueError(f"manifest.id({manifest.id}) != 目标({plugin_id})")
        dest = os.path.join(self.plugins_dir, plugin_id, f"v{manifest.version}")
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        shutil.copytree(sandbox_dir, dest, dirs_exist_ok=True)
        return dest
