"""
Redis Streams broker implementation.
"""

from __future__ import annotations

from typing import Any, Callable, Awaitable
import logging

from core.messaging.base import MessageBroker
from core.messaging.config import get_messaging_settings
from core.messaging.redis.producer import RedisProducer
from core.messaging.redis.consumer import RedisConsumer


logger = logging.getLogger(__name__)


class RedisBroker(MessageBroker):
    """
    Redis Streams message broker implementation.
    
    Lightweight alternative to Kafka using Redis Streams.
    Good for smaller deployments or when Redis is already in use.
    
    Example:
        broker = RedisBroker()
        await broker.connect()
        await broker.publish("events", {"type": "test"})
        await broker.disconnect()
    """
    
    name = "redis"
    
    def __init__(self, redis_url: str | None = None, **kwargs: Any):
        """
        Initialize Redis broker.
        
        Args:
            redis_url: Redis connection URL
            **kwargs: Additional configuration
        """
        self._settings = get_messaging_settings()
        self._redis_url = redis_url or self._settings.redis_url
        self._extra_config = kwargs
        
        self._producer: RedisProducer | None = None
        self._consumers: dict[str, RedisConsumer] = {}
        self._redis = None
        self._connected = False
    
    async def connect(self) -> None:
        """Connect to Redis."""
        if self._connected:
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
        )
        
        # Test connection
        await self._redis.ping()
        
        # Initialize producer
        self._producer = RedisProducer(redis_url=self._redis_url)
        await self._producer.start()
        
        self._connected = True
        logger.info(f"Connected to Redis: {self._redis_url}")
    
    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if not self._connected:
            return
        
        # Stop consumers
        for consumer in self._consumers.values():
            await consumer.stop()
        self._consumers.clear()
        
        # Stop producer
        if self._producer:
            await self._producer.stop()
            self._producer = None
        
        # Close connection
        if self._redis:
            await self._redis.close()
            self._redis = None
        
        self._connected = False
        logger.info("Disconnected from Redis")
    
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._connected
    
    async def publish(
        self,
        topic: str,
        message: dict[str, Any],
        key: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Publish message to stream."""
        if not self._connected:
            await self.connect()
        
        await self._producer.send(topic, message, key, headers)
    
    async def subscribe(
        self,
        topics: list[str],
        group_id: str,
        handler: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Subscribe to streams."""
        if group_id in self._consumers:
            await self._consumers[group_id].stop()
        
        consumer = RedisConsumer(
            group_id=group_id,
            topics=topics,
            redis_url=self._redis_url,
            message_handler=handler,
        )
        
        await consumer.start()
        self._consumers[group_id] = consumer
    
    async def create_topic(
        self,
        topic: str,
        partitions: int = 1,
        replication_factor: int = 1,
    ) -> None:
        """
        Create a stream (Redis streams are auto-created).
        
        This is a no-op for Redis as streams are created on first write.
        """
        pass
    
    async def delete_topic(self, topic: str) -> None:
        """Delete a stream."""
        if not self._connected:
            await self.connect()
        
        await self._redis.delete(topic)
        logger.info(f"Deleted stream: {topic}")
    
    async def list_topics(self) -> list[str]:
        """
        List all streams.
        
        Note: This scans all keys, which may be slow on large databases.
        """
        if not self._connected:
            await self.connect()
        
        # Get all stream keys
        streams = []
        async for key in self._redis.scan_iter(match="*", _type="stream"):
            if isinstance(key, bytes):
                key = key.decode("utf-8")
            streams.append(key)
        
        return streams
