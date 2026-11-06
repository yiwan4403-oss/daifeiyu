"""Browser 适配器 v1：只读抓取网页文本。结果一律 untrusted，只当数据处理。"""

import urllib.request

from adapters.base import Adapter


class BrowserAdapter(Adapter):
    name = "browser"

    def __init__(self, timeout: int = 20, max_bytes: int = 60_000) -> None:
        self.timeout = timeout
        self.max_bytes = max_bytes

    def capabilities(self) -> list[str]:
        return ["web_fetch"]

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def fetch_text(self, url: str) -> str:
        if not url.startswith(("http://", "https://")):
            return "[拒绝] 只允许 http/https"
        req = urllib.request.Request(url, headers={"User-Agent": "Resident/0.5"})
        for attempt in range(2):
            try:
                if attempt == 1:
                    import ssl

                    ctx = ssl._create_unverified_context()
                    with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
                        body = resp.read(self.max_bytes + 1)
                else:
                    with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                        body = resp.read(self.max_bytes + 1)
                text = body[: self.max_bytes].decode("utf-8", errors="replace")
                return f"[untrusted 网页内容] {text}"
            except Exception as exc:
                if attempt == 0 and "CERTIFICATE" in str(exc):
                    continue
                return f"[抓取失败] {exc}"
        return "[抓取失败]"
