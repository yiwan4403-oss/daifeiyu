"""研究工具：GitHub 搜索 + 只读抓取。全部返回 untrusted 数据。"""

import json
import urllib.request

GITHUB_API = "https://api.github.com"


class ResearchError(Exception):
    pass


class Researcher:
    def __init__(self, timeout: int = 20, max_bytes: int = 100_000) -> None:
        self.timeout = timeout
        self.max_bytes = max_bytes

    def search_repos(self, query: str, k: int = 5) -> list[dict]:
        url = (
            GITHUB_API + "/search/repositories?q="
            + urllib.parse.quote(query) + f"&per_page={k}"
        )
        data = self._get_json(url)
        return [
            {
                "full_name": r.get("full_name"),
                "description": (r.get("description") or "")[:200],
                "stars": r.get("stargazers_count"),
                "license": (r.get("license") or {}).get("spdx_id"),
                "html_url": r.get("html_url"),
            }
            for r in data.get("items", [])
        ]

    def fetch_raw(self, owner: str, repo: str, path: str, branch: str = "main") -> str:
        """抓取单文件原文（untrusted，限长）。"""
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
        req = urllib.request.Request(url, headers={"User-Agent": "Resident"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read(self.max_bytes + 1)
        except Exception as exc:
            raise ResearchError(str(exc)) from exc
        if len(body) > self.max_bytes:
            return body[: self.max_bytes].decode("utf-8", errors="replace") + "\n[截断]"
        return body.decode("utf-8", errors="replace")

    def _get_json(self, url: str) -> dict:
        req = urllib.request.Request(url, headers={"User-Agent": "Resident"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise ResearchError(str(exc)) from exc
