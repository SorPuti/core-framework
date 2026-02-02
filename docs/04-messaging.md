# Messaging

Async messaging with Kafka, RabbitMQ, or Redis.

## Configuration

```python
# src/main.py
from core.messaging import configure_messaging

configure_messaging(
    broker="kafka",  # kafka, rabbitmq, redis
    bootstrap_servers="localhost:9092",
)
```

Environment variables:

```env
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
# or
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
# or
REDIS_URL=redis://localhost:6379/0
```

## @event Decorator (Auto-Publish)

Emit events automatically after ViewSet actions succeed.

```python
from core import ModelViewSet, action
from core.messaging import event

class UserViewSet(ModelViewSet):
    model = User
    
    @action(methods=["POST"], detail=False)
    @event("user.created", topic="user-events", key_field="id")
    async def register(self, request, db, **kwargs):
        """POST /users/register - auto-publishes event on success."""
        body = await request.json()
        user = await User.create_user(
            email=body["email"],
            password=body["password"],
            db=db,
        )
        return {"id": user.id, "email": user.email}
```

When `register()` succeeds, event is published automatically:

```json
{
  "name": "user.created",
  "data": {"id": 1, "email": "user@example.com"},
  "timestamp": "2026-02-01T12:00:00Z",
  "source": "my-service"
}
```

### @event Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| event_name | str | Event name (e.g., "user.created") |
| topic | str | Target topic (uses default if None) |
| key_field | str | Field from result to use as message key |
| include_result | bool | Include function result in event data |

## Manual Producer

For cases where you need more control.

```python
from core.messaging import get_producer

async def send_order_created(order_id: int, user_id: int):
    producer = get_producer()
    await producer.send(
        topic="orders.created",
        message={
            "order_id": order_id,
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )
```

## publish_event Helper

Direct event publishing without decorator.

```python
from core.messaging import publish_event

async def notify_user_updated(user_id: int, email: str):
    await publish_event(
        event_name="user.updated",
        data={"id": user_id, "email": email},
        topic="user-events",
    )
```

## @consumer + @on_event (Class-Based)

Group related event handlers in a class.

```python
from core.messaging import consumer, on_event
from core.messaging.base import Event

@consumer("order-service", topics=["user-events", "payment-events"])
class OrderEventsConsumer:
    
    @on_event("user.created")
    async def handle_user_created(self, event: Event, db):
        """Create welcome order for new user."""
        await Order.create_welcome_order(
            user_id=event.data["id"],
            db=db,
        )
    
    @on_event("payment.completed")
    async def handle_payment_completed(self, event: Event, db):
        """Mark order as paid."""
        await Order.mark_paid(
            order_id=event.data["order_id"],
            db=db,
        )
```

### @consumer Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| group_id | str | Consumer group ID (for load balancing) |
| topics | list[str] | Topics to subscribe to |
| auto_start | bool | Auto-start when worker runs |

## @message_handler (Function-Based)

Simpler approach for single handlers.

```python
from core.messaging import message_handler

@message_handler(topic="orders.created")
async def handle_order_created(message: dict, db):
    """Process new order."""
    order_id = message["order_id"]
    
    await send_email(
        to=message["user_email"],
        subject="Order Confirmed",
        body=f"Order #{order_id} received.",
    )
```

## Handler with Retry

```python
@message_handler(
    topic="payments.process",
    max_retries=3,
    retry_delay=5,  # seconds
)
async def process_payment(message: dict, db):
    """Process payment with retry on failure."""
    result = await payment_gateway.charge(
        amount=message["amount"],
        card_token=message["card_token"],
    )
    
    if not result.success:
        raise Exception("Payment failed")  # Will retry
```

## Multiple Topics

```python
@message_handler(topic=["orders.created", "orders.updated"])
async def sync_inventory(message: dict, db):
    """Handle multiple order events."""
    pass
```

## Run Consumer

```bash
# Single consumer
core consumer --topic orders.created

# Multiple topics
core consumer --topic orders.created --topic orders.updated

# All registered handlers
core consumer
```

## Complete ViewSet Example

Using `@event` for auto-publish (recommended):

```python
from core import ModelViewSet, action
from core.messaging import event

class OrderViewSet(ModelViewSet):
    model = Order
    
    @event("order.created", topic="order-events", key_field="id")
    async def perform_create(self, data: dict, db) -> Order:
        """Auto-publishes order.created after save."""
        order = await super().perform_create(data, db)
        return order
    
    @action(methods=["POST"], detail=True)
    @event("order.completed", topic="order-events", key_field="id")
    async def complete(self, request, db, **kwargs):
        """POST /orders/{id}/complete - auto-publishes on success."""
        order = await self.get_object(db, **kwargs)
        order.status = "completed"
        await order.save(db)
        return {"id": order.id, "status": order.status}
```

Using manual producer (more control):

```python
from core import ModelViewSet
from core.messaging import get_producer

class OrderViewSet(ModelViewSet):
    model = Order
    
    async def perform_create(self, data: dict, db) -> Order:
        order = await super().perform_create(data, db)
        
        # Manual publish with custom data
        producer = get_producer()
        await producer.send("orders.created", {
            "order_id": order.id,
            "user_id": order.user_id,
            "total": float(order.total),
            "items_count": len(order.items),
        })
        
        return order
```

## Typed Messages

```python
from pydantic import BaseModel
from core.messaging import message_handler

class OrderCreatedEvent(BaseModel):
    order_id: int
    user_id: int
    total: float

@message_handler(topic="orders.created", schema=OrderCreatedEvent)
async def handle_order(message: OrderCreatedEvent, db):
    # message is validated and typed
    print(f"Order {message.order_id} total: {message.total}")
```

## Summary

| Approach | Use Case |
|----------|----------|
| `@event` | Auto-publish after action success |
| `publish_event()` | Direct publish anywhere |
| `get_producer()` | Full control over message |
| `@consumer` + `@on_event` | Class-based handlers |
| `@message_handler` | Simple function handlers |

Next: [Multi-Service Architecture](05-multi-service.md)
