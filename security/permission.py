"""权限与审批：安全由程序执行，模型不得自我授权。"""

import time
from dataclasses import dataclass, field


@dataclass
class PermissionManager:
    """动作 → 所需等级；L0 只读/规划，L1 沙箱内生成与测试，
    L2 安装/依赖/外部操作（需人工审批），L3 核心修改/删除（仅人工）。"""

    _matrix: dict = field(default_factory=lambda: {
        "read": 0,
        "plan": 0,
        "generate_code": 1,
        "run_tests": 1,
        "install_plugin": 2,
        "install_dependency": 2,
        "upgrade_plugin": 2,
        "rollback_plugin": 2,
        "uninstall_plugin": 2,
        "modify_core": 3,
        "modify_identity": 3,
        "delete_data": 3,
    })

    def level_of(self, action: str) -> int:
        return self._matrix.get(action, 3)

    def check(self, action: str, granted_level: int) -> bool:
        return granted_level >= self.level_of(action)


@dataclass
class ApprovalManager:
    """L2 审批队列：程序裁决 L0/L1，人工裁决 L2+。"""

    _pending: dict = field(default_factory=dict)
    _counter: int = 0

    def submit(self, request: str, resource: str, action: str) -> int:
        self._counter += 1
        self._pending[self._counter] = {
            "id": self._counter,
            "request": request,
            "resource": resource,
            "action": action,
            "ts": time.time(),
            "status": "pending",
        }
        return self._counter

    def decide(self, approval_id: int, ok: bool, by: str = "human") -> bool:
        """返回是否成功处理该项（True=已裁决），裁决结果记录在 item 里。"""
        item = self._pending.get(approval_id)
        if not item or item["status"] != "pending":
            return False
        item["status"] = "approved" if ok else "rejected"
        item["by"] = by
        return True

    def pending(self) -> list[dict]:
        return [i for i in self._pending.values() if i["status"] == "pending"]


@dataclass
class AuditLog:
    _conn: object = None

    def log(self, actor: str, action: str, resource: str, result: str, detail: str = "") -> None:
        if self._conn is None:
            return
        self._conn.execute(
            "INSERT INTO audit(ts, actor, action, resource, result, detail) VALUES (?,?,?,?,?,?)",
            (time.time(), actor, action, resource, result, detail),
        )
        self._conn.commit()
