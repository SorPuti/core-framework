"""
Kafka implementation for Core Framework messaging.

Provides KafkaBroker, KafkaProducer, KafkaConsumer, and KafkaAdmin
for enterprise-grade message streaming.

Requirements:
    pip install aiokafka

Usage:
    from core.messaging.kafka import KafkaBroker, KafkaProducer, KafkaConsumer
    
    # Configure broker
    broker = KafkaBroker()
    await broker.connect()
    
    # Produce messages
    producer = KafkaProducer()
    await producer.start()
    await producer.send("user-events", {"event": "user.created", "data": {...}})
    
    # Consume messages
    consumer = KafkaConsumer(group_id="order-service", topics=["user-events"])
    await consumer.start()
"""

from core.messaging.kafka.producer import KafkaProducer
from core.messaging.kafka.consumer import KafkaConsumer
from core.messaging.kafka.broker import KafkaBroker
from core.messaging.kafka.admin import (
    KafkaAdmin,
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
    "KafkaBroker",
    "KafkaProducer",
    "KafkaConsumer",
    "KafkaAdmin",
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
