"""
Topic definitions for plug-and-play messaging.

Define topics as classes with automatic schema registration.

Example:
    from core.messaging import Topic, publish
    from pydantic import BaseModel
    
    class UserCreatedEvent(BaseModel):
        user_id: int
        email: str
    
    class UserEvents(Topic):
        name = "user-events"
        schema = UserCreatedEvent
    
    # Publish with 1 line
    await publish(UserEvents, {"user_id": 1, "email": "user@example.com"})
"""

from __future__ import annotations

from typing import Any, TypeVar, Generic, TYPE_CHECKING
from dataclasses import dataclass, field
from pydantic import BaseModel

if TYPE_CHECKING:
    from core.messaging.avro import AvroModel


# Registry of all topics
_topic_registry: dict[str, "Topic"] = {}


class TopicMeta(type):
    """Metaclass that auto-registers Topic classes."""
    
    def __new__(mcs, name: str, bases: tuple, namespace: dict):
        cls = super().__new__(mcs, name, bases, namespace)
        
        # Don't register the base Topic class
        if name != "Topic" and hasattr(cls, "name") and cls.name:
            _topic_registry[cls.name] = cls
        
        return cls


class Topic(metaclass=TopicMeta):
    """
    Base class for topic definitions.
    
    Define topics as classes for type-safe messaging:
    
        class OrderEvents(Topic):
            name = "order-events"
            schema = OrderEvent  # Pydantic model
            partitions = 3
            replication = 2
            retention_ms = 7 * 24 * 60 * 60 * 1000  # 7 days
    
    Features:
        - Auto-registration in topic registry
        - Schema validation on publish
        - Auto-conversion to Avro if using AvroModel
        - Configurable partitions and replication
    """
    
    # Required
    name: str = ""
    
    # Optional schema (Pydantic model or AvroModel)
    schema: type[BaseModel] | None = None
    
    # Kafka topic configuration
    partitions: int = 1
    replication_factor: int = 1
    retention_ms: int | None = None  # None = use broker default
    cleanup_policy: str = "delete"  # "delete", "compact", "delete,compact"
    
    # Serialization
    key_serializer: str = "string"  # "string", "json", "avro"
    value_serializer: str = "json"  # "json", "avro"
    
    @classmethod
    def validate(cls, data: dict[str, Any] | BaseModel) -> dict[str, Any]:
        """
        Validate data against topic schema.
        
        Args:
            data: Data to validate (dict or Pydantic model)
        
        Returns:
            Validated data as dict
        
        Raises:
            ValidationError: If data doesn't match schema
        """
        if cls.schema is None:
            # No schema, accept any dict
            if isinstance(data, BaseModel):
                return data.model_dump()
            return data
        
        if isinstance(data, cls.schema):
            return data.model_dump()
        
        if isinstance(data, BaseModel):
            data = data.model_dump()
        
        # Validate through schema
        validated = cls.schema.model_validate(data)
        return validated.model_dump()
    
    @classmethod
    def get_avro_schema(cls) -> dict[str, Any] | None:
        """
        Get Avro schema if schema is an AvroModel.
        
        Returns:
            Avro schema dict or None
        """
        if cls.schema is None:
            return None
        
        # Check if it's an AvroModel
        if hasattr(cls.schema, "__avro_schema__"):
            return cls.schema.__avro_schema__()
        
        return None
    
    @classmethod
    def get_config(cls) -> dict[str, Any]:
        """Get Kafka topic configuration."""
        config = {}
        
        if cls.retention_ms is not None:
            config["retention.ms"] = str(cls.retention_ms)
        
        if cls.cleanup_policy:
            config["cleanup.policy"] = cls.cleanup_policy
        
        return config


def get_topic(name: str) -> type[Topic] | None:
    """
    Get a registered topic by name.
    
    Args:
        name: Topic name
    
    Returns:
        Topic class or None if not found
    """
    return _topic_registry.get(name)


def get_all_topics() -> dict[str, type[Topic]]:
    """
    Get all registered topics.
    
    Returns:
        Dict of topic name -> Topic class
    """
    return _topic_registry.copy()


def register_topic(topic_class: type[Topic]) -> type[Topic]:
    """
    Manually register a topic class.
    
    Args:
        topic_class: Topic class to register
    
    Returns:
        The registered topic class
    """
    if topic_class.name:
        _topic_registry[topic_class.name] = topic_class
    return topic_class


# =============================================================================
# Common Topic Patterns
# =============================================================================

class EventTopic(Topic):
    """
    Base class for event topics.
    
    Events are immutable facts that happened in the system.
    
    Example:
        class UserCreated(EventTopic):
            name = "user.created"
            schema = UserCreatedEvent
    """
    
    cleanup_policy = "delete"


class CommandTopic(Topic):
    """
    Base class for command topics.
    
    Commands are requests to perform an action.
    
    Example:
        class SendEmail(CommandTopic):
            name = "email.send"
            schema = SendEmailCommand
    """
    
    cleanup_policy = "delete"


class StateTopic(Topic):
    """
    Base class for compacted state topics.
    
    State topics store the latest value for each key.
    
    Example:
        class UserState(StateTopic):
            name = "user.state"
            schema = UserStateModel
    """
    
    cleanup_policy = "compact"
    key_serializer = "string"
