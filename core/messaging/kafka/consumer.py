"""Kafka consumer using aiokafka."""

from __future__ import annotations

from typing import Any, Callable, Awaitable
import json
import asyncio
import logging

from core.messaging.base import Consumer, Event, EventHandler
from core.config import get_settings
from core.messaging.registry import get_event_handlers

logger = logging.getLogger(__name__)


class KafkaConsumer(Consumer):
    """Async Kafka consumer with automatic event tracking."""

    def __init__(
        self,
        group_id: str,
        topics: list[str],
        bootstrap_servers: str | None = None,
        message_handler: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        **kwargs: Any,
    ):
        self._settings = get_settings()
        self.group_id = group_id
        self.topics = self._resolve_topics(topics)
        self._bootstrap_servers = bootstrap_servers or self._settings.kafka_bootstrap_servers
        self._message_handler = message_handler
        self._extra_config = kwargs
        self._consumer = None
        self._running = False
        self._task: asyncio.Task | None = None
        self._db_session_factory = None

    @staticmethod
    def _resolve_topics(topics: list) -> list[str]:
        resolved = []
        for topic in topics:
            if isinstance(topic, str):
                resolved.append(topic)
            elif hasattr(topic, "name"):
                resolved.append(topic.name)
            elif hasattr(topic, "value"):
                resolved.append(topic.value)
            else:
                resolved.append(str(topic))
        return resolved

    def set_db_session_factory(self, factory: Callable) -> None:
        self._db_session_factory = factory

    async def start(self) -> None:
        if self._running:
            return

        from aiokafka import AIOKafkaConsumer

        config = {
            "bootstrap_servers": self._bootstrap_servers,
            "group_id": self.group_id,
            "value_deserializer": self._deserialize,
            "auto_offset_reset": self._settings.kafka_auto_offset_reset,
            "enable_auto_commit": self._settings.kafka_enable_auto_commit,
            "auto_commit_interval_ms": self._settings.kafka_auto_commit_interval_ms,
            "max_poll_records": self._settings.kafka_max_poll_records,
            "session_timeout_ms": self._settings.kafka_session_timeout_ms,
            "heartbeat_interval_ms": self._settings.kafka_heartbeat_interval_ms,
        }

        if self._settings.kafka_security_protocol != "PLAINTEXT":
            config["security_protocol"] = self._settings.kafka_security_protocol
            if self._settings.kafka_sasl_mechanism:
                config["sasl_mechanism"] = self._settings.kafka_sasl_mechanism
                config["sasl_plain_username"] = self._settings.kafka_sasl_username
                config["sasl_plain_password"] = self._settings.kafka_sasl_password

        config.update(self._extra_config)
        self._consumer = AIOKafkaConsumer(*self.topics, **config)
        await self._consumer.start()
        self._running = True
        self._task = asyncio.create_task(self._consume_loop())
        logger.info(f"Consumer '{self.group_id}' started, topics: {self.topics}")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._consumer:
            await self._consumer.stop()
            self._consumer = None
        logger.info(f"Consumer '{self.group_id}' stopped")

    def is_running(self) -> bool:
        return self._running

    async def _consume_loop(self) -> None:
        try:
            async for message in self._consumer:
                if not self._running:
                    break
                try:
                    await self._track_message(message)
                    await self.process_message(message.value)
                except Exception as e:
                    logger.error(f"Error processing message: {e}", exc_info=True)
        except asyncio.CancelledError:
            pass

    async def _track_message(self, message: Any) -> None:
        from core.messaging.tracking import track_incoming

        headers_dict = {}
        if message.headers:
            for key, value in message.headers:
                if value:
                    headers_dict[key] = value.decode("utf-8") if isinstance(value, bytes) else str(value)

        key = None
        if message.key:
            key = message.key.decode("utf-8") if isinstance(message.key, bytes) else str(message.key)

        payload = message.value if isinstance(message.value, dict) else {"raw": str(message.value)}
        await track_incoming(
            topic=message.topic,
            partition=message.partition,
            offset=message.offset,
            message=payload,
            headers=headers_dict or None,
            key=key,
            worker_id=self.group_id,
        )

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
                await self._execute_handler(handler, event)
            except Exception as e:
                logger.error(f"Handler error for {event_name}: {e}", exc_info=True)

    async def _execute_handler(self, handler: EventHandler, event: Event) -> None:
        if handler.consumer_class:
            consumer_instance = handler.consumer_class()
            handler_method = getattr(consumer_instance, handler.method_name)
        else:
            handler_method = handler.handler

        if self._db_session_factory:
            async with self._db_session_factory() as db:
                await handler_method(event, db)
        else:
            await handler_method(event, None)

    def _deserialize(self, value: bytes) -> dict[str, Any]:
        if value is None:
            return {}
        try:
            return json.loads(value.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {"raw": value.decode("utf-8", errors="replace")}


class KafkaConsumerRunner:
    """Runs multiple Kafka consumers."""

    def __init__(self):
        self._consumers: list[KafkaConsumer] = []
        self._running = False
        self._shutdown_event = asyncio.Event()

    def add_consumer(self, consumer_class: type, db_session_factory: Callable | None = None) -> None:
        group_id = getattr(consumer_class, "_group_id", consumer_class.__name__)
        topics = getattr(consumer_class, "_topics", [])
        consumer = KafkaConsumer(group_id=group_id, topics=topics)
        if db_session_factory:
            consumer.set_db_session_factory(db_session_factory)
        self._consumers.append(consumer)

    async def start(self) -> None:
        self._running = True
        for consumer in self._consumers:
            await consumer.start()
        logger.info(f"Started {len(self._consumers)} consumer(s)")

    async def stop(self) -> None:
        self._running = False
        for consumer in self._consumers:
            await consumer.stop()
        self._shutdown_event.set()
        logger.info("All consumers stopped")

    async def wait(self) -> None:
        await self._shutdown_event.wait()

    def request_shutdown(self) -> None:
        self._shutdown_event.set()
