"""Kafka producer using aiokafka."""

from __future__ import annotations

from typing import Any
import json

from core.messaging.base import Producer, Event
from core.config import get_settings


class KafkaProducer(Producer):
    """Async Kafka producer with automatic event tracking."""

    def __init__(
        self,
        bootstrap_servers: str | None = None,
        client_id: str | None = None,
        **kwargs: Any,
    ):
        self._settings = get_settings()
        self._bootstrap_servers = bootstrap_servers or self._settings.kafka_bootstrap_servers
        self._client_id = client_id or self._settings.kafka_client_id
        self._extra_config = kwargs
        self._producer = None
        self._started = False

    @staticmethod
    def _resolve_topic(topic) -> str:
        if isinstance(topic, str):
            return topic
        if hasattr(topic, "name"):
            return topic.name
        if hasattr(topic, "value"):
            return topic.value
        return str(topic)

    async def start(self) -> None:
        if self._started:
            return

        from aiokafka import AIOKafkaProducer

        compression = self._settings.kafka_compression_type
        if compression == "none":
            compression = None

        config = {
            "bootstrap_servers": self._bootstrap_servers,
            "client_id": self._client_id,
            "value_serializer": self._serialize,
            "key_serializer": self._serialize_key,
            "request_timeout_ms": self._settings.kafka_request_timeout_ms,
            "retry_backoff_ms": self._settings.kafka_retry_backoff_ms,
            "max_batch_size": self._settings.kafka_max_batch_size,
            "linger_ms": self._settings.kafka_linger_ms,
            "compression_type": compression,
        }

        if self._settings.kafka_security_protocol != "PLAINTEXT":
            config["security_protocol"] = self._settings.kafka_security_protocol
            if self._settings.kafka_sasl_mechanism:
                config["sasl_mechanism"] = self._settings.kafka_sasl_mechanism
                config["sasl_plain_username"] = self._settings.kafka_sasl_username
                config["sasl_plain_password"] = self._settings.kafka_sasl_password
            if self._settings.kafka_ssl_cafile:
                config["ssl_context"] = self._create_ssl_context()

        config.update(self._extra_config)
        self._producer = AIOKafkaProducer(**config)
        await self._producer.start()
        self._started = True

    async def stop(self) -> None:
        if self._producer and self._started:
            await self._producer.stop()
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

        resolved_topic = self._resolve_topic(topic)
        if wait is None:
            wait = not self._settings.kafka_fire_and_forget

        from core.messaging.tracking import track_outgoing, track_sent, track_failed
        event_id, headers = await track_outgoing(resolved_topic, message, headers, key)

        kafka_headers = [(k, v.encode()) for k, v in headers.items()] if headers else None

        try:
            if wait:
                result = await self._producer.send_and_wait(
                    resolved_topic, value=message, key=key, headers=kafka_headers
                )
                await track_sent(event_id, result.partition, result.offset)
                return result
            return await self._producer.send(
                resolved_topic, value=message, key=key, headers=kafka_headers
            )
        except Exception as e:
            await track_failed(event_id, str(e))
            raise

    async def send_fire_and_forget(
        self,
        topic: str,
        message: dict[str, Any],
        key: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        await self.send(topic, message, key, headers, wait=False)

    async def flush(self, timeout: float | None = None) -> int:
        if self._producer and self._started:
            await self._producer.flush(timeout_ms=int(timeout * 1000) if timeout else None)
        return 0

    async def send_event(self, topic: str, event: Event, key: str | None = None) -> None:
        headers = {"event_name": event.name, "event_id": event.id, "event_source": event.source}
        await self.send(topic, message=event.to_dict(), key=key, headers=headers)

    async def send_batch(
        self,
        topic: str,
        messages: list[dict[str, Any]],
        wait: bool | None = None,
    ) -> int:
        if not self._started:
            await self.start()

        if wait is None:
            wait = not self._settings.kafka_fire_and_forget

        batch = self._producer.create_batch()
        for message in messages:
            serialized = self._serialize(message)
            metadata = batch.append(key=None, value=serialized, timestamp=None)
            if metadata is None:
                await self._producer.send_batch(batch, topic)
                batch = self._producer.create_batch()
                batch.append(key=None, value=serialized, timestamp=None)

        if batch.record_count() > 0:
            await self._producer.send_batch(batch, topic)

        if wait:
            await self.flush()

        return len(messages)

    async def send_batch_fire_and_forget(self, topic: str, messages: list[dict[str, Any]]) -> int:
        if not self._started:
            await self.start()
        for message in messages:
            await self._producer.send(topic, value=message)
        return len(messages)

    def _serialize(self, value: Any) -> bytes:
        if value is None:
            return None
        if isinstance(value, bytes):
            return value
        if isinstance(value, str):
            return value.encode("utf-8")
        return json.dumps(value).encode("utf-8")

    def _serialize_key(self, key: Any) -> bytes | None:
        if key is None:
            return None
        if isinstance(key, bytes):
            return key
        return str(key).encode("utf-8")

    def _create_ssl_context(self):
        import ssl
        context = ssl.create_default_context()
        if self._settings.kafka_ssl_cafile:
            context.load_verify_locations(self._settings.kafka_ssl_cafile)
        if self._settings.kafka_ssl_certfile and self._settings.kafka_ssl_keyfile:
            context.load_cert_chain(
                certfile=self._settings.kafka_ssl_certfile,
                keyfile=self._settings.kafka_ssl_keyfile,
            )
        return context
