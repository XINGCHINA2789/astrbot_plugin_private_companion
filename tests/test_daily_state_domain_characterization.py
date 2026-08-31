# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from astrbot_plugin_private_companion.daily_state import DailyStateMixin


class _DomainHarness(DailyStateMixin):
    def __init__(self) -> None:
        self.data = {}

    def _environment_now(self) -> datetime:
        return datetime(2026, 7, 23, 22, 0, tzinfo=timezone.utc)

    def _environment_fromtimestamp(self, value: float) -> datetime:
        return datetime.fromtimestamp(value, tz=timezone.utc)

    def _effective_plan_now_minutes(self, _plan_date: str) -> int | None:
        return 22 * 60


class DailyStateDomainCharacterizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = _DomainHarness()

    def test_location_inference_preserves_rule_precedence(self) -> None:
        cases = {
            "我在教室里整理书包": "学校",
            "下班后去了便利店": "工作场所",
            "坐在阳台吹风": "过道或窗边",
            "没有任何地点线索": "",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(expected, self.harness._infer_location_from_text(text))

    def test_sleepy_plan_item_negative_markers_win(self) -> None:
        self.assertTrue(self.harness._is_sleepy_plan_item({"activity": "回被窝继续睡"}))
        self.assertFalse(self.harness._is_sleepy_plan_item({"activity": "睡醒后起床洗漱"}))
        self.assertFalse(self.harness._is_sleepy_plan_item({"activity": "失眠，躺着睡不着"}))

    def test_sleep_delay_parser_keeps_existing_caps_and_period_rules(self) -> None:
        now = datetime(2026, 7, 23, 22, 0, tzinfo=timezone.utc)
        until_ts, explicit = self.harness._parse_sleep_delay_until_ts("陪我到凌晨2点半再睡", now_dt=now)
        self.assertTrue(explicit)
        self.assertEqual(datetime(2026, 7, 24, 2, 30, tzinfo=timezone.utc), datetime.fromtimestamp(until_ts, tz=timezone.utc))
        self.assertEqual((0.0, False), self.harness._parse_sleep_delay_until_ts("今晚晚点睡", now_dt=now))

    def test_health_cause_order_and_dedup_inputs_are_stable(self) -> None:
        with patch("astrbot_plugin_private_companion.daily_state.random.random", return_value=0.0):
            causes = self.harness._build_health_causes(
                sleep_label="失眠了",
                weather_text="阴，有风，8°C",
                diary_tags={"失眠", "低能量"},
            )
        self.assertEqual(
            [
                "昨晚没睡踏实",
                "前一天状态就有点透支",
                "空气有点潮,身上那股乏劲更明显",
                "吹了点风,身上容易发空",
            ],
            causes,
        )

    def test_schedule_normalizers_keep_legacy_aliases_and_order(self) -> None:
        self.assertEqual("cancelled", self.harness._normalize_schedule_lifecycle_status("已取消"))
        self.assertEqual(
            ["weather", "state", "coarse_plan"],
            self.harness._normalize_schedule_basis(["weather", "state", "weather", "bad", "coarse_plan", "persona"]),
        )
        self.assertEqual([23 * 60 + 30, 24 * 60 + 30], self.harness._normalized_plan_item_starts([
            {"time": "23:30"},
            {"time": "00:30"},
        ]))

    def test_schedule_runtime_status_preserves_changed_and_cancelled(self) -> None:
        self.assertEqual(
            "changed",
            self.harness._schedule_window_runtime_status(21 * 60, 23 * 60, plan_date="2026-07-23", explicit_status="changed"),
        )
        self.assertEqual(
            "cancelled",
            self.harness._schedule_window_runtime_status(21 * 60, 23 * 60, plan_date="2026-07-23", explicit_status="取消"),
        )


if __name__ == "__main__":
    unittest.main()
