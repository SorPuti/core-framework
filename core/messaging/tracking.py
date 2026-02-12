"""Unified event tracking for all messaging backends."""

from __future__ import annotations

import uuid
import logging
from typing import Any

logger = logging.getLogger("core.messaging.tracking")

_tracker = None
_enabled = None


def _get_tracker():
    """Get tracker instance lazily."""
    global _tracker, _enabled
    if _tracker is None:
        from core.admin.event_tracking import get_event_tracker
        _tracker = get_event_tracker()
    if _enabled is None:
        _enabled = _tracker.is_enabled()
    return _tracker if _enabled else None


def extract_event_name(message: dict, headers: dict | None = None, topic: str | None = None) -> str:
    """Extract event name from headers, message payload, or topic."""
    if headers and headers.get("event_name"):
        return headers["event_name"]
    if isinstance(message, dict):
        name = (
            message.get("name") or
            message.get("event_name") or
            message.get("type") or
            message.get("action")
        )
        if name:
            return name
    if topic:
        return topic.replace("-", ".").replace("_", ".")
    return "unknown"


def generate_event_id() -> str:
    """Generate unique event ID."""
    return str(uuid.uuid4())


async def track_outgoing(
    topic: str,
    message: dict,
    headers: dict | None,
    key: str | None = None,
) -> tuple[str | None, dict | None]:
    """Track outgoing event, returns (event_id, updated_headers)."""
    tracker = _get_tracker()
    if not tracker:
        return None, headers

    event_id = headers.get("event_id") if headers else None
    if not event_id:
        event_id = generate_event_id()
        headers = headers.copy() if headers else {}
        headers["event_id"] = event_id

    event_name = extract_event_name(message, headers, topic)
    
    await tracker.track_outgoing(
        event_id=event_id,
        event_name=event_name,
        topic=topic,
        payload=message,
        headers=headers,
        key=key,
    )
    return event_id, headers


async def track_sent(event_id: str | None, partition: int, offset: int) -> None:
    """Mark event as sent."""
    if not event_id:
        return
    tracker = _get_tracker()
    if tracker:
        await tracker.mark_sent(event_id, partition, offset)


async def track_failed(event_id: str | None, error: str) -> None:
    """Mark event as failed."""
    if not event_id:
        return
    tracker = _get_tracker()
    if tracker:
        await tracker.mark_failed(event_id, error)


async def track_incoming(
    topic: str,
    partition: int,
    offset: int,
    message: dict,
    headers: dict | None = None,
    key: str | None = None,
    worker_id: str | None = None,
) -> None:
    """Track incoming event."""
    tracker = _get_tracker()
    if not tracker:
        return

    event_id = f"in-{topic}-{partition}-{offset}"
    event_name = extract_event_name(message, headers, topic)

    await tracker.track_incoming(
        event_id=event_id,
        event_name=event_name,
        topic=topic,
        partition=partition,
        offset=offset,
        payload=message,
        headers=headers,
        key=key,
        source_worker_id=worker_id,
    )
