"""
Confluent Kafka admin client for topic management.

High-performance admin using confluent-kafka (librdkafka).
Provides topic creation, deletion, listing, and description.

Compatible with KafkaAdmin (aiokafka) — same interface.
"""

from __future__ import annotations

from typing import Any
from dataclasses import dataclass
import logging
import asyncio

from core.config import get_settings


logger = logging.getLogger(__name__)


@dataclass
class TopicInfo:
    """Information about a Kafka topic."""

    name: str
    partitions: int
    replication_factor: int
    configs: dict[str, str]


class ConfluentAdmin:
    """
    Confluent Kafka admin client for topic management.

    Uses confluent_kafka.admin.AdminClient (librdkafka) for high-performance
    topic management operations.

    Example:
        admin = ConfluentAdmin()
        await admin.connect()

        # Create topic
        await admin.create_topic("user-events", partitions=3)

        # List topics
        topics = await admin.list_topics()

        # Delete topic
        await admin.delete_topic("old-events")

        await admin.close()
    """

    def __init__(
        self,
        bootstrap_servers: str | None = None,
        **kwargs: Any,
    ):
        """
        Initialize Confluent admin client.

        Args:
            bootstrap_servers: Kafka servers (comma-separated)
            **kwargs: Additional admin client options
        """
        self._settings = get_settings()
        self._bootstrap_servers = bootstrap_servers or self._settings.kafka_bootstrap_servers
        self._extra_config = kwargs
        self._admin = None

    async def connect(self) -> None:
        """Connect to Kafka cluster."""
        try:
            from confluent_kafka.admin import AdminClient
        except ImportError:
            raise ImportError(
                "confluent-kafka is required for Confluent backend. "
                "Install with: pip install confluent-kafka"
            )

        config = {
            "bootstrap.servers": self._bootstrap_servers,
        }

        # Add security config if needed
        if self._settings.kafka_security_protocol != "PLAINTEXT":
            config["security.protocol"] = self._settings.kafka_security_protocol

            if self._settings.kafka_sasl_mechanism:
                config["sasl.mechanism"] = self._settings.kafka_sasl_mechanism
                config["sasl.username"] = self._settings.kafka_sasl_username
                config["sasl.password"] = self._settings.kafka_sasl_password

            if self._settings.kafka_ssl_cafile:
                config["ssl.ca.location"] = self._settings.kafka_ssl_cafile
            if self._settings.kafka_ssl_certfile:
                config["ssl.certificate.location"] = self._settings.kafka_ssl_certfile
            if self._settings.kafka_ssl_keyfile:
                config["ssl.key.location"] = self._settings.kafka_ssl_keyfile

        config.update(self._extra_config)

        self._admin = AdminClient(config)

    async def close(self) -> None:
        """Close connection to Kafka cluster."""
        # confluent_kafka AdminClient doesn't have an explicit close,
        # but we clear the reference for consistency.
        self._admin = None

    async def create_topic(
        self,
        name: str,
        partitions: int = 1,
        replication_factor: int = 1,
        configs: dict[str, str] | None = None,
    ) -> bool:
        """
        Create a new topic.

        Args:
            name: Topic name
            partitions: Number of partitions
            replication_factor: Replication factor
            configs: Optional topic configurations

        Returns:
            True if created, False if already exists
        """
        try:
            from confluent_kafka.admin import NewTopic
        except ImportError:
            raise ImportError(
                "confluent-kafka is required for Confluent backend. "
                "Install with: pip install confluent-kafka"
            )

        if not self._admin:
            await self.connect()

        topic = NewTopic(
            topic=name,
            num_partitions=partitions,
            replication_factor=replication_factor,
            config=configs or {},
        )

        # create_topics returns a dict of {topic_name: future}
        futures = self._admin.create_topics([topic])

        # Wait for the result in the event loop
        loop = asyncio.get_event_loop()

        for topic_name, future in futures.items():
            try:
                await loop.run_in_executor(None, future.result)
                logger.info(f"Created topic: {topic_name}")
                return True
            except Exception as e:
                if "TOPIC_ALREADY_EXISTS" in str(e) or "already exists" in str(e).lower():
                    logger.info(f"Topic already exists: {topic_name}")
                    return False
                raise

        return False

    async def delete_topic(self, name: str) -> bool:
        """
        Delete a topic.

        Args:
            name: Topic name

        Returns:
            True if deleted, False if not found
        """
        if not self._admin:
            await self.connect()

        futures = self._admin.delete_topics([name])

        loop = asyncio.get_event_loop()

        for topic_name, future in futures.items():
            try:
                await loop.run_in_executor(None, future.result)
                logger.info(f"Deleted topic: {topic_name}")
                return True
            except Exception as e:
                if "UNKNOWN_TOPIC_OR_PART" in str(e) or "not found" in str(e).lower():
                    logger.info(f"Topic not found: {topic_name}")
                    return False
                raise

        return False

    async def list_topics(self) -> list[str]:
        """
        List all topics.

        Returns:
            List of topic names (excluding internal topics)
        """
        if not self._admin:
            await self.connect()

        loop = asyncio.get_event_loop()

        try:
            # list_topics() is synchronous in confluent-kafka
            metadata = await loop.run_in_executor(
                None, lambda: self._admin.list_topics(timeout=10)
            )

            # Filter out internal topics (starting with __)
            return [
                name for name in metadata.topics.keys()
                if not name.startswith("__")
            ]
        except Exception as e:
            logger.error(f"Error listing topics: {e}")
            return []

    async def describe_topic(self, name: str) -> TopicInfo | None:
        """
        Get detailed information about a topic.

        Args:
            name: Topic name

        Returns:
            TopicInfo or None if not found
        """
        if not self._admin:
            await self.connect()

        loop = asyncio.get_event_loop()

        try:
            metadata = await loop.run_in_executor(
                None, lambda: self._admin.list_topics(topic=name, timeout=10)
            )

            topic_metadata = metadata.topics.get(name)
            if topic_metadata is None:
                return None

            if topic_metadata.error is not None:
                logger.error(f"Error describing topic {name}: {topic_metadata.error}")
                return None

            # Get partition count
            num_partitions = len(topic_metadata.partitions)

            # Get replication factor from first partition
            replication_factor = 1
            if topic_metadata.partitions:
                first_partition = list(topic_metadata.partitions.values())[0]
                replication_factor = len(first_partition.replicas)

            return TopicInfo(
                name=name,
                partitions=num_partitions,
                replication_factor=replication_factor,
                configs={},
            )
        except Exception as e:
            logger.error(f"Error describing topic {name}: {e}")
            return None

    async def ensure_topics(
        self,
        topics: list[dict[str, Any]],
    ) -> None:
        """
        Ensure topics exist, creating if necessary.

        Args:
            topics: List of topic configs
                [{"name": "events", "partitions": 3}, ...]
        """
        for topic_config in topics:
            name = topic_config["name"]
            partitions = topic_config.get("partitions", 1)
            replication = topic_config.get("replication_factor", 1)
            configs = topic_config.get("configs", {})

            await self.create_topic(
                name=name,
                partitions=partitions,
                replication_factor=replication,
                configs=configs,
            )
