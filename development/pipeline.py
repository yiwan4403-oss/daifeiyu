"""自主开发流水线：缺口→生成→白名单→测试→提案→审批→装配→加载→回滚。"""

import os
import time

from development.builder import Builder
from development.generator import CodeGenerator
from development.researcher import Researcher
from development.tester import Tester, check_imports
from development.workspace import DevWorkspace
from extensions.loader import PluginLoader
from extensions.registry import CapabilityRegistry
from security.permission import ApprovalManager, AuditLog, PermissionManager

import yaml  # noqa: E402  (manifest 由 generator 以 dict 产出)


class PipelineError(Exception):
    pass


class DevPipeline:
    def __init__(self, cfg: dict, components: dict) -> None:
        data_dir = os.path.abspath(cfg["resident"]["data_dir"])
        dev_cfg = cfg.get("development", {})
        self.workspace = DevWorkspace(data_dir)
        self.plugins_dir = os.path.join(data_dir, "..", "plugins")
        self.generator = CodeGenerator(cfg)
        self.tester = Tester(int(dev_cfg.get("test_timeout_seconds", 60)))
        self.builder = Builder(self.plugins_dir)
        self.researcher = Researcher()
        self.registry = components.get("registry") or CapabilityRegistry()
        self.loader = PluginLoader(self.plugins_dir, self.registry, components)
        self.permissions = components.get("permissions") or PermissionManager()
        self.approvals = ApprovalManager()
        self.audit = AuditLog(_conn=components["conn"])
        self.components = components
        self._artifacts: dict[str, dict] = {}  # proposal_id -> artifact

    def auto_load(self) -> list[str]:
        """启动时把已安装插件（每个插件最高版本）加载回来。"""
        loaded = []
        if not os.path.isdir(self.plugins_dir):
            return loaded
        for pid in sorted(os.listdir(self.plugins_dir)):
            pdir = os.path.join(self.plugins_dir, pid)
            if not os.path.isdir(pdir):
                continue
            versions = self.loader.versions(pid)
            if not versions:
                continue
            try:
                self.loader.enable(pid, versions[-1])
                loaded.append(pid)
            except Exception as exc:
                self.audit.log("self", "autoload", pid, "failed", str(exc))
                print(f"[plugins] 自动加载失败 {pid}: {exc}")
        return loaded

    # ---- 查询 ----
    def capabilities(self) -> list[str]:
        return self.registry.capabilities()

    def tools(self) -> list[str]:
        return self.registry.tools()

    def missing(self, requirement: str) -> bool:
        """粗判：需求词不在能力列表即视为缺口（真判定靠人工/LLM）。"""
        return True

    # ---- 流程 ----
    async def develop(self, requirement: str) -> dict:
        """L0/L1 全自动：研究(可选) → 生成 → 白名单 → 测试 → 提案。"""
        self.audit.log("resident", "generate_code", requirement, "started")
        artifact = await self.generator.generate(requirement)
        if "error" in artifact:
            self.audit.log("resident", "generate_code", requirement, "failed", artifact["error"])
            return {"status": "failed", "detail": artifact["error"]}

        ok, why = check_imports(artifact["code"])
        if not ok:
            self.audit.log("resident", "generate_code", requirement, "rejected", why)
            return {"status": "rejected", "detail": why}

        files = {
            "manifest.yaml": self._manifest_yaml(artifact),
            "plugin.py": artifact["code"],
            "test_plugin.py": artifact["tests"],
        }
        sandbox_dir = self.workspace.write_generated(artifact["id"], files)
        ok, output = self.tester.run(sandbox_dir)
        if not ok:
            self.audit.log("resident", "run_tests", artifact["id"], "failed", output)
            return {"status": "failed", "detail": f"测试未通过：{output}"}

        proposal_id = self.approvals.submit(
            f"安装插件 {artifact['name']}（{artifact['description']}）",
            resource=f"plugins/{artifact['id']}",
            action="install_plugin",
        )
        self._artifacts[proposal_id] = {"artifact": artifact, "sandbox_dir": sandbox_dir}
        self.audit.log("resident", "run_tests", artifact["id"], "passed")
        self.audit.log("resident", "install_plugin", artifact["id"], "proposed", f"id={proposal_id}")
        result = {
            "status": "proposed",
            "approval_id": proposal_id,
            "plugin": artifact["id"],
            "version": artifact["version"],
            "test_output": output[-300:],
        }
        # 完全权限模式：测试通过即自动批准安装
        if self.permissions.allowed("install_plugin") and getattr(self.permissions, "auto_approve", False):
            installed = self.approve(proposal_id, True)
            installed["auto_approved"] = True
            installed["test_output"] = result["test_output"]
            return installed
        return result

    def approve(self, approval_id: int, ok: bool) -> dict:
        """人工裁决；批准后装配+加载（L2）。"""
        if not self.approvals.decide(approval_id, ok):
            return {"status": "error", "detail": "审批项不存在或已处理"}
        if not ok:
            return {"status": "rejected", "approval_id": approval_id}
        art = self._artifacts.get(approval_id)
        if not art:
            return {"status": "error", "detail": "产物丢失"}
        artifact, sandbox_dir = art["artifact"], art["sandbox_dir"]
        outbox = self.components.get("outbox")
        if outbox is not None:
            key = f"install:{artifact['id']}:{artifact['version']}"
            tid = outbox.enqueue(
                "install_plugin", key,
                {"plugin": artifact["id"], "version": artifact["version"]},
            )
            task = outbox.claim(tid)
            if task is None:
                return {"status": "skipped", "detail": "该版本已安装或正在安装（幂等）"}
            try:
                self.builder.assemble(artifact["id"], sandbox_dir)
                self.loader.enable(artifact["id"], artifact["version"])
            except Exception as exc:
                outbox.finish(tid, False, str(exc))
                self.audit.log("human", "install_plugin", artifact["id"], "failed", str(exc))
                return {"status": "failed", "detail": str(exc)}
            outbox.finish(tid, True)
            self.audit.log("human", "install_plugin", artifact["id"], "installed", artifact["version"])
            return {
                "status": "installed",
                "plugin": artifact["id"],
                "version": artifact["version"],
                "capabilities": self.registry.capabilities(),
            }
        try:
            self.builder.assemble(artifact["id"], sandbox_dir)
            self.loader.enable(artifact["id"], artifact["version"])
        except Exception as exc:
            self.audit.log("human", "install_plugin", artifact["id"], "failed", str(exc))
            return {"status": "failed", "detail": str(exc)}
        self.audit.log("human", "install_plugin", artifact["id"], "installed", artifact["version"])
        return {
            "status": "installed",
            "plugin": artifact["id"],
            "version": artifact["version"],
            "capabilities": self.registry.capabilities(),
        }

    def rollback(self, plugin_id: str) -> dict:
        prev = self.loader.rollback(plugin_id)
        if prev is None:
            return {"status": "error", "detail": "没有可回滚的版本"}
        self.loader.enable(plugin_id, prev)
        self.audit.log("human", "rollback_plugin", plugin_id, "rolled_back", prev)
        return {"status": "rolled_back", "plugin": plugin_id, "version": prev}

    def pending(self) -> list[dict]:
        return self.approvals.pending()

    def loaded(self) -> list[str]:
        return self.loader.loaded()

    @staticmethod
    def _manifest_yaml(artifact: dict) -> str:
        data = {
            "id": artifact["id"],
            "name": artifact["name"],
            "version": artifact["version"],
            "description": artifact.get("description", ""),
            "capabilities": artifact.get("capabilities", []),
            "tools": artifact.get("tools", []),
            "permissions": artifact.get("permissions", []),
        }
        return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
