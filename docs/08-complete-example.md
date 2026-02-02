# Complete Example: E-commerce API

Full example combining all features.

## Project Structure

```
/ecommerce-api
  /src
    /apps
      /users
        models.py
        views.py
        schemas.py
        routes.py
      /products
        models.py
        views.py
        schemas.py
        routes.py
      /orders
        models.py
        views.py
        schemas.py
        routes.py
        tasks.py
        handlers.py
    /api
      config.py
    main.py
```

## Models

```python
# src/apps/users/models.py
from core.auth import AbstractUser
from sqlalchemy.orm import Mapped, mapped_column

class User(AbstractUser):
    __tablename__ = "users"
    
    phone: Mapped[str | None] = mapped_column(default=None)
    address: Mapped[str | None] = mapped_column(default=None)
```

```python
# src/apps/products/models.py
from core import Model
from sqlalchemy.orm import Mapped, mapped_column
from decimal import Decimal

class Product(Model):
    __tablename__ = "products"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(index=True)
    description: Mapped[str]
    price: Mapped[Decimal]
    stock: Mapped[int] = mapped_column(default=0)
    published: Mapped[bool] = mapped_column(default=False)
```

```python
# src/apps/orders/models.py
from core import Model
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey
from decimal import Decimal

class Order(Model):
    __tablename__ = "orders"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(default="pending")
    total: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order")

class OrderItem(Model):
    __tablename__ = "order_items"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int]
    price: Mapped[Decimal]
    
    order: Mapped["Order"] = relationship(back_populates="items")
```

## Schemas

```python
# src/apps/products/schemas.py
from core import InputSchema, OutputSchema
from decimal import Decimal

class ProductInput(InputSchema):
    name: str
    description: str
    price: Decimal
    stock: int = 0
    published: bool = False

class ProductOutput(OutputSchema):
    id: int
    name: str
    description: str
    price: Decimal
    stock: int
    published: bool
```

```python
# src/apps/orders/schemas.py
from core import InputSchema, OutputSchema
from decimal import Decimal

class OrderItemInput(InputSchema):
    product_id: int
    quantity: int

class OrderInput(InputSchema):
    items: list[OrderItemInput]

class OrderItemOutput(OutputSchema):
    id: int
    product_id: int
    quantity: int
    price: Decimal

class OrderOutput(OutputSchema):
    id: int
    user_id: int
    status: str
    total: Decimal
    items: list[OrderItemOutput]
```

## ViewSets

```python
# src/apps/products/views.py
from core import ModelViewSet, action
from core.permissions import AllowAny, IsAuthenticated, IsAdmin
from .models import Product
from .schemas import ProductInput, ProductOutput

class ProductViewSet(ModelViewSet):
    model = Product
    input_schema = ProductInput
    output_schema = ProductOutput
    tags = ["Products"]
    
    permission_classes = [AllowAny]
    permission_classes_by_action = {
        "create": [IsAdmin],
        "update": [IsAdmin],
        "destroy": [IsAdmin],
    }
    
    def get_queryset(self, db):
        qs = super().get_queryset(db)
        user = getattr(self.request.state, "user", None)
        if not user or not user.is_staff:
            return qs.filter(published=True)
        return qs
    
    @action(methods=["POST"], detail=True, permission_classes=[IsAdmin])
    async def publish(self, request, db, **kwargs):
        product = await self.get_object(db, **kwargs)
        product.published = True
        await product.save(db)
        return {"status": "published"}
```

```python
# src/apps/orders/views.py
from core import ModelViewSet, action
from core.permissions import IsAuthenticated
from core.messaging import get_producer
from decimal import Decimal
from .models import Order, OrderItem
from .schemas import OrderInput, OrderOutput
from src.apps.products.models import Product

class OrderViewSet(ModelViewSet):
    model = Order
    input_schema = OrderInput
    output_schema = OrderOutput
    tags = ["Orders"]
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self, db):
        qs = super().get_queryset(db)
        user = self.request.state.user
        if not user.is_staff:
            return qs.filter(user_id=user.id)
        return qs
    
    async def perform_create(self, data: dict, db) -> Order:
        user = self.request.state.user
        items_data = data.pop("items", [])
        
        # Create order
        order = Order(user_id=user.id, total=Decimal("0"))
        await order.save(db)
        
        # Create items and calculate total
        total = Decimal("0")
        for item_data in items_data:
            product = await Product.objects.using(db).get(id=item_data["product_id"])
            
            item = OrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=item_data["quantity"],
                price=product.price,
            )
            await item.save(db)
            total += product.price * item_data["quantity"]
        
        order.total = total
        await order.save(db)
        
        # Publish event
        producer = get_producer()
        await producer.send("orders.created", {
            "order_id": order.id,
            "user_id": user.id,
            "user_email": user.email,
            "total": str(total),
        })
        
        return order
    
    @action(methods=["POST"], detail=True)
    async def pay(self, request, db, **kwargs):
        order = await self.get_object(db, **kwargs)
        
        if order.status != "pending":
            from fastapi import HTTPException
            raise HTTPException(400, "Order already processed")
        
        # Queue payment task
        from .tasks import process_payment
        await process_payment.delay(order_id=order.id)
        
        return {"message": "Payment processing started"}
```

## Tasks

```python
# src/apps/orders/tasks.py
from core.tasks import task
from core.messaging import get_producer
from core.models import get_session

@task(queue="payments", max_retries=3)
async def process_payment(order_id: int):
    async with get_session() as db:
        from .models import Order
        order = await Order.objects.using(db).get(id=order_id)
        
        # Process payment (mock)
        success = await payment_gateway.charge(
            amount=float(order.total),
            user_id=order.user_id,
        )
        
        if success:
            order.status = "paid"
            await order.save(db)
            
            producer = get_producer()
            await producer.send("orders.paid", {
                "order_id": order.id,
                "user_id": order.user_id,
            })
        else:
            raise Exception("Payment failed")
```

## Message Handlers

```python
# src/apps/orders/handlers.py
from core.messaging import message_handler

@message_handler(topic="orders.paid")
async def on_order_paid(message: dict, db):
    """Update inventory after payment."""
    from .models import Order, OrderItem
    from src.apps.products.models import Product
    
    order = await Order.objects.using(db).get(id=message["order_id"])
    items = await OrderItem.objects.using(db).filter(order_id=order.id).all()
    
    for item in items:
        product = await Product.objects.using(db).get(id=item.product_id)
        product.stock -= item.quantity
        await product.save(db)
```

## Routes

```python
# src/apps/products/routes.py
from core import AutoRouter
from .views import ProductViewSet

router = AutoRouter(prefix="/products", tags=["Products"])
router.register("", ProductViewSet)
```

```python
# src/apps/orders/routes.py
from core import AutoRouter
from .views import OrderViewSet

router = AutoRouter(prefix="/orders", tags=["Orders"])
router.register("", OrderViewSet)
```

## Main

```python
# src/main.py
from core import CoreApp, AutoRouter
from core.datetime import configure_datetime
from core.auth import configure_auth
from core.messaging import configure_messaging

from src.api.config import settings
from src.apps.users.models import User
from src.apps.products.routes import router as products_router
from src.apps.orders.routes import router as orders_router

# Import handlers
from src.apps.orders import handlers

configure_datetime(default_timezone="UTC")
configure_auth(
    secret_key=settings.secret_key,
    user_model=User,
)
configure_messaging(
    broker="kafka",
    bootstrap_servers=settings.kafka_bootstrap_servers,
)

api_router = AutoRouter(prefix="/api/v1")
api_router.include_router(products_router)
api_router.include_router(orders_router)

app = CoreApp(
    title="E-commerce API",
    routers=[api_router],
)
```

## Run

```bash
# Development
core run

# Production
docker compose up -d
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/v1/products/ | List products |
| POST | /api/v1/products/ | Create product (admin) |
| GET | /api/v1/products/{id} | Get product |
| POST | /api/v1/products/{id}/publish/ | Publish product (admin) |
| GET | /api/v1/orders/ | List user orders |
| POST | /api/v1/orders/ | Create order |
| GET | /api/v1/orders/{id} | Get order |
| POST | /api/v1/orders/{id}/pay/ | Process payment |
