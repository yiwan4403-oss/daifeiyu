"""Phase 4 测试：SDK/Registry/Loader/Tester/Pipeline 全链路（含审批与回滚）。"""

import asyncio
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import development.pipeline as pipeline_mod  # noqa: E402
from development.tester import check_imports, Tester  # noqa: E402
from extensions.loader import PluginLoader  # noqa: E402
from extensions.manifest import load_manifest  # noqa: E402
from extensions.registry import CapabilityRegistry  # noqa: E402
from identity.identity_manager import IdentityManager  # noqa: E402
from memory.event_store import EventStore  # noqa: E402
from memory.manager import MemoryManager  # noqa: E402
from storage.database import init_schema, open_db  # noqa: E402

DICE_CODE = '''
from extensions.sdk import Plugin, Manifest, ToolSpec


class PluginClass(Plugin):
    manifest = Manifest(
        id="dice",
        name="掷骰子",
        version="1.0.0",
        description="掷一个六面骰子",
        capabilities=["dice"],
        tools=[ToolSpec(name="roll", description="掷一个骰子", params="{}")],
    )

    def tool(self, name):
        if name == "roll":
            return roll
        return None


def roll():
    import random
    return str(random.randint(1, 6))
'''

DICE_TESTS = '''
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plugin import PluginClass  # noqa: E402


def test_roll():
    p = PluginClass(None)
    v = p.tool("roll")()
    assert v in "123456"


def test_manifest():
    assert PluginClass.manifest.id == "dice"
'''


def make_components(tmp_path):
    conn = open_db(str(tmp_path / "r.db"))
    init_schema(conn)
    identity = IdentityManager(conn, {"name": "大肥鱼"})
    identity.ensure_default()
    from core.event_bus import EventBus
    from identity.emotion import EmotionManager

    return {
        "conn": conn,
        "identity": identity,
        "events": EventStore(conn),
        "memories": MemoryManager(conn),
        "bus": EventBus(),
        "emotion": EmotionManager(conn),
        "last_user_ts": time.time(),
    }


def make_cfg(tmp_path):
    return {
        "resident": {"name": "大肥鱼", "data_dir": str(tmp_path / "data")},
        "model": {
            "base_url": "http://mock",
            "api_key_env": "DEEPSEEK_API_KEY",
            "model": "deepseek-flash",
            "timeout_seconds": 5,
            "max_tokens": 100,
            "temperature": 0.9,
        },
        "task_models": {"light": "deepseek-flash", "reason": "deepseek-flash"},
        "budget": {"daily_usd": 1.0, "usd_per_mtok_in": 0.28, "usd_per_mtok_out": 1.68},
        "development": {"test_timeout_seconds": 60},
    }


def test_check_imports_whitelist():
    ok, why = check_imports("import json\nimport random\n")
    assert ok, why
    ok, why = check_imports("import os\n")
    assert not ok and "os" in why
    ok, why = check_imports("from extensions.sdk import Plugin\n")
    assert ok, why


def test_manifest_validate(tmp_path):
    p = tmp_path / "manifest.yaml"
    p.write_text("id: dice\nname: 掷骰子\nversion: 1.0.0\n", encoding="utf-8")
    m = load_manifest(str(p))
    assert m.id == "dice" and m.version == "1.0.0"


def test_registry_register_and_lookup():
    reg = CapabilityRegistry()

    class M:
        capabilities = ["dice"]
        tools = []

    reg.register_plugin("dice", M(), {"roll": lambda: "3"})
    assert reg.has_capability("dice")
    assert reg.get_tool("roll")() == "3"
    reg.unregister_plugin("dice")
    assert not reg.has_capability("dice")


def test_loader_lifecycle(tmp_path):
    components = make_components(tmp_path)
    reg = CapabilityRegistry()
    plugins_dir = str(tmp_path / "plugins")
    os.makedirs(os.path.join(plugins_dir, "dice", "v1.0.0"))
    pdir = os.path.join(plugins_dir, "dice", "v1.0.0")
    with open(os.path.join(pdir, "plugin.py"), "w", encoding="utf-8") as f:
        f.write(DICE_CODE)
    with open(os.path.join(pdir, "manifest.yaml"), "w", encoding="utf-8") as f:
        f.write("id: dice\nname: 掷骰子\nversion: 1.0.0\ndescription: x\n"
                "capabilities: [dice]\ntools:\n  - name: roll\n    description: 掷\n")

    loader = PluginLoader(plugins_dir, reg, components)
    plugin = loader.load("dice", "1.0.0")
    assert reg.has_capability("dice")
    assert reg.get_tool("roll")() in "123456"
    loader.disable("dice")
    assert not reg.has_capability("dice")
    assert loader.versions("dice") == ["1.0.0"]


def test_tester_rejects_and_passes(tmp_path):
    sandbox = tmp_path / "sbx"
    sandbox.mkdir()
    t = Tester(timeout_seconds=60, project_root=ROOT)
    ok, out = t.run(str(sandbox))
    assert not ok  # 没有测试文件

    (sandbox / "plugin.py").write_text(DICE_CODE, encoding="utf-8")
    (sandbox / "test_plugin.py").write_text(DICE_TESTS, encoding="utf-8")
    ok, out = t.run(str(sandbox))
    assert ok, out

    (sandbox / "test_plugin.py").write_text("def test_bad():\n    assert 1 == 2\n", encoding="utf-8")
    ok, out = t.run(str(sandbox))
    assert not ok


def test_pipeline_auto_approve_full_permissions(tmp_path, monkeypatch):
    """完全权限：测试通过即自动安装，无需人工审批。"""
    from security.permission import PermissionManager

    components = make_components(tmp_path)
    cfg = make_cfg(tmp_path)
    reg = CapabilityRegistry()
    components["registry"] = reg
    components["permissions"] = PermissionManager(max_level=3, auto_approve=True)
    pipeline = pipeline_mod.DevPipeline(cfg, components)

    class FakeGenerator:
        def __init__(self, *a, **k):
            pass

        async def generate(self, requirement):
            return {
                "id": "dice",
                "name": "掷骰子",
                "version": "1.0.0",
                "description": "d",
                "capabilities": ["dice"],
                "tools": [{"name": "roll", "description": "掷", "params": "{}"}],
                "permissions": [],
                "code": DICE_CODE,
                "tests": DICE_TESTS,
            }

    monkeypatch.setattr(pipeline_mod, "CodeGenerator", FakeGenerator)
    pipeline.generator = FakeGenerator()

    result = asyncio.run(pipeline.develop("掷骰子"))
    assert result["status"] == "installed", result
    assert result.get("auto_approved") is True
    assert pipeline.pending() == []
    assert reg.has_capability("dice")


def test_pipeline_end_to_end(tmp_path, monkeypatch):
    components = make_components(tmp_path)
    cfg = make_cfg(tmp_path)
    reg = CapabilityRegistry()
    components["registry"] = reg
    pipeline = pipeline_mod.DevPipeline(cfg, components)
    components["dev"] = pipeline

    class FakeGenerator:
        def __init__(self, *a, **k):
            pass

        async def generate(self, requirement):
            return {
                "id": "dice",
                "name": "掷骰子",
                "version": "1.0.0",
                "description": "掷一个六面骰子",
                "capabilities": ["dice"],
                "tools": [{"name": "roll", "description": "掷一个骰子", "params": "{}"}],
                "permissions": [],
                "code": DICE_CODE,
                "tests": DICE_TESTS,
            }

    monkeypatch.setattr(pipeline_mod, "CodeGenerator", FakeGenerator)
    pipeline.generator = FakeGenerator()

    result = asyncio.run(pipeline.develop("我要一个掷骰子工具"))
    assert result["status"] == "proposed", result
    pid = result["approval_id"]
    assert pipeline.pending()

    # 模型不能自我批准：approve 是人工命令
    result = pipeline.approve(pid, True)
    assert result["status"] == "installed", result
    assert reg.has_capability("dice")
    assert reg.get_tool("roll")() in "123456"

    # 第二版 + 回滚
    class FakeGenerator2(FakeGenerator):
        async def generate(self, requirement):
            d = await super().generate(requirement)
            d["version"] = "2.0.0"
            return d

    monkeypatch.setattr(pipeline_mod, "CodeGenerator", FakeGenerator2)
    pipeline.generator = FakeGenerator2()
    result = asyncio.run(pipeline.develop("升级骰子"))
    assert result["status"] == "proposed"
    result = pipeline.approve(result["approval_id"], True)
    assert result["status"] == "installed"
    assert pipeline.loader.versions("dice") == ["1.0.0", "2.0.0"]

    rb = pipeline.rollback("dice")
    assert rb["status"] == "rolled_back" and rb["version"] == "1.0.0"
    assert reg.has_capability("dice")

    # 重启后自动加载已装插件
    loaded = pipeline.auto_load()
    assert "dice" in loaded
    assert reg.has_capability("dice")

    # 拒绝路径
    result = asyncio.run(pipeline.develop("再来一个"))
    pid2 = result["approval_id"]
    result = pipeline.approve(pid2, False)
    assert result["status"] == "rejected"
    assert pipeline.pending() == []
