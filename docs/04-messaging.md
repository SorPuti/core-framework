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

## Producer

Send messages to topics.

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

## Consumer

Process messages from topics.

```python
from core.messaging import message_handler

@message_handler(topic="orders.created")
async def handle_order_created(message: dict, db):
    """Process new order."""
    order_id = message["order_id"]
    
    # Send confirmation email
    await send_email(
        to=message["user_email"],
        subject="Order Confirmed",
        body=f"Order #{order_id} received.",
    )
```

## Consumer with Retry

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

## Producer in ViewSet

```python
from core import ModelViewSet
from core.messaging import get_producer

class OrderViewSet(ModelViewSet):
    model = Order
    
    async def perform_create(self, data: dict, db) -> Order:
        order = await super().perform_create(data, db)
        
        # Publish event
        producer = get_producer()
        await producer.send("orders.created", {
            "order_id": order.id,
            "user_id": order.user_id,
            "total": float(order.total),
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

## Manual Consumer

```python
from core.messaging.kafka import KafkaConsumer

async def run_custom_consumer():
    consumer = KafkaConsumer(
        group_id="my-service",
        topics=["orders.created"],
        message_handler=process_message,
    )
    await consumer.start()
```

Next: [Multi-Service Architecture](05-multi-service.md)
