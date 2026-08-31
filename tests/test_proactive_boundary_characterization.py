from __future__ import annotations

from astrbot_plugin_private_companion.proactive_engine import ProactiveEngineMixin
from astrbot_plugin_private_companion.proactive_message import ProactiveMessageMixin


class _EngineHarness(ProactiveEngineMixin):
    @staticmethod
    def _normalize_legacy_proactive_text(value, *, limit=40):
        return str(value or "").strip()[:limit]


def test_timeliness_policy_preserves_reason_and_source_precedence():
    harness = _EngineHarness()

    assert harness._proactive_timeliness_level(reason="weather_alert") == "urgent"
    assert harness._proactive_timeliness_level(source="body_monitor") == "urgent"
    assert harness._proactive_timeliness_level(reason="environment_change") == "timely"
    assert harness._proactive_timeliness_level(source="night_care") == "timely"
    assert harness._proactive_timeliness_level(reason="news_share", source="news_share") == "routine"


def test_freshness_policy_preserves_media_and_durable_route_rules():
    harness = _EngineHarness()

    assert harness._proactive_item_freshness_class(
        action="message", reason="health_alert", source="body_monitor"
    ) == "immediate"
    assert harness._proactive_item_freshness_class(
        action="message", reason="news_share", source="news_share"
    ) == "durable"
    assert harness._proactive_item_freshness_class(
        action="message+photo_text", reason="check_in", source="random"
    ) == "immediate"
    assert harness._proactive_item_freshness_class(
        action="message", reason="check_in", source="random"
    ) == "contextual"


def test_delivery_receipt_classification_and_line_filter_are_stable():
    harness = ProactiveMessageMixin()

    assert harness._is_proactive_delivery_receipt_text("消息发送成功。") is True
    assert harness._is_proactive_delivery_receipt_text("今晚风有点凉，记得加件衣服。") is False
    assert harness._strip_proactive_delivery_receipt_lines(
        "消息发送成功。\n今晚风有点凉，记得加件衣服。"
    ) == "今晚风有点凉，记得加件衣服。"


def test_provider_error_and_platform_rejection_classification_are_stable():
    assert ProactiveMessageMixin._looks_like_internal_provider_error_text(
        "BadRequestError: functionDeclaration schema didn't specify properties"
    ) is True
    assert ProactiveMessageMixin._looks_like_internal_provider_error_text(
        "今天的请求很简单，换个说法也没关系。"
    ) is False
    assert ProactiveMessageMixin._is_onebot_event_checker_send_rejection(
        "ActionFailed retcode=1200 EventChecker Failed NodeIKernelMsgService/sendMsg"
    ) is True
    assert ProactiveMessageMixin._is_onebot_event_checker_send_rejection(
        "ActionFailed retcode=1404 sendMsg"
    ) is False
