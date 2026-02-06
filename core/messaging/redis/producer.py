"""
Redis Streams producer implementation.
"""

from __future__ import annotations

from typing import Any
import json

from core.messaging.base import Producer, Event
from core.config import get_settings


class RedisProducer(Producer):
    """
    Redis Streams message producer.
    
    Uses Redis Streams (XADD) for message production.
    Lightweight alternative to Kafka for smaller deployments.
    
    Example:
        producer = RedisProducer()
        await producer.start()
        await producer.send("user-events", {"action": "created", "user_id": 1})
        await producer.stop()
    """
    
    def __init__(self, redis_url: str | None = None, **kwargs: Any):
        """
        Initialize Redis producer.
        
        Args:
            redis_url: Redis connection URL
            **kwargs: Additional redis options
        """
        self._settings = get_settings()
        self._redis_url = redis_url or self._settings.redis_url
        self._extra_config = kwargs
        self._redis = None
        self._started = False
    
    async def start(self) -> None:
        """Start the producer and connect to Redis."""
        if self._started:
            return
        
        try:
            import redis.asyncio as redis
        except ImportError:
            raise ImportError(
                "redis is required for Redis support. "
                "Install with: pip install redis"
            )
        
        self._redis = redis.from_url(
            self._redis_url,
            max_connections=self._settings.redis_max_connections,
            **self._extra_config,
        )
        self._started = True
    
    async def stop(self) -> None:
        """Stop the producer."""
        if self._redis and self._started:
            await self._redis.close()
            self._started = False
    
    async def send(
        self,
        topic: str,
        message: dict[str, Any],
        key: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """
        Send a message to a Redis stream.
        
        Args:
            topic: Stream name
            message: Message payload
            key: Optional message key (stored in message)
            headers: Optional headers (stored in message)
        """
        if not self._started:
            await self.start()
        
        # Build stream entry
        entry = {
            "data": json.dumps(message),
        }
        
        if key:
            entry["key"] = key
        
        if headers:
            entry["headers"] = json.dumps(headers)
        
        # Add to stream with max length trimming
        await self._redis.xadd(
            topic,
            entry,
            maxlen=self._settings.redis_stream_max_len,
            approximate=True,
        )
    
    async def send_event(
        self,
        topic: str,
        event: Event,
        key: str | None = None,
    ) -> None:
        """
        Send an Event object to a stream.
        
        Args:
            topic: Stream name
            event: Event object
            key: Optional message key
        """
        headers = {
            "event_name": event.name,
            "event_id": event.id,
            "event_source": event.source,
        }
        
        await self.send(
            topic,
            message=event.to_dict(),
            key=key,
            headers=headers,
        )
    
    async def send_batch(
        self,
        topic: str,
        messages: list[dict[str, Any]],
    ) -> None:
        """
        Send multiple messages using pipeline.
        
        Args:
            topic: Stream name
            messages: List of message payloads
        """
        if not self._started:
            await self.start()
        
        async with self._redis.pipeline() as pipe:
            for message in messages:
                entry = {"data": json.dumps(message)}
                pipe.xadd(
                    topic,
                    entry,
                    maxlen=self._settings.redis_stream_max_len,
                    approximate=True,
                )
            await pipe.execute()
