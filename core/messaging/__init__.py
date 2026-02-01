"""
Core Framework - Enterprise Messaging System.

Plug-and-play messaging for scaling applications to enterprise level.
Supports Kafka, Redis Streams, and RabbitMQ.

Usage:
    from core.messaging import event, consumer, on_event, producer
    
    # Emit event after action
    @action(methods=["POST"], detail=False)
    @event("user.created", topic="user-events")
    async def register(self, request, db, **kwargs):
        user = await User.create_user(...)
        return UserOutput.model_validate(user).model_dump()
    
    # Consume events
    @consumer("order-service", topics=["user-events"])
    class UserEventsConsumer:
        @on_event("user.created")
        async def handle_user_created(self, event, db):
            await Order.create_welcome_order(user_id=event["user_id"], db=db)
    
    # Manual producer
    await producer.send("user-events", {"event": "user.created", "data": {...}})
"""

from core.messaging.base import (
    MessageBroker,
    Producer,
    Consumer,
    Event,
    EventHandler,
)
from core.messaging.config import (
    MessagingSettings,
    get_messaging_settings,
    configure_messaging,
)
from core.messaging.decorators import (
    event,
    consumer,
    on_event,
)
from core.messaging.registry import (
    get_broker,
    get_producer,
    register_broker,
    register_consumer,
    get_consumers,
)

__all__ = [
    # Base classes
    "MessageBroker",
    "Producer",
    "Consumer",
    "Event",
    "EventHandler",
    # Config
    "MessagingSettings",
    "get_messaging_settings",
    "configure_messaging",
    # Decorators
    "event",
    "consumer",
    "on_event",
    # Registry
    "get_broker",
    "get_producer",
    "register_broker",
    "register_consumer",
    "get_consumers",
]
