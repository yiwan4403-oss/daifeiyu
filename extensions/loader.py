"""插件加载器：启停/升级/降级/卸载/错误隔离。版本目录式管理。"""

import importlib.util
import os
import sys

from extensions.manifest import ManifestError, load_manifest
from extensions.sdk import Plugin, PluginContext


class LoaderError(Exception):
    pass


class PluginLoader:
    def __init__(self, plugins_dir: str, registry, components: dict) -> None:
        self.plugins_dir = plugins_dir
        self.registry = registry
        self.components = components
        self._loaded: dict[str, tuple[str, object]] = {}  # plugin_id -> (version, plugin)

    def _plugin_dir(self, plugin_id: str, version: str) -> str:
        return os.path.join(self.plugins_dir, plugin_id, f"v{version}")

    def versions(self, plugin_id: str) -> list[str]:
        base = os.path.join(self.plugins_dir, plugin_id)
        if not os.path.isdir(base):
            return []
        return sorted(
            [d[1:] for d in os.listdir(base) if d.startswith("v")],
            key=lambda s: [int(x) for x in s.split(".")],
        )

    def load(self, plugin_id: str, version: str) -> object:
        pdir = self._plugin_dir(plugin_id, version)
        plugin_py = os.path.join(pdir, "plugin.py")
        if not os.path.isfile(plugin_py):
            raise LoaderError(f"找不到 {plugin_py}")
        try:
            manifest = load_manifest(os.path.join(pdir, "manifest.yaml"))
        except ManifestError as exc:
            raise LoaderError(str(exc)) from exc

        mod_name = f"resident_plugin_{plugin_id}_{version}".replace("-", "_")
        spec = importlib.util.spec_from_file_location(mod_name, plugin_py)
        if spec is None or spec.loader is None:
            raise LoaderError("无法解析插件模块")
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            sys.modules.pop(mod_name, None)
            raise LoaderError(f"插件执行失败（已隔离，不影响核心）: {exc}") from exc

        ctx = PluginContext(self.components, self.registry, plugin_id)
        try:
            plugin = module.PluginClass(ctx)
        except Exception as exc:
            raise LoaderError(f"插件实例化失败: {exc}") from exc
        if not isinstance(plugin, Plugin):
            raise LoaderError("PluginClass 必须继承 extensions.sdk.Plugin")

        handlers = {}
        for t in manifest.tools:
            try:
                handler = plugin.tool(t.name)
            except Exception as exc:
                raise LoaderError(f"工具 {t.name} 注册失败: {exc}") from exc
            if handler is not None:
                handlers[t.name] = handler
        self.registry.register_plugin(plugin_id, manifest, handlers)
        self._loaded[plugin_id] = (version, plugin)
        return plugin

    def unload(self, plugin_id: str) -> None:
        if plugin_id in self._loaded:
            self.registry.unregister_plugin(plugin_id)
            del self._loaded[plugin_id]

    def enable(self, plugin_id: str, version: str) -> object:
        self.unload(plugin_id)  # 先卸旧的，错误隔离
        return self.load(plugin_id, version)

    def disable(self, plugin_id: str) -> None:
        self.unload(plugin_id)

    def rollback(self, plugin_id: str) -> str | None:
        versions = self.versions(plugin_id)
        if len(versions) < 2:
            return None
        return versions[-2]

    def uninstall(self, plugin_id: str) -> None:
        self.disable(plugin_id)
        base = os.path.join(self.plugins_dir, plugin_id)
        import shutil

        shutil.rmtree(base, ignore_errors=True)

    def loaded(self) -> list[str]:
        return list(self._loaded.keys())
