"""
Confluent Kafka admin client for topic and consumer group management.

High-performance admin using confluent-kafka (librdkafka).
Provides topic creation, deletion, listing, description, and consumer group monitoring.

Compatible with KafkaAdmin (aiokafka) — same interface.
"""

from __future__ import annotations

from typing import Any
from dataclasses import dataclass, field
import logging
import asyncio

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
        List all topics (names only).

        Returns:
            List of topic names (excluding internal topics)
        """
        topics_info = await self.list_topics_with_info()
        return [t.name for t in topics_info]
    
    async def list_topics_with_info(self) -> list[TopicInfo]:
        """
        List all topics with partition info.

        Returns:
            List of TopicInfo
        """
        if not self._admin:
            await self.connect()

        loop = asyncio.get_event_loop()

        metadata = await loop.run_in_executor(
            None, lambda: self._admin.list_topics(timeout=10)
        )

        result = []
        for name, topic_meta in metadata.topics.items():
            if name.startswith("__"):
                continue
            
            # Get replication factor from first partition
            replication_factor = 1
            if topic_meta.partitions:
                first_partition = list(topic_meta.partitions.values())[0]
                replication_factor = len(first_partition.replicas)
            
            result.append(TopicInfo(
                name=name,
                partitions=len(topic_meta.partitions),
                replication_factor=replication_factor,
                configs={},
            ))
        
        return result

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

    # ─── Consumer Group Methods ─────────────────────────────────────

    async def list_consumer_groups(self) -> list[ConsumerGroupInfo]:
        """
        List all consumer groups with basic information.
        
        Returns:
            List of ConsumerGroupInfo with group_id, state, members_count, topics
        """
        if not self._admin:
            await self.connect()
        
        loop = asyncio.get_event_loop()
        
        try:
            from confluent_kafka import Consumer
            
            # Use a consumer to list groups (more compatible across versions)
            consumer_config = {
                "bootstrap.servers": self._bootstrap_servers,
                "group.id": "admin-list-groups-temp",
            }
            
            if self._settings.kafka_security_protocol != "PLAINTEXT":
                consumer_config["security.protocol"] = self._settings.kafka_security_protocol
                if self._settings.kafka_sasl_mechanism:
                    consumer_config["sasl.mechanism"] = self._settings.kafka_sasl_mechanism
                    consumer_config["sasl.username"] = self._settings.kafka_sasl_username
                    consumer_config["sasl.password"] = self._settings.kafka_sasl_password
            
            consumer = Consumer(consumer_config)
            
            try:
                # list_groups() returns a ListGroupsResponse
                groups_response = await loop.run_in_executor(
                    None, lambda: consumer.list_groups(timeout=10)
                )
                
                result = []
                for group in groups_response:
                    group_id = group.group if hasattr(group, 'group') else str(group)
                    state = getattr(group, 'state', 'Unknown')
                    members = getattr(group, 'members', [])
                    
                    result.append(ConsumerGroupInfo(
                        group_id=group_id,
                        state=str(state) if state else "Unknown",
                        members_count=len(members) if members else 0,
                        topics=[],
                    ))
                
                return result
            finally:
                consumer.close()
            
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
        
        loop = asyncio.get_event_loop()
        
        try:
            from confluent_kafka import Consumer
            
            # Use consumer.list_groups to get group details
            consumer_config = {
                "bootstrap.servers": self._bootstrap_servers,
                "group.id": "admin-describe-group-temp",
            }
            
            if self._settings.kafka_security_protocol != "PLAINTEXT":
                consumer_config["security.protocol"] = self._settings.kafka_security_protocol
                if self._settings.kafka_sasl_mechanism:
                    consumer_config["sasl.mechanism"] = self._settings.kafka_sasl_mechanism
                    consumer_config["sasl.username"] = self._settings.kafka_sasl_username
                    consumer_config["sasl.password"] = self._settings.kafka_sasl_password
            
            consumer = Consumer(consumer_config)
            
            try:
                groups_response = await loop.run_in_executor(
                    None, lambda: consumer.list_groups(group=group_id, timeout=10)
                )
                
                if not groups_response:
                    return None
                
                group = groups_response[0]
                group_members = getattr(group, 'members', []) or []
                
                # Build member info
                members = []
                topics = set()
                
                for member in group_members:
                    member_id = getattr(member, 'id', '') or getattr(member, 'member_id', '') or ''
                    client_id = getattr(member, 'client_id', '') or ''
                    host = getattr(member, 'client_host', '') or getattr(member, 'host', '') or ''
                    
                    # Try to get assignment
                    partitions = []
                    assignment = getattr(member, 'assignment', None)
                    if assignment:
                        for tp in assignment:
                            topic = getattr(tp, 'topic', None)
                            partition = getattr(tp, 'partition', None)
                            if topic:
                                topics.add(topic)
                                partitions.append({"topic": topic, "partition": partition})
                    
                    members.append(MemberInfo(
                        member_id=member_id,
                        client_id=client_id,
                        host=host,
                        partitions=partitions,
                    ))
                
                # Get offsets for this group
                offsets: dict[str, list[PartitionOffset]] = {}
                total_lag = 0
                
                if topics:
                    try:
                        offsets = await self.get_consumer_group_offsets(group_id, list(topics))
                        total_lag = sum(
                            po.lag for topic_offsets in offsets.values() for po in topic_offsets
                        )
                    except Exception as e:
                        logger.warning(f"Could not get offsets for {group_id}: {e}")
                
                state = getattr(group, 'state', 'Unknown')
                
                return ConsumerGroupDetail(
                    group_id=group_id,
                    state=str(state) if state else "Unknown",
                    coordinator=-1,
                    protocol_type=getattr(group, 'protocol_type', '') or '',
                    protocol=getattr(group, 'protocol', '') or '',
                    members=members,
                    offsets=offsets,
                    total_lag=total_lag,
                )
            finally:
                consumer.close()
                
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
        
        loop = asyncio.get_event_loop()
        result: dict[str, list[PartitionOffset]] = {}
        
        try:
            from confluent_kafka import TopicPartition, Consumer
            
            # List committed offsets for the group
            futures = self._admin.list_consumer_group_offsets([group_id])
            offsets_future = futures.get(group_id)
            
            if not offsets_future:
                return result
            
            offsets_result = await loop.run_in_executor(None, offsets_future.result)
            
            if not offsets_result.topic_partitions:
                return result
            
            # Group by topic
            topic_partitions: dict[str, list[TopicPartition]] = {}
            committed_offsets: dict[str, dict[int, int]] = {}
            
            for tp in offsets_result.topic_partitions:
                topic = tp.topic
                
                if topics and topic not in topics:
                    continue
                
                if topic not in topic_partitions:
                    topic_partitions[topic] = []
                    committed_offsets[topic] = {}
                
                topic_partitions[topic].append(tp)
                committed_offsets[topic][tp.partition] = tp.offset
            
            # Create a consumer to get end offsets
            consumer_config = {
                "bootstrap.servers": self._bootstrap_servers,
                "group.id": f"admin-offset-check-{group_id}",
                "enable.auto.commit": False,
            }
            
            if self._settings.kafka_security_protocol != "PLAINTEXT":
                consumer_config["security.protocol"] = self._settings.kafka_security_protocol
                if self._settings.kafka_sasl_mechanism:
                    consumer_config["sasl.mechanism"] = self._settings.kafka_sasl_mechanism
                    consumer_config["sasl.username"] = self._settings.kafka_sasl_username
                    consumer_config["sasl.password"] = self._settings.kafka_sasl_password
            
            consumer = Consumer(consumer_config)
            
            try:
                for topic, tps in topic_partitions.items():
                    # Get watermark offsets (low, high) for each partition
                    partition_offsets = []
                    
                    for tp in tps:
                        try:
                            low, high = consumer.get_watermark_offsets(tp, timeout=5.0)
                            current = committed_offsets[topic].get(tp.partition, 0)
                            lag = max(0, high - current)
                            
                            partition_offsets.append(PartitionOffset(
                                topic=topic,
                                partition=tp.partition,
                                current_offset=current,
                                end_offset=high,
                                lag=lag,
                            ))
                        except Exception as e:
                            logger.warning(f"Error getting watermarks for {tp}: {e}")
                            partition_offsets.append(PartitionOffset(
                                topic=topic,
                                partition=tp.partition,
                                current_offset=committed_offsets[topic].get(tp.partition, 0),
                                end_offset=0,
                                lag=0,
                            ))
                    
                    result[topic] = partition_offsets
                    
            finally:
                consumer.close()
            
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
        
        loop = asyncio.get_event_loop()
        
        try:
            # Get cluster metadata
            metadata = await loop.run_in_executor(
                None, lambda: self._admin.list_topics(timeout=10)
            )
            
            brokers = []
            for broker_id, broker in metadata.brokers.items():
                brokers.append(BrokerInfo(
                    id=broker_id,
                    host=broker.host,
                    port=broker.port,
                    rack=None,  # Not available in basic metadata
                ))
            
            # Count topics and partitions (excluding internal)
            topics_count = 0
            partitions_count = 0
            
            for topic_name, topic_meta in metadata.topics.items():
                if not topic_name.startswith("__"):
                    topics_count += 1
                    partitions_count += len(topic_meta.partitions)
            
            # ClusterMetadata attributes vary by confluent-kafka version
            # Use getattr with defaults for maximum compatibility
            cluster_id = getattr(metadata, 'cluster_id', None)
            if cluster_id is None:
                orig_broker = getattr(metadata, 'orig_broker_id', None)
                if orig_broker is not None:
                    cluster_id = f"cluster-{orig_broker}"
                else:
                    cluster_id = "unknown"
            
            controller_id = getattr(metadata, 'controller_id', None) or -1
            
            return ClusterInfo(
                cluster_id=cluster_id,
                brokers=brokers,
                controller_id=controller_id,
                topics_count=topics_count,
                partitions_count=partitions_count,
            )
            
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
        
        loop = asyncio.get_event_loop()
        
        try:
            metadata = await loop.run_in_executor(
                None, lambda: self._admin.list_topics(topic=name, timeout=10)
            )
            
            topic_meta = metadata.topics.get(name)
            if not topic_meta:
                return []
            
            result = []
            for partition_id, partition_meta in topic_meta.partitions.items():
                result.append(PartitionInfo(
                    partition=partition_id,
                    leader=partition_meta.leader,
                    replicas=list(partition_meta.replicas),
                    isr=list(partition_meta.isrs),
                ))
            
            return result
            
        except Exception as e:
            logger.error(f"Error describing topic partitions for {name}: {e}")
            return []
