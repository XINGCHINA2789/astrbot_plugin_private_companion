"""Small, framework-neutral primitives for message event dispatch.

The public plugin mixin remains the AstrBot compatibility surface.  Keeping these
operations free of AstrBot imports makes classification, recall lookup and handler
boundaries independently testable.
"""
from __future__ import annotations

import inspect
import os
from collections.abc import Awaitable, Callable, Iterable, Mapping
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")

_OUTBOUND_DIRECTIONS = {"outbound", "outgoing", "send", "sent", "sending", "egress", "output"}
_OUTBOUND_STATUSES = {"outbound", "outgoing", "send", "sent", "sending", "delivered"}
_TRUE_MARKERS = {"1", "true", "yes", "on", "self", "outbound", "outgoing", "sent"}
_NON_MESSAGE_POST_TYPES = {"notice", "request", "meta_event", "message_sent", "outbound", "send", "sent"}


def read_event_field(owner: Any, name: str) -> Any:
    if owner is None:
        return None
    if isinstance(owner, Mapping):
        return owner.get(name)
    try:
        value = getattr(owner, name, None)
    except Exception:
        return None
    if callable(value):
        try:
            return value()
        except Exception:
            return None
    return value


def marker_enabled(value: Any) -> bool:
    if value is True:
        return True
    if type(value) in {int, float}:
        return value == 1
    return isinstance(value, str) and value.strip().casefold() in _TRUE_MARKERS


def is_explicitly_outbound(*owners: Any) -> bool:
    for owner in owners:
        if any(marker_enabled(read_event_field(owner, name)) for name in (
            "is_self", "from_self", "is_outbound", "outbound", "is_sent"
        )):
            return True
        if any(str(read_event_field(owner, name) or "").strip().casefold() in _OUTBOUND_DIRECTIONS
               for name in ("direction", "message_direction", "event_direction", "flow")):
            return True
        if any(str(read_event_field(owner, name) or "").strip().casefold() in _OUTBOUND_STATUSES
               for name in ("status", "message_status", "delivery_status")):
            return True
    return False


def classify_inbound_message(
    raw: Mapping[str, Any],
    *,
    event: Any,
    message_obj: Any,
    sender_id: str,
    self_id: str,
) -> bool:
    """Apply adapter-independent inbound filtering after IDs are resolved."""
    if is_explicitly_outbound(raw, event, message_obj):
        return False
    if sender_id and self_id and sender_id == self_id:
        return False
    post_type = str(raw.get("post_type") or "").strip().lower()
    if post_type == "message":
        return True
    if post_type in _NON_MESSAGE_POST_TYPES:
        return False
    if raw:
        message_type = str(raw.get("message_type") or "").strip().lower()
        if message_type in {"private", "group"}:
            return True
        if any(key in raw for key in ("notice_type", "request_type", "meta_event_type")):
            return False
    return True


def ordered_recall_ids(
    primary_ids: Iterable[Any],
    cache: Mapping[str, Any] | None,
) -> list[str]:
    """Deduplicate IDs and expand one level of cached reply aliases in stable order."""
    result: list[str] = []
    seen: set[str] = set()
    for value in primary_ids:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    if not isinstance(cache, Mapping):
        return result
    for message_id in tuple(result):
        snapshot = cache.get(message_id)
        nested_ids = snapshot.get("reply_message_ids") if isinstance(snapshot, Mapping) else None
        if not isinstance(nested_ids, list):
            continue
        for value in nested_ids:
            text = str(value or "").strip()
            if text and text not in seen:
                seen.add(text)
                result.append(text)
    return result


def iter_cache_entries(root: Path) -> Iterable[tuple[Path, bool]]:
    """Yield files immediately and directories post-order without materialising a tree."""
    def visit(directory: Path) -> Iterable[tuple[Path, bool]]:
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                if entry.is_dir(follow_symlinks=False):
                    yield from visit(path)
                    yield path, True
                elif entry.is_file(follow_symlinks=False):
                    yield path, False
    yield from visit(root)


async def invoke_handler(
    handler: Callable[..., T | Awaitable[T]],
    *args: Any,
    on_error: Callable[[Exception], None] | None = None,
    **kwargs: Any,
) -> T | None:
    """Invoke one handler with a narrow exception boundary.

    Cancellation and other ``BaseException`` subclasses intentionally propagate.
    Ordinary handler failures are reported and isolated from later dispatch work.
    """
    try:
        result = handler(*args, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result
    except Exception as exc:
        if on_error is not None:
            on_error(exc)
        return None
