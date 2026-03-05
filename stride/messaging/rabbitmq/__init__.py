"""
RabbitMQ implementation for Stride messaging.

Provides RabbitMQProducer, RabbitMQConsumer, and RabbitMQBroker
for traditional message queue patterns.

Requirements:
    pip install aio-pika

Usage:
    from stride.messaging.rabbitmq import RabbitMQBroker, RabbitMQProducer
    
    broker = RabbitMQBroker()
    await broker.connect()
    await broker.publish("user-events", {"event": "user.created"})
"""

from stride.messaging.rabbitmq.producer import RabbitMQProducer
from stride.messaging.rabbitmq.consumer import RabbitMQConsumer
from stride.messaging.rabbitmq.broker import RabbitMQBroker

__all__ = [
    "RabbitMQBroker",
    "RabbitMQProducer",
    "RabbitMQConsumer",
]
