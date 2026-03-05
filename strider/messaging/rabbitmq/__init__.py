"""
RabbitMQ implementation for Stride messaging.

Provides RabbitMQProducer, RabbitMQConsumer, and RabbitMQBroker
for traditional message queue patterns.

Requirements:
    pip install aio-pika

Usage:
    from strider.messaging.rabbitmq import RabbitMQBroker, RabbitMQProducer
    
    broker = RabbitMQBroker()
    await broker.connect()
    await broker.publish("user-events", {"event": "user.created"})
"""

from strider.messaging.rabbitmq.producer import RabbitMQProducer
from strider.messaging.rabbitmq.consumer import RabbitMQConsumer
from strider.messaging.rabbitmq.broker import RabbitMQBroker

__all__ = [
    "RabbitMQBroker",
    "RabbitMQProducer",
    "RabbitMQConsumer",
]
