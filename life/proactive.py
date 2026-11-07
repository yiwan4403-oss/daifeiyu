"""主动消息投递策略：免打扰、每日额度、去重键。"""

import time


def quiet_now(cfg: dict, hour: int) -> bool:
    start = int(cfg.get("quiet_start_hour", 23))
    end = int(cfg.get("quiet_end_hour", 8))
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end


def daily_count(conn, action: str) -> int:
    start = time.mktime(time.strptime(time.strftime("%Y-%m-%d"), "%Y-%m-%d"))
    row = conn.execute(
        "SELECT COUNT(*) FROM outbox WHERE action=? AND created_at>=?",
        (action, start),
    ).fetchone()
    return int(row[0])


def can_send(conn, cfg: dict, hour: int | None = None) -> tuple[bool, str]:
    if not cfg.get("enabled", True):
        return False, "主动投递已关闭"
    hour = time.localtime().tm_hour if hour is None else hour
    if quiet_now(cfg, hour):
        return False, "免打扰时段"
    cap = int(cfg.get("max_per_day", 3))
    if daily_count(conn, "proactive_qq") >= cap:
        return False, "今日额度用完"
    return True, ""
