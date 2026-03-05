"""
Confluent Kafka backend for enterprise messaging.

Uses confluent-kafka (librdkafka) for high-performance messaging.

Features:
    - Higher throughput than aiokafka
    - Schema Registry integration
    - Avro/JSON Schema/Protobuf serialization
    - Transactional support
    - Better compression support
    - Admin client for topic management
    - Unified broker interface

Example:
    from stride.messaging import configure_messaging
    
    configure_messaging(
        kafka_backend="confluent",
        kafka_bootstrap_servers="kafka:9092",
        kafka_schema_registry_url="http://schema-registry:8081",
    )

Usage:
    from stride.messaging.confluent import ConfluentBroker, ConfluentProducer, ConfluentConsumer, ConfluentAdmin
    
    # Unified broker
    broker = ConfluentBroker()
    await broker.connect()
    
    # Produce messages
    producer = ConfluentProducer()
    await producer.start()
    await producer.send("user-events", {"event": "user.created", "data": {...}})
    
    # Consume messages
    consumer = ConfluentConsumer(group_id="order-service", topics=["user-events"])
    await consumer.start()
    
    # Admin operations
    admin = ConfluentAdmin()
    await admin.connect()
    await admin.create_topic("new-topic", partitions=3)
"""

from stride.messaging.confluent.producer import ConfluentProducer
from stride.messaging.confluent.consumer import ConfluentConsumer
from stride.messaging.confluent.broker import ConfluentBroker
from stride.messaging.confluent.admin import (
    ConfluentAdmin,
    TopicInfo,
    BrokerInfo,
    PartitionInfo,
    PartitionOffset,
    MemberInfo,
    ConsumerGroupInfo,
    ConsumerGroupDetail,
    ClusterInfo,
)

__all__ = [
    "ConfluentBroker",
    "ConfluentProducer",
    "ConfluentConsumer",
    "ConfluentAdmin",
    # Types
    "TopicInfo",
    "BrokerInfo",
    "PartitionInfo",
    "PartitionOffset",
    "MemberInfo",
    "ConsumerGroupInfo",
    "ConsumerGroupDetail",
    "ClusterInfo",
]
