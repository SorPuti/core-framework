"""Event tracking system for Kafka message monitoring."""

from __future__ import annotations

import json
import logging
import asyncio
from typing import Any
from dataclasses import dataclass

logger = logging.getLogger("core.admin.event_tracking")

_event_subscribers: list[asyncio.Queue] = []
_subscriber_lock = asyncio.Lock()


@dataclass
class TrackedEvent:
    """Represents an event being tracked."""
    event_id: str
    event_name: str
    topic: str
    direction: str
    payload: dict | str
    headers: dict | None = None
    key: str | None = None
    partition: int | None = None
    offset: int | None = None
    schema_name: str | None = None
    source_service: str | None = None
    source_worker_id: str | None = None
    status: str = "pending"
    error: str | None = None


async def broadcast_event(event_type: str, data: dict) -> None:
    """Broadcast event to WebSocket subscribers."""
    message = json.dumps({"type": event_type, "data": data})
    async with _subscriber_lock:
        dead = []
        for queue in _event_subscribers:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                dead.append(queue)
        for q in dead:
            _event_subscribers.remove(q)


def subscribe_events() -> asyncio.Queue:
    """Subscribe to event broadcasts."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
    _event_subscribers.append(queue)
    return queue


def unsubscribe_events(queue: asyncio.Queue) -> None:
    """Unsubscribe from event broadcasts."""
    if queue in _event_subscribers:
        _event_subscribers.remove(queue)


class EventTracker:
    """Singleton for tracking Kafka events."""

    _instance: "EventTracker | None" = None
    _enabled: bool | None = None

    def __new__(cls) -> "EventTracker":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def is_enabled(cls) -> bool:
        if cls._enabled is None:
            from core.config import get_settings
            cls._enabled = getattr(get_settings(), "ops_event_tracking", False)
        return cls._enabled

    @classmethod
    def reset(cls) -> None:
        cls._instance = None
        cls._enabled = None

    async def track_outgoing(
        self,
        event_id: str,
        event_name: str,
        topic: str,
        payload: dict | str,
        headers: dict | None = None,
        key: str | None = None,
        schema_name: str | None = None,
        source_service: str | None = None,
        source_worker_id: str | None = None,
    ) -> int | None:
        """Track outgoing event before sending to Kafka."""
        if not self.is_enabled():
            return None
        try:
            from core.models import get_session
            from core.admin.models import EventLog
            db = await get_session()
            async with db:
                log = await EventLog.log_outgoing(
                    db,
                    event_id=event_id,
                    event_name=event_name,
                    topic=topic,
                    payload=payload,
                    headers=headers,
                    key=key,
                    schema_name=schema_name,
                    source_service=source_service,
                    source_worker_id=source_worker_id,
                )
                await db.commit()
                await broadcast_event("kafka_pending", log.to_dict())
                return log.id
        except Exception as e:
            logger.warning(f"Failed to track outgoing event: {e}")
            return None

    async def mark_sent(self, event_id: str, partition: int, offset: int) -> None:
        """Mark event as sent to Kafka."""
        if not self.is_enabled():
            return
        try:
            from core.models import get_session
            from core.admin.models import EventLog
            db = await get_session()
            async with db:
                await EventLog.mark_sent(db, event_id, partition, offset)
                await broadcast_event("kafka_sent", {"event_id": event_id, "partition": partition, "offset": offset})
        except Exception as e:
            logger.warning(f"Failed to mark event as sent: {e}")

    async def mark_failed(self, event_id: str, error: str) -> None:
        """Mark event as failed."""
        if not self.is_enabled():
            return
        try:
            from core.models import get_session
            from core.admin.models import EventLog
            db = await get_session()
            async with db:
                await EventLog.mark_failed(db, event_id, error)
                await broadcast_event("kafka_failed", {"event_id": event_id, "error": error})
        except Exception as e:
            logger.warning(f"Failed to mark event as failed: {e}")

    async def track_incoming(
        self,
        event_id: str,
        event_name: str,
        topic: str,
        partition: int,
        offset: int,
        payload: dict | str,
        headers: dict | None = None,
        key: str | None = None,
        schema_name: str | None = None,
        source_worker_id: str | None = None,
    ) -> int | None:
        """Track incoming event received from Kafka."""
        if not self.is_enabled():
            return None
        try:
            from core.models import get_session
            from core.admin.models import EventLog
            db = await get_session()
            async with db:
                log = await EventLog.log_incoming(
                    db,
                    event_id=event_id,
                    event_name=event_name,
                    topic=topic,
                    partition=partition,
                    offset=offset,
                    payload=payload,
                    headers=headers,
                    key=key,
                    schema_name=schema_name,
                    source_worker_id=source_worker_id,
                )
                await db.commit()
                await broadcast_event("kafka_delivered", log.to_dict())
                return log.id
        except Exception as e:
            logger.warning(f"Failed to track incoming event: {e}")
            return None


def get_event_tracker() -> EventTracker:
    """Get the global EventTracker instance."""
    return EventTracker()
