"""Bilibili 适配器 v2：扫码登录 + 风控参数表 + 已登录工具。结果 untrusted、限频。"""

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from urllib.parse import urlencode, urlparse

from adapters.base import Adapter

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Resident/0.7"

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61,
    26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36,
    20, 34, 44, 52,
]


def _mixin_key(orig: str) -> str:
    return "".join(orig[i] for i in MIXIN_KEY_ENC_TAB)[:32]


def re_clean(text) -> str:
    return re.sub(r"<[^>]+>", "", str(text))


class BiliGovernor:
    """风控参数表（程序化执行，参数不可被 LLM 改）。"""

    def __init__(self, cfg: dict | None = None) -> None:
        cfg = cfg or {}
        self.read_per_hour = int(cfg.get("read_per_hour", 600))
        self.read_per_day = int(cfg.get("read_per_day", 3000))
        self.write_per_hour = int(cfg.get("write_per_hour", 12))
        self.write_per_day = int(cfg.get("write_per_day", 30))
        self.write_cooldown = float(cfg.get("write_cooldown_seconds", 120))
        self.dm_cooldown = float(cfg.get("dm_cooldown_seconds", 60))
        self.req_interval = float(cfg.get("request_interval_seconds", 1.5))
        self.backoff_steps = [300, 600, 1200, 1800]
        self._reads: deque = deque()
        self._writes: deque = deque()
        self._last_req = 0.0
        self._last_write = 0.0
        self._last_dm = 0.0
        self._backoff_until = 0.0
        self._backoff_level = 0

    def _purge(self, dq: deque, window: float) -> None:
        now = time.time()
        while dq and now - dq[0] > window:
            dq.popleft()

    def pause_until(self) -> float:
        return max(self._backoff_until, time.time())

    def throttle(self) -> None:
        wait = self.req_interval - (time.time() - self._last_req)
        if wait > 0:
            time.sleep(wait)
        self._last_req = time.time()

    def allow_read(self) -> str:
        now = time.time()
        if now < self._backoff_until:
            return f"平台暂停中，还需 {int(self._backoff_until - now)} 秒"
        self._purge(self._reads, 3600)
        if len(self._reads) >= self.read_per_hour:
            return "读预算耗尽（600/时）"
        self._purge(self._reads, 86400)
        if len(self._reads) >= self.read_per_day:
            return "读预算耗尽（3000/天）"
        return ""

    def allow_write(self, is_dm: bool = False) -> str:
        now = time.time()
        if now < self._backoff_until:
            return f"平台暂停中，还需 {int(self._backoff_until - now)} 秒"
        cd = self.dm_cooldown if is_dm else self.write_cooldown
        last = self._last_dm if is_dm else self._last_write
        if now - last < cd:
            return f"冷却中，还需 {int(cd - (now - last))} 秒"
        self._purge(self._writes, 3600)
        if len(self._writes) >= self.write_per_hour:
            return "写预算耗尽（12/时）"
        self._purge(self._writes, 86400)
        if len(self._writes) >= self.write_per_day:
            return "写预算耗尽（30/天）"
        return ""

    def record_read(self) -> None:
        self._reads.append(time.time())

    def record_write(self, is_dm: bool = False) -> None:
        now = time.time()
        self._writes.append(now)
        if is_dm:
            self._last_dm = now
        else:
            self._last_write = now

    def record_throttle_hit(self) -> int:
        """撞 412/429：升级退避，返回暂停秒数。"""
        step = self.backoff_steps[min(self._backoff_level, len(self.backoff_steps) - 1)]
        self._backoff_level = min(self._backoff_level + 1, len(self.backoff_steps) - 1)
        self._backoff_until = time.time() + step
        return step

    def record_success(self) -> None:
        self._backoff_level = 0


class BilibiliAdapter(Adapter):
    name = "bilibili"

    def __init__(self, cfg: dict | None = None, credentials_path: str | None = None) -> None:
        cfg = cfg or {}
        self.min_interval = float(cfg.get("min_interval_seconds", 1.5))
        self.timeout = int(cfg.get("timeout_seconds", 15))
        self.owner_mid = str(cfg.get("owner_mid", "") or "")
        self.cred_path = credentials_path or os.path.join(
            os.getcwd(), "credentials", "bili.json"
        )
        self.gov = BiliGovernor(cfg.get("risk", {}))
        self.gov.req_interval = self.min_interval
        self._last_call = 0.0
        self._cookie = ""
        self._wbi_key_cache = ""
        self._wbi_ts = 0.0
        self._login_key = ""
        self._load_credentials()

    # ---------- 凭据 ----------
    def _load_credentials(self) -> None:
        if os.path.isfile(self.cred_path):
            try:
                data = json.load(open(self.cred_path, encoding="utf-8"))
                self._cookie = str(data.get("cookie", ""))
            except Exception:
                self._cookie = ""

    def _save_credentials(self) -> None:
        os.makedirs(os.path.dirname(self.cred_path), exist_ok=True)
        json.dump({"cookie": self._cookie}, open(self.cred_path, "w", encoding="utf-8"))

    @property
    def logged_in(self) -> bool:
        return "SESSDATA" in self._cookie

    # ---------- 基础请求（过风控） ----------
    def capabilities(self) -> list[str]:
        return ["bilibili_search", "bilibili_video", "bilibili_me", "bilibili_dm"]

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def _ensure_cookie(self) -> None:
        if self._cookie:
            return
        try:
            req = urllib.request.Request("https://www.bilibili.com/", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                cookies = resp.headers.get_all("Set-Cookie") or []
                resp.read(1)
        except Exception:
            return
        for c in cookies:
            if "buvid3=" in c:
                self._cookie = "buvid3=" + c.split("buvid3=", 1)[1].split(";", 1)[0] + ";"
                break

    def _headers(self) -> dict:
        headers = {
            "User-Agent": UA,
            "Referer": "https://www.bilibili.com",
            "Accept": "application/json",
        }
        if self._cookie:
            headers["Cookie"] = self._cookie
        return headers

    def _raw(self, url: str, data: bytes | None = None, method: str = "GET"):
        headers = self._headers()
        if data is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        return urllib.request.urlopen(req, timeout=self.timeout)

    def _get(self, url: str, count_read: bool = True) -> dict:
        if count_read:
            self._ensure_cookie()
            deny = self.gov.allow_read()
            if deny:
                return {"error": deny}
            self.gov.throttle()
        for attempt in range(2):
            try:
                with self._raw(url) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                if count_read:
                    self.gov.record_read()
                self.gov.record_success()
                return data
            except urllib.error.HTTPError as exc:
                if exc.code in (412, 429):
                    secs = self.gov.record_throttle_hit()
                    return {"error": f"被平台限流，暂停 {secs} 秒"}
                if attempt == 0 and exc.code in (412, 403) and not self._cookie:
                    self._ensure_cookie()
                    continue
                return {"error": str(exc)}
            except Exception as exc:
                return {"error": str(exc)}
        return {"error": "retry exhausted"}

    # ---------- 扫码登录 ----------
    def login_start(self) -> dict:
        data = self._get(
            "https://passport.bilibili.com/x/passport-login/web/qrcode/generate",
            count_read=False,
        )
        if "error" in data:
            return data
        d = data.get("data") or {}
        self._login_key = d.get("qrcode_key", "")
        return {"qrcode_key": self._login_key, "url": d.get("url", "")}

    def login_poll(self) -> dict:
        """0=成功 86038=过期 86090=已扫待确认 86101=未扫。成功后自动保存凭据。"""
        if not self._login_key:
            return {"status": "no_key"}
        data = self._get(
            "https://passport.bilibili.com/x/passport-login/web/qrcode/poll?qrcode_key="
            + urllib.parse.quote(self._login_key),
            count_read=False,
        )
        if "error" in data:
            return {"status": "error", "detail": data["error"]}
        code = int((data.get("data") or {}).get("code", data.get("code", -1)))
        if code == 0:
            # 抓登录后的 cookie：走一遍 nav 拿 Set-Cookie
            try:
                with self._raw("https://api.bilibili.com/x/web-interface/nav") as resp:
                    cookies = resp.headers.get_all("Set-Cookie") or []
                    resp.read(1)
                jar = {}
                for c in cookies:
                    if "=" in c:
                        k = c.split("=", 1)[0].strip()
                        v = c.split("=", 1)[1].split(";", 1)[0]
                        jar[k] = v
                parts = ";".join(f"{k}={v}" for k, v in jar.items())
                if parts:
                    self._cookie = self._cookie.rstrip(";") + ";" + parts
                self._save_credentials()
            except Exception as exc:
                return {"status": "error", "detail": f"登录成功但取凭据失败: {exc}"}
            return {"status": "success"}
        return {"status": "waiting", "code": code}

    def me(self) -> str:
        data = self._get("https://api.bilibili.com/x/web-interface/nav")
        if "error" in data:
            return f"[B站未登录/失败] {data['error']}"
        d = data.get("data") or {}
        if not d.get("isLogin"):
            return "[B站未登录]"
        return f"[B站账号] {re_clean(d.get('uname',''))}（mid {d.get('mid','?')}，等级 {d.get('level_info',{}).get('current_level','?')}）"

    def dm_status(self) -> str:
        if not self.owner_mid:
            return "[未配置 owner_mid]"
        data = self._get(f"https://api.bilibili.com/x/relation/stat?vmid={self.owner_mid}")
        if "error" in data:
            return f"[查询失败] {data['error']}"
        attribute = (data.get("data") or {}).get("attribute", 0)
        return f"[互关状态] attribute={attribute}（6=互关，可发私信）"

    def send_dm(self, text: str, target_mid: str = "") -> dict:
        """三条硬限制：只发 owner、必须互关、一天锁定一个收信人。"""
        if not self.owner_mid:
            return {"ok": False, "detail": "未配置 owner_mid"}
        target = target_mid or self.owner_mid
        if target != self.owner_mid:
            return {"ok": False, "detail": "只允许发给 owner"}
        if not self.logged_in:
            return {"ok": False, "detail": "未登录"}
        deny = self.gov.allow_write(is_dm=True)
        if deny:
            return {"ok": False, "detail": deny}
        if not hasattr(self, "_dm_target_day"):
            self._dm_target_day = ""
        today = time.strftime("%Y-%m-%d")
        if self._dm_target_day != today:
            self._dm_target_day = today
        data = self._get(
            f"https://api.bilibili.com/x/relation/stat?vmid={target}"
        )
        if int((data.get("data") or {}).get("attribute", 0)) != 6:
            return {"ok": False, "detail": "未互关（需要 attribute=6）"}
        import urllib.parse as _up

        bili_jct = ""
        for part in self._cookie.split(";"):
            if part.strip().startswith("bili_jct="):
                bili_jct = part.strip().split("=", 1)[1]
        if not bili_jct:
            return {"ok": False, "detail": "缺少 bili_jct（csrf）"}
        payload = {
            "msg[sender_uid]": "",
            "msg[receiver_id]": target,
            "msg[msg_type]": 1,
            "msg[content]": json.dumps({"content": text}),
            "msg[timestamp]": int(time.time()),
            "msg[dev_id]": "resident",
            "csrf": bili_jct,
            "csrf_token": bili_jct,
            "build": 0,
            "mobi_app": "web",
        }
        body = urlencode(payload).encode("utf-8")
        try:
            with self._raw(
                "https://api.vc.bilibili.com/web_im/v1/web_im/send_msg",
                data=body,
                method="POST",
            ) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            return {"ok": False, "detail": str(exc)}
        if result.get("code") != 0:
            return {"ok": False, "detail": f"code={result.get('code')} {result.get('msg','')}"}
        self.gov.record_write(is_dm=True)
        return {"ok": True, "detail": "已发送"}

    # ---------- 公开只读（原 v1） ----------
    def _wbi_keys(self) -> str:
        if self._wbi_key_cache and time.time() - self._wbi_ts < 3600:
            return self._wbi_key_cache
        nav = self._get("https://api.bilibili.com/x/web-interface/nav")
        img = (nav.get("data") or {}).get("wbi_img") or {}
        try:
            img_key = urlparse(img.get("img_url", "")).path.split("/")[-1].split(".")[0]
            sub_key = urlparse(img.get("sub_url", "")).path.split("/")[-1].split(".")[0]
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

    def search_items(self, query: str, k: int = 5) -> list[dict]:
        """wbi 搜索，返回原始条目（供生物钟挑选）。"""
        params = self._signed_params(
            {"search_type": "video", "keyword": query, "page": 1, "page_size": k}
        )
        url = "https://api.bilibili.com/x/web-interface/wbi/search/type?" + urlencode(params)
        data = self._get(url)
        if "error" in data:
            return []
        results = (data.get("data") or {}).get("result") or []
        return [
            {
                "title": re_clean(item.get("title", "")),
                "bvid": item.get("bvid", "?"),
                "play": item.get("play", 0),
            }
            for item in results
        ]

    def search(self, query: str, k: int = 5) -> str:
        items = self.search_items(query, k)
        if not items:
            return "[B站搜索失败] 无结果或接口受限"
        lines = [f"[untrusted B站搜索结果] 共 {len(items)} 条"]
        for it in items[:k]:
            lines.append(f"- {it['title']}（{it['bvid']}，播放 {it['play']}）")
        return "\n".join(lines)

    def video_info(self, bvid: str) -> str:
        url = "https://api.bilibili.com/x/web-interface/view?bvid=" + urllib.parse.quote(bvid)
        data = self._get(url)
        if "error" in data:
            return f"[B站获取失败] {data['error']}"
        v = data.get("data") or {}
        if not v:
            return "[B站获取失败] 无数据"
        stats = v.get("stat") or {}
        owner = v.get("owner") or {}
        return (
            f"[untrusted B站视频] {re_clean(v.get('title',''))} "
            f"（up：{re_clean(owner.get('name',''))}，播放 {stats.get('view','?')}，"
            f"点赞 {stats.get('like','?')}）\n简介：{re_clean(v.get('desc',''))[:200]}"
        )
