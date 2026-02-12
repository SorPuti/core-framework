"""RabbitMQ producer using aio-pika."""

from __future__ import annotations

from typing import Any
import json

from core.messaging.base import Producer, Event
from core.config import get_settings


class RabbitMQProducer(Producer):
    """RabbitMQ producer with automatic event tracking."""

    def __init__(self, url: str | None = None, **kwargs: Any):
        self._settings = get_settings()
        self._url = url or self._settings.rabbitmq_url
        self._extra_config = kwargs
        self._connection = None
        self._channel = None
        self._exchange = None
        self._started = False

    async def start(self) -> None:
        if self._started:
            return

        import aio_pika
        self._connection = await aio_pika.connect_robust(self._url)
        self._channel = await self._connection.channel()
        self._exchange = await self._channel.declare_exchange(
            self._settings.rabbitmq_exchange,
            aio_pika.ExchangeType.TOPIC,
            durable=self._settings.rabbitmq_durable,
        )
        self._started = True

    async def stop(self) -> None:
        if self._connection and self._started:
            await self._connection.close()
            self._started = False

    async def send(
        self,
        topic: str,
        message: dict[str, Any],
        key: str | None = None,
        headers: dict[str, str] | None = None,
        wait: bool | None = None,
    ) -> Any:
        if not self._started:
            await self.start()

        import aio_pika
        from core.messaging.tracking import track_outgoing, track_sent

        event_id, headers = await track_outgoing(topic, message, headers, key)

        msg = aio_pika.Message(
            body=json.dumps(message).encode("utf-8"),
            content_type="application/json",
            correlation_id=key,
            headers=headers or {},
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )

        await self._exchange.publish(msg, routing_key=topic)

        if event_id:
            await track_sent(event_id, 0, 0)

    async def send_event(self, topic: str, event: Event, key: str | None = None) -> None:
        headers = {"event_name": event.name, "event_id": event.id, "event_source": event.source}
        await self.send(topic, message=event.to_dict(), key=key or event.id, headers=headers)

    async def send_batch(self, topic: str, messages: list[dict[str, Any]], wait: bool | None = None) -> int:
        for message in messages:
            await self.send(topic, message)
        return len(messages)
