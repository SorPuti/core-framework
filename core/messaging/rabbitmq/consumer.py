"""
RabbitMQ consumer implementation.
"""

from __future__ import annotations

from typing import Any, Callable, Awaitable
import json
import asyncio
import logging

from core.messaging.base import Consumer, Event
from core.messaging.config import get_messaging_settings
from core.messaging.registry import get_event_handlers


logger = logging.getLogger(__name__)


class RabbitMQConsumer(Consumer):
    """
    RabbitMQ message consumer using aio-pika.
    
    Example:
        consumer = RabbitMQConsumer(
            group_id="order-service",
            topics=["user.*", "payment.*"],
        )
        await consumer.start()
    """
    
    def __init__(
        self,
        group_id: str,
        topics: list[str],
        url: str | None = None,
        message_handler: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        **kwargs: Any,
    ):
        """
        Initialize RabbitMQ consumer.
        
        Args:
            group_id: Queue name (consumer group)
            topics: Routing key patterns to bind
            url: RabbitMQ connection URL
            message_handler: Optional custom handler
            **kwargs: Additional options
        """
        self._settings = get_messaging_settings()
        self.group_id = group_id
        self.topics = topics
        self._url = url or self._settings.rabbitmq_url
        self._message_handler = message_handler
        self._extra_config = kwargs
        
        self._connection = None
        self._channel = None
        self._queue = None
        self._running = False
        self._consumer_tag = None
    
    async def start(self) -> None:
        """Start consuming messages."""
        if self._running:
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
        
        # Set prefetch
        await self._channel.set_qos(prefetch_count=self._settings.rabbitmq_prefetch_count)
        
        # Declare exchange
        exchange = await self._channel.declare_exchange(
            self._settings.rabbitmq_exchange,
            aio_pika.ExchangeType.TOPIC,
            durable=self._settings.rabbitmq_durable,
        )
        
        # Declare queue
        self._queue = await self._channel.declare_queue(
            self.group_id,
            durable=self._settings.rabbitmq_durable,
        )
        
        # Bind to routing keys
        for topic in self.topics:
            await self._queue.bind(exchange, routing_key=topic)
        
        # Start consuming
        self._consumer_tag = await self._queue.consume(self._on_message)
        self._running = True
        
        logger.info(
            f"RabbitMQ consumer '{self.group_id}' started, bindings: {self.topics}"
        )
    
    async def stop(self) -> None:
        """Stop consuming messages."""
        self._running = False
        
        if self._queue and self._consumer_tag:
            await self._queue.cancel(self._consumer_tag)
        
        if self._connection:
            await self._connection.close()
            self._connection = None
        
        logger.info(f"RabbitMQ consumer '{self.group_id}' stopped")
    
    def is_running(self) -> bool:
        """Check if consumer is running."""
        return self._running
    
    async def _on_message(self, message) -> None:
        """Handle incoming message."""
        async with message.process():
            try:
                body = json.loads(message.body.decode("utf-8"))
                await self.process_message(body)
            except Exception as e:
                logger.error(f"Error processing message: {e}")
    
    async def process_message(self, message: dict[str, Any]) -> None:
        """Process a single message."""
        if self._message_handler:
            await self._message_handler(message)
            return
        
        # Route to event handlers
        event_name = message.get("name")
        if not event_name:
            return
        
        event = Event.from_dict(message)
        handlers = get_event_handlers(event_name)
        
        for handler in handlers:
            try:
                if handler.consumer_class:
                    instance = handler.consumer_class()
                    method = getattr(instance, handler.method_name)
                    await method(event, None)
                else:
                    await handler.handler(event, None)
            except Exception as e:
                logger.error(f"Handler error for {event_name}: {e}")
