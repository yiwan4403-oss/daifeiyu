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
        self.permissions = PermissionManager()
        self.approvals = ApprovalManager()
        self.audit = AuditLog(_conn=components["conn"])
        self.components = components
        self._artifacts: dict[str, dict] = {}  # proposal_id -> artifact

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
        return {
            "status": "proposed",
            "approval_id": proposal_id,
            "plugin": artifact["id"],
            "version": artifact["version"],
            "test_output": output[-300:],
        }

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
