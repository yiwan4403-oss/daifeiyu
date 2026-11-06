"""调度器：低频节拍驱动自主生活（事件驱动 + 后台 tick，禁止高频 LLM）。"""

import asyncio
import time
from collections import deque
from datetime import datetime

from life.activities import ActivityManager
from life.desire import DesireManager
from life.goals import GoalManager
from life.planner import LifePlanner

ACTIVITY_TO_DESIRE = {
    "发呆": None,
    "整理记忆": "整理自己的记忆",
    "写日记": "整理自己的记忆",
    "想想某个朋友": "想和朋友们聊天",
    "休息": "好好休息",
    "学点新东西": "学点新东西",
    "等朋友来聊天": "想和朋友们聊天",
}


class Scheduler:
    def __init__(self, cfg: dict, components: dict) -> None:
        self.cfg = cfg.get("life", {})
        self.components = components
        self.tick_seconds = int(self.cfg.get("tick_seconds", 60))
        self.idle_minutes = float(self.cfg.get("idle_minutes", 10))
        self.activity_interval = float(self.cfg.get("activity_interval_minutes", 30))
        self.max_decisions = int(self.cfg.get("max_decisions_per_hour", 6))
        self.reflect_every = int(self.cfg.get("reflect_every_activities", 8))
        self._decision_ts: deque = deque()
        self._last_activity_ts = 0.0
        self._activity_count = 0
        self.planner = LifePlanner(cfg, components)
        self.activities = ActivityManager(components["conn"])
        self.desires = DesireManager(components["conn"])
        self.goals = GoalManager(components["conn"])
        self.stop = asyncio.Event()

    def _allow_decision(self) -> bool:
        now = time.time()
        while self._decision_ts and now - self._decision_ts[0] > 3600:
            self._decision_ts.popleft()
        return len(self._decision_ts) < self.max_decisions

    def _state_text(self) -> str:
        now = datetime.now()
        emotion = self.components["emotion"].summary()
        desires = "、".join(f"{n}({s:.1f})" for n, s in self.desires.top(3))
        goals = "；".join(g["text"] for g in self.goals.list_active(3)) or "无"
        current = self.activities.current()
        activity = current["kind"] if current else "无"
        recent = self.components["events"].recent(6)
        recent_txt = "\n".join(f"- [{e.type}] {e.payload[:40]}" for e in recent)
        return (
            f"现在是 {now:%Y-%m-%d %H:%M}（周{'一二三四五六日'[now.weekday()]}）。\n"
            f"当前情绪：{emotion}\n当前欲望：{desires}\n进行中的目标：{goals}\n"
            f"正在做：{activity}\n最近发生：\n{recent_txt}"
        )

    def _proactive_ok(self) -> bool:
        pro = self.cfg.get("proactive", {})
        if not pro.get("enabled", True):
            return False
        now = datetime.now()
        if not (int(pro.get("start_hour", 8)) <= now.hour < int(pro.get("end_hour", 23))):
            return False
        if hasattr(self, "_last_say_ts"):
            gap = float(pro.get("min_gap_minutes", 60)) * 60
            if time.time() - self._last_say_ts < gap:
                return False
        return True

    async def _tick(self) -> None:
        self.components["emotion"].decay()
        idle_sec = time.time() - self.components.get("last_user_ts", 0.0)
        if idle_sec < self.idle_minutes * 60:
            return
        now = time.time()
        if now - self._last_activity_ts < self.activity_interval * 60:
            return
        if not self._allow_decision():
            return
        plan = await self.planner.decide(self._state_text())
        if not plan:
            return
        self._decision_ts.append(now)
        activity = str(plan.get("activity", "")).strip()
        if activity in ACTIVITY_TO_DESIRE:
            self.activities.start(activity)
            self._last_activity_ts = now
            self._activity_count += 1
            self.components["events"].append(
                "ActivityStarted", "private", "self", "", activity
            )
            desire = ACTIVITY_TO_DESIRE[activity]
            if desire:
                self.desires.feed(desire)
            print(f"[life] 现在去做：{activity}")
            if self._activity_count % self.reflect_every == 0:
                line = await self.planner.reflect(self.activities.today_summary())
                if line:
                    self.components["memories"].save(
                        "autobiographical",
                        line,
                        source="self",
                        salience=0.8,
                    )
                    print(f"[life] 自我观察：{line}")
        goal = str(plan.get("goal", "") or "").strip()
        if goal and len(goal) <= 60:
            self.goals.create(goal)
            print(f"[life] 立了个目标：{goal}")
        say = str(plan.get("say", "") or "").strip()
        if say and self._proactive_ok():
            self._last_say_ts = time.time()
            self.components["bus"].publish("proactive", say)

    async def run(self) -> None:
        while not self.stop.is_set():
            try:
                await asyncio.wait_for(self.stop.wait(), timeout=self.tick_seconds)
            except asyncio.TimeoutError:
                pass
            if self.stop.is_set():
                return
            try:
                await self._tick()
            except Exception as exc:
                print(f"[life] tick 失败（不影响聊天）：{exc}")
