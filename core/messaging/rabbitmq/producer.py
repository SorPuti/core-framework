"""
RabbitMQ producer implementation.
"""

from __future__ import annotations

from typing import Any
import json

from core.messaging.base import Producer, Event
from core.config import get_settings


class RabbitMQProducer(Producer):
    """
    RabbitMQ message producer using aio-pika.
    
    Example:
        producer = RabbitMQProducer()
        await producer.start()
        await producer.send("user-events", {"action": "created"})
        await producer.stop()
    """
    
    def __init__(self, url: str | None = None, **kwargs: Any):
        """
        Initialize RabbitMQ producer.
        
        Args:
            url: RabbitMQ connection URL
            **kwargs: Additional options
        """
        self._settings = get_settings()
        self._url = url or self._settings.rabbitmq_url
        self._extra_config = kwargs
        self._connection = None
        self._channel = None
        self._exchange = None
        self._started = False
    
    async def start(self) -> None:
        """Start the producer and connect to RabbitMQ."""
        if self._started:
            return
        
        try:
            import aio_pika
        except ImportError:
            raise ImportError(
                "aio-pika is required for RabbitMQ support. "
                "Install with: pip install aio-pika"
            )
        
        self._connection = await aio_pika.connect_robust(self._url)
        self._channel = await self._connection.channel()
        
        # Declare exchange
        self._exchange = await self._channel.declare_exchange(
            self._settings.rabbitmq_exchange,
            aio_pika.ExchangeType.TOPIC,
            durable=self._settings.rabbitmq_durable,
        )
        
        self._started = True
    
    async def stop(self) -> None:
        """Stop the producer."""
        if self._connection and self._started:
            await self._connection.close()
            self._started = False
    
    async def send(
        self,
        topic: str,
        message: dict[str, Any],
        key: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """
        Send a message to a routing key.
        
        Args:
            topic: Routing key (e.g., "user.created")
            message: Message payload
            key: Optional correlation ID
            headers: Optional message headers
        """
        if not self._started:
            await self.start()
        
        try:
            import aio_pika
        except ImportError:
            raise ImportError("aio-pika is required")
        
        # Build message
        msg = aio_pika.Message(
            body=json.dumps(message).encode("utf-8"),
            content_type="application/json",
            correlation_id=key,
            headers=headers or {},
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        
        await self._exchange.publish(msg, routing_key=topic)
    
    async def send_event(
        self,
        topic: str,
        event: Event,
        key: str | None = None,
    ) -> None:
        """Send an Event object."""
        headers = {
            "event_name": event.name,
            "event_id": event.id,
            "event_source": event.source,
        }
        
        await self.send(
            topic,
            message=event.to_dict(),
            key=key or event.id,
            headers=headers,
        )
