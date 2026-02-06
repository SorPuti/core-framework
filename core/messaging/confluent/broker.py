"""
Confluent Kafka broker implementation.

Provides a unified interface for Kafka operations including
producing, consuming, and topic management using confluent-kafka (librdkafka).

Compatible with KafkaBroker (aiokafka) — same interface.
"""

from __future__ import annotations

from typing import Any, Callable, Awaitable
import logging

from core.messaging.base import MessageBroker
from core.config import get_settings
from core.messaging.confluent.producer import ConfluentProducer
from core.messaging.confluent.consumer import ConfluentConsumer
from core.messaging.confluent.admin import ConfluentAdmin


logger = logging.getLogger(__name__)


class ConfluentBroker(MessageBroker):
    """
    Confluent Kafka message broker implementation.

    Provides a unified interface for all Kafka operations using
    confluent-kafka (librdkafka) for high performance.

    Compatible with KafkaBroker (aiokafka) — same interface, allowing
    plug-and-play switching via kafka_backend setting.

    Example:
        broker = ConfluentBroker()
        await broker.connect()

        # Publish message
        await broker.publish("user-events", {"event": "user.created", "data": {...}})

        # Subscribe to topic
        async def handler(message):
            print(f"Received: {message}")

        await broker.subscribe(["user-events"], "my-service", handler)

        # Topic management
        await broker.create_topic("new-topic", partitions=3)
        topics = await broker.list_topics()

        await broker.disconnect()
    """

    name = "confluent"

    def __init__(
        self,
        bootstrap_servers: str | None = None,
        schema_registry_url: str | None = None,
        **kwargs: Any,
    ):
        """
        Initialize Confluent broker.

        Args:
            bootstrap_servers: Kafka servers (comma-separated)
            schema_registry_url: Schema Registry URL for Avro support
            **kwargs: Additional configuration
        """
        self._settings = get_settings()
        self._bootstrap_servers = bootstrap_servers or self._settings.kafka_bootstrap_servers
        self._schema_registry_url = schema_registry_url or getattr(
            self._settings, "kafka_schema_registry_url", None
        )
        self._extra_config = kwargs

        self._producer: ConfluentProducer | None = None
        self._consumers: dict[str, ConfluentConsumer] = {}
        self._admin: ConfluentAdmin | None = None
        self._connected = False

    async def connect(self) -> None:
        """Connect to Kafka cluster."""
        if self._connected:
            return

        # Initialize producer
        self._producer = ConfluentProducer(
            bootstrap_servers=self._bootstrap_servers,
            schema_registry_url=self._schema_registry_url,
            **self._extra_config,
        )
        await self._producer.start()

        # Initialize admin
        self._admin = ConfluentAdmin(
            bootstrap_servers=self._bootstrap_servers,
        )
        await self._admin.connect()

        self._connected = True
        logger.info(f"Connected to Kafka (confluent): {self._bootstrap_servers}")

    async def disconnect(self) -> None:
        """Disconnect from Kafka cluster."""
        if not self._connected:
            return

        # Stop all consumers
        for consumer in self._consumers.values():
            await consumer.stop()
        self._consumers.clear()

        # Stop producer
        if self._producer:
            await self._producer.stop()
            self._producer = None

        # Close admin
        if self._admin:
            await self._admin.close()
            self._admin = None

        self._connected = False
        logger.info("Disconnected from Kafka (confluent)")

    def is_connected(self) -> bool:
        """Check if connected to Kafka."""
        return self._connected

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
            topic: Topic name
            message: Message payload
            key: Optional message key
            headers: Optional headers
        """
        if not self._connected:
            await self.connect()

        await self._producer.send(topic, message, key, headers)

    async def subscribe(
        self,
        topics: list[str],
        group_id: str,
        handler: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """
        Subscribe to topics and process messages.

        Args:
            topics: List of topics
            group_id: Consumer group ID
            handler: Message handler function
        """
        if group_id in self._consumers:
            logger.warning(f"Consumer {group_id} already exists, stopping old one")
            await self._consumers[group_id].stop()

        consumer = ConfluentConsumer(
            group_id=group_id,
            topics=topics,
            message_handler=handler,
        )

        await consumer.start()
        self._consumers[group_id] = consumer

    async def unsubscribe(self, group_id: str) -> None:
        """
        Unsubscribe a consumer group.

        Args:
            group_id: Consumer group ID
        """
        if group_id in self._consumers:
            await self._consumers[group_id].stop()
            del self._consumers[group_id]

    async def create_topic(
        self,
        topic: str,
        partitions: int = 1,
        replication_factor: int = 1,
    ) -> None:
        """
        Create a topic.

        Args:
            topic: Topic name
            partitions: Number of partitions
            replication_factor: Replication factor
        """
        if not self._admin:
            self._admin = ConfluentAdmin(bootstrap_servers=self._bootstrap_servers)
            await self._admin.connect()

        await self._admin.create_topic(topic, partitions, replication_factor)

    async def delete_topic(self, topic: str) -> None:
        """
        Delete a topic.

        Args:
            topic: Topic name
        """
        if not self._admin:
            self._admin = ConfluentAdmin(bootstrap_servers=self._bootstrap_servers)
            await self._admin.connect()

        await self._admin.delete_topic(topic)

    async def list_topics(self) -> list[str]:
        """
        List all topics.

        Returns:
            List of topic names
        """
        if not self._admin:
            self._admin = ConfluentAdmin(bootstrap_servers=self._bootstrap_servers)
            await self._admin.connect()

        return await self._admin.list_topics()

    def get_producer(self) -> ConfluentProducer:
        """Get the producer instance."""
        if not self._producer:
            raise RuntimeError("Broker not connected. Call connect() first.")
        return self._producer

    def get_consumer(self, group_id: str) -> ConfluentConsumer | None:
        """Get a consumer by group ID."""
        return self._consumers.get(group_id)

    def get_admin(self) -> ConfluentAdmin:
        """Get the admin instance."""
        if not self._admin:
            raise RuntimeError("Broker not connected. Call connect() first.")
        return self._admin
