"""
DRF-style decorators for messaging.

Provides @event, @consumer, and @on_event decorators for
declarative event-driven architecture.
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Awaitable, TypeVar
import asyncio
import inspect

from core.messaging.base import Event, EventHandler
from core.messaging.registry import (
    register_consumer,
    register_event_handler,
    get_producer,
)
from core.config import get_settings


F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def event(
    event_name: str,
    topic: str | None = None,
    key_field: str | None = None,
    include_result: bool = True,
) -> Callable[[F], F]:
    """
    Decorator to emit an event after successful execution.
    
    Use on ViewSet actions or any async function to automatically
    emit an event when the function completes successfully.
    
    Args:
        event_name: Name of the event (e.g., "user.created")
        topic: Topic to publish to (uses default if None)
        key_field: Field from result to use as message key
        include_result: Whether to include function result in event data
    
    Example:
        class UserViewSet(ModelViewSet):
            @action(methods=["POST"], detail=False)
            @event("user.created", topic="user-events")
            async def register(self, request, db, **kwargs):
                user = await User.create_user(...)
                return UserOutput.model_validate(user).model_dump()
        
        # When register() succeeds, an event is emitted:
        # {
        #     "name": "user.created",
        #     "data": {"id": 1, "email": "user@example.com", ...},
        #     "timestamp": "2024-01-01T00:00:00Z",
        #     "source": "my-service"
        # }
    """
    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Execute the original function
            result = await func(*args, **kwargs)
            
            # Get settings
            settings = get_settings()
            
            if not settings.messaging_enabled:
                return result
            
            # Build event data
            event_data = {}
            if include_result and result is not None:
                if isinstance(result, dict):
                    event_data = result
                elif hasattr(result, "model_dump"):
                    event_data = result.model_dump()
                elif hasattr(result, "to_dict"):
                    event_data = result.to_dict()
                else:
                    event_data = {"result": result}
            
            # Create event
            evt = Event(
                name=event_name,
                data=event_data,
                source=settings.messaging_event_source,
            )
            
            # Determine message key
            msg_key = None
            if key_field and isinstance(event_data, dict):
                msg_key = str(event_data.get(key_field, ""))
            
            # Publish event (fire and forget)
            target_topic = topic or settings.messaging_default_topic
            
            try:
                producer = get_producer()
                asyncio.create_task(
                    producer.send_event(target_topic, evt, key=msg_key)
                )
            except Exception:
                # Don't fail the request if event publishing fails
                # TODO: Add logging
                pass
            
            return result
        
        # Mark function as event emitter
        wrapper._event_name = event_name  # type: ignore
        wrapper._event_topic = topic  # type: ignore
        
        return wrapper  # type: ignore
    
    return decorator


def consumer(
    group_id: str,
    topics: list[str] | None = None,
    auto_start: bool = True,
) -> Callable[[type], type]:
    """
    Decorator to mark a class as an event consumer.
    
    The decorated class should have methods decorated with @on_event
    to handle specific events.
    
    Args:
        group_id: Consumer group ID (for load balancing)
        topics: List of topics to subscribe to
        auto_start: Whether to auto-start when worker runs
    
    Example:
        @consumer("order-service", topics=["user-events", "payment-events"])
        class OrderEventsConsumer:
            
            @on_event("user.created")
            async def handle_user_created(self, event: Event, db):
                await Order.create_welcome_order(user_id=event.data["id"], db=db)
            
            @on_event("payment.completed")
            async def handle_payment_completed(self, event: Event, db):
                await Order.mark_paid(order_id=event.data["order_id"], db=db)
    """
    def decorator(cls: type) -> type:
        # Store metadata on class
        cls._group_id = group_id  # type: ignore
        cls._topics = topics or []  # type: ignore
        cls._auto_start = auto_start  # type: ignore
        cls._event_handlers = {}  # type: ignore
        
        # Find all @on_event decorated methods
        for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
            if hasattr(method, "_event_name"):
                event_name = method._event_name
                cls._event_handlers[event_name] = name  # type: ignore
                
                # Register global handler
                handler = EventHandler(
                    event_name=event_name,
                    handler=method,
                    consumer_class=cls,
                    method_name=name,
                )
                register_event_handler(handler)
        
        # Register consumer
        register_consumer(cls, group_id)
        
        return cls
    
    return decorator


def on_event(event_name: str) -> Callable[[F], F]:
    """
    Decorator to mark a method as an event handler.
    
    Use inside a @consumer decorated class to handle specific events.
    
    Args:
        event_name: Name of event to handle (e.g., "user.created")
    
    Example:
        @consumer("order-service", topics=["user-events"])
        class UserEventsConsumer:
            
            @on_event("user.created")
            async def handle_user_created(self, event: Event, db):
                '''Handle user creation event.'''
                user_id = event.data["id"]
                await Order.create_welcome_order(user_id=user_id, db=db)
            
            @on_event("user.deleted")
            async def handle_user_deleted(self, event: Event, db):
                '''Handle user deletion event.'''
                user_id = event.data["id"]
                await Order.cancel_pending_orders(user_id=user_id, db=db)
    """
    def decorator(func: F) -> F:
        # Mark function as event handler
        func._event_name = event_name  # type: ignore
        return func
    
    return decorator


def emit_event(
    event_name: str,
    data: dict[str, Any],
    topic: str | None = None,
    key: str | None = None,
) -> Callable[[], Awaitable[None]]:
    """
    Helper to emit an event programmatically.
    
    Returns an async function that can be awaited or scheduled.
    
    Args:
        event_name: Event name
        data: Event data
        topic: Topic to publish to
        key: Message key
    
    Example:
        # Emit immediately
        await emit_event("user.updated", {"id": 1, "email": "new@example.com"})()
        
        # Schedule for later
        asyncio.create_task(emit_event("cleanup.completed", {"count": 100})())
    """
    async def _emit() -> None:
        settings = get_settings()
        
        if not settings.messaging_enabled:
            return
        
        evt = Event(
            name=event_name,
            data=data,
            source=settings.messaging_event_source,
        )
        
        target_topic = topic or settings.messaging_default_topic
        
        try:
            producer = get_producer()
            await producer.send_event(target_topic, evt, key=key)
        except Exception:
            # TODO: Add logging
            pass
    
    return _emit


async def publish_event(
    event_name: str,
    data: dict[str, Any],
    topic: str | None = None,
    key: str | None = None,
) -> None:
    """
    Publish an event immediately.
    
    Convenience function for emitting events outside of decorators.
    
    Args:
        event_name: Event name
        data: Event data
        topic: Topic to publish to
        key: Message key
    
    Example:
        await publish_event("user.updated", {"id": 1, "email": "new@example.com"})
    """
    await emit_event(event_name, data, topic, key)()
