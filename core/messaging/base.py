"""
Base interfaces for messaging system.

All message brokers (Kafka, Redis, RabbitMQ) implement these interfaces,
allowing plug-and-play switching between brokers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, TypeVar, Generic
from datetime import datetime
import json
import uuid

from core.datetime import timezone


# Type aliases
MessageHandler = Callable[[dict[str, Any]], Awaitable[None]]
EventHandlerFunc = Callable[["Event", Any], Awaitable[None]]


@dataclass
class Event:
    """
    Represents a message event.
    
    Attributes:
        name: Event name (e.g., "user.created", "order.completed")
        data: Event payload data
        id: Unique event ID
        timestamp: When the event was created
        source: Source service/app that created the event
        metadata: Additional metadata (headers, etc.)
    """
    
    name: str
    data: dict[str, Any]
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=timezone.now)
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "metadata": self.metadata,
        }
    
    def to_json(self) -> str:
        """Convert event to JSON string."""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Event":
        """Create event from dictionary."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data["name"],
            data=data.get("data", {}),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else timezone.now(),
            source=data.get("source", ""),
            metadata=data.get("metadata", {}),
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> "Event":
        """Create event from JSON string."""
        return cls.from_dict(json.loads(json_str))


@dataclass
class EventHandler:
    """
    Represents an event handler registration.
    
    Attributes:
        event_name: Name of event to handle (e.g., "user.created")
        handler: Async function to call when event is received
        consumer_class: Class that contains the handler
        method_name: Name of the handler method
    """
    
    event_name: str
    handler: EventHandlerFunc
    consumer_class: type | None = None
    method_name: str = ""


class MessageBroker(ABC):
    """
    Abstract base class for message brokers.
    
    All broker implementations (Kafka, Redis, RabbitMQ) must implement
    this interface for plug-and-play compatibility.
    
    Example:
        class KafkaBroker(MessageBroker):
            name = "kafka"
            
            async def connect(self):
                self._producer = AIOKafkaProducer(...)
                await self._producer.start()
            
            async def publish(self, topic, message, key=None):
                await self._producer.send(topic, message, key)
    """
    
    name: str = "base"
    
    @abstractmethod
    async def connect(self) -> None:
        """
        Connect to the message broker.
        
        Should be called during application startup.
        """
        ...
    
    @abstractmethod
    async def disconnect(self) -> None:
        """
        Disconnect from the message broker.
        
        Should be called during application shutdown.
        """
        ...
    
    @abstractmethod
    async def publish(
        self,
        topic: str,
        message: dict[str, Any],
        key: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """
        Publish a message to a topic.
        
        Args:
            topic: Topic/queue name to publish to
            message: Message payload (will be JSON serialized)
            key: Optional message key for partitioning
            headers: Optional message headers
        """
        ...
    
    @abstractmethod
    async def subscribe(
        self,
        topics: list[str],
        group_id: str,
        handler: MessageHandler,
    ) -> None:
        """
        Subscribe to topics and process messages.
        
        Args:
            topics: List of topics to subscribe to
            group_id: Consumer group ID
            handler: Async function to call for each message
        """
        ...
    
    @abstractmethod
    async def create_topic(
        self,
        topic: str,
        partitions: int = 1,
        replication_factor: int = 1,
    ) -> None:
        """
        Create a topic if it doesn't exist.
        
        Args:
            topic: Topic name
            partitions: Number of partitions
            replication_factor: Replication factor
        """
        ...
    
    @abstractmethod
    async def delete_topic(self, topic: str) -> None:
        """
        Delete a topic.
        
        Args:
            topic: Topic name to delete
        """
        ...
    
    @abstractmethod
    async def list_topics(self) -> list[str]:
        """
        List all available topics.
        
        Returns:
            List of topic names
        """
        ...
    
    def is_connected(self) -> bool:
        """Check if broker is connected."""
        return False


class Producer(ABC):
    """
    Abstract base class for message producers.
    
    Producers are responsible for sending messages to topics.
    
    Example:
        producer = get_producer()
        await producer.send("user-events", {"event": "user.created", "data": {...}})
    """
    
    @abstractmethod
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
            message: Message payload
            key: Optional message key
            headers: Optional headers
        """
        ...
    
    @abstractmethod
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
        ...
    
    async def send_batch(
        self,
        topic: str,
        messages: list[dict[str, Any]],
    ) -> None:
        """
        Send multiple messages to a topic.
        
        Default implementation sends one by one.
        Override for batch optimization.
        
        Args:
            topic: Topic name
            messages: List of message payloads
        """
        for message in messages:
            await self.send(topic, message)
    
    @abstractmethod
    async def start(self) -> None:
        """Start the producer."""
        ...
    
    @abstractmethod
    async def stop(self) -> None:
        """Stop the producer."""
        ...


class Consumer(ABC):
    """
    Abstract base class for message consumers.
    
    Consumers subscribe to topics and process incoming messages.
    
    Example:
        @consumer("order-service", topics=["user-events"])
        class UserEventsConsumer(Consumer):
            @on_event("user.created")
            async def handle_user_created(self, event, db):
                await Order.create_welcome_order(...)
    """
    
    group_id: str = ""
    topics: list[str] = []
    
    @abstractmethod
    async def start(self) -> None:
        """
        Start consuming messages.
        
        This should start a background task that continuously
        polls for new messages and dispatches them to handlers.
        """
        ...
    
    @abstractmethod
    async def stop(self) -> None:
        """
        Stop consuming messages.
        
        Should gracefully stop the consumer and commit offsets.
        """
        ...
    
    @abstractmethod
    async def process_message(self, message: dict[str, Any]) -> None:
        """
        Process a single message.
        
        Routes the message to the appropriate event handler.
        
        Args:
            message: Deserialized message payload
        """
        ...
    
    def is_running(self) -> bool:
        """Check if consumer is running."""
        return False


class ConsumerGroup:
    """
    Manages a group of consumers for the same topics.
    
    Allows scaling consumers horizontally while maintaining
    message ordering within partitions.
    """
    
    def __init__(
        self,
        group_id: str,
        topics: list[str],
        consumer_class: type[Consumer],
        concurrency: int = 1,
    ):
        self.group_id = group_id
        self.topics = topics
        self.consumer_class = consumer_class
        self.concurrency = concurrency
        self._consumers: list[Consumer] = []
    
    async def start(self) -> None:
        """Start all consumers in the group."""
        for _ in range(self.concurrency):
            consumer = self.consumer_class()
            consumer.group_id = self.group_id
            consumer.topics = self.topics
            await consumer.start()
            self._consumers.append(consumer)
    
    async def stop(self) -> None:
        """Stop all consumers in the group."""
        for consumer in self._consumers:
            await consumer.stop()
        self._consumers.clear()
    
    @property
    def running_count(self) -> int:
        """Number of running consumers."""
        return sum(1 for c in self._consumers if c.is_running())
