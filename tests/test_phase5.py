"""Phase 5/6 测试：Browser/Windows 适配器、MCP 真实链路、自我维护、事件规范化。"""

import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from adapters.browser import BrowserAdapter  # noqa: E402
from adapters.windows import WindowsAdapter  # noqa: E402
from development.mcp_client import MCPHub  # noqa: E402
from development.self_maintenance import SelfMaintenance  # noqa: E402
from identity.identity_manager import IdentityManager  # noqa: E402
from memory.event_store import EventStore  # noqa: E402
from memory.manager import MemoryManager  # noqa: E402
from storage.database import init_schema, open_db  # noqa: E402


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
    }


def test_browser_fetch_untrusted(monkeypatch):
    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n):
            return "<html>hello</html>".encode("utf-8")[:n]

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: FakeResp())
    b = BrowserAdapter()
    text = b.fetch_text("https://example.com")
    assert "[untrusted" in text and "hello" in text
    assert b.fetch_text("file:///etc/passwd").startswith("[拒绝]")


def test_windows_whitelist(tmp_path):
    allowed = str(tmp_path / "ws")
    os.makedirs(allowed)
    with open(os.path.join(allowed, "note.txt"), "w", encoding="utf-8") as f:
        f.write("她的日记")
    w = WindowsAdapter([allowed])
    assert "note.txt" in w.list_dir(allowed)
    assert "她的日记" in w.read_file(os.path.join(allowed, "note.txt"))
    assert w.read_file(str(tmp_path / "outside.txt")).startswith("[拒绝]")


def test_windows_write_and_run_gated(tmp_path):
    from security.permission import PermissionManager

    allowed = str(tmp_path / "ws")
    os.makedirs(allowed, exist_ok=True)
    # 低权限：拒绝
    low = WindowsAdapter([allowed])
    low.permissions = PermissionManager(max_level=1)
    assert low.write_file(os.path.join(allowed, "a.txt"), "x").startswith("[拒绝]")
    assert low.run_command("echo hi").startswith("[拒绝]")
    # 完全权限：允许
    high = WindowsAdapter([allowed])
    high.permissions = PermissionManager(max_level=3, auto_approve=True)
    target = os.path.join(allowed, "a.txt")
    assert "写入" in high.write_file(target, "hello")
    assert open(target, encoding="utf-8").read() == "hello"
    out = high.run_command("echo hi")
    assert "hi" in out


def test_windows_unrestricted_and_deny(tmp_path):
    outside = str(tmp_path / "outside")
    os.makedirs(outside, exist_ok=True)
    w = WindowsAdapter([str(tmp_path / "ws")], deny_dirs=[str(tmp_path / "secret")])
    assert w.read_file(os.path.join(outside, "x.txt")).startswith("[拒绝]")
    w.unrestricted = True
    assert "写入" in w.write_file(os.path.join(outside, "x.txt"), "ok")
    os.makedirs(str(tmp_path / "secret"), exist_ok=True)
    assert w.read_file(os.path.join(str(tmp_path / "secret"), "s.txt")).startswith("[拒绝]")


def test_event_payload_sanitized(tmp_path):
    components = make_components(tmp_path)
    components["events"].append("UserMessageReceived", "private", "user", "u", "正常\x00消息\x07")
    assert components["events"].recent(1)[0].payload == "正常消息"


def test_self_maintenance_disables_bad_plugin(tmp_path):
    components = make_components(tmp_path)

    class GoodPlugin:
        def health(self):
            return "ok"

    class BadPlugin:
        def health(self):
            raise RuntimeError("boom")

    class FakeLoader:
        def __init__(self):
            self._loaded = {"good": ("1.0.0", GoodPlugin()), "bad": ("1.0.0", BadPlugin())}

        def disable(self, pid):
            del self._loaded[pid]

    class FakeDev:
        def __init__(self, loader):
            self.loader = loader

        def loaded(self):
            return list(self.loader._loaded.keys())

    components["dev"] = FakeDev(FakeLoader())
    sm = SelfMaintenance(components)
    report = asyncio.run(sm.run_once())
    assert report["plugins"]["good"]["health"] == "ok"
    assert report["plugins"]["bad"]["health"].startswith("异常已禁用")
    assert "bad" not in components["dev"].loaded()
    assert report["metrics"]["memories"] >= 1  # procedural 记忆已沉淀


def test_mcp_echo_server_roundtrip():
    async def run():
        hub = MCPHub(
            [{"name": "echo", "command": "python", "args": [os.path.join(ROOT, "tests", "mcp_echo_server.py")]}]
        )
        started = await hub.start_all()
        assert "echo" in started
        assert "echo" in hub.list_tools().get("echo", [])
        out = await hub.call("echo", "echo", {"text": "hi"})
        await hub.stop_all()
        return out

    out = asyncio.run(run())
    assert "echo:hi" in out
