"""
Core Framework - Enterprise Messaging System.

Plug-and-play messaging for scaling applications to enterprise level.
Supports Kafka (aiokafka or confluent-kafka), Redis Streams, and RabbitMQ.

Quick Start:
    from core.messaging import publish, Topic
    
    # Simple publish (1 line!)
    await publish("user-events", {"user_id": 1, "action": "created"})
    
    # With Topic class (schema validation)
    class UserEvents(Topic):
        name = "user-events"
        schema = UserEventSchema
    
    await publish(UserEvents, {"user_id": 1})

Workers:
    from core.messaging import worker, Worker
    
    # Decorator style
    @worker(topic="events.raw", output_topic="events.enriched")
    async def enrich_event(event: dict) -> dict:
        return {**event, "processed": True}
    
    # Class style
    class MyWorker(Worker):
        input_topic = "events.raw"
        output_topic = "events.enriched"
        
        async def process(self, event: dict) -> dict:
            return {**event, "processed": True}
    
    # Run: core runworker enrich_event

Avro Support:
    from core.messaging import AvroModel
    
    class UserEvent(AvroModel):
        user_id: int
        email: str
    
    # Auto-generates Avro schema
    schema = UserEvent.__avro_schema__()

Configuration:
    # core.toml or environment variables
    [messaging]
    message_broker = "kafka"
    kafka_backend = "confluent"  # or "aiokafka"
    kafka_bootstrap_servers = "kafka:9092"
    kafka_schema_registry_url = "http://schema-registry:8081"
    kafka_fire_and_forget = true
"""

from core.messaging.base import (
    MessageBroker,
    Producer,
    Consumer,
    Event,
    EventHandler,
)
from core.messaging.config import (
    MessagingSettings,
    get_messaging_settings,
    configure_messaging,
)
from core.messaging.decorators import (
    event,
    consumer,
    on_event,
)
from core.messaging.registry import (
    get_broker,
    get_producer,
    register_broker,
    register_consumer,
    get_consumers,
    get_kafka_consumer_class,
    create_consumer,
    publish,
    publish_event,
)
from core.messaging.topics import (
    Topic,
    EventTopic,
    CommandTopic,
    StateTopic,
    get_topic,
    get_all_topics,
    register_topic,
)
from core.messaging.avro import (
    AvroModel,
    avro_schema,
)
from core.messaging.workers import (
    worker,
    Worker,
    WorkerConfig,
    RetryPolicy,
    get_worker,
    get_all_workers,
    list_workers,
    run_worker,
    run_all_workers,
)

__all__ = [
    # Base classes
    "MessageBroker",
    "Producer",
    "Consumer",
    "Event",
    "EventHandler",
    # Config
    "MessagingSettings",
    "get_messaging_settings",
    "configure_messaging",
    # Decorators
    "event",
    "consumer",
    "on_event",
    # Registry & Publishing
    "get_broker",
    "get_producer",
    "register_broker",
    "register_consumer",
    "get_consumers",
    "get_kafka_consumer_class",
    "create_consumer",
    "publish",
    "publish_event",
    # Topics
    "Topic",
    "EventTopic",
    "CommandTopic",
    "StateTopic",
    "get_topic",
    "get_all_topics",
    "register_topic",
    # Avro
    "AvroModel",
    "avro_schema",
    # Workers
    "worker",
    "Worker",
    "WorkerConfig",
    "RetryPolicy",
    "get_worker",
    "get_all_workers",
    "list_workers",
    "run_worker",
    "run_all_workers",
]
