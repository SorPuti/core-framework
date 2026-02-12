"""Confluent Kafka consumer using librdkafka."""

from __future__ import annotations

from typing import Any, Callable, Awaitable
import json
import asyncio
import logging

from core.messaging.base import Consumer, Event, EventHandler
from core.config import get_settings
from core.messaging.registry import get_event_handlers

logger = logging.getLogger(__name__)


class ConfluentConsumer(Consumer):
    """High-performance Kafka consumer with automatic event tracking."""

    def __init__(
        self,
        group_id: str | None = None,
        topics: list[str] | None = None,
        message_handler: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        **kwargs: Any,
    ):
        self._settings = get_settings()
        self.group_id = group_id or ""
        self.topics = self._resolve_topics(topics or [])
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

        from confluent_kafka import Consumer as CKConsumer

        config = {
            "bootstrap.servers": self._settings.kafka_bootstrap_servers,
            "group.id": self.group_id,
            "auto.offset.reset": self._settings.kafka_auto_offset_reset,
            "enable.auto.commit": self._settings.kafka_enable_auto_commit,
            "auto.commit.interval.ms": self._settings.kafka_auto_commit_interval_ms,
            "max.poll.interval.ms": 300000,
            "session.timeout.ms": self._settings.kafka_session_timeout_ms,
            "heartbeat.interval.ms": self._settings.kafka_heartbeat_interval_ms,
        }

        if self._settings.kafka_security_protocol != "PLAINTEXT":
            config["security.protocol"] = self._settings.kafka_security_protocol
            if self._settings.kafka_sasl_mechanism:
                config["sasl.mechanism"] = self._settings.kafka_sasl_mechanism
                config["sasl.username"] = self._settings.kafka_sasl_username
                config["sasl.password"] = self._settings.kafka_sasl_password
            if self._settings.kafka_ssl_cafile:
                config["ssl.ca.location"] = self._settings.kafka_ssl_cafile

        config.update(self._extra_config)
        self._consumer = CKConsumer(config)
        self._consumer.subscribe(self.topics)
        self._running = True
        self._task = asyncio.create_task(self._consume_loop())
        logger.info(f"Consumer '{self.group_id}' started, topics: {self.topics}")

    async def _consume_loop(self) -> None:
        try:
            while self._running:
                msg = self._consumer.poll(timeout=1.0)
                if msg is None:
                    await asyncio.sleep(0.01)
                    continue
                if msg.error():
                    error = msg.error()
                    if error.code() != error._PARTITION_EOF:
                        logger.error(f"Consumer error: {error}")
                    continue
                try:
                    value = json.loads(msg.value().decode("utf-8"))
                    await self._track_message(msg, value)
                    await self.process_message(value)
                except json.JSONDecodeError:
                    logger.error(f"Failed to decode message: {msg.value()}")
                except Exception as e:
                    logger.error(f"Error processing message: {e}", exc_info=True)
        except asyncio.CancelledError:
            pass

    async def _track_message(self, msg: Any, value: dict) -> None:
        from core.messaging.tracking import track_incoming

        headers_dict = {}
        if msg.headers():
            for key, val in msg.headers():
                if val:
                    headers_dict[key] = val.decode("utf-8") if isinstance(val, bytes) else str(val)

        key = None
        if msg.key():
            key = msg.key().decode("utf-8") if isinstance(msg.key(), bytes) else str(msg.key())

        await track_incoming(
            topic=msg.topic(),
            partition=msg.partition(),
            offset=msg.offset(),
            message=value,
            headers=headers_dict or None,
            key=key,
            worker_id=self.group_id,
        )

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
            self._consumer.close()
            self._consumer = None
        logger.info(f"Consumer '{self.group_id}' stopped")

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

    def is_running(self) -> bool:
        return self._running

    async def commit(self) -> None:
        if self._consumer:
            self._consumer.commit()

    async def seek_to_beginning(self) -> None:
        if self._consumer:
            from confluent_kafka import OFFSET_BEGINNING
            partitions = self._consumer.assignment()
            for partition in partitions:
                partition.offset = OFFSET_BEGINNING
            self._consumer.assign(partitions)

    async def seek_to_end(self) -> None:
        if self._consumer:
            from confluent_kafka import OFFSET_END
            partitions = self._consumer.assignment()
            for partition in partitions:
                partition.offset = OFFSET_END
            self._consumer.assign(partitions)
