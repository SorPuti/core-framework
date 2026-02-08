# Messaging (Kafka)

Event-driven architecture with Kafka.

## Setup

```python
# src/settings.py
class AppSettings(Settings):
    kafka_enabled: bool = True
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_backend: str = "aiokafka"  # or "confluent"
```

## Producer

```python
# src/apps/orders/events.py
from core.messaging import producer

@producer(topic="orders")
async def order_created(order_id: int, user_id: int, total: float):
    """Publish order created event."""
    return {
        "event": "order.created",
        "order_id": order_id,
        "user_id": user_id,
        "total": total,
    }

# Usage
await order_created(order_id=123, user_id=456, total=99.99)
```

## Consumer

```python
# src/apps/notifications/consumers.py
from core.messaging import consumer

@consumer(topic="orders", group="notifications")
async def handle_order_created(message: dict):
    """React to order created events."""
    if message["event"] == "order.created":
        await send_notification(
            user_id=message["user_id"],
            text=f"Order #{message['order_id']} confirmed!"
        )
```

## Event Decorator

```python
from core.messaging import event

@event("user.registered")
async def on_user_registered(user_id: int, email: str):
    """Triggered when user registers."""
    await send_welcome_email(email)
    await create_default_settings(user_id)
```

## Topics

```python
# src/topics.py
from core.messaging import Topic

class OrderTopic(Topic):
    name = "orders"
    partitions = 3
    replication_factor = 1
    
class UserTopic(Topic):
    name = "users"
    partitions = 1
```

## Run Consumer

```bash
# Start consumer
core consumer start

# With specific group
core consumer start --group notifications

# List topics
core topics_list

# Create topic
core topics_create orders --partitions 3
```

## Avro Schemas

```python
# src/schemas/order.py
from core.messaging import AvroSchema

class OrderCreatedSchema(AvroSchema):
    order_id: int
    user_id: int
    total: float
    created_at: str

@producer(topic="orders", schema=OrderCreatedSchema)
async def order_created(order_id: int, user_id: int, total: float):
    ...
```

## Multi-Service

```python
# Service A: Publish
@producer(topic="payments")
async def payment_processed(order_id: int, amount: float):
    return {"order_id": order_id, "amount": amount, "status": "success"}

# Service B: Consume
@consumer(topic="payments", group="orders-service")
async def handle_payment(message: dict):
    if message["status"] == "success":
        await Order.objects.filter(id=message["order_id"]).update(paid=True)
```

## Error Handling

```python
from core.messaging import consumer, ConsumerError

@consumer(topic="orders", group="processor", max_retries=3)
async def process_order(message: dict):
    try:
        await do_processing(message)
    except TemporaryError:
        raise ConsumerError("Retry")  # Will retry
    except PermanentError:
        # Log and skip message
        logger.error(f"Failed to process: {message}")
```

## Next

- [Tasks](20-tasks.md) — Background jobs
- [CLI](07-cli.md) — Kafka commands
