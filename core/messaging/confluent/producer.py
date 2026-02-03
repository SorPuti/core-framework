"""
Confluent Kafka producer implementation.

High-performance producer using confluent-kafka (librdkafka).
Supports Schema Registry, Avro serialization, and fire-and-forget.
"""

from __future__ import annotations

from typing import Any, Callable
import json
import threading
import atexit

from core.messaging.base import Producer, Event
from core.messaging.config import get_messaging_settings


class ConfluentProducer(Producer):
    """
    High-performance Kafka producer using confluent-kafka.
    
    Features:
        - Fire-and-forget by default (configurable)
        - Schema Registry integration
        - Avro/JSON serialization
        - Connection pooling (singleton pattern)
        - Thread-safe
    
    Example:
        producer = ConfluentProducer()
        await producer.start()
        
        # Fire-and-forget (fastest)
        await producer.send("topic", {"key": "value"})
        
        # With Avro schema
        await producer.send_avro("topic", data, schema)
        
        # Ensure delivery before shutdown
        await producer.flush()
    """
    
    # Singleton instance
    _instance: "ConfluentProducer | None" = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        """Singleton pattern for connection reuse."""
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
        """
        Initialize Confluent producer.
        
        Args:
            bootstrap_servers: Kafka servers (comma-separated)
            schema_registry_url: Schema Registry URL for Avro
            **kwargs: Additional confluent-kafka config
        """
        # Only initialize once (singleton)
        if hasattr(self, "_initialized") and self._initialized:
            return
        
        self._settings = get_messaging_settings()
        self._bootstrap_servers = bootstrap_servers or self._settings.kafka_bootstrap_servers
        self._schema_registry_url = schema_registry_url or getattr(
            self._settings, "kafka_schema_registry_url", None
        )
        self._extra_config = kwargs
        self._producer = None
        self._avro_producer = None
        self._schema_registry = None
        self._started = False
        self._initialized = True
        
        # Register cleanup on exit
        atexit.register(self._cleanup)
    
    def _cleanup(self):
        """Cleanup on process exit."""
        if self._producer:
            try:
                self._producer.flush(timeout=5)
            except Exception:
                pass
    
    async def start(self) -> None:
        """Start the producer and connect to Kafka."""
        if self._started:
            return
        
        try:
            from confluent_kafka import Producer as CKProducer
        except ImportError:
            raise ImportError(
                "confluent-kafka is required for Confluent backend. "
                "Install with: pip install confluent-kafka"
            )
        
        # Build producer config
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
        
        # Add security config
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
        
        # Merge extra config
        config.update(self._extra_config)
        
        self._producer = CKProducer(config)
        self._started = True
        
        # Initialize Schema Registry if URL provided
        if self._schema_registry_url:
            await self._init_schema_registry()
    
    async def _init_schema_registry(self) -> None:
        """Initialize Schema Registry client."""
        try:
            from confluent_kafka.schema_registry import SchemaRegistryClient
        except ImportError:
            return  # Schema Registry not available
        
        self._schema_registry = SchemaRegistryClient({
            "url": self._schema_registry_url,
        })
    
    async def stop(self) -> None:
        """Stop the producer and flush pending messages."""
        if self._producer and self._started:
            self._producer.flush(timeout=30)
            self._started = False
    
    async def send(
        self,
        topic: str,
        message: dict[str, Any],
        key: str | None = None,
        headers: dict[str, str] | None = None,
        wait: bool = False,
        on_delivery: Callable | None = None,
    ) -> None:
        """
        Send a message to a topic.
        
        By default uses fire-and-forget for maximum throughput.
        
        Args:
            topic: Topic name
            message: Message payload (dict)
            key: Optional message key for partitioning
            headers: Optional message headers
            wait: If True, wait for delivery confirmation
            on_delivery: Optional callback(err, msg) for async confirmation
        """
        if not self._started:
            await self.start()
        
        # Serialize
        value = json.dumps(message).encode("utf-8")
        key_bytes = key.encode("utf-8") if key else None
        
        # Convert headers
        kafka_headers = None
        if headers:
            kafka_headers = [(k, v.encode("utf-8")) for k, v in headers.items()]
        
        # Send
        self._producer.produce(
            topic=topic,
            value=value,
            key=key_bytes,
            headers=kafka_headers,
            on_delivery=on_delivery,
        )
        
        # Poll to trigger callbacks (non-blocking)
        self._producer.poll(0)
        
        if wait:
            # Block until delivered
            self._producer.flush()
    
    async def send_avro(
        self,
        topic: str,
        message: dict[str, Any],
        schema: dict[str, Any],
        key: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """
        Send a message with Avro serialization.
        
        Requires Schema Registry to be configured.
        
        Args:
            topic: Topic name
            message: Message payload (dict)
            schema: Avro schema dict
            key: Optional message key
            headers: Optional headers
        """
        if not self._started:
            await self.start()
        
        if self._schema_registry is None:
            raise RuntimeError(
                "Schema Registry not configured. "
                "Set kafka_schema_registry_url in settings."
            )
        
        try:
            from confluent_kafka.schema_registry.avro import AvroSerializer
            from confluent_kafka.serialization import SerializationContext, MessageField
        except ImportError:
            raise ImportError(
                "confluent-kafka[avro] is required for Avro serialization. "
                "Install with: pip install confluent-kafka[avro]"
            )
        
        # Create serializer
        avro_serializer = AvroSerializer(
            self._schema_registry,
            json.dumps(schema),
        )
        
        # Serialize
        ctx = SerializationContext(topic, MessageField.VALUE)
        value = avro_serializer(message, ctx)
        key_bytes = key.encode("utf-8") if key else None
        
        # Convert headers
        kafka_headers = None
        if headers:
            kafka_headers = [(k, v.encode("utf-8")) for k, v in headers.items()]
        
        # Send
        self._producer.produce(
            topic=topic,
            value=value,
            key=key_bytes,
            headers=kafka_headers,
        )
        
        self._producer.poll(0)
    
    async def send_fire_and_forget(
        self,
        topic: str,
        message: dict[str, Any],
        key: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """
        Send a message without waiting for broker acknowledgment.
        
        This is the fastest method for high-throughput scenarios.
        Messages are batched internally by librdkafka and sent efficiently.
        
        Use this when:
        - You need maximum throughput (>10k msg/sec)
        - Message ordering per partition is sufficient
        - You can tolerate rare message loss on broker failure
        
        Args:
            topic: Topic name
            message: Message payload (dict)
            key: Optional message key for partitioning
            headers: Optional message headers
        
        Example:
            # High-throughput event streaming
            for event in events:
                await producer.send_fire_and_forget("events", event)
            
            # Flush at end of batch if needed
            await producer.flush()
        """
        await self.send(topic, message, key, headers, wait=False)
    
    async def send_batch_fire_and_forget(
        self,
        topic: str,
        messages: list[dict[str, Any]],
    ) -> int:
        """
        Send multiple messages without waiting for acknowledgment.
        
        This is the fastest method for bulk message sending.
        Returns immediately after queueing all messages.
        
        Args:
            topic: Topic name
            messages: List of message payloads
        
        Returns:
            Number of messages queued
        
        Example:
            # Send 10k events in ~100ms
            count = await producer.send_batch_fire_and_forget("events", events)
            print(f"Queued {count} events")
            
            # Optional: ensure delivery at end of request
            await producer.flush()
        """
        return await self.send_batch(topic, messages, wait=False)
    
    async def send_event(
        self,
        topic: str,
        event: Event,
        key: str | None = None,
    ) -> None:
        """
        Send an Event object to a topic.
        
        Args:
            topic: Topic name
            event: Event object
            key: Optional message key
        """
        headers = {
            "event_name": event.name,
            "event_id": event.id,
            "event_source": event.source,
        }
        
        await self.send(
            topic,
            message=event.to_dict(),
            key=key,
            headers=headers,
        )
    
    async def send_batch(
        self,
        topic: str,
        messages: list[dict[str, Any]],
        wait: bool = False,
    ) -> int:
        """
        Send multiple messages efficiently.
        
        Args:
            topic: Topic name
            messages: List of message payloads
            wait: If True, wait for all deliveries
        
        Returns:
            Number of messages queued
        """
        if not self._started:
            await self.start()
        
        for message in messages:
            value = json.dumps(message).encode("utf-8")
            self._producer.produce(topic=topic, value=value)
            self._producer.poll(0)
        
        if wait:
            self._producer.flush()
        
        return len(messages)
    
    async def flush(self, timeout: float | None = None) -> int:
        """
        Flush all pending messages.
        
        Args:
            timeout: Max seconds to wait (None = wait forever)
        
        Returns:
            Number of messages still in queue (0 = all delivered)
        """
        if self._producer:
            return self._producer.flush(timeout=timeout or -1)
        return 0
    
    def poll(self, timeout: float = 0) -> int:
        """
        Poll for delivery callbacks.
        
        Call periodically in long-running processes.
        
        Args:
            timeout: Max seconds to block
        
        Returns:
            Number of callbacks triggered
        """
        if self._producer:
            return self._producer.poll(timeout)
        return 0
