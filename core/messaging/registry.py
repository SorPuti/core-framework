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
    Get a registered producer.
    
    Args:
        name: Producer name
    
    Returns:
        Producer instance
    
    Raises:
        ValueError: If producer not found
    """
    if name not in _producers:
        # Try to create default producer from broker
        if _default_broker and _default_broker in _brokers:
            from core.messaging.kafka import KafkaProducer
            from core.messaging.config import get_messaging_settings
            
            settings = get_messaging_settings()
            if settings.message_broker == "kafka":
                producer = KafkaProducer()
                register_producer(producer, name)
                return producer
        
        raise ValueError(f"Producer '{name}' not found. Call register_producer() first.")
    
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
