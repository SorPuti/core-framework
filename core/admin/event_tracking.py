"""
Event tracking system for Kafka message monitoring.

Provides automatic tracking of Kafka events (sent/received) for the
Operations Center dashboard. Tracking is optional and can be enabled
via the `ops_event_tracking` setting.

Usage:
    # In settings
    ops_event_tracking: bool = True  # Enable event tracking
    
    # Events are automatically tracked when using KafkaProducer/KafkaConsumer
    # View in Operations Center > Events

Architecture:
    - EventTracker: Singleton that handles event logging
    - Interceptors: Called by producers/consumers to log events
    - WebSocket broadcast: Real-time updates to admin dashboard
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Awaitable
from dataclasses import dataclass, field
import asyncio

logger = logging.getLogger("core.admin.event_tracking")


@dataclass
class TrackedEvent:
    """Represents an event being tracked."""
    
    event_id: str
    event_name: str
    topic: str
    direction: str  # IN or OUT
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


# Global event broadcaster for WebSocket updates
_event_subscribers: list[asyncio.Queue] = []
_subscriber_lock = asyncio.Lock()


async def broadcast_event(event_type: str, data: dict) -> None:
    """
    Broadcast an event to all WebSocket subscribers.
    
    Args:
        event_type: Type of event (kafka_sent, kafka_delivered, kafka_failed, etc.)
        data: Event data to broadcast
    """
    message = json.dumps({"type": event_type, "data": data})
    
    async with _subscriber_lock:
        dead_queues = []
        for queue in _event_subscribers:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                # Queue is full, mark for removal
                dead_queues.append(queue)
        
        # Remove dead queues
        for queue in dead_queues:
            _event_subscribers.remove(queue)


def subscribe_events() -> asyncio.Queue:
    """
    Subscribe to event broadcasts.
    
    Returns:
        Queue that will receive event messages
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
    _event_subscribers.append(queue)
    return queue


def unsubscribe_events(queue: asyncio.Queue) -> None:
    """
    Unsubscribe from event broadcasts.
    
    Args:
        queue: Queue to remove from subscribers
    """
    if queue in _event_subscribers:
        _event_subscribers.remove(queue)


class EventTracker:
    """
    Singleton for tracking Kafka events.
    
    Handles logging events to the database and broadcasting to WebSocket.
    """
    
    _instance: "EventTracker | None" = None
    _enabled: bool | None = None
    
    def __new__(cls) -> "EventTracker":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def is_enabled(cls) -> bool:
        """Check if event tracking is enabled."""
        if cls._enabled is None:
            from core.config import get_settings
            settings = get_settings()
            cls._enabled = getattr(settings, "ops_event_tracking", False)
        return cls._enabled
    
    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing)."""
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
        """
        Track an outgoing event (before sending to Kafka).
        
        Args:
            event_id: Unique event ID
            event_name: Name of the event
            topic: Kafka topic
            payload: Event payload
            headers: Kafka headers
            key: Message key
            schema_name: Avro schema name if applicable
            source_service: Service that sent the event
            source_worker_id: Worker ID that sent the event
            
        Returns:
            Database ID of the event log entry, or None if tracking is disabled
        """
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
                
                # Broadcast to WebSocket
                await broadcast_event("kafka_pending", log.to_dict())
                
                return log.id
                
        except Exception as e:
            logger.warning(f"Failed to track outgoing event: {e}")
            return None
    
    async def mark_sent(
        self,
        event_id: str,
        partition: int,
        offset: int,
    ) -> None:
        """
        Mark an event as successfully sent to Kafka.
        
        Args:
            event_id: Event ID to update
            partition: Kafka partition
            offset: Kafka offset
        """
        if not self.is_enabled():
            return
        
        try:
            from core.models import get_session
            from core.admin.models import EventLog
            
            db = await get_session()
            async with db:
                await EventLog.mark_sent(db, event_id, partition, offset)
                
                # Broadcast to WebSocket
                await broadcast_event("kafka_sent", {
                    "event_id": event_id,
                    "partition": partition,
                    "offset": offset,
                })
                
        except Exception as e:
            logger.warning(f"Failed to mark event as sent: {e}")
    
    async def mark_failed(
        self,
        event_id: str,
        error: str,
    ) -> None:
        """
        Mark an event as failed.
        
        Args:
            event_id: Event ID to update
            error: Error message
        """
        if not self.is_enabled():
            return
        
        try:
            from core.models import get_session
            from core.admin.models import EventLog
            
            db = await get_session()
            async with db:
                await EventLog.mark_failed(db, event_id, error)
                
                # Broadcast to WebSocket
                await broadcast_event("kafka_failed", {
                    "event_id": event_id,
                    "error": error,
                })
                
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
        """
        Track an incoming event (received from Kafka).
        
        Args:
            event_id: Unique event ID (from headers)
            event_name: Name of the event (from headers)
            topic: Kafka topic
            partition: Kafka partition
            offset: Kafka offset
            payload: Event payload
            headers: Kafka headers
            key: Message key
            schema_name: Avro schema name if applicable
            source_worker_id: Worker ID that received the event
            
        Returns:
            Database ID of the event log entry, or None if tracking is disabled
        """
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
                
                # Broadcast to WebSocket
                await broadcast_event("kafka_delivered", log.to_dict())
                
                return log.id
                
        except Exception as e:
            logger.warning(f"Failed to track incoming event: {e}")
            return None


# Convenience function to get the tracker instance
def get_event_tracker() -> EventTracker:
    """Get the global EventTracker instance."""
    return EventTracker()
