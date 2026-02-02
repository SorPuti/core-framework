# Core Framework

Framework Python sobre FastAPI. Padrão DRF, alta performance, baixo acoplamento.

## Sumario

1. [Instalacao](#instalacao)
2. [Configuracao](#configuracao)
3. [Models](#models)
4. [ViewSets](#viewsets)
5. [Autenticacao](#autenticacao)
6. [Permissoes](#permissoes)
7. [Messaging](#messaging)
8. [Tasks](#tasks)
9. [Deploy](#deploy)
10. [Microservicos](#microservicos)

---

## Instalacao

```bash
pipx install "core-framework @ git+https://TOKEN@github.com/user/core-framework.git"
core init my-project --python 3.13
cd my-project && source .venv/bin/activate
core makemigrations --name initial && core migrate
core run
```

---

## Configuracao

```env
APP_NAME=My API
SECRET_KEY=your-secret-key
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/db
API_PREFIX=/api/v1
AUTH_ACCESS_TOKEN_EXPIRE_MINUTES=30
AUTH_REFRESH_TOKEN_EXPIRE_DAYS=7
AUTH_PASSWORD_HASHER=pbkdf2_sha256
MESSAGE_BROKER=kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
```

---

## Models

```python
from sqlalchemy.orm import Mapped
from core import Model, Field

class Post(Model):
    __tablename__ = "posts"
    
    id: Mapped[int] = Field.pk()
    title: Mapped[str] = Field.string(max_length=200)
    slug: Mapped[str] = Field.string(max_length=200, unique=True)
    content: Mapped[str] = Field.text()
    is_published: Mapped[bool] = Field.boolean(default=False)
    author_id: Mapped[int] = Field.foreign_key("users.id")
```

### QuerySet

```python
posts = await Post.objects.using(db).filter(is_published=True).all()
post = await Post.objects.using(db).get(id=1)
count = await Post.objects.using(db).filter(is_published=True).count()
```

---

## ViewSets

### ModelViewSet

CRUD completo automatico. Sem decoradores FastAPI.

```python
from core import ModelViewSet, action
from core.permissions import IsAuthenticated, AllowAny

class PostViewSet(ModelViewSet):
    """
    GET    /posts/           list
    POST   /posts/           create
    GET    /posts/{id}/      retrieve
    PUT    /posts/{id}/      update
    PATCH  /posts/{id}/      partial_update
    DELETE /posts/{id}/      destroy
    """
    model = Post
    input_schema = PostInput
    output_schema = PostOutput
    tags = ["Posts"]
    
    permission_classes = [IsAuthenticated]
    permission_classes_by_action = {
        "list": [AllowAny],
        "retrieve": [AllowAny],
    }
    
    unique_fields = ["slug"]
    page_size = 20
    
    def get_queryset(self, db):
        return Post.objects.using(db).filter(is_published=True)
```

### Custom Actions

```python
class PostViewSet(ModelViewSet):
    model = Post
    
    @action(methods=["POST"], detail=True, permission_classes=[IsAuthenticated])
    async def publish(self, request: Request, db: AsyncSession, **kwargs):
        """POST /posts/{id}/publish/"""
        post = await self.get_object(db, **kwargs)
        post.is_published = True
        await post.save(db)
        return {"published": True}
    
    @action(methods=["GET"], detail=False, permission_classes=[AllowAny])
    async def featured(self, request: Request, db: AsyncSession, **kwargs):
        """GET /posts/featured/"""
        posts = await Post.objects.using(db).filter(
            is_published=True, views_count__gt=100
        ).limit(5).all()
        return [PostOutput.model_validate(p).model_dump() for p in posts]
```

### Lookup Field Customizado

Por padrao usa `id` (Integer). Suporta UUID, String ou qualquer tipo SQLAlchemy.

```python
class PostViewSet(ModelViewSet):
    model = Post
    lookup_field = "slug"  # GET /posts/my-post-slug/

class DocumentViewSet(ModelViewSet):
    model = Document
    lookup_field = "uuid"  # GET /documents/550e8400-e29b-41d4-a716-446655440000/
```

O framework detecta automaticamente o tipo do campo e converte. Erros retornam:

```json
{
  "detail": {
    "error": "invalid_lookup_value",
    "message": "Invalid id format. Expected integer.",
    "field": "id",
    "value": "abc",
    "expected_type": "integer"
  }
}
```

### ReadOnlyModelViewSet

Apenas list e retrieve.

```python
from core.views import ReadOnlyModelViewSet

class PublicPostViewSet(ReadOnlyModelViewSet):
    model = Post
    output_schema = PostOutput
    permission_classes = [AllowAny]
```

### APIView

Endpoints customizados sem model.

```python
from core import APIView

class HealthView(APIView):
    permission_classes = [AllowAny]
    tags = ["System"]
    
    async def get(self, request, **kwargs):
        return {"status": "healthy"}
```

### Routing

```python
from core import AutoRouter

posts_router = AutoRouter(prefix="/posts", tags=["Posts"])
posts_router.register("", PostViewSet, basename="post")

api_router = AutoRouter(prefix="/api/v1")
api_router.include_router(posts_router)

app = CoreApp(routers=[api_router])
```

---

## Autenticacao

### Configuracao Basica

```python
from core.auth import configure_auth
from src.apps.users.models import User

configure_auth(
    secret_key="your-secret-key",
    access_token_expire_minutes=30,
    refresh_token_expire_days=7,
    password_hasher="pbkdf2_sha256",  # pbkdf2_sha256, argon2, bcrypt, scrypt
    user_model=User,
)
```

### Tokens

```python
from core.auth import create_access_token, create_refresh_token, verify_token

access = create_access_token(user_id=user.id, extra_claims={"email": user.email})
refresh = create_refresh_token(user_id=user.id)

payload = verify_token(access, token_type="access")
user_id = payload["sub"]
```

### AuthViewSet Completo

```python
from core import ModelViewSet, action
from core.auth import create_access_token, create_refresh_token, verify_token
from core.permissions import AllowAny, IsAuthenticated

class AuthViewSet(ModelViewSet):
    model = User
    tags = ["Auth"]
    permission_classes = [AllowAny]
    
    # Desabilita CRUD padrao
    async def list(self, *a, **kw): raise HTTPException(404)
    async def retrieve(self, *a, **kw): raise HTTPException(404)
    async def create(self, *a, **kw): raise HTTPException(404)
    async def update(self, *a, **kw): raise HTTPException(404)
    async def destroy(self, *a, **kw): raise HTTPException(404)
    
    @action(methods=["POST"], detail=False)
    async def register(self, request: Request, db: AsyncSession, **kwargs):
        """POST /auth/register/"""
        body = await request.json()
        data = RegisterInput.model_validate(body)
        
        if await User.get_by_email(data.email, db):
            raise HTTPException(400, "Email already registered")
        
        user = await User.create_user(
            email=data.email, password=data.password, db=db
        )
        return UserOutput.model_validate(user).model_dump()
    
    @action(methods=["POST"], detail=False)
    async def login(self, request: Request, db: AsyncSession, **kwargs):
        """POST /auth/login/"""
        body = await request.json()
        data = LoginInput.model_validate(body)
        
        user = await User.authenticate(data.email, data.password, db)
        if not user:
            raise HTTPException(401, "Invalid credentials")
        
        return {
            "access_token": create_access_token(user_id=user.id, extra_claims={"email": user.email}),
            "refresh_token": create_refresh_token(user_id=user.id),
            "token_type": "bearer",
        }
    
    @action(methods=["POST"], detail=False)
    async def refresh(self, request: Request, db: AsyncSession, **kwargs):
        """POST /auth/refresh/"""
        body = await request.json()
        payload = verify_token(body["refresh_token"], token_type="refresh")
        if not payload:
            raise HTTPException(401, "Invalid refresh token")
        
        return {
            "access_token": create_access_token(user_id=payload["sub"]),
            "refresh_token": create_refresh_token(user_id=payload["sub"]),
            "token_type": "bearer",
        }
    
    @action(methods=["GET"], detail=False, permission_classes=[IsAuthenticated])
    async def me(self, request: Request, db: AsyncSession, **kwargs):
        """GET /auth/me/"""
        return UserOutput.model_validate(request.state.user).model_dump()
```

### Backend Customizado

```python
from core.auth import AuthBackend, register_auth_backend

class LDAPBackend(AuthBackend):
    name = "ldap"
    
    async def authenticate(self, request, db, **credentials):
        username = credentials.get("username")
        password = credentials.get("password")
        # Implementar logica LDAP
        return user_or_none
    
    async def get_user(self, user_id: int, db):
        return await User.objects.using(db).get_or_none(id=user_id)

register_auth_backend(LDAPBackend())
```

### Password Hasher Customizado

```python
from core.auth import PasswordHasher, register_password_hasher

class CustomHasher(PasswordHasher):
    name = "custom_sha512"
    
    def hash(self, password: str) -> str:
        # Implementar hash
        return hashed
    
    def verify(self, password: str, hashed: str) -> bool:
        # Verificar
        return True/False

register_password_hasher(CustomHasher())
# Usar: AUTH_PASSWORD_HASHER=custom_sha512
```

### Token Backend Customizado

```python
from core.auth import TokenBackend, register_token_backend

class CustomJWT(TokenBackend):
    name = "custom_jwt"
    
    def create_token(self, payload, token_type="access", expires_delta=None):
        # Criar token
        return token_string
    
    def decode_token(self, token):
        # Decodificar
        return payload_or_none
    
    def verify_token(self, token, token_type="access"):
        # Verificar tipo e validade
        return payload_or_none

register_token_backend(CustomJWT())
```

---

## Permissoes

### Classes Disponiveis

```python
from core.permissions import (
    AllowAny,           # Qualquer acesso
    IsAuthenticated,    # Requer autenticacao
    IsAdmin,            # Requer is_superuser=True
    IsStaff,            # Requer is_staff=True
    IsOwner,            # Verifica propriedade do objeto
    HasPermission,      # Verifica permissao especifica
    IsInGroup,          # Verifica grupo
)
```

### Uso em ViewSet

```python
class PostViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    
    permission_classes_by_action = {
        "list": [AllowAny],
        "retrieve": [AllowAny],
        "create": [IsAuthenticated],
        "update": [IsAuthenticated, IsOwner],
        "destroy": [HasPermission("posts.delete")],
    }
```

### Permissao Customizada

```python
from core.permissions import Permission

class IsVerified(Permission):
    async def has_permission(self, request, view) -> bool:
        user = getattr(request.state, "user", None)
        return user and getattr(user, "is_verified", False)
    
    async def has_object_permission(self, request, view, obj) -> bool:
        return await self.has_permission(request, view)
```

---

## Messaging

Sistema de eventos com Kafka, Redis ou RabbitMQ.

### Configuracao

```env
MESSAGE_BROKER=kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# Ou Redis
MESSAGE_BROKER=redis
REDIS_URL=redis://localhost:6379/0

# Ou RabbitMQ
MESSAGE_BROKER=rabbitmq
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
```

### Producer - Emitir Eventos

```python
from core.messaging import event

class OrderViewSet(ModelViewSet):
    model = Order
    
    @action(methods=["POST"], detail=False)
    @event("order.created", topic="order-events")
    async def create_order(self, request, db, **kwargs):
        body = await request.json()
        order = await Order.objects.create(**body, db=db)
        return OrderOutput.model_validate(order).model_dump()
        # Evento emitido automaticamente com o retorno
```

Emissao manual:

```python
from core.messaging import publish_event

await publish_event(
    "user.updated",
    data={"id": 1, "email": "new@example.com"},
    topic="user-events",
)
```

### Consumer - Receber Eventos

```python
from core.messaging import consumer, on_event

@consumer("notification-service", topics=["user-events", "order-events"])
class NotificationConsumer:
    
    @on_event("user.created")
    async def on_user_created(self, event, db):
        await send_welcome_email(event.data["email"])
    
    @on_event("order.created")
    async def on_order_created(self, event, db):
        await send_order_confirmation(event.data["user_id"], event.data["id"])
```

### CLI

```bash
core consumer --group notification-service --topic user-events
core topics list
core topics create user-events --partitions 3
```

---

## Tasks

Background jobs integrados com messaging.

### Task Simples

```python
from core.tasks import task

@task(queue="emails", retry=3, timeout=300)
async def send_email(to: str, subject: str, body: str):
    await EmailService.send(to, subject, body)

# Execucao imediata
await send_email("user@example.com", "Hello", "World")

# Background
task_id = await send_email.delay("user@example.com", "Hello", "World")

# Com delay
task_id = await send_email.apply_async(
    args=("user@example.com", "Hello", "World"),
    countdown=60,
)
```

### Task Periodica

```python
from core.tasks import periodic_task

@periodic_task(cron="0 0 * * *")  # Meia-noite
async def daily_cleanup():
    await Session.objects.filter(expired=True).delete()

@periodic_task(interval=300)  # 5 minutos
async def sync_data():
    await ExternalAPI.sync()
```

### CLI

```bash
core worker --queue default --concurrency 4
core scheduler
core tasks
```

---

## Deploy

### Docker

```bash
core deploy docker
docker-compose up -d
docker-compose up -d --scale worker=4
```

### PM2

```bash
core deploy pm2
pm2 start ecosystem.config.js
```

### Kubernetes

```bash
core deploy k8s
kubectl apply -k k8s/
```

---

## Microservicos

Exemplo de duas APIs REST comunicando via eventos.

### Estrutura

```
services/
  user-api/
    src/main.py
    docker-compose.yml
  order-api/
    src/main.py
    docker-compose.yml
  docker-compose.network.yml
```

### Network Compartilhada

```yaml
# docker-compose.network.yml
networks:
  microservices:
    driver: bridge

services:
  kafka:
    image: confluentinc/cp-kafka:7.5.0
    networks:
      - microservices
    environment:
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092
    # ... config kafka

  zookeeper:
    image: confluentinc/cp-zookeeper:7.5.0
    networks:
      - microservices

  redis:
    image: redis:7-alpine
    networks:
      - microservices

  db:
    image: postgres:16-alpine
    networks:
      - microservices
```

### User API (Porta 8001)

```python
# user-api/src/main.py
from core import CoreApp, AutoRouter, ModelViewSet, action
from core.auth import configure_auth
from core.messaging import event, consumer, on_event
from core.permissions import AllowAny, IsAuthenticated

class User(Model):
    __tablename__ = "users"
    id: Mapped[int] = Field.pk()
    email: Mapped[str] = Field.string(unique=True)
    order_count: Mapped[int] = Field.integer(default=0)

class UserViewSet(ModelViewSet):
    model = User
    input_schema = UserInput
    output_schema = UserOutput
    tags = ["Users"]
    
    @action(methods=["POST"], detail=False, permission_classes=[AllowAny])
    @event("user.created", topic="user-events")
    async def register(self, request, db, **kwargs):
        body = await request.json()
        user = await User.create_user(email=body["email"], password=body["password"], db=db)
        return UserOutput.model_validate(user).model_dump()

# Consumer para eventos de Order
@consumer("user-service", topics=["order-events"])
class OrderEventsConsumer:
    
    @on_event("order.created")
    async def on_order_created(self, event, db):
        """Incrementa contador de pedidos do usuario."""
        user_id = event.data["user_id"]
        user = await User.objects.using(db).get(id=user_id)
        user.order_count += 1
        await user.save(db)

# App
configure_auth(secret_key="secret", user_model=User)
router = AutoRouter(prefix="/api/v1")
router.register("/users", UserViewSet)
app = CoreApp(title="User API", routers=[router])
```

```yaml
# user-api/docker-compose.yml
services:
  user-api:
    build: .
    ports:
      - "8001:8000"
    environment:
      DATABASE_URL: postgresql+asyncpg://user:pass@db:5432/users
      KAFKA_BOOTSTRAP_SERVERS: kafka:9092
    networks:
      - microservices_microservices
    depends_on:
      - db
      - kafka

  user-worker:
    build: .
    command: core consumer --group user-service --topic order-events
    environment:
      DATABASE_URL: postgresql+asyncpg://user:pass@db:5432/users
      KAFKA_BOOTSTRAP_SERVERS: kafka:9092
    networks:
      - microservices_microservices

networks:
  microservices_microservices:
    external: true
```

### Order API (Porta 8002)

```python
# order-api/src/main.py
from core import CoreApp, AutoRouter, ModelViewSet, action
from core.messaging import event, consumer, on_event
from core.permissions import IsAuthenticated

class Order(Model):
    __tablename__ = "orders"
    id: Mapped[int] = Field.pk()
    user_id: Mapped[int] = Field.integer()
    total: Mapped[float] = Field.float_()
    status: Mapped[str] = Field.string(default="pending")

class OrderViewSet(ModelViewSet):
    model = Order
    input_schema = OrderInput
    output_schema = OrderOutput
    tags = ["Orders"]
    permission_classes = [IsAuthenticated]
    
    @action(methods=["POST"], detail=False)
    @event("order.created", topic="order-events")
    async def create_order(self, request, db, **kwargs):
        body = await request.json()
        order = Order(
            user_id=request.state.user.id,
            total=body["total"],
        )
        await order.save(db)
        return OrderOutput.model_validate(order).model_dump()

# Consumer para eventos de User
@consumer("order-service", topics=["user-events"])
class UserEventsConsumer:
    
    @on_event("user.created")
    async def on_user_created(self, event, db):
        """Cria pedido de boas-vindas."""
        order = Order(
            user_id=event.data["id"],
            total=0,
            status="welcome",
        )
        await order.save(db)

# App
router = AutoRouter(prefix="/api/v1")
router.register("/orders", OrderViewSet)
app = CoreApp(title="Order API", routers=[router])
```

```yaml
# order-api/docker-compose.yml
services:
  order-api:
    build: .
    ports:
      - "8002:8000"
    environment:
      DATABASE_URL: postgresql+asyncpg://user:pass@db:5432/orders
      KAFKA_BOOTSTRAP_SERVERS: kafka:9092
    networks:
      - microservices_microservices

  order-worker:
    build: .
    command: core consumer --group order-service --topic user-events
    environment:
      DATABASE_URL: postgresql+asyncpg://user:pass@db:5432/orders
      KAFKA_BOOTSTRAP_SERVERS: kafka:9092
    networks:
      - microservices_microservices

networks:
  microservices_microservices:
    external: true
```

### Iniciar

```bash
# 1. Subir infra compartilhada
cd services && docker-compose -f docker-compose.network.yml up -d

# 2. Subir User API
cd user-api && docker-compose up -d

# 3. Subir Order API
cd order-api && docker-compose up -d
```

### Fluxo

```
1. POST /api/v1/users/register/ (User API :8001)
   -> Cria usuario
   -> Emite "user.created" no Kafka

2. order-worker consome "user.created"
   -> Cria pedido de boas-vindas

3. POST /api/v1/orders/create_order/ (Order API :8002)
   -> Cria pedido
   -> Emite "order.created" no Kafka

4. user-worker consome "order.created"
   -> Incrementa order_count do usuario
```

### Comunicacao Sincrona (Opcional)

Para chamadas diretas entre APIs:

```python
import httpx

class OrderViewSet(ModelViewSet):
    
    @action(methods=["GET"], detail=True)
    async def with_user(self, request, db, **kwargs):
        order = await self.get_object(db, **kwargs)
        
        # Busca usuario na User API
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"http://user-api:8000/api/v1/users/{order.user_id}/",
                headers={"Authorization": request.headers.get("Authorization")},
            )
            user_data = resp.json()
        
        return {
            **OrderOutput.model_validate(order).model_dump(),
            "user": user_data,
        }
```

---

## Migrations

```bash
core makemigrations --name add_phone
core migrate
core migrate --rollback
core showmigrations
```

---

## CLI

```bash
core init <project>          # Criar projeto
core run                     # Servidor dev
core makemigrations          # Criar migracao
core migrate                 # Aplicar migracoes
core worker                  # Worker de tasks
core scheduler               # Scheduler de tasks periodicas
core consumer                # Consumer de eventos
core topics                  # Gerenciar topics Kafka
core deploy docker|pm2|k8s   # Gerar arquivos de deploy
```
