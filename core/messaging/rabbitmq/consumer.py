"""RabbitMQ consumer using aio-pika."""

from __future__ import annotations

from typing import Any, Callable, Awaitable
import json
import logging

from core.messaging.base import Consumer, Event
from core.config import get_settings
from core.messaging.registry import get_event_handlers

logger = logging.getLogger(__name__)


class RabbitMQConsumer(Consumer):
    """RabbitMQ consumer with automatic event tracking."""

    def __init__(
        self,
        group_id: str,
        topics: list[str],
        url: str | None = None,
        message_handler: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        **kwargs: Any,
    ):
        self._settings = get_settings()
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
        self._message_count = 0

    async def start(self) -> None:
        if self._running:
            return

        import aio_pika
        self._connection = await aio_pika.connect_robust(self._url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=self._settings.rabbitmq_prefetch_count)

        exchange = await self._channel.declare_exchange(
            self._settings.rabbitmq_exchange,
            aio_pika.ExchangeType.TOPIC,
            durable=self._settings.rabbitmq_durable,
        )

        self._queue = await self._channel.declare_queue(
            self.group_id, durable=self._settings.rabbitmq_durable
        )

        for topic in self.topics:
            await self._queue.bind(exchange, routing_key=topic)

        self._consumer_tag = await self._queue.consume(self._on_message)
        self._running = True
        logger.info(f"RabbitMQ consumer '{self.group_id}' started, bindings: {self.topics}")

    async def stop(self) -> None:
        self._running = False
        if self._queue and self._consumer_tag:
            await self._queue.cancel(self._consumer_tag)
        if self._connection:
            await self._connection.close()
            self._connection = None
        logger.info(f"RabbitMQ consumer '{self.group_id}' stopped")

    def is_running(self) -> bool:
        return self._running

    async def _on_message(self, message) -> None:
        async with message.process():
            try:
                body = json.loads(message.body.decode("utf-8"))
                headers = dict(message.headers) if message.headers else None

                self._message_count += 1
                from core.messaging.tracking import track_incoming
                await track_incoming(
                    topic=message.routing_key or self.group_id,
                    partition=0,
                    offset=self._message_count,
                    message=body,
                    headers=headers,
                    key=message.correlation_id,
                    worker_id=self.group_id,
                )

                await self.process_message(body)
            except Exception as e:
                logger.error(f"Error processing message: {e}")

    async def process_message(self, message: dict[str, Any]) -> None:
        if self._message_handler:
            await self._message_handler(message)
            return

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
