# Multi-Service Architecture

Este guia demonstra duas APIs independentes comunicando via Kafka. O padrao e aplicavel a qualquer arquitetura de microservicos onde servicos precisam reagir a eventos de outros servicos.

## Estrutura do Projeto

Cada servico e um projeto independente com seu proprio banco de dados. A comunicacao acontece exclusivamente via mensagens.

```
/services
  /orders-api              # Servico de pedidos
    /src
      /apps/orders
        models.py
        views.py
        schemas.py
        routes.py
      main.py
    docker-compose.yml     # Compose especifico do servico
    
  /notifications-api       # Servico de notificacoes
    /src
      /apps/notifications
        models.py
        handlers.py        # Consumers de eventos
      main.py
    docker-compose.yml
    
  docker-compose.yml       # Infraestrutura compartilhada (Kafka, Postgres, Redis)
```

**Decisao arquitetural**: Cada servico tem seu proprio banco. Isso garante isolamento, mas exige consistencia eventual. Se voce precisa de transacoes distribuidas, considere o padrao Saga.

## Infraestrutura Compartilhada

O compose da raiz define servicos de infraestrutura usados por todos os microservicos.

```yaml
# /services/docker-compose.yml
version: "3.8"

services:
  kafka:
    image: bitnami/kafka:latest
    environment:
      # Kafka em modo KRaft (sem Zookeeper) - recomendado para novos deployments
      KAFKA_CFG_NODE_ID: 0
      KAFKA_CFG_PROCESS_ROLES: controller,broker
      KAFKA_CFG_LISTENERS: PLAINTEXT://:9092,CONTROLLER://:9093
      # ADVERTISED_LISTENERS deve usar hostname resolvivel pelos outros containers
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
      # Cada servico cria seu proprio database nesta instancia
      # Alternativa: uma instancia Postgres por servico (mais isolamento)
    networks:
      - services-network

networks:
  # Network nomeada permite que outros compose files se conectem
  services-network:
    name: services-network
    driver: bridge
```

**Trade-off de Postgres compartilhado**: Simplicidade vs isolamento. Em producao, considere instancias separadas para evitar que um servico impacte outro.

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
    
    # user_id referencia usuario em outro servico
    # NAO use ForeignKey - o servico de usuarios e separado
    user_id: Mapped[int]
    
    # user_email duplicado para evitar chamadas sincronas ao servico de usuarios
    # Trade-off: duplicacao vs acoplamento
    user_email: Mapped[str]
    
    # Decimal para valores monetarios - evita erros de ponto flutuante
    total: Mapped[Decimal]
    
    status: Mapped[str] = mapped_column(default="pending")
```

### ViewSet com Publicacao de Eventos

```python
# orders-api/src/apps/orders/views.py
from core import ModelViewSet, action
from core.messaging import event
from .models import Order
from .schemas import OrderInput, OrderOutput

class OrderViewSet(ModelViewSet):
    model = Order
    input_schema = OrderInput
    output_schema = OutputOutput
    tags = ["Orders"]
    
    @event("orders.created", topic="order-events", key_field="order_id")
    async def perform_create(self, data: dict, db) -> dict:
        """
        @event publica automaticamente apos sucesso.
        
        key_field="order_id": Garante que eventos do mesmo pedido
        vao para a mesma particao Kafka, mantendo ordenacao.
        
        IMPORTANTE: O retorno DEVE ser dict com os dados do evento.
        Se retornar o model diretamente, a serializacao pode falhar
        ou incluir campos indesejados.
        """
        order = await super().perform_create(data, db)
        
        # Retorna dict explicito com dados necessarios para consumidores
        return {
            "order_id": order.id,
            "user_id": order.user_id,
            "user_email": order.user_email,
            "total": str(order.total),  # Decimal -> str para JSON
        }
    
    @action(methods=["POST"], detail=True)
    @event("orders.completed", topic="order-events", key_field="order_id")
    async def complete(self, request, db, **kwargs):
        """
        POST /orders/{id}/complete
        
        Evento publicado apenas se a acao completar sem erro.
        Se levantar excecao, evento NAO e publicado.
        """
        order = await self.get_object(db, **kwargs)
        order.status = "completed"
        await order.save(db)
        
        return {
            "order_id": order.id,
            "user_email": order.user_email,
            "status": "completed",
        }
```

**Sobre o retorno de perform_create**: O metodo original retorna `Order`. Ao usar `@event`, o retorno e usado como payload do evento. Retornar dict garante controle sobre o que e publicado.

### Main

```python
# orders-api/src/main.py
from core import CoreApp, AutoRouter
from core.messaging import configure_messaging
from src.apps.orders.routes import router as orders_router

# Configuracao de messaging ANTES de importar rotas
# Isso garante que decorators @event funcionem corretamente
configure_messaging(
    broker="kafka",
    # "kafka" e o hostname do container na network Docker
    bootstrap_servers="kafka:9092",
)

api_router = AutoRouter(prefix="/api/v1")
api_router.include_router(orders_router)

app = CoreApp(
    title="Orders API",
    routers=[api_router],
)
```

### Docker Compose do Servico

```yaml
# orders-api/docker-compose.yml
version: "3.8"

services:
  orders-api:
    build: .
    ports:
      - "8001:8000"  # Porta diferente de outros servicos
    environment:
      # Database especifico deste servico
      DATABASE_URL: postgresql+asyncpg://postgres:postgres@postgres:5432/orders
      KAFKA_BOOTSTRAP_SERVERS: kafka:9092
    networks:
      # Conecta a network externa definida no compose da raiz
      - services-network
    depends_on:
      - postgres
      - kafka

networks:
  services-network:
    # external: true indica que a network ja existe
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
    
    # Nullable - preenchido quando email e enviado
    sent_at: Mapped[DateTime | None] = mapped_column(default=None)
```

### Event Handlers

Handlers baseados em classe agrupam logica relacionada.

```python
# notifications-api/src/apps/notifications/handlers.py
from core.messaging import consumer, on_event
from core.messaging.base import Event
from .models import Notification

@consumer("notifications-service", topics=["order-events"])
class OrderNotificationsConsumer:
    """
    @consumer define:
    - group_id: "notifications-service"
      Multiplas instancias deste consumer dividem a carga.
      Cada mensagem e processada por apenas uma instancia.
    
    - topics: ["order-events"]
      Este consumer so recebe mensagens deste topico.
      Handlers @on_event filtram por nome do evento.
    """
    
    @on_event("orders.created")
    async def on_order_created(self, event: Event, db):
        """
        Chamado quando evento "orders.created" e recebido.
        
        event.data contem o payload publicado pelo Orders API.
        db e sessao de banco injetada automaticamente.
        """
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
        """
        Mesmo consumer pode ter multiplos handlers.
        Cada @on_event filtra por nome de evento diferente.
        """
        data = event.data
        notification = Notification(
            user_email=data["user_email"],
            subject="Order Completed",
            body=f"Your order #{data['order_id']} has been completed and shipped.",
        )
        await notification.save(db)
        await self.send_email(notification)
    
    async def send_email(self, notification: Notification):
        """
        Metodo auxiliar compartilhado entre handlers.
        Vantagem de usar classe vs funcoes isoladas.
        """
        from core.datetime import DateTime
        notification.sent_at = DateTime.now()
        await notification.save(notification._session)
        # Implementar envio real de email aqui
        # await email_client.send(...)
```

Alternativa com funcoes (para casos simples):

```python
from core.messaging import message_handler

@message_handler(topic="orders.created")
async def on_order_created(message: dict, db):
    """
    Handler baseado em funcao.
    Mais simples, mas sem compartilhamento de estado/metodos.
    
    message e dict (nao Event) - acesso direto ao payload.
    """
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

# IMPORTANTE: Importar handlers registra os consumers
# Sem este import, @consumer e @on_event nao sao executados
from src.apps.notifications import handlers

configure_messaging(
    broker="kafka",
    bootstrap_servers="kafka:9092",
)

# Este servico pode nao ter rotas HTTP
# Funciona apenas como consumer de eventos
app = CoreApp(title="Notifications API")
```

### Docker Compose

```yaml
# notifications-api/docker-compose.yml
version: "3.8"

services:
  # API HTTP (opcional - pode ser apenas consumer)
  notifications-api:
    build: .
    ports:
      - "8002:8000"
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:postgres@postgres:5432/notifications
      KAFKA_BOOTSTRAP_SERVERS: kafka:9092
    networks:
      - services-network

  # Consumer como processo separado
  # ESSENCIAL: Sem este servico, eventos nao sao processados
  notifications-consumer:
    build: .
    command: core consumer  # Executa todos os handlers registrados
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:postgres@postgres:5432/notifications
      KAFKA_BOOTSTRAP_SERVERS: kafka:9092
    networks:
      - services-network
    depends_on:
      - kafka
    # Em producao, considere replicas para alta disponibilidade
    # deploy:
    #   replicas: 2

networks:
  services-network:
    external: true
```

## Execucao

```bash
# 1. Iniciar infraestrutura compartilhada
cd /services
docker compose up -d

# 2. Aguardar Kafka estar pronto (healthcheck)
docker compose logs -f kafka

# 3. Iniciar Orders API
cd orders-api
docker compose up -d

# 4. Iniciar Notifications API + Consumer
cd ../notifications-api
docker compose up -d
```

## Fluxo de Dados

```
[Cliente] --POST /orders/--> [Orders API]
                                  |
                                  | 1. Salva pedido no banco
                                  | 2. Publica "orders.created" no Kafka
                                  |
                                  v
                             [Kafka]
                                  |
                                  | 3. Entrega mensagem ao consumer group
                                  |
                                  v
                        [Notifications Consumer]
                                  |
                                  | 4. Cria notificacao no banco
                                  | 5. Envia email
```

**Consistencia eventual**: O email pode ser enviado segundos apos a criacao do pedido. Se o consumer estiver fora do ar, mensagens ficam no Kafka ate serem processadas (retencao configuravel).

## Teste Manual

```bash
# Criar pedido
curl -X POST http://localhost:8001/api/v1/orders/ \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1, "user_email": "user@example.com", "total": "99.99"}'

# Aguardar processamento (1-2 segundos)
sleep 2

# Verificar notificacao criada
curl http://localhost:8002/api/v1/notifications/
```

**Debug**: Se notificacoes nao aparecem, verifique logs do consumer:
```bash
docker compose logs -f notifications-consumer
```

---

Proximo: [Background Tasks](06-tasks.md) - Execucao de tarefas em background com workers.
