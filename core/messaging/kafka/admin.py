"""
Kafka admin client for topic and consumer group management.

Provides topic creation, deletion, listing, and consumer group monitoring.
Uses aiokafka for async Kafka operations.
"""

from __future__ import annotations

from typing import Any
from dataclasses import dataclass, field
import logging

from core.config import get_settings


logger = logging.getLogger(__name__)


# ─── Dataclasses ─────────────────────────────────────────────────


@dataclass
class TopicInfo:
    """Information about a Kafka topic."""
    
    name: str
    partitions: int
    replication_factor: int
    configs: dict[str, str]


@dataclass
class BrokerInfo:
    """Information about a Kafka broker."""
    
    id: int
    host: str
    port: int
    rack: str | None = None


@dataclass
class PartitionInfo:
    """Information about a topic partition."""
    
    partition: int
    leader: int
    replicas: list[int] = field(default_factory=list)
    isr: list[int] = field(default_factory=list)


@dataclass
class PartitionOffset:
    """Offset information for a partition."""
    
    topic: str
    partition: int
    current_offset: int
    end_offset: int
    lag: int


@dataclass
class MemberInfo:
    """Information about a consumer group member."""
    
    member_id: str
    client_id: str
    host: str
    partitions: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ConsumerGroupInfo:
    """Basic information about a consumer group."""
    
    group_id: str
    state: str  # Stable, Empty, Rebalancing, Dead, PreparingRebalance, CompletingRebalance
    members_count: int
    topics: list[str] = field(default_factory=list)


@dataclass
class ConsumerGroupDetail:
    """Detailed information about a consumer group."""
    
    group_id: str
    state: str
    coordinator: int
    protocol_type: str
    protocol: str
    members: list[MemberInfo] = field(default_factory=list)
    offsets: dict[str, list[PartitionOffset]] = field(default_factory=dict)
    total_lag: int = 0


@dataclass
class ClusterInfo:
    """Information about the Kafka cluster."""
    
    cluster_id: str | None
    brokers: list[BrokerInfo] = field(default_factory=list)
    controller_id: int = -1
    topics_count: int = 0
    partitions_count: int = 0


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

    # ─── Consumer Group Methods ─────────────────────────────────────

    async def list_consumer_groups(self) -> list[ConsumerGroupInfo]:
        """
        List all consumer groups with basic information.
        
        Returns:
            List of ConsumerGroupInfo with group_id, state, members_count, topics
        """
        if not self._admin:
            await self.connect()
        
        try:
            # aiokafka doesn't have direct consumer group listing,
            # we need to use the admin client's describe_consumer_groups
            # First, list groups using a workaround
            groups_result = await self._admin.list_consumer_groups()
            
            result = []
            for group in groups_result:
                # Get basic info - group is a tuple (group_id, protocol_type)
                group_id = group[0] if isinstance(group, tuple) else group
                
                result.append(ConsumerGroupInfo(
                    group_id=group_id,
                    state="Unknown",  # Will be filled by describe
                    members_count=0,
                    topics=[],
                ))
            
            # Describe groups to get more details
            if result:
                group_ids = [g.group_id for g in result]
                try:
                    descriptions = await self._admin.describe_consumer_groups(group_ids)
                    for desc in descriptions:
                        for group_info in result:
                            if group_info.group_id == desc.group_id:
                                group_info.state = desc.state
                                group_info.members_count = len(desc.members)
                                # Extract topics from member assignments
                                topics = set()
                                for member in desc.members:
                                    if member.assignment:
                                        for tp in member.assignment:
                                            topics.add(tp.topic)
                                group_info.topics = list(topics)
                                break
                except Exception as e:
                    logger.warning(f"Error describing consumer groups: {e}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error listing consumer groups: {e}")
            return []

    async def describe_consumer_group(self, group_id: str) -> ConsumerGroupDetail | None:
        """
        Get detailed information about a consumer group.
        
        Args:
            group_id: Consumer group ID
            
        Returns:
            ConsumerGroupDetail with members, offsets, and lag information
        """
        if not self._admin:
            await self.connect()
        
        try:
            descriptions = await self._admin.describe_consumer_groups([group_id])
            
            if not descriptions:
                return None
            
            desc = descriptions[0]
            
            # Build member info
            members = []
            topics = set()
            for member in desc.members:
                partitions = []
                if member.assignment:
                    for tp in member.assignment:
                        topics.add(tp.topic)
                        partitions.append({
                            "topic": tp.topic,
                            "partition": tp.partition,
                        })
                
                members.append(MemberInfo(
                    member_id=member.member_id,
                    client_id=member.client_id,
                    host=member.host or "",
                    partitions=partitions,
                ))
            
            # Get offsets for this group
            offsets = await self.get_consumer_group_offsets(group_id, list(topics))
            
            # Calculate total lag
            total_lag = sum(
                po.lag for topic_offsets in offsets.values() for po in topic_offsets
            )
            
            return ConsumerGroupDetail(
                group_id=desc.group_id,
                state=desc.state,
                coordinator=desc.coordinator.node_id if desc.coordinator else -1,
                protocol_type=desc.protocol_type or "",
                protocol=desc.protocol or "",
                members=members,
                offsets=offsets,
                total_lag=total_lag,
            )
            
        except Exception as e:
            logger.error(f"Error describing consumer group {group_id}: {e}")
            return None

    async def get_consumer_group_offsets(
        self,
        group_id: str,
        topics: list[str] | None = None,
    ) -> dict[str, list[PartitionOffset]]:
        """
        Get committed offsets for a consumer group with lag calculation.
        
        Args:
            group_id: Consumer group ID
            topics: Optional list of topics to filter (if None, gets all)
            
        Returns:
            Dict mapping topic names to list of PartitionOffset
        """
        if not self._admin:
            await self.connect()
        
        result: dict[str, list[PartitionOffset]] = {}
        
        try:
            from aiokafka import AIOKafkaConsumer, TopicPartition
            
            # Get committed offsets
            offsets_response = await self._admin.list_consumer_group_offsets(group_id)
            
            if not offsets_response:
                return result
            
            # Create a temporary consumer to get end offsets
            consumer = AIOKafkaConsumer(
                bootstrap_servers=self._bootstrap_servers,
            )
            await consumer.start()
            
            try:
                # Group offsets by topic
                topic_partitions: dict[str, list[int]] = {}
                committed_offsets: dict[str, dict[int, int]] = {}
                
                for tp, offset_meta in offsets_response.items():
                    topic = tp.topic
                    partition = tp.partition
                    
                    if topics and topic not in topics:
                        continue
                    
                    if topic not in topic_partitions:
                        topic_partitions[topic] = []
                        committed_offsets[topic] = {}
                    
                    topic_partitions[topic].append(partition)
                    committed_offsets[topic][partition] = offset_meta.offset
                
                # Get end offsets for each topic
                for topic, partitions in topic_partitions.items():
                    tps = [TopicPartition(topic, p) for p in partitions]
                    end_offsets = await consumer.end_offsets(tps)
                    
                    partition_offsets = []
                    for tp in tps:
                        current = committed_offsets[topic].get(tp.partition, 0)
                        end = end_offsets.get(tp, 0)
                        lag = max(0, end - current)
                        
                        partition_offsets.append(PartitionOffset(
                            topic=topic,
                            partition=tp.partition,
                            current_offset=current,
                            end_offset=end,
                            lag=lag,
                        ))
                    
                    result[topic] = partition_offsets
                    
            finally:
                await consumer.stop()
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting consumer group offsets for {group_id}: {e}")
            return result

    async def get_cluster_info(self) -> ClusterInfo:
        """
        Get information about the Kafka cluster.
        
        Returns:
            ClusterInfo with brokers, controller, topics, and partitions count
        """
        if not self._admin:
            await self.connect()
        
        try:
            from aiokafka import AIOKafkaConsumer
            
            # Use a consumer to get cluster metadata
            consumer = AIOKafkaConsumer(
                bootstrap_servers=self._bootstrap_servers,
            )
            await consumer.start()
            
            try:
                # Get cluster metadata
                cluster = consumer._client.cluster
                
                brokers = []
                for node in cluster.brokers():
                    brokers.append(BrokerInfo(
                        id=node.nodeId,
                        host=node.host,
                        port=node.port,
                        rack=node.rack,
                    ))
                
                # Count topics and partitions
                topics = await consumer.topics()
                topics_count = len([t for t in topics if not t.startswith("__")])
                
                partitions_count = 0
                for topic in topics:
                    if not topic.startswith("__"):
                        parts = consumer.partitions_for_topic(topic)
                        if parts:
                            partitions_count += len(parts)
                
                return ClusterInfo(
                    cluster_id=cluster.cluster_id(),
                    brokers=brokers,
                    controller_id=cluster.controller_id() or -1,
                    topics_count=topics_count,
                    partitions_count=partitions_count,
                )
                
            finally:
                await consumer.stop()
                
        except Exception as e:
            logger.error(f"Error getting cluster info: {e}")
            return ClusterInfo(cluster_id=None)

    async def describe_topic_partitions(self, name: str) -> list[PartitionInfo]:
        """
        Get detailed partition information for a topic.
        
        Args:
            name: Topic name
            
        Returns:
            List of PartitionInfo with leader, replicas, and ISR
        """
        if not self._admin:
            await self.connect()
        
        try:
            from aiokafka import AIOKafkaConsumer
            
            consumer = AIOKafkaConsumer(
                bootstrap_servers=self._bootstrap_servers,
            )
            await consumer.start()
            
            try:
                partitions = consumer.partitions_for_topic(name)
                if not partitions:
                    return []
                
                result = []
                cluster = consumer._client.cluster
                
                for partition_id in partitions:
                    partition_meta = cluster.partition_for_topic(name, partition_id)
                    if partition_meta:
                        result.append(PartitionInfo(
                            partition=partition_id,
                            leader=partition_meta.leader,
                            replicas=list(partition_meta.replicas),
                            isr=list(partition_meta.isr),
                        ))
                    else:
                        result.append(PartitionInfo(
                            partition=partition_id,
                            leader=-1,
                            replicas=[],
                            isr=[],
                        ))
                
                return result
                
            finally:
                await consumer.stop()
                
        except Exception as e:
            logger.error(f"Error describing topic partitions for {name}: {e}")
            return []
