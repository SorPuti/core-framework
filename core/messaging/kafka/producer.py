"""
Kafka producer implementation.

Provides async message production to Kafka topics with
automatic serialization, batching, and error handling.
"""

from __future__ import annotations

from typing import Any
import json
import asyncio

from core.messaging.base import Producer, Event
from core.messaging.config import get_messaging_settings


class KafkaProducer(Producer):
    """
    Kafka message producer using aiokafka.
    
    Features:
        - Automatic JSON serialization
        - Batching support
        - Compression
        - Retry logic
        - Async/await native
    
    Example:
        producer = KafkaProducer()
        await producer.start()
        
        # Send simple message
        await producer.send("user-events", {"action": "created", "user_id": 1})
        
        # Send with key (for partitioning)
        await producer.send("user-events", {"action": "updated"}, key="user-1")
        
        # Send Event object
        event = Event(name="user.created", data={"id": 1})
        await producer.send_event("user-events", event)
        
        await producer.stop()
    """
    
    def __init__(
        self,
        bootstrap_servers: str | None = None,
        client_id: str | None = None,
        **kwargs: Any,
    ):
        """
        Initialize Kafka producer.
        
        Args:
            bootstrap_servers: Kafka servers (comma-separated)
            client_id: Client identifier
            **kwargs: Additional aiokafka producer options
        """
        self._settings = get_messaging_settings()
        self._bootstrap_servers = bootstrap_servers or self._settings.kafka_bootstrap_servers
        self._client_id = client_id or self._settings.kafka_client_id
        self._extra_config = kwargs
        self._producer = None
        self._started = False
    
    async def start(self) -> None:
        """Start the producer and connect to Kafka."""
        if self._started:
            return
        
        try:
            from aiokafka import AIOKafkaProducer
        except ImportError:
            raise ImportError(
                "aiokafka is required for Kafka support. "
                "Install with: pip install aiokafka"
            )
        
        # Build producer config
        config = {
            "bootstrap_servers": self._bootstrap_servers,
            "client_id": self._client_id,
            "value_serializer": self._serialize,
            "key_serializer": self._serialize_key,
            "request_timeout_ms": self._settings.kafka_request_timeout_ms,
            "retry_backoff_ms": self._settings.kafka_retry_backoff_ms,
            "max_batch_size": self._settings.kafka_max_batch_size,
            "linger_ms": self._settings.kafka_linger_ms,
            "compression_type": self._settings.kafka_compression_type,
        }
        
        # Add security config if needed
        if self._settings.kafka_security_protocol != "PLAINTEXT":
            config["security_protocol"] = self._settings.kafka_security_protocol
            
            if self._settings.kafka_sasl_mechanism:
                config["sasl_mechanism"] = self._settings.kafka_sasl_mechanism
                config["sasl_plain_username"] = self._settings.kafka_sasl_username
                config["sasl_plain_password"] = self._settings.kafka_sasl_password
            
            if self._settings.kafka_ssl_cafile:
                config["ssl_context"] = self._create_ssl_context()
        
        # Merge extra config
        config.update(self._extra_config)
        
        self._producer = AIOKafkaProducer(**config)
        await self._producer.start()
        self._started = True
    
    async def stop(self) -> None:
        """Stop the producer and flush pending messages."""
        if self._producer and self._started:
            await self._producer.stop()
            self._started = False
    
    async def send(
        self,
        topic: str,
        message: dict[str, Any],
        key: str | None = None,
        headers: dict[str, str] | None = None,
        wait: bool = True,
    ) -> None:
        """
        Send a message to a topic.
        
        Args:
            topic: Topic name
            message: Message payload (dict)
            key: Optional message key for partitioning
            headers: Optional message headers
            wait: If True (default), waits for broker acknowledgment.
                  If False, returns immediately (fire-and-forget).
        
        Note:
            For high-throughput scenarios, use wait=False or send_fire_and_forget().
            Messages are still delivered reliably via Kafka's internal batching.
        """
        if not self._started:
            await self.start()
        
        kafka_headers = None
        if headers:
            kafka_headers = [(k, v.encode()) for k, v in headers.items()]
        
        if wait:
            await self._producer.send_and_wait(
                topic,
                value=message,
                key=key,
                headers=kafka_headers,
            )
        else:
            # Fire-and-forget: returns Future, doesn't wait
            await self._producer.send(
                topic,
                value=message,
                key=key,
                headers=kafka_headers,
            )
    
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
        Messages are batched internally by aiokafka and sent efficiently.
        
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
    
    async def flush(self, timeout: float | None = None) -> None:
        """
        Flush all pending messages to Kafka.
        
        Call this after send_fire_and_forget() batches to ensure
        all messages are delivered before continuing.
        
        Args:
            timeout: Max seconds to wait (None = wait forever)
        
        Example:
            # Send batch without waiting
            for event in events:
                await producer.send_fire_and_forget("events", event)
            
            # Ensure all delivered before response
            await producer.flush()
        """
        if self._producer and self._started:
            await self._producer.flush(timeout_ms=int(timeout * 1000) if timeout else None)
    
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
        wait: bool = True,
    ) -> None:
        """
        Send multiple messages to a topic efficiently.
        
        Uses Kafka's batching for better throughput.
        
        Args:
            topic: Topic name
            messages: List of message payloads
            wait: If True, waits for all messages to be acknowledged.
                  If False, returns after queueing (call flush() later).
        
        Performance Tips:
            - For maximum throughput, use wait=False
            - Batch size is controlled by kafka_max_batch_size setting
            - Use linger_ms > 0 to allow more batching
        """
        if not self._started:
            await self.start()
        
        # Create batch
        batch = self._producer.create_batch()
        
        for message in messages:
            serialized = self._serialize(message)
            metadata = batch.append(
                key=None,
                value=serialized,
                timestamp=None,
            )
            
            if metadata is None:
                # Batch is full, send it and create new one
                await self._producer.send_batch(batch, topic)
                batch = self._producer.create_batch()
                batch.append(key=None, value=serialized, timestamp=None)
        
        # Send remaining messages
        if batch.record_count() > 0:
            await self._producer.send_batch(batch, topic)
        
        # Wait for acknowledgment if requested
        if wait:
            await self.flush()
    
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
        if not self._started:
            await self.start()
        
        # Send all without waiting
        for message in messages:
            await self._producer.send(topic, value=message)
        
        return len(messages)
    
    def _serialize(self, value: Any) -> bytes:
        """Serialize value to bytes."""
        if value is None:
            return None
        if isinstance(value, bytes):
            return value
        if isinstance(value, str):
            return value.encode("utf-8")
        return json.dumps(value).encode("utf-8")
    
    def _serialize_key(self, key: Any) -> bytes | None:
        """Serialize key to bytes."""
        if key is None:
            return None
        if isinstance(key, bytes):
            return key
        return str(key).encode("utf-8")
    
    def _create_ssl_context(self):
        """Create SSL context for secure connections."""
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
