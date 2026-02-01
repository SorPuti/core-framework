"""
RabbitMQ implementation for Core Framework messaging.

Provides RabbitMQProducer, RabbitMQConsumer, and RabbitMQBroker
for traditional message queue patterns.

Requirements:
    pip install aio-pika

Usage:
    from core.messaging.rabbitmq import RabbitMQBroker, RabbitMQProducer
    
    broker = RabbitMQBroker()
    await broker.connect()
    await broker.publish("user-events", {"event": "user.created"})
"""

from core.messaging.rabbitmq.producer import RabbitMQProducer
from core.messaging.rabbitmq.consumer import RabbitMQConsumer
from core.messaging.rabbitmq.broker import RabbitMQBroker

__all__ = [
    "RabbitMQBroker",
    "RabbitMQProducer",
    "RabbitMQConsumer",
]
