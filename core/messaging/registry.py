"""
Registry for message brokers, producers, and consumers.

Provides a central place to register and retrieve messaging components.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.messaging.base import MessageBroker, Producer, Consumer, EventHandler


# Global registries
_brokers: dict[str, "MessageBroker"] = {}
_producers: dict[str, "Producer"] = {}
_consumers: dict[str, type] = {}
_event_handlers: dict[str, list["EventHandler"]] = {}
_default_broker: str | None = None


def register_broker(broker: "MessageBroker", default: bool = False) -> None:
    """
    Register a message broker.
    
    Args:
        broker: MessageBroker instance
        default: Whether this is the default broker
    
    Example:
        from core.messaging.kafka import KafkaBroker
        
        broker = KafkaBroker(bootstrap_servers="localhost:9092")
        register_broker(broker, default=True)
    """
    global _default_broker
    _brokers[broker.name] = broker
    if default or _default_broker is None:
        _default_broker = broker.name


def get_broker(name: str | None = None) -> "MessageBroker":
    """
    Get a registered broker by name.
    
    Args:
        name: Broker name (uses default if None)
    
    Returns:
        MessageBroker instance
    
    Raises:
        ValueError: If broker not found
    """
    broker_name = name or _default_broker
    if broker_name is None:
        raise ValueError("No broker registered. Call register_broker() first.")
    
    if broker_name not in _brokers:
        raise ValueError(f"Broker '{broker_name}' not found. Available: {list(_brokers.keys())}")
    
    return _brokers[broker_name]


def register_producer(producer: "Producer", name: str = "default") -> None:
    """
    Register a producer.
    
    Args:
        producer: Producer instance
        name: Producer name for retrieval
    """
    _producers[name] = producer


def get_producer(name: str = "default") -> "Producer":
    """
    Get a registered producer (auto-creates if not exists).
    
    Automatically creates the appropriate producer based on settings:
    - kafka_backend="confluent" -> ConfluentProducer
    - kafka_backend="aiokafka" -> KafkaProducer (default)
    
    Configuração via .env:
        KAFKA_BACKEND=confluent
    
    Args:
        name: Producer name
    
    Returns:
        Producer instance
    
    Example:
        producer = get_producer()
        await producer.send("topic", {"key": "value"})
    """
    if name not in _producers:
        from core.config import get_settings
        
        settings = get_settings()
        kafka_backend = getattr(settings, "kafka_backend", "aiokafka")
        
        if kafka_backend == "confluent":
            from core.messaging.confluent import ConfluentProducer
            producer = ConfluentProducer()
        else:
            from core.messaging.kafka import KafkaProducer
            producer = KafkaProducer()
        
        register_producer(producer, name)
        return producer
    
    return _producers[name]


def register_consumer(consumer_class: type, group_id: str | None = None) -> None:
    """
    Register a consumer class.
    
    Args:
        consumer_class: Consumer class (decorated with @consumer)
        group_id: Optional group ID override
    
    Example:
        @consumer("order-service", topics=["user-events"])
        class UserEventsConsumer:
            @on_event("user.created")
            async def handle_user_created(self, event, db):
                ...
        
        # Automatically registered by @consumer decorator
    """
    gid = group_id or getattr(consumer_class, "_group_id", consumer_class.__name__)
    _consumers[gid] = consumer_class


def get_consumer(group_id: str) -> type:
    """
    Get a registered consumer class.
    
    Args:
        group_id: Consumer group ID
    
    Returns:
        Consumer class
    
    Raises:
        ValueError: If consumer not found
    """
    if group_id not in _consumers:
        raise ValueError(f"Consumer '{group_id}' not found. Available: {list(_consumers.keys())}")
    
    return _consumers[group_id]


def get_kafka_consumer_class() -> type:
    """
    Get the appropriate Kafka consumer class based on settings.
    
    Configuração via .env:
        KAFKA_BACKEND=confluent
    
    Returns:
        Consumer class (KafkaConsumer or ConfluentConsumer)
    """
    from core.config import get_settings
    
    settings = get_settings()
    kafka_backend = getattr(settings, "kafka_backend", "aiokafka")
    
    if kafka_backend == "confluent":
        from core.messaging.confluent import ConfluentConsumer
        return ConfluentConsumer
    else:
        from core.messaging.kafka import KafkaConsumer
        return KafkaConsumer


def create_consumer(
    group_id: str,
    topics: list[str],
    **kwargs,
) -> "Consumer":
    """
    Create a consumer instance with the appropriate backend.
    
    Factory function that creates the correct consumer based on settings.
    
    Args:
        group_id: Consumer group ID
        topics: List of topics to subscribe to
        **kwargs: Additional consumer configuration
    
    Returns:
        Consumer instance (KafkaConsumer or ConfluentConsumer)
    
    Example:
        consumer = create_consumer(
            group_id="my-service",
            topics=["user-events", "payment-events"],
        )
        await consumer.start()
    """
    ConsumerClass = get_kafka_consumer_class()
    return ConsumerClass(group_id=group_id, topics=topics, **kwargs)


def get_consumers() -> dict[str, type]:
    """
    Get all registered consumers.
    
    Returns:
        Dictionary of group_id -> consumer class
    """
    return _consumers.copy()


def register_event_handler(handler: "EventHandler") -> None:
    """
    Register an event handler.
    
    Args:
        handler: EventHandler instance
    """
    if handler.event_name not in _event_handlers:
        _event_handlers[handler.event_name] = []
    _event_handlers[handler.event_name].append(handler)


def get_event_handlers(event_name: str) -> list["EventHandler"]:
    """
    Get handlers for an event.
    
    Args:
        event_name: Event name (e.g., "user.created")
    
    Returns:
        List of EventHandler instances
    """
    return _event_handlers.get(event_name, [])


def get_all_event_handlers() -> dict[str, list["EventHandler"]]:
    """
    Get all registered event handlers.
    
    Returns:
        Dictionary of event_name -> list of handlers
    """
    return _event_handlers.copy()


def clear_registry() -> None:
    """
    Clear all registries.
    
    Useful for testing.
    """
    global _default_broker
    _brokers.clear()
    _producers.clear()
    _consumers.clear()
    _event_handlers.clear()
    _default_broker = None


async def start_all_producers() -> None:
    """Start all registered producers."""
    for producer in _producers.values():
        await producer.start()


async def stop_all_producers() -> None:
    """Stop all registered producers."""
    for producer in _producers.values():
        await producer.stop()


async def connect_all_brokers() -> None:
    """Connect all registered brokers."""
    for broker in _brokers.values():
        await broker.connect()


async def disconnect_all_brokers() -> None:
    """Disconnect all registered brokers."""
    for broker in _brokers.values():
        await broker.disconnect()


# =============================================================================
# Simplified Publishing API
# =============================================================================

async def publish(
    topic: str | type,
    data: dict[str, Any] | Any,
    key: str | None = None,
    headers: dict[str, str] | None = None,
    wait: bool | None = None,
) -> None:
    """
    Publish a message to a topic (simplified API).
    
    This is the recommended way to publish messages.
    Automatically handles:
    - Producer creation and connection pooling
    - Schema validation (if Topic class with schema)
    - Serialization (JSON or Avro)
    - Backend selection (aiokafka or confluent)
    
    Args:
        topic: Topic name (str) or Topic class
        data: Message payload (dict or Pydantic model)
        key: Optional message key for partitioning
        headers: Optional message headers
        wait: If True, wait for delivery confirmation.
              If False, fire-and-forget.
              If None (default), uses kafka_fire_and_forget setting (inverted).
    
    Example:
        # Simple string topic
        await publish("user-events", {"user_id": 1, "action": "created"})
        
        # With Topic class (validates schema)
        class UserEvents(Topic):
            name = "user-events"
            schema = UserEventSchema
        
        await publish(UserEvents, {"user_id": 1, "action": "created"})
        
        # With Pydantic model
        event = UserEventSchema(user_id=1, action="created")
        await publish(UserEvents, event)
        
        # Explicit wait for confirmation
        await publish("critical-events", data, wait=True)
    """
    from pydantic import BaseModel
    from core.messaging.topics import Topic
    
    # Resolve topic name and validate
    topic_name: str
    if isinstance(topic, type) and issubclass(topic, Topic):
        topic_name = topic.name
        data = topic.validate(data)
    elif isinstance(topic, str):
        topic_name = topic
        if isinstance(data, BaseModel):
            data = data.model_dump()
    else:
        raise TypeError(f"topic must be str or Topic class, got {type(topic)}")
    
    # Get producer and send
    producer = get_producer()
    
    # Ensure started
    if hasattr(producer, "_started") and not producer._started:
        await producer.start()
    
    # Send - wait=None lets the producer use its settings
    await producer.send(topic_name, data, key=key, headers=headers, wait=wait)


async def publish_event(
    event_name: str,
    data: dict[str, Any],
    topic: str | None = None,
    key: str | None = None,
    source: str | None = None,
) -> None:
    """
    Publish an event with standard Event envelope.
    
    Creates an Event object with metadata and publishes it.
    
    Args:
        event_name: Event name (e.g., "user.created")
        data: Event payload
        topic: Topic name (defaults to messaging_default_topic)
        key: Optional message key
        source: Event source (defaults to messaging_event_source)
    
    Example:
        await publish_event(
            "user.created",
            {"user_id": 1, "email": "user@example.com"},
            topic="user-events",
        )
    """
    from core.messaging.base import Event
    from core.messaging.config import get_messaging_settings
    
    settings = get_messaging_settings()
    
    event = Event(
        name=event_name,
        data=data,
        source=source or settings.messaging_event_source,
    )
    
    topic_name = topic or settings.messaging_default_topic
    
    producer = get_producer()
    if hasattr(producer, "_started") and not producer._started:
        await producer.start()
    
    await producer.send_event(topic_name, event, key=key)
