# Multi-Service Architecture

Two APIs communicating via messaging on the same network.

## Project Structure

```
/services
  /orders-api
    /src
      /apps/orders
        models.py
        views.py
        schemas.py
        routes.py
      main.py
    docker-compose.yml
  /notifications-api
    /src
      /apps/notifications
        models.py
        handlers.py
      main.py
    docker-compose.yml
  docker-compose.yml  # Shared infrastructure
```

## Shared Infrastructure

```yaml
# /services/docker-compose.yml
version: "3.8"

services:
  kafka:
    image: bitnami/kafka:latest
    environment:
      KAFKA_CFG_NODE_ID: 0
      KAFKA_CFG_PROCESS_ROLES: controller,broker
      KAFKA_CFG_LISTENERS: PLAINTEXT://:9092,CONTROLLER://:9093
      KAFKA_CFG_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092
      KAFKA_CFG_CONTROLLER_QUORUM_VOTERS: 0@kafka:9093
      KAFKA_CFG_CONTROLLER_LISTENER_NAMES: CONTROLLER
    networks:
      - services-network

  redis:
    image: redis:7-alpine
    networks:
      - services-network

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    networks:
      - services-network

networks:
  services-network:
    name: services-network
    driver: bridge
```

## Orders API

### Model

```python
# orders-api/src/apps/orders/models.py
from core import Model
from sqlalchemy.orm import Mapped, mapped_column
from decimal import Decimal

class Order(Model):
    __tablename__ = "orders"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int]
    user_email: Mapped[str]
    total: Mapped[Decimal]
    status: Mapped[str] = mapped_column(default="pending")
```

### ViewSet with Auto-Publish Events

```python
# orders-api/src/apps/orders/views.py
from core import ModelViewSet, action
from core.messaging import event
from .models import Order
from .schemas import OrderInput, OrderOutput

class OrderViewSet(ModelViewSet):
    model = Order
    input_schema = OrderInput
    output_schema = OrderOutput
    tags = ["Orders"]
    
    @event("orders.created", topic="order-events", key_field="order_id")
    async def perform_create(self, data: dict, db) -> Order:
        """Auto-publishes orders.created after save."""
        order = await super().perform_create(data, db)
        # Return dict with all data needed in event
        return {
            "order_id": order.id,
            "user_id": order.user_id,
            "user_email": order.user_email,
            "total": str(order.total),
        }
    
    @action(methods=["POST"], detail=True)
    @event("orders.completed", topic="order-events", key_field="order_id")
    async def complete(self, request, db, **kwargs):
        """Auto-publishes orders.completed on success."""
        order = await self.get_object(db, **kwargs)
        order.status = "completed"
        await order.save(db)
        
        return {
            "order_id": order.id,
            "user_email": order.user_email,
            "status": "completed",
        }
```

Event is published automatically after response is sent to client.

### Main

```python
# orders-api/src/main.py
from core import CoreApp, AutoRouter
from core.messaging import configure_messaging
from src.apps.orders.routes import router as orders_router

configure_messaging(
    broker="kafka",
    bootstrap_servers="kafka:9092",
)

api_router = AutoRouter(prefix="/api/v1")
api_router.include_router(orders_router)

app = CoreApp(
    title="Orders API",
    routers=[api_router],
)
```

### Docker Compose

```yaml
# orders-api/docker-compose.yml
version: "3.8"

services:
  orders-api:
    build: .
    ports:
      - "8001:8000"
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:postgres@postgres:5432/orders
      KAFKA_BOOTSTRAP_SERVERS: kafka:9092
    networks:
      - services-network
    depends_on:
      - postgres
      - kafka

networks:
  services-network:
    external: true
```

## Notifications API

### Model

```python
# notifications-api/src/apps/notifications/models.py
from core import Model
from sqlalchemy.orm import Mapped, mapped_column
from core.datetime import DateTime

class Notification(Model):
    __tablename__ = "notifications"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_email: Mapped[str]
    subject: Mapped[str]
    body: Mapped[str]
    sent_at: Mapped[DateTime | None] = mapped_column(default=None)
```

### Event Handlers (Class-Based)

```python
# notifications-api/src/apps/notifications/handlers.py
from core.messaging import consumer, on_event
from core.messaging.base import Event
from .models import Notification

@consumer("notifications-service", topics=["order-events"])
class OrderNotificationsConsumer:
    
    @on_event("orders.created")
    async def on_order_created(self, event: Event, db):
        """Send order confirmation email."""
        data = event.data
        notification = Notification(
            user_email=data["user_email"],
            subject="Order Received",
            body=f"Your order #{data['order_id']} has been received. Total: ${data['total']}",
        )
        await notification.save(db)
        await self.send_email(notification)
    
    @on_event("orders.completed")
    async def on_order_completed(self, event: Event, db):
        """Send order completion email."""
        data = event.data
        notification = Notification(
            user_email=data["user_email"],
            subject="Order Completed",
            body=f"Your order #{data['order_id']} has been completed and shipped.",
        )
        await notification.save(db)
        await self.send_email(notification)
    
    async def send_email(self, notification: Notification):
        from core.datetime import DateTime
        notification.sent_at = DateTime.now()
        # await email_client.send(...)
```

Alternative: Function-based handlers

```python
from core.messaging import message_handler

@message_handler(topic="orders.created")
async def on_order_created(message: dict, db):
    notification = Notification(
        user_email=message["user_email"],
        subject="Order Received",
        body=f"Your order #{message['order_id']} received.",
    )
    await notification.save(db)
```

### Main

```python
# notifications-api/src/main.py
from core import CoreApp
from core.messaging import configure_messaging

# Import handlers to register them
from src.apps.notifications import handlers

configure_messaging(
    broker="kafka",
    bootstrap_servers="kafka:9092",
)

app = CoreApp(title="Notifications API")
```

### Docker Compose

```yaml
# notifications-api/docker-compose.yml
version: "3.8"

services:
  notifications-api:
    build: .
    ports:
      - "8002:8000"
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:postgres@postgres:5432/notifications
      KAFKA_BOOTSTRAP_SERVERS: kafka:9092
    networks:
      - services-network

  notifications-consumer:
    build: .
    command: core consumer
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:postgres@postgres:5432/notifications
      KAFKA_BOOTSTRAP_SERVERS: kafka:9092
    networks:
      - services-network
    depends_on:
      - kafka

networks:
  services-network:
    external: true
```

## Running

```bash
# Start shared infrastructure
cd /services
docker compose up -d

# Start Orders API
cd orders-api
docker compose up -d

# Start Notifications API + Consumer
cd ../notifications-api
docker compose up -d
```

## Flow

1. Client creates order via `POST /api/v1/orders/`
2. Orders API saves order and publishes to `orders.created`
3. Notifications consumer receives message
4. Notification is created and email sent
5. Client completes order via `POST /api/v1/orders/{id}/complete/`
6. Orders API publishes to `orders.completed`
7. Notifications consumer sends completion email

## Testing

```bash
# Create order
curl -X POST http://localhost:8001/api/v1/orders/ \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1, "user_email": "user@example.com", "total": "99.99"}'

# Check notifications (after a few seconds)
curl http://localhost:8002/api/v1/notifications/
```

Next: [Background Tasks](06-tasks.md)
