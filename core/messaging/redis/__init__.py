"""
Redis Streams implementation for Core Framework messaging.

Provides RedisProducer, RedisConsumer, and RedisBroker
for lightweight message streaming using Redis Streams.

Supports three connection modes (configured via settings):
- standalone: Single Redis instance (default)
- cluster: Redis Cluster with multiple nodes
- sentinel: Redis Sentinel for high availability

Requirements:
    pip install redis

Configuration:
    # src/settings.py
    class AppSettings(Settings):
        # Standalone
        redis_url: str = "redis://localhost:6379/0"
        redis_mode: str = "standalone"
        
        # Cluster
        redis_url: str = "redis://node1:6379,node2:6379,node3:6379"
        redis_mode: str = "cluster"
        
        # Sentinel
        redis_url: str = "redis://sentinel1:26379,sentinel2:26379"
        redis_mode: str = "sentinel"
        redis_sentinel_master: str = "mymaster"

Usage:
    from core.messaging.redis import RedisBroker, RedisProducer, RedisConsumer
    
    # Configure broker
    broker = RedisBroker()
    await broker.connect()
    
    # Produce messages
    producer = RedisProducer()
    await producer.start()
    await producer.send("user-events", {"event": "user.created", "data": {...}})
"""

from core.messaging.redis.producer import RedisProducer
from core.messaging.redis.consumer import RedisConsumer
from core.messaging.redis.broker import RedisBroker
from core.messaging.redis.connection import (
    create_redis_client,
    parse_redis_hosts,
    get_redis_info,
)

__all__ = [
    "RedisBroker",
    "RedisProducer",
    "RedisConsumer",
    "create_redis_client",
    "parse_redis_hosts",
    "get_redis_info",
]
