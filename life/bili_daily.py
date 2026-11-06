"""B 站生物钟：随机醒、克制分享、沉默衰减（设计借 dsh-bili-whale，登录态可选）。"""

import json
import os
import random
import time
from datetime import datetime

WATCH_TOPICS = ["我的世界", "独立游戏", "科普"]


class BiliDaily:
    def __init__(self, components: dict, cfg: dict) -> None:
        self.components = components
        self.cfg = cfg.get("bili_daily", {})
        self.adapter = (components.get("adapters") or {}).get("bilibili")
        self.window_start = int(self.cfg.get("window_start_hour", 20))
        self.window_end = int(self.cfg.get("window_end_hour", 24))
        self.max_share = int(self.cfg.get("max_share_per_day", 3))
        self.deep_read = int(self.cfg.get("deep_read", 3))
        self.skip_chance = float(self.cfg.get("skip_chance", 0.3))
        self.topics = list(self.cfg.get("topics", WATCH_TOPICS))
        data_dir = os.path.abspath(cfg.get("resident", {}).get("data_dir", "data"))
        self._state_path = os.path.join(data_dir, "bili_daily.json")
        self._state = self._load_state()

    def _today(self) -> str:
        return time.strftime("%Y-%m-%d")

    def _load_state(self) -> dict:
        try:
            with open(self._state_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"date": "", "shared": 0, "woke": False, "skipped": False}

    def _save_state(self) -> None:
        os.makedirs(os.path.dirname(self._state_path), exist_ok=True)
        with open(self._state_path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, ensure_ascii=False)

    def _wake_minute(self) -> int:
        return random.Random(self._today()).randint(0, 59)

    def maybe_wake(self) -> bool:
        """作息窗口内、当天随机时刻、按概率决定今天看不看。"""
        if self.adapter is None:
            return False
        today = self._today()
        if self._state.get("date") == today:
            return False
        now = datetime.now()
        if not (self.window_start <= now.hour < self.window_end):
            return False
        if now.hour == self.window_start and now.minute < self._wake_minute():
            return False
        skipped = random.Random(today + "skip").random() < self.skip_chance
        self._state = {"date": today, "shared": 0, "woke": True, "skipped": skipped}
        self._save_state()
        return not skipped

    def _owner_engaged_recently(self, days: int) -> bool:
        owner_ids = set(self.components.get("qq_owner_ids", set()) or set())
        if not owner_ids:
            return True
        conn = self.components["conn"]
        rows = conn.execute(
            "SELECT actor FROM events WHERE type='UserMessageReceived' AND ts > ?",
            (time.time() - days * 86400,),
        ).fetchall()
        return any(str(r[0]) in owner_ids for r in rows)

    def _quota(self) -> int:
        """沉默衰减：3 天没互动降额度，7 天归零（日记照写）。"""
        if not self._owner_engaged_recently(7):
            return 0
        if not self._owner_engaged_recently(3):
            return min(self.max_share, 2)
        return self.max_share

    def pick_videos(self) -> list[dict]:
        topic = random.Random(self._today()).choice(self.topics)
        try:
            items = self.adapter.search_items(topic, 5)
        except Exception:
            return []
        return sorted(items, key=lambda x: int(x.get("play") or 0), reverse=True)[: self.deep_read]

    async def run_session(self) -> str:
        items = self.pick_videos()
        if not items:
            return "今天没找到想看的。"
        lines = ["今天在 B 站看了这些："]
        for it in items:
            lines.append(f"- {it.get('title','')}（{it.get('bvid','?')}）")
        summary = "\n".join(lines)
        self.components["memories"].save("episodic", summary, source="self", salience=0.6)
        self.components["memories"].save(
            "autobiographical",
            f"{self._today()} 我看了 {len(items)} 个视频，最喜欢「{items[0].get('title','')}」。",
            source="self",
            salience=0.7,
        )
        shared = self._state.get("shared", 0)
        if shared < self._quota():
            pick = items[0]
            msg = f"给你挑了个视频：「{pick.get('title','')}」（{pick.get('bvid','?')}）"
            self.components["bus"].publish("proactive", msg)
            self._state["shared"] = shared + 1
            self._save_state()
        return summary

    async def maybe_run_async(self) -> str | None:
        if not self.maybe_wake():
            return None
        if self._state.get("skipped"):
            note = f"{self._today()} 今天不想看视频，休息一下。"
            self.components["memories"].save("episodic", note, source="self", salience=0.4)
            return note
        return await self.run_session()
