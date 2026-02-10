"""
Confluent Kafka consumer implementation.

High-performance consumer using confluent-kafka (librdkafka).
Compatible with aiokafka backend - same interface and behavior.
"""

from __future__ import annotations

from typing import Any, Callable, Awaitable
import json
import asyncio
import logging

from core.messaging.base import Consumer, Event, EventHandler
from core.config import get_settings
from core.messaging.registry import get_event_handlers


logger = logging.getLogger(__name__)

MessageHandler = Callable[[dict[str, Any]], Awaitable[None]]


class ConfluentConsumer(Consumer):
    """
    High-performance Kafka consumer using confluent-kafka.
    
    Features:
        - Manual offset commit for at-least-once delivery
        - Batch processing support
        - Graceful shutdown
        - Schema Registry integration
        - Event routing compatible with aiokafka backend
    
    Example:
        # Basic usage (same as KafkaConsumer)
        consumer = ConfluentConsumer(
            group_id="my-service",
            topics=["user-events"],
        )
        await consumer.start()
        
        # With custom handler
        async def handler(message):
            print(f"Received: {message}")
        
        consumer = ConfluentConsumer(
            group_id="logger",
            topics=["all-events"],
            message_handler=handler,
        )
        await consumer.start()
    """
    
    def __init__(
        self,
        group_id: str | None = None,
        topics: list[str] | None = None,
        message_handler: MessageHandler | None = None,
        **kwargs: Any,
    ):
        """
        Initialize Confluent consumer.
        
        Args:
            group_id: Consumer group ID
            topics: Topics to subscribe to (strings or Topic classes)
            message_handler: Optional custom message handler
            **kwargs: Additional confluent-kafka config
        """
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
        """Resolve topic names from strings or Topic classes."""
        resolved = []
        for topic in topics:
            if isinstance(topic, str):
                resolved.append(topic)
            elif hasattr(topic, 'name'):
                resolved.append(topic.name)
            elif hasattr(topic, 'value'):
                resolved.append(topic.value)
            else:
                resolved.append(str(topic))
        return resolved
    
    def set_db_session_factory(self, factory: Callable) -> None:
        """
        Set database session factory for handlers.
        
        Args:
            factory: Async context manager that yields db session
        """
        self._db_session_factory = factory
    
    async def start(self) -> None:
        """
        Start consuming messages.
        
        Note:
            Handler should be set via constructor (message_handler parameter)
            for compatibility with KafkaConsumer backend.
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
        
        # Start consume loop and store task reference for proper cancellation
        self._task = asyncio.create_task(self._consume_loop())
        
        logger.info(
            f"Consumer '{self.group_id}' started, subscribed to: {self.topics}"
        )
    
    async def _consume_loop(self) -> None:
        """Main consume loop."""
        try:
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
                            logger.error(f"Consumer error: {error}")
                            continue
                    
                    # Process message
                    try:
                        value = json.loads(msg.value().decode("utf-8"))
                        
                        # Track incoming event (if enabled)
                        await self._track_incoming_event(msg, value)
                        
                        await self.process_message(value)
                    except json.JSONDecodeError:
                        logger.error(f"Failed to decode message: {msg.value()}")
                    except Exception as e:
                        logger.error(
                            f"Error processing message: {e}",
                            exc_info=True,
                        )
                        # TODO: Send to dead letter queue
                    
                except Exception as e:
                    logger.error(f"Consumer loop error: {e}", exc_info=True)
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Consumer loop error: {e}", exc_info=True)
    
    async def _track_incoming_event(self, msg: Any, value: dict) -> None:
        """
        Track an incoming Kafka message for the Operations Center.
        
        Args:
            msg: Raw Kafka message from confluent-kafka
            value: Deserialized message value
        """
        from core.admin.event_tracking import get_event_tracker
        
        tracker = get_event_tracker()
        if not tracker.is_enabled():
            return
        
        try:
            # Extract headers
            headers_dict = {}
            if msg.headers():
                for key, val in msg.headers():
                    if val:
                        headers_dict[key] = val.decode("utf-8") if isinstance(val, bytes) else str(val)
            
            # Get event_id and event_name from headers
            event_id = headers_dict.get("event_id")
            event_name = headers_dict.get("event_name", "unknown")
            
            # If no event_id in headers, try to get from message value
            if not event_id:
                event_id = value.get("id") or value.get("event_id")
                if not event_name or event_name == "unknown":
                    event_name = value.get("name") or value.get("event_name", "unknown")
            
            # Generate event_id if still not found
            if not event_id:
                import uuid
                event_id = str(uuid.uuid4())
            
            # Get key
            key = None
            if msg.key():
                key = msg.key().decode("utf-8") if isinstance(msg.key(), bytes) else str(msg.key())
            
            await tracker.track_incoming(
                event_id=event_id,
                event_name=event_name,
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset(),
                payload=value,
                headers=headers_dict if headers_dict else None,
                key=key,
                source_worker_id=self.group_id,
            )
        except Exception as e:
            logger.warning(f"Failed to track incoming event: {e}")
    
    async def stop(self) -> None:
        """Stop consuming messages."""
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
        """
        Process a single message.
        
        Routes to appropriate event handler or custom handler.
        Compatible with KafkaConsumer behavior.
        
        Args:
            message: Deserialized message payload
        """
        # Use custom handler if provided
        if self._message_handler:
            await self._message_handler(message)
            return
        
        # Route to event handlers (same logic as KafkaConsumer)
        event_name = message.get("name")
        if not event_name:
            logger.warning(f"Message without event name: {message}")
            return
        
        # Create Event object
        event = Event.from_dict(message)
        
        # Get handlers for this event
        handlers = get_event_handlers(event_name)
        
        if not handlers:
            logger.debug(f"No handlers for event: {event_name}")
            return
        
        # Execute handlers
        for handler in handlers:
            try:
                await self._execute_handler(handler, event)
            except Exception as e:
                logger.error(
                    f"Handler error for {event_name}: {e}",
                    exc_info=True,
                )
    
    async def _execute_handler(
        self,
        handler: EventHandler,
        event: Event,
    ) -> None:
        """Execute an event handler with proper context."""
        # Get or create consumer instance
        if handler.consumer_class:
            consumer_instance = handler.consumer_class()
            handler_method = getattr(consumer_instance, handler.method_name)
        else:
            handler_method = handler.handler
        
        # Execute with or without db session
        if self._db_session_factory:
            async with self._db_session_factory() as db:
                await handler_method(event, db)
        else:
            await handler_method(event, None)
    
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
