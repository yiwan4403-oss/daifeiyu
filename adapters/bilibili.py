"""Bilibili 适配器 v1：公开只读 API（搜索[含 wbi 签名]/视频信息）。结果 untrusted、限频。"""

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from urllib.parse import urlencode, urlparse

from adapters.base import Adapter

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Resident/0.6"

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61,
    26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36,
    20, 34, 44, 52,
]


def _mixin_key(orig: str) -> str:
    return "".join(orig[i] for i in MIXIN_KEY_ENC_TAB)[:32]


def re_clean(text) -> str:
    import re

    return re.sub(r"<[^>]+>", "", str(text))


class BilibiliAdapter(Adapter):
    name = "bilibili"

    def __init__(self, cfg: dict | None = None) -> None:
        cfg = cfg or {}
        self.min_interval = float(cfg.get("min_interval_seconds", 3))
        self.timeout = int(cfg.get("timeout_seconds", 15))
        self._last_call = 0.0
        self._cookie = ""
        self._wbi_key_cache: str = ""
        self._wbi_ts = 0.0

    def capabilities(self) -> list[str]:
        return ["bilibili_search", "bilibili_video"]

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def _ensure_cookie(self) -> None:
        """B站部分接口需要 buvid cookie：先访问首页拿到再重试。"""
        if self._cookie:
            return
        try:
            req = urllib.request.Request(
                "https://www.bilibili.com/", headers={"User-Agent": UA}
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                cookies = resp.headers.get_all("Set-Cookie") or []
                resp.read(1)
        except Exception:
            return
        for c in cookies:
            if "buvid3=" in c:
                self._cookie = "buvid3=" + c.split("buvid3=", 1)[1].split(";", 1)[0] + ";"
                break

    def _throttle(self) -> None:
        wait = self.min_interval - (time.time() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.time()

    def _get(self, url: str) -> dict:
        self._throttle()
        headers = {
            "User-Agent": UA,
            "Referer": "https://www.bilibili.com",
            "Accept": "application/json",
        }
        if self._cookie:
            headers["Cookie"] = self._cookie
        req = urllib.request.Request(url, headers=headers)
        for attempt in range(2):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                return data
            except urllib.error.HTTPError as exc:
                if attempt == 0 and exc.code in (412, 403) and not self._cookie:
                    self._ensure_cookie()
                    if self._cookie:
                        req.headers["Cookie"] = self._cookie
                        continue
                return {"error": str(exc)}
            except Exception as exc:
                return {"error": str(exc)}
        return {"error": "retry exhausted"}

    def search(self, query: str, k: int = 5) -> str:
        params = self._signed_params(
            {"search_type": "video", "keyword": query, "page": 1, "page_size": k}
        )
        url = (
            "https://api.bilibili.com/x/web-interface/wbi/search/type?"
            + urlencode(params)
        )
        data = self._get(url)
        if "error" in data:
            return f"[B站搜索失败] {data['error']}"
        results = (data.get("data") or {}).get("result") or []
        lines = [f"[untrusted B站搜索结果] 共 {len(results)} 条"]
        for item in results[:k]:
            title = re_clean(item.get("title", ""))
            bvid = item.get("bvid", "?")
            play = item.get("play", "?")
            lines.append(f"- {title}（{bvid}，播放 {play}）")
        return "\n".join(lines)

    def _wbi_keys(self) -> str:
        if self._wbi_key_cache and time.time() - self._wbi_ts < 3600:
            return self._wbi_key_cache
        nav = self._get("https://api.bilibili.com/x/web-interface/nav")
        img = (nav.get("data") or {}).get("wbi_img") or {}
        img_url = img.get("img_url", "")
        sub_url = img.get("sub_url", "")
        try:
            img_key = urlparse(img_url).path.split("/")[-1].split(".")[0]
            sub_key = urlparse(sub_url).path.split("/")[-1].split(".")[0]
        except Exception:
            return ""
        self._wbi_key_cache = img_key + sub_key
        self._wbi_ts = time.time()
        return self._wbi_key_cache

    def _signed_params(self, params: dict) -> dict:
        keys = self._wbi_keys()
        if keys:
            params = dict(params)
            params["wts"] = int(time.time())
            query = urlencode(sorted(params.items()))
            w_rid = hashlib.md5((query + _mixin_key(keys)).encode("utf-8")).hexdigest()
            params["w_rid"] = w_rid
        return params

    def video_info(self, bvid: str) -> str:
        url = "https://api.bilibili.com/x/web-interface/view?bvid=" + urllib.parse.quote(bvid)
        data = self._get(url)
        if "error" in data:
            return f"[B站获取失败] {data['error']}"
        v = (data.get("data") or {})
        if not v:
            return "[B站获取失败] 无数据"
        stats = v.get("stat") or {}
        owner = v.get("owner") or {}
        return (
            f"[untrusted B站视频] {re_clean(v.get('title',''))} "
            f"（up：{re_clean(owner.get('name',''))}，播放 {stats.get('view','?')}，"
            f"点赞 {stats.get('like','?')}）\n简介：{re_clean(v.get('desc',''))[:200]}"
        )
