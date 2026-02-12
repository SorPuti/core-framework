"""Confluent Kafka producer using librdkafka."""

from __future__ import annotations

from typing import Any, Callable
import json
import threading
import atexit

from core.messaging.base import Producer, Event
from core.config import get_settings


class ConfluentProducer(Producer):
    """High-performance Kafka producer with singleton pattern."""

    _instance: "ConfluentProducer | None" = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        bootstrap_servers: str | None = None,
        schema_registry_url: str | None = None,
        **kwargs: Any,
    ):
        if hasattr(self, "_initialized") and self._initialized:
            return

        self._settings = get_settings()
        self._bootstrap_servers = bootstrap_servers or self._settings.kafka_bootstrap_servers
        self._schema_registry_url = schema_registry_url or getattr(
            self._settings, "kafka_schema_registry_url", None
        )
        self._extra_config = kwargs
        self._producer = None
        self._schema_registry = None
        self._started = False
        self._initialized = True
        atexit.register(self._cleanup)

    def _cleanup(self):
        if self._producer:
            try:
                self._producer.flush(timeout=5)
            except Exception:
                pass

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

        from confluent_kafka import Producer as CKProducer

        config = {
            "bootstrap.servers": self._bootstrap_servers,
            "client.id": self._settings.kafka_client_id,
            "acks": "all",
            "retries": 3,
            "retry.backoff.ms": self._settings.kafka_retry_backoff_ms,
            "batch.size": self._settings.kafka_max_batch_size,
            "linger.ms": self._settings.kafka_linger_ms,
            "compression.type": self._settings.kafka_compression_type,
        }

        if self._settings.kafka_security_protocol != "PLAINTEXT":
            config["security.protocol"] = self._settings.kafka_security_protocol
            if self._settings.kafka_sasl_mechanism:
                config["sasl.mechanism"] = self._settings.kafka_sasl_mechanism
                config["sasl.username"] = self._settings.kafka_sasl_username
                config["sasl.password"] = self._settings.kafka_sasl_password
            if self._settings.kafka_ssl_cafile:
                config["ssl.ca.location"] = self._settings.kafka_ssl_cafile
            if self._settings.kafka_ssl_certfile:
                config["ssl.certificate.location"] = self._settings.kafka_ssl_certfile
            if self._settings.kafka_ssl_keyfile:
                config["ssl.key.location"] = self._settings.kafka_ssl_keyfile

        config.update(self._extra_config)
        self._producer = CKProducer(config)
        self._started = True

        if self._schema_registry_url:
            await self._init_schema_registry()

    async def _init_schema_registry(self) -> None:
        try:
            from confluent_kafka.schema_registry import SchemaRegistryClient
            self._schema_registry = SchemaRegistryClient({"url": self._schema_registry_url})
        except ImportError:
            pass

    async def stop(self) -> None:
        if self._producer and self._started:
            self._producer.flush(timeout=30)
            self._started = False

    async def send(
        self,
        topic: str,
        message: dict[str, Any],
        key: str | None = None,
        headers: dict[str, str] | None = None,
        wait: bool | None = None,
        on_delivery: Callable | None = None,
    ) -> Any:
        if not self._started:
            await self.start()

        resolved_topic = self._resolve_topic(topic)
        if wait is None:
            wait = not self._settings.kafka_fire_and_forget

        from core.messaging.tracking import track_outgoing, track_sent, track_failed
        event_id, headers = await track_outgoing(resolved_topic, message, headers, key)

        value = json.dumps(message).encode("utf-8")
        key_bytes = key.encode("utf-8") if key else None
        kafka_headers = [(k, v.encode("utf-8")) for k, v in headers.items()] if headers else None

        delivery_result = {"partition": None, "offset": None, "error": None}

        def _delivery_callback(err, msg):
            if err:
                delivery_result["error"] = str(err)
            else:
                delivery_result["partition"] = msg.partition()
                delivery_result["offset"] = msg.offset()
            if on_delivery:
                on_delivery(err, msg)

        try:
            self._producer.produce(
                topic=resolved_topic,
                value=value,
                key=key_bytes,
                headers=kafka_headers,
                on_delivery=_delivery_callback if event_id else on_delivery,
            )
            self._producer.poll(0)

            if wait:
                self._producer.flush()
                if event_id:
                    if delivery_result["error"]:
                        await track_failed(event_id, delivery_result["error"])
                    elif delivery_result["partition"] is not None:
                        await track_sent(event_id, delivery_result["partition"], delivery_result["offset"])
                return delivery_result

        except Exception as e:
            await track_failed(event_id, str(e))
            raise

    async def send_avro(
        self,
        topic: str,
        message: dict[str, Any],
        schema: dict[str, Any],
        key: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        if not self._started:
            await self.start()

        if self._schema_registry is None:
            raise RuntimeError("Schema Registry not configured")

        from confluent_kafka.schema_registry.avro import AvroSerializer
        from confluent_kafka.serialization import SerializationContext, MessageField

        avro_serializer = AvroSerializer(self._schema_registry, json.dumps(schema))
        ctx = SerializationContext(topic, MessageField.VALUE)
        value = avro_serializer(message, ctx)
        key_bytes = key.encode("utf-8") if key else None
        kafka_headers = [(k, v.encode("utf-8")) for k, v in headers.items()] if headers else None

        self._producer.produce(topic=topic, value=value, key=key_bytes, headers=kafka_headers)
        self._producer.poll(0)

    async def send_fire_and_forget(
        self,
        topic: str,
        message: dict[str, Any],
        key: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        await self.send(topic, message, key, headers, wait=False)

    async def send_batch_fire_and_forget(self, topic: str, messages: list[dict[str, Any]]) -> int:
        return await self.send_batch(topic, messages, wait=False)

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

        for message in messages:
            value = json.dumps(message).encode("utf-8")
            self._producer.produce(topic=topic, value=value)
            self._producer.poll(0)

        if wait:
            self._producer.flush()

        return len(messages)

    async def flush(self, timeout: float | None = None) -> int:
        if self._producer:
            return self._producer.flush(timeout=timeout or -1)
        return 0

    def poll(self, timeout: float = 0) -> int:
        if self._producer:
            return self._producer.poll(timeout)
        return 0
