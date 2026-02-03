"""
Confluent Kafka backend for enterprise messaging.

Uses confluent-kafka (librdkafka) for high-performance messaging.

Features:
    - Higher throughput than aiokafka
    - Schema Registry integration
    - Avro/JSON Schema/Protobuf serialization
    - Transactional support
    - Better compression support

Example:
    from core.messaging import configure_messaging
    
    configure_messaging(
        kafka_backend="confluent",
        kafka_bootstrap_servers="kafka:9092",
        kafka_schema_registry_url="http://schema-registry:8081",
    )
"""

from core.messaging.confluent.producer import ConfluentProducer
from core.messaging.confluent.consumer import ConfluentConsumer

__all__ = [
    "ConfluentProducer",
    "ConfluentConsumer",
]
