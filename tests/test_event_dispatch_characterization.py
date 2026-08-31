from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from astrbot_plugin_private_companion.event_dispatch import EventDispatchMixin
from astrbot_plugin_private_companion.event_dispatch_core import invoke_handler


class _Event:
    def __init__(self, raw: dict, *, sender_id: str = "user", self_id: str = "bot") -> None:
        self.message_obj = SimpleNamespace(raw_message=raw, sender=SimpleNamespace(user_id=sender_id))
        self.message_str = raw.get("raw_message", "")
        self._sender_id = sender_id
        self._self_id = self_id

    def get_sender_id(self) -> str:
        return self._sender_id

    def get_self_id(self) -> str:
        return self._self_id

    def get_messages(self) -> list[object]:
        return []


class _Harness(EventDispatchMixin):
    def _event_is_recent_req036_denial_echo(self, _event: object) -> bool:
        return False


@pytest.mark.parametrize(
    ("raw", "sender_id", "expected"),
    [
        ({"post_type": "message", "message_type": "private", "raw_message": "hi"}, "user", True),
        ({"post_type": "notice", "notice_type": "group_recall"}, "user", False),
        ({"post_type": "message_sent", "message_type": "private"}, "user", False),
        ({"post_type": "message", "message_type": "private", "direction": "outbound"}, "user", False),
        ({"post_type": "message", "message_type": "private"}, "bot", False),
        ({"message_type": "group", "raw_message": "image-only"}, "user", True),
    ],
)
def test_inbound_message_classification_is_stable(raw: dict, sender_id: str, expected: bool) -> None:
    assert _Harness()._event_is_inbound_chat_message(_Event(raw, sender_id=sender_id)) is expected


def test_recall_trigger_ids_preserve_order_deduplicate_and_expand_cached_replies() -> None:
    harness = _Harness()
    harness._recall_message_cache = {
        "current": {"reply_message_ids": ["quoted", "nested", "nested"]},
    }
    harness._event_is_platform_message_event = lambda _event: True
    harness._event_message_id = lambda _event: "current"
    harness._group_current_reply_quote_message_id = lambda _event: "quoted"
    harness._event_reply_message_ids = lambda _event: ["component", "quoted"]

    assert harness._reply_cancel_trigger_message_ids(object(), "extra", "current") == [
        "current",
        "quoted",
        "component",
        "extra",
        "nested",
    ]


def test_recall_image_cleanup_source_does_not_materialize_recursive_walk() -> None:
    source = (Path(__file__).resolve().parents[1] / "event_dispatch.py").read_text(encoding="utf-8")
    assert 'list(root_resolved.rglob("*"))' not in source


@pytest.mark.asyncio
async def test_handler_boundary_supports_sync_and_async_handlers_and_reports_failures() -> None:
    errors: list[str] = []

    assert await invoke_handler(lambda value: value + 1, 1) == 2

    async def async_handler() -> str:
        return "ok"

    assert await invoke_handler(async_handler) == "ok"

    def broken_handler() -> None:
        raise ValueError("broken")

    assert await invoke_handler(broken_handler, on_error=lambda exc: errors.append(str(exc))) is None
    assert errors == ["broken"]


@pytest.mark.asyncio
async def test_handler_boundary_does_not_swallow_cancellation() -> None:
    async def cancelled_handler() -> None:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await invoke_handler(cancelled_handler)
