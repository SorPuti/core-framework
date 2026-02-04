"""
Kafka consumer implementation.

Provides async message consumption from Kafka topics with
automatic deserialization, offset management, and event routing.
"""

from __future__ import annotations

from typing import Any, Callable, Awaitable
import json
import asyncio
import logging

from core.messaging.base import Consumer, Event, EventHandler
from core.messaging.config import get_messaging_settings
from core.messaging.registry import get_event_handlers


logger = logging.getLogger(__name__)


class KafkaConsumer(Consumer):
    """
    Kafka message consumer using aiokafka.
    
    Features:
        - Automatic JSON deserialization
        - Consumer group support
        - Auto offset commit
        - Event routing to handlers
        - Graceful shutdown
    
    Example:
        # Basic usage
        consumer = KafkaConsumer(
            group_id="order-service",
            topics=["user-events", "payment-events"],
        )
        await consumer.start()
        
        # With custom handler
        async def handle_message(message):
            print(f"Received: {message}")
        
        consumer = KafkaConsumer(
            group_id="logger",
            topics=["all-events"],
            message_handler=handle_message,
        )
        await consumer.start()
    """
    
    def __init__(
        self,
        group_id: str,
        topics: list[str],
        bootstrap_servers: str | None = None,
        message_handler: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        **kwargs: Any,
    ):
        """
        Initialize Kafka consumer.
        
        Args:
            group_id: Consumer group ID
            topics: List of topics to subscribe to (strings or Topic classes)
            bootstrap_servers: Kafka servers (comma-separated)
            message_handler: Optional custom message handler
            **kwargs: Additional aiokafka consumer options
        """
        self._settings = get_messaging_settings()
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
        """Start consuming messages."""
        if self._running:
            return
        
        try:
            from aiokafka import AIOKafkaConsumer
        except ImportError:
            raise ImportError(
                "aiokafka is required for Kafka support. "
                "Install with: pip install aiokafka"
            )
        
        # Build consumer config
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
        
        # Add security config if needed
        if self._settings.kafka_security_protocol != "PLAINTEXT":
            config["security_protocol"] = self._settings.kafka_security_protocol
            
            if self._settings.kafka_sasl_mechanism:
                config["sasl_mechanism"] = self._settings.kafka_sasl_mechanism
                config["sasl_plain_username"] = self._settings.kafka_sasl_username
                config["sasl_plain_password"] = self._settings.kafka_sasl_password
        
        # Merge extra config
        config.update(self._extra_config)
        
        self._consumer = AIOKafkaConsumer(*self.topics, **config)
        await self._consumer.start()
        self._running = True
        
        # Start consume loop
        self._task = asyncio.create_task(self._consume_loop())
        
        logger.info(
            f"Consumer '{self.group_id}' started, subscribed to: {self.topics}"
        )
    
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
            await self._consumer.stop()
            self._consumer = None
        
        logger.info(f"Consumer '{self.group_id}' stopped")
    
    def is_running(self) -> bool:
        """Check if consumer is running."""
        return self._running
    
    async def _consume_loop(self) -> None:
        """Main consume loop."""
        try:
            async for message in self._consumer:
                if not self._running:
                    break
                
                try:
                    await self.process_message(message.value)
                except Exception as e:
                    logger.error(
                        f"Error processing message: {e}",
                        exc_info=True,
                    )
                    # TODO: Send to dead letter queue
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Consumer loop error: {e}", exc_info=True)
    
    async def process_message(self, message: dict[str, Any]) -> None:
        """
        Process a single message.
        
        Routes to appropriate event handler or custom handler.
        
        Args:
            message: Deserialized message payload
        """
        # Use custom handler if provided
        if self._message_handler:
            await self._message_handler(message)
            return
        
        # Route to event handlers
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
    
    def _deserialize(self, value: bytes) -> dict[str, Any]:
        """Deserialize message value from bytes."""
        if value is None:
            return {}
        try:
            return json.loads(value.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {"raw": value.decode("utf-8", errors="replace")}


class KafkaConsumerRunner:
    """
    Runs multiple Kafka consumers.
    
    Used by the CLI worker command to start all registered consumers.
    
    Example:
        runner = KafkaConsumerRunner()
        runner.add_consumer(UserEventsConsumer)
        runner.add_consumer(PaymentEventsConsumer)
        await runner.start()
        
        # Wait for shutdown signal
        await runner.wait()
        
        await runner.stop()
    """
    
    def __init__(self):
        self._consumers: list[KafkaConsumer] = []
        self._running = False
        self._shutdown_event = asyncio.Event()
    
    def add_consumer(
        self,
        consumer_class: type,
        db_session_factory: Callable | None = None,
    ) -> None:
        """
        Add a consumer class to run.
        
        Args:
            consumer_class: Consumer class decorated with @consumer
            db_session_factory: Optional db session factory
        """
        group_id = getattr(consumer_class, "_group_id", consumer_class.__name__)
        topics = getattr(consumer_class, "_topics", [])
        
        consumer = KafkaConsumer(group_id=group_id, topics=topics)
        
        if db_session_factory:
            consumer.set_db_session_factory(db_session_factory)
        
        self._consumers.append(consumer)
    
    async def start(self) -> None:
        """Start all consumers."""
        self._running = True
        for consumer in self._consumers:
            await consumer.start()
        logger.info(f"Started {len(self._consumers)} consumer(s)")
    
    async def stop(self) -> None:
        """Stop all consumers."""
        self._running = False
        for consumer in self._consumers:
            await consumer.stop()
        self._shutdown_event.set()
        logger.info("All consumers stopped")
    
    async def wait(self) -> None:
        """Wait for shutdown signal."""
        await self._shutdown_event.wait()
    
    def request_shutdown(self) -> None:
        """Request graceful shutdown."""
        self._shutdown_event.set()
