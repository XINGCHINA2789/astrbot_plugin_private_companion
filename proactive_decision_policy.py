# -*- coding: utf-8 -*-
"""Pure classifications shared by proactive planning and scheduling."""
from __future__ import annotations

from typing import Any, Callable


NormalizeText = Callable[..., str]


def proactive_item_freshness_class(
    *,
    action: str,
    reason: str,
    source: str,
    semantic_kind: str = "",
    normalize: NormalizeText,
) -> str:
    normalized_reason = normalize(reason, limit=40)
    normalized_source = normalize(source, limit=40)
    normalized_kind = normalize(semantic_kind, limit=40)
    if normalized_reason in {"environment_change", "weather_alert", "health_alert", "memo_note_reminder"} or normalized_source in {
        "environment_change",
        "weather_alert",
        "body_monitor",
        "memo_note",
    }:
        return "immediate"
    if normalized_source == "timer" or normalized_reason in {
        "birthday_eve_hint",
        "birthday_celebration",
        "birthday_makeup",
        "birthday_afterglow",
        "important_date_share",
        "special_day_greeting",
        "bili_video_share",
        "news_share",
        "web_exploration_share",
        "creative_share",
    }:
        return "durable"
    action_parts = {part.strip() for part in str(action or "").split("+") if part.strip()}
    if {"photo_text", "screen_peek"} & action_parts:
        return "immediate"
    if normalized_kind in {"self_share", "observation"} and normalized_source in {
        "story",
        "daily_story",
        "state",
        "event",
        "simulation",
    }:
        return "immediate"
    return "contextual"


def proactive_timeliness_level(
    *, reason: Any = "", source: Any = "", normalize: NormalizeText
) -> str:
    """Classify only events whose value materially decays within minutes."""
    normalized_reason = normalize(reason, limit=40)
    normalized_source = normalize(source, limit=40)
    if normalized_reason in {"weather_alert", "health_alert"} or normalized_source in {
        "weather_alert",
        "body_monitor",
    }:
        return "urgent"
    if normalized_reason in {
        "environment_change",
        "memo_note_reminder",
        "birthday_celebration",
        "special_day_greeting",
        "insomnia_night",
    } or normalized_source in {
        "environment_change",
        "memo_note",
        "special_day_ritual",
        "night_care",
    }:
        return "timely"
    return "routine"
