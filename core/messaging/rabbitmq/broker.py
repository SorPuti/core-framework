"""
RabbitMQ broker implementation.
"""

from __future__ import annotations

from typing import Any, Callable, Awaitable
import logging

from core.messaging.base import MessageBroker
from core.messaging.config import get_messaging_settings
from core.messaging.rabbitmq.producer import RabbitMQProducer
from core.messaging.rabbitmq.consumer import RabbitMQConsumer


logger = logging.getLogger(__name__)


class RabbitMQBroker(MessageBroker):
    """
    RabbitMQ message broker implementation.
    
    Traditional message queue with topic exchange pattern.
    Good for complex routing and guaranteed delivery.
    
    Example:
        broker = RabbitMQBroker()
        await broker.connect()
        await broker.publish("user.created", {"id": 1})
        await broker.disconnect()
    """
    
    name = "rabbitmq"
    
    def __init__(self, url: str | None = None, **kwargs: Any):
        """
        Initialize RabbitMQ broker.
        
        Args:
            url: RabbitMQ connection URL
            **kwargs: Additional configuration
        """
        self._settings = get_messaging_settings()
        self._url = url or self._settings.rabbitmq_url
        self._extra_config = kwargs
        
        self._producer: RabbitMQProducer | None = None
        self._consumers: dict[str, RabbitMQConsumer] = {}
        self._connection = None
        self._connected = False
    
    async def connect(self) -> None:
        """Connect to RabbitMQ."""
        if self._connected:
            return
        
        try:
            import aio_pika
        except ImportError:
            raise ImportError(
                "aio-pika is required for RabbitMQ support. "
                "Install with: pip install aio-pika"
            )
        
        self._connection = await aio_pika.connect_robust(self._url)
        
        # Initialize producer
        self._producer = RabbitMQProducer(url=self._url)
        await self._producer.start()
        
        self._connected = True
        logger.info(f"Connected to RabbitMQ: {self._url}")
    
    async def disconnect(self) -> None:
        """Disconnect from RabbitMQ."""
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
        if self._connection:
            await self._connection.close()
            self._connection = None
        
        self._connected = False
        logger.info("Disconnected from RabbitMQ")
    
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
        """Publish message with routing key."""
        if not self._connected:
            await self.connect()
        
        await self._producer.send(topic, message, key, headers)
    
    async def subscribe(
        self,
        topics: list[str],
        group_id: str,
        handler: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Subscribe to routing key patterns."""
        if group_id in self._consumers:
            await self._consumers[group_id].stop()
        
        consumer = RabbitMQConsumer(
            group_id=group_id,
            topics=topics,
            url=self._url,
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
        Create a queue (RabbitMQ equivalent).
        
        Note: In RabbitMQ, queues are created on demand.
        This creates a durable queue for the topic.
        """
        if not self._connected:
            await self.connect()
        
        try:
            import aio_pika
        except ImportError:
            raise ImportError("aio-pika is required")
        
        channel = await self._connection.channel()
        await channel.declare_queue(topic, durable=True)
        await channel.close()
    
    async def delete_topic(self, topic: str) -> None:
        """Delete a queue."""
        if not self._connected:
            await self.connect()
        
        try:
            import aio_pika
        except ImportError:
            raise ImportError("aio-pika is required")
        
        channel = await self._connection.channel()
        await channel.queue_delete(topic)
        await channel.close()
        logger.info(f"Deleted queue: {topic}")
    
    async def list_topics(self) -> list[str]:
        """
        List queues.
        
        Note: RabbitMQ management API would be needed for full listing.
        This returns an empty list as a placeholder.
        """
        # Would need RabbitMQ management plugin/API
        return []
