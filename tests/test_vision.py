"""视觉适配器测试：本地 OCR 结构、Ollama 本地模型调用（mock）。"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from adapters.vision import VisionAdapter  # noqa: E402


def test_to_prompt_structure():
    info = {"basics": "100×50 PNG RGB", "ocr": "你好世界"}
    out = VisionAdapter.to_prompt(info)
    assert "100×50" in out
    assert "你好世界" in out
    empty = VisionAdapter.to_prompt({"basics": "1×1 PNG", "ocr": ""})
    assert "未识别到" in empty


def test_local_available_flag():
    off = VisionAdapter({"local": {"enabled": False, "model": "x"}})
    assert off.local_available() is False
    on = VisionAdapter({"local": {"enabled": True, "model": "qwen2.5vl:3b"}})
    assert on.local_available() is True
    assert on.caption_local("nope.png") == ""  # 文件不存在时安全返回空


def test_fetch_file_url_windows_style(tmp_path):
    img = tmp_path / "b.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 50)
    adapter = VisionAdapter({})
    url = "file:///" + str(img).replace("\\", "/")
    assert os.path.isfile(adapter.fetch(url))


def test_caption_local_mocked(tmp_path, monkeypatch):
    img = tmp_path / "a.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 100)
    adapter = VisionAdapter(
        {"local": {"enabled": True, "model": "qwen2.5vl:3b"}}
    )

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"response": "一只橘猫趴在键盘上。"}).encode("utf-8")

    import urllib.request

    calls = {}

    def fake_urlopen(req, timeout):
        calls["url"] = req.full_url
        calls["body"] = json.loads(req.data.decode("utf-8"))
        return FakeResp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    out = adapter.caption_local(str(img))
    assert "橘猫" in out
    assert calls["url"].endswith("/api/generate")
    assert calls["body"]["model"] == "qwen2.5vl:3b"
    assert calls["body"]["images"]
