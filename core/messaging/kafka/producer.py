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
    ) -> None:
        """
        Send a message to a topic.
        
        Args:
            topic: Topic name
            message: Message payload (dict)
            key: Optional message key for partitioning
            headers: Optional message headers
        """
        if not self._started:
            await self.start()
        
        kafka_headers = None
        if headers:
            kafka_headers = [(k, v.encode()) for k, v in headers.items()]
        
        await self._producer.send_and_wait(
            topic,
            value=message,
            key=key,
            headers=kafka_headers,
        )
    
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
    ) -> None:
        """
        Send multiple messages to a topic efficiently.
        
        Uses Kafka's batching for better throughput.
        
        Args:
            topic: Topic name
            messages: List of message payloads
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
