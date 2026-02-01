"""
Redis Streams implementation for Core Framework messaging.

Provides RedisProducer, RedisConsumer, and RedisBroker
for lightweight message streaming using Redis Streams.

Requirements:
    pip install redis

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

__all__ = [
    "RedisBroker",
    "RedisProducer",
    "RedisConsumer",
]
