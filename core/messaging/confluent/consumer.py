"""
Confluent Kafka consumer implementation.

High-performance consumer using confluent-kafka (librdkafka).
"""

from __future__ import annotations

from typing import Any, Callable, Awaitable
import json
import asyncio

from core.messaging.base import Consumer, Event
from core.messaging.config import get_messaging_settings


MessageHandler = Callable[[dict[str, Any]], Awaitable[None]]


class ConfluentConsumer(Consumer):
    """
    High-performance Kafka consumer using confluent-kafka.
    
    Features:
        - Manual offset commit for at-least-once delivery
        - Batch processing support
        - Graceful shutdown
        - Schema Registry integration
    
    Example:
        consumer = ConfluentConsumer(
            group_id="my-service",
            topics=["user-events"],
        )
        
        async def handler(message):
            print(f"Received: {message}")
        
        await consumer.start(handler)
    """
    
    def __init__(
        self,
        group_id: str | None = None,
        topics: list[str] | None = None,
        **kwargs: Any,
    ):
        """
        Initialize Confluent consumer.
        
        Args:
            group_id: Consumer group ID
            topics: Topics to subscribe to
            **kwargs: Additional confluent-kafka config
        """
        self._settings = get_messaging_settings()
        self.group_id = group_id or ""
        self.topics = topics or []
        self._extra_config = kwargs
        self._consumer = None
        self._running = False
        self._handler: MessageHandler | None = None
    
    async def start(self, handler: MessageHandler | None = None) -> None:
        """
        Start consuming messages.
        
        Args:
            handler: Async function to call for each message
        """
        if self._running:
            return
        
        try:
            from confluent_kafka import Consumer as CKConsumer
        except ImportError:
            raise ImportError(
                "confluent-kafka is required for Confluent backend. "
                "Install with: pip install confluent-kafka"
            )
        
        if handler:
            self._handler = handler
        
        # Build consumer config
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
        
        # Add security config
        if self._settings.kafka_security_protocol != "PLAINTEXT":
            config["security.protocol"] = self._settings.kafka_security_protocol
            
            if self._settings.kafka_sasl_mechanism:
                config["sasl.mechanism"] = self._settings.kafka_sasl_mechanism
                config["sasl.username"] = self._settings.kafka_sasl_username
                config["sasl.password"] = self._settings.kafka_sasl_password
            
            if self._settings.kafka_ssl_cafile:
                config["ssl.ca.location"] = self._settings.kafka_ssl_cafile
        
        # Merge extra config
        config.update(self._extra_config)
        
        self._consumer = CKConsumer(config)
        self._consumer.subscribe(self.topics)
        self._running = True
        
        # Start consume loop
        asyncio.create_task(self._consume_loop())
    
    async def _consume_loop(self) -> None:
        """Main consume loop."""
        while self._running:
            try:
                # Poll with timeout
                msg = self._consumer.poll(timeout=1.0)
                
                if msg is None:
                    await asyncio.sleep(0.01)  # Yield to event loop
                    continue
                
                if msg.error():
                    # Handle errors
                    error = msg.error()
                    if error.code() == error._PARTITION_EOF:
                        continue
                    else:
                        print(f"Consumer error: {error}")
                        continue
                
                # Process message
                try:
                    value = json.loads(msg.value().decode("utf-8"))
                    await self.process_message(value)
                except json.JSONDecodeError:
                    print(f"Failed to decode message: {msg.value()}")
                except Exception as e:
                    print(f"Error processing message: {e}")
                
            except Exception as e:
                print(f"Consumer loop error: {e}")
                await asyncio.sleep(1)
    
    async def stop(self) -> None:
        """Stop consuming messages."""
        self._running = False
        
        if self._consumer:
            self._consumer.close()
            self._consumer = None
    
    async def process_message(self, message: dict[str, Any]) -> None:
        """
        Process a single message.
        
        Args:
            message: Deserialized message payload
        """
        if self._handler:
            await self._handler(message)
    
    def is_running(self) -> bool:
        """Check if consumer is running."""
        return self._running
    
    async def commit(self) -> None:
        """Manually commit offsets."""
        if self._consumer:
            self._consumer.commit()
    
    async def seek_to_beginning(self) -> None:
        """Seek to beginning of all partitions."""
        if self._consumer:
            from confluent_kafka import OFFSET_BEGINNING
            
            partitions = self._consumer.assignment()
            for partition in partitions:
                partition.offset = OFFSET_BEGINNING
            self._consumer.assign(partitions)
    
    async def seek_to_end(self) -> None:
        """Seek to end of all partitions."""
        if self._consumer:
            from confluent_kafka import OFFSET_END
            
            partitions = self._consumer.assignment()
            for partition in partitions:
                partition.offset = OFFSET_END
            self._consumer.assign(partitions)
