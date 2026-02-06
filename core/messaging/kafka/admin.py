"""
Kafka admin client for topic management.

Provides topic creation, deletion, and listing functionality.
"""

from __future__ import annotations

from typing import Any
from dataclasses import dataclass
import logging

from core.config import get_settings


logger = logging.getLogger(__name__)


@dataclass
class TopicInfo:
    """Information about a Kafka topic."""
    
    name: str
    partitions: int
    replication_factor: int
    configs: dict[str, str]


class KafkaAdmin:
    """
    Kafka admin client for topic management.
    
    Example:
        admin = KafkaAdmin()
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
        Initialize Kafka admin client.
        
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
            from aiokafka.admin import AIOKafkaAdminClient
        except ImportError:
            raise ImportError(
                "aiokafka is required for Kafka support. "
                "Install with: pip install aiokafka"
            )
        
        config = {
            "bootstrap_servers": self._bootstrap_servers,
        }
        
        # Add security config if needed
        if self._settings.kafka_security_protocol != "PLAINTEXT":
            config["security_protocol"] = self._settings.kafka_security_protocol
            
            if self._settings.kafka_sasl_mechanism:
                config["sasl_mechanism"] = self._settings.kafka_sasl_mechanism
                config["sasl_plain_username"] = self._settings.kafka_sasl_username
                config["sasl_plain_password"] = self._settings.kafka_sasl_password
        
        config.update(self._extra_config)
        
        self._admin = AIOKafkaAdminClient(**config)
        await self._admin.start()
    
    async def close(self) -> None:
        """Close connection to Kafka cluster."""
        if self._admin:
            await self._admin.close()
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
            from aiokafka.admin import NewTopic
        except ImportError:
            raise ImportError(
                "aiokafka is required for Kafka support. "
                "Install with: pip install aiokafka"
            )
        
        if not self._admin:
            await self.connect()
        
        topic = NewTopic(
            name=name,
            num_partitions=partitions,
            replication_factor=replication_factor,
            topic_configs=configs or {},
        )
        
        try:
            await self._admin.create_topics([topic])
            logger.info(f"Created topic: {name}")
            return True
        except Exception as e:
            if "TopicExistsException" in str(type(e).__name__) or "already exists" in str(e).lower():
                logger.info(f"Topic already exists: {name}")
                return False
            raise
    
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
        
        try:
            await self._admin.delete_topics([name])
            logger.info(f"Deleted topic: {name}")
            return True
        except Exception as e:
            if "UnknownTopicOrPartitionError" in str(type(e).__name__):
                logger.info(f"Topic not found: {name}")
                return False
            raise
    
    async def list_topics(self) -> list[str]:
        """
        List all topics.
        
        Returns:
            List of topic names
        """
        if not self._admin:
            await self.connect()
        
        # Use describe_cluster to get metadata
        try:
            from aiokafka import AIOKafkaConsumer
            
            # Temporary consumer to get metadata
            consumer = AIOKafkaConsumer(
                bootstrap_servers=self._bootstrap_servers,
            )
            await consumer.start()
            topics = list(await consumer.topics())
            await consumer.stop()
            
            # Filter internal topics
            return [t for t in topics if not t.startswith("__")]
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
        
        try:
            from aiokafka import AIOKafkaConsumer
            
            consumer = AIOKafkaConsumer(
                bootstrap_servers=self._bootstrap_servers,
            )
            await consumer.start()
            
            partitions = consumer.partitions_for_topic(name)
            await consumer.stop()
            
            if partitions is None:
                return None
            
            return TopicInfo(
                name=name,
                partitions=len(partitions),
                replication_factor=1,  # Would need describe_configs for accurate value
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
