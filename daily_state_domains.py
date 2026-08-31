# -*- coding: utf-8 -*-
"""Pure domain rules used by ``DailyStateMixin``.

This module deliberately has no AstrBot, persistence, configuration, clock, or
network dependencies.  Keeping these classification/normalization rules here
makes state generation easier to characterize without changing the mixin's
public surface or MRO.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Callable, Iterable


_LOCATION_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("被窝", "床上", "床边", "卧室", "房间", "书桌", "台灯", "家里", "客厅", "沙发", "洗漱台", "餐桌"), "家里"),
    (("教室", "课间", "食堂", "校门", "走廊", "操场", "上课", "下课", "自习", "老师", "书包", "制服"), "学校"),
    (("工位", "会议", "办公室", "上班", "下班", "通勤", "打卡"), "工作场所"),
    (("便利店", "超市", "商店"), "便利店附近"),
    (("路上", "街上", "出门", "楼下", "外面", "街边", "回家路上", "校门口"), "外面"),
    (("楼梯口", "走廊栏杆", "窗边", "阳台"), "过道或窗边"),
)

_LIFECYCLE_ALIASES = {
    "planned": "planned", "计划": "planned", "未开始": "planned",
    "active": "active", "进行": "active", "进行中": "active",
    "completed": "completed", "完成": "completed", "已完成": "completed",
    "changed": "changed", "变更": "changed", "已变更": "changed",
    "cancelled": "cancelled", "canceled": "cancelled", "取消": "cancelled", "已取消": "cancelled",
    "deferred": "deferred", "postponed": "deferred", "顺延": "deferred", "延期": "deferred",
}
_ALLOWED_SCHEDULE_BASES = frozenset(
    {"calendar", "persona", "adjustment", "state", "weather", "continuity", "inspiration", "coarse_plan"}
)
_SLEEP_PHASE_LABELS = {
    "awake": "清醒",
    "falling_asleep": "入睡中",
    "light_sleep": "浅睡",
    "woken": "被叫醒",
    "staying_up": "临时晚睡",
    "sleeping_again": "继续睡",
    "natural_wake": "自然醒",
}
_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def single_line(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def build_health_causes(
    *,
    sleep_label: str,
    weather_text: str,
    diary_tags: set[str],
    random_value: Callable[[], float],
) -> list[str]:
    """Derive ordered health-pressure causes with entropy supplied explicitly."""

    causes: list[str] = []
    if sleep_label not in {"睡眠平稳", "睡得很踏实"} and random_value() < 0.7:
        causes.append("昨晚没睡踏实")
    if any(tag in diary_tags for tag in {"失眠", "低能量"}) and random_value() < 0.45:
        causes.append("前一天状态就有点透支")
    weather_lower = str(weather_text or "").lower()
    if any(token in weather_text for token in ("降雨", "小雨", "中雨", "大雨", "阴", "多云")) and random_value() < 0.4:
        causes.append("空气有点潮,身上那股乏劲更明显")
    if any(token in weather_text for token in ("风", "降温", "冷")) and random_value() < 0.55:
        causes.append("吹了点风,身上容易发空")
    temp_match = re.search(r"(-?\d+(?:\.\d+)?)\s*°C", weather_lower)
    if temp_match:
        try:
            temp = float(temp_match.group(1))
        except ValueError:
            temp = 20.0
        if temp <= 10 and random_value() < 0.55:
            causes.append("天气偏冷,早上容易着凉")
        elif temp >= 30 and random_value() < 0.35:
            causes.append("天气闷热,整个人有点蔫")
    return causes


def pick_health_spec(
    causes: list[str],
    intensity: float,
    *,
    random_value: Callable[[], float],
    choose: Callable[[list[tuple[str, str, int, int]]], tuple[str, str, int, int]],
) -> tuple[str, str, int, int, str] | None:
    if not causes:
        return None
    chance = min(0.42, 0.12 + len(causes) * 0.1 * max(0.5, intensity))
    if random_value() > chance:
        return None
    cause_text = ",".join(dict.fromkeys(causes[:2]))
    pool = [
        ("喉咙有点发紧,今天想少说重话", "安静", -10, 24),
        ("头有点沉,做事想放慢一点", "疲惫", -14, 18),
        ("像有点发虚,反应会慢半拍", "疲惫", -18, 30),
    ]
    label, mood, energy_delta, duration_hours = choose(pool)
    if "闷热" in cause_text and "喉咙" in label:
        label = "有点发闷,只想把动作放轻一点"
    if "潮" in cause_text and "头有点沉" in label:
        label = "身上有点沉,今天想把事情做轻一点"
    return label, mood, energy_delta, duration_hours, cause_text


def infer_location_from_text(text: Any) -> str:
    normalized = single_line(text, 200)
    for keywords, label in _LOCATION_RULES:
        if any(keyword in normalized for keyword in keywords):
            return label
    return ""


def is_sleepy_plan_item(item: dict[str, Any] | None) -> bool:
    if not isinstance(item, dict):
        return False
    text = " ".join(
        value for key in ("activity", "mood", "message_seed")
        if (value := single_line(item.get(key), 100))
    )
    if not text:
        return False
    if re.search(r"继续睡|睡回去|重新入睡|再次入睡|回笼觉", text):
        return True
    if re.search(
        r"自然醒|睡醒|醒来|醒后|刚醒|醒了|已醒|醒着|清醒|睁眼|起床|起身|洗漱|"
        r"不睡|没睡|未睡|还没睡|睡不着|失眠",
        text,
    ):
        return False
    return bool(re.search(
        r"睡觉|睡眠|入睡|熟睡|浅睡|午睡|午休|小睡|补觉|回笼觉|打盹|"
        r"眯(?:一|半)?会(?:儿)?|梦乡|被窝|准备睡|睡前|继续睡|睡回去|熄灯休息",
        text,
    ))


def normalize_schedule_lifecycle_status(value: Any) -> str:
    return _LIFECYCLE_ALIASES.get(single_line(value, 20).lower(), "")


def normalize_schedule_basis(value: Any, *, default: Iterable[str] | None = None) -> list[str]:
    raw = value if isinstance(value, list) else re.split(r"[,，;；\s]+", str(value or ""))
    result: list[str] = []
    for item in raw:
        key = single_line(item, 24).lower()
        if key in _ALLOWED_SCHEDULE_BASES and key not in result:
            result.append(key)
    return result[:3] or list(default or [])[:3]


def parse_hhmm_to_minutes(value: Any) -> int | None:
    match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(value or ""))
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return hour * 60 + minute


def minutes_to_hhmm(minutes: int) -> str:
    wrapped = max(0, int(minutes)) % (24 * 60)
    return f"{wrapped // 60:02d}:{wrapped % 60:02d}"


def normalized_plan_item_starts(items: Any) -> list[int | None]:
    if not isinstance(items, list):
        return []
    normalized: list[int | None] = []
    day_offset = 0
    previous_raw: int | None = None
    for item in items:
        raw = parse_hhmm_to_minutes(item.get("time")) if isinstance(item, dict) else None
        if raw is None:
            normalized.append(None)
            continue
        if previous_raw is not None and raw < previous_raw:
            day_offset += 24 * 60
        normalized.append(raw + day_offset)
        previous_raw = raw
    return normalized


def schedule_window_runtime_status(
    start: int,
    end: int,
    *,
    explicit_status: Any,
    now_minutes: int | None,
    date_text: str,
    today_key: str,
) -> str:
    explicit = normalize_schedule_lifecycle_status(explicit_status)
    if explicit == "cancelled":
        return explicit
    if now_minutes is None:
        return "completed" if date_text and date_text < today_key else "planned"
    normalized_end = int(end)
    if normalized_end <= start:
        normalized_end += 24 * 60
    if now_minutes < start:
        runtime = "planned"
    elif now_minutes >= normalized_end:
        runtime = "completed"
    else:
        runtime = "active"
    return "changed" if explicit == "changed" and runtime != "completed" else runtime


def sleep_phase_label(phase: str) -> str:
    return _SLEEP_PHASE_LABELS.get(str(phase or ""), "清醒")


def sleep_delay_cn_number(value: Any) -> int | None:
    text = str(value or "").strip().replace("兩", "两").replace("〇", "零")
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if text in _CN_DIGITS:
        return _CN_DIGITS[text]
    if "十" in text:
        left, _, right = text.partition("十")
        tens = _CN_DIGITS.get(left, 1) if left else 1
        ones = _CN_DIGITS.get(right, 0) if right else 0
        return tens * 10 + ones
    return None


def sleep_delay_parse_minute(value: Any) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    fixed = {"半": 30, "一刻": 15, "三刻": 45}
    if text in fixed:
        return fixed[text]
    parsed = sleep_delay_cn_number(text)
    return 0 if parsed is None else max(0, min(59, parsed))


def parse_sleep_delay_until_ts(
    compact: str,
    *,
    current: datetime,
    next_local_ts: Callable[[int, int], float],
    fromtimestamp: Callable[[float], datetime],
) -> tuple[float, bool]:
    hour_token = r"(?:\d{1,2}|[零〇一二两兩三四五六七八九十]{1,3})"
    minute_token = r"(?:\d{1,2}|[零〇一二两兩三四五六七八九十]{1,3}|半|一刻|三刻)"
    match = re.search(
        rf"(?:陪(?:我|着我)?到|陪到|撑到|等到|到|至)"
        rf"(凌晨|半夜|今晚|今夜|夜里|晚上|明早|明天早上|明天)?"
        rf"({hour_token})(?:[:：点點时])({minute_token})?",
        compact,
    )
    if not match:
        return 0.0, False
    period = str(match.group(1) or "")
    hour = sleep_delay_cn_number(match.group(2))
    if hour is None:
        return 0.0, False
    minute = sleep_delay_parse_minute(match.group(3))
    if period in {"凌晨", "半夜"}:
        hour = 0 if hour == 12 else hour
    elif period in {"今晚", "今夜", "夜里", "晚上"}:
        hour = 0 if hour == 12 else hour + 12 if 6 <= hour <= 11 else hour
    elif period in {"明早", "明天早上"}:
        hour = 0 if hour == 12 else hour
    elif current.hour >= 18:
        hour = 0 if hour == 12 else hour + 12 if 6 <= hour <= 11 else hour
    if hour > 23:
        return 0.0, False
    target_ts = next_local_ts(hour, minute)
    if period in {"明早", "明天早上"}:
        target_dt = fromtimestamp(target_ts)
        if target_dt.date() == current.date():
            target_ts = (target_dt + timedelta(days=1)).timestamp()
    explicit_cap = min(current.timestamp() + 6 * 3600, next_local_ts(6, 0))
    return min(target_ts, explicit_cap), True
