# Messaging

Sistema de mensageria plug-and-play para comunicação entre serviços. Suporta Kafka (aiokafka ou confluent-kafka), RabbitMQ e Redis.

## Quick Start

```python
from core.messaging import publish

# Publicar mensagem em 1 linha
await publish("user-events", {"user_id": 1, "action": "created"})
```

## Configuração

### Via core.toml (Recomendado)

```toml
# core.toml
[messaging]
message_broker = "kafka"
kafka_bootstrap_servers = "localhost:9092"
kafka_backend = "confluent"  # ou "aiokafka"
kafka_fire_and_forget = true
```

### Via Variáveis de Ambiente

```env
MESSAGE_BROKER=kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_BACKEND=confluent
KAFKA_FIRE_AND_FORGET=true
KAFKA_SCHEMA_REGISTRY_URL=http://schema-registry:8081
```

### Via Código

```python
from core.messaging import configure_messaging

configure_messaging(
    message_broker="kafka",
    kafka_bootstrap_servers="localhost:9092",
    kafka_backend="confluent",
    kafka_fire_and_forget=True,
    kafka_schema_registry_url="http://schema-registry:8081",
)
```

### Todas as Configurações Disponíveis

| Configuração | Tipo | Padrão | Descrição |
|--------------|------|--------|-----------|
| `message_broker` | str | "kafka" | Broker: "kafka", "redis", "rabbitmq", "memory" |
| `kafka_backend` | str | "aiokafka" | Backend Kafka: "aiokafka" (async) ou "confluent" (librdkafka) |
| `kafka_bootstrap_servers` | str | "localhost:9092" | Servidores Kafka (separados por vírgula) |
| `kafka_schema_registry_url` | str | None | URL do Schema Registry para Avro |
| `kafka_fire_and_forget` | bool | False | Se True, não aguarda confirmação do broker |
| `kafka_security_protocol` | str | "PLAINTEXT" | Protocolo: PLAINTEXT, SSL, SASL_PLAINTEXT, SASL_SSL |
| `kafka_sasl_mechanism` | str | None | Mecanismo SASL: PLAIN, SCRAM-SHA-256, SCRAM-SHA-512 |
| `kafka_sasl_username` | str | None | Usuário SASL |
| `kafka_sasl_password` | str | None | Senha SASL |
| `kafka_compression_type` | str | "none" | Compressão: none, gzip, snappy, lz4, zstd |
| `kafka_linger_ms` | int | 0 | Tempo para acumular batch (ms) |
| `kafka_max_batch_size` | int | 16384 | Tamanho máximo do batch (bytes) |

### Comparação de Backends Kafka

| Backend | Throughput | Latência | Features | Quando Usar |
|---------|------------|----------|----------|-------------|
| `aiokafka` | Alto | Baixa | Async nativo | Apps FastAPI simples |
| `confluent` | Muito Alto | Muito Baixa | Schema Registry, Avro, Transações | Enterprise, alta performance |

## Publicação de Mensagens

### Método Simples: `publish()`

```python
from core.messaging import publish

# Publicar dict simples
await publish("user-events", {"user_id": 1, "email": "user@example.com"})

# Com chave de partição (garante ordenação por chave)
await publish("user-events", {"user_id": 1}, key="user-1")

# Aguardar confirmação do broker
await publish("user-events", data, wait=True)
```

### Com Topic Class (Validação de Schema)

```python
from core.messaging import publish, Topic
from pydantic import BaseModel

class UserCreatedEvent(BaseModel):
    user_id: int
    email: str
    created_at: datetime

class UserEvents(Topic):
    name = "user-events"
    schema = UserCreatedEvent  # Valida automaticamente

# Publicar - valida contra o schema
await publish(UserEvents, {"user_id": 1, "email": "test@example.com"})

# Também aceita Pydantic model diretamente
event = UserCreatedEvent(user_id=1, email="test@example.com", created_at=datetime.now())
await publish(UserEvents, event)
```

### Com Decorator @event (ViewSets)

```python
from core import ModelViewSet, action
from core.messaging import event

class UserViewSet(ModelViewSet):
    model = User
    
    @action(methods=["POST"], detail=False)
    @event("user.created", topic="user-events", key_field="id")
    async def register(self, request, db, **kwargs):
        """
        Evento publicado automaticamente após sucesso.
        O retorno do método se torna o payload do evento.
        """
        body = await request.json()
        user = await User.create_user(email=body["email"], password=body["password"], db=db)
        return {"id": user.id, "email": user.email}
```

### Publicação Manual (Controle Total)

```python
from core.messaging import get_producer

producer = get_producer()

# Garantir que está conectado
await producer.start()

# Enviar com confirmação
await producer.send("topic", {"key": "value"}, wait=True)

# Fire-and-forget (mais rápido)
await producer.send_fire_and_forget("topic", {"key": "value"})

# Batch fire-and-forget
events = [{"id": i} for i in range(1000)]
count = await producer.send_batch_fire_and_forget("topic", events)

# Garantir entrega de todos os pendentes
await producer.flush()
```

## Topic Classes

Defina tópicos como classes para organização e validação:

```python
from core.messaging import Topic, EventTopic, CommandTopic, StateTopic
from pydantic import BaseModel

# Schema do evento
class OrderCreatedEvent(BaseModel):
    order_id: int
    user_id: int
    total: float
    items: list[dict]

# Topic com configurações
class OrderEvents(Topic):
    name = "order-events"
    schema = OrderCreatedEvent
    partitions = 6
    replication_factor = 3
    retention_ms = 7 * 24 * 60 * 60 * 1000  # 7 dias
    cleanup_policy = "delete"
    value_serializer = "json"  # ou "avro"

# Topics pré-definidos
class OrderCreated(EventTopic):
    """Eventos são fatos imutáveis."""
    name = "order.created"
    schema = OrderCreatedEvent

class SendEmail(CommandTopic):
    """Commands são requisições de ação."""
    name = "email.send"
    schema = SendEmailCommand

class UserState(StateTopic):
    """State topics usam compaction."""
    name = "user.state"
    schema = UserStateModel
```

### Listar Topics Registrados

```python
from core.messaging import get_all_topics, get_topic

# Todos os topics
topics = get_all_topics()
for name, topic_class in topics.items():
    print(f"{name}: {topic_class.schema}")

# Topic específico
order_topic = get_topic("order-events")
```

## Avro Schemas

### Auto-Geração a partir de Pydantic

```python
from core.messaging import AvroModel
from datetime import datetime
from typing import Optional

class UserEvent(AvroModel):
    __avro_namespace__ = "com.myapp.events"
    
    user_id: int
    email: str
    created_at: datetime
    roles: list[str] = []
    metadata: dict[str, str] | None = None

# Schema Avro gerado automaticamente
schema = UserEvent.__avro_schema__()
print(UserEvent.avro_schema_json())
```

Output:
```json
{
  "type": "record",
  "name": "UserEvent",
  "namespace": "com.myapp.events",
  "fields": [
    {"name": "user_id", "type": "long"},
    {"name": "email", "type": "string"},
    {"name": "created_at", "type": {"type": "long", "logicalType": "timestamp-millis"}},
    {"name": "roles", "type": {"type": "array", "items": "string"}, "default": []},
    {"name": "metadata", "type": ["null", {"type": "map", "values": "string"}], "default": null}
  ]
}
```

### Serialização Avro

```python
# Requer: pip install fastavro

# Serializar para bytes
avro_bytes = event.to_avro()

# Deserializar
event = UserEvent.from_avro(avro_bytes)
```

### Decorator @avro_schema

```python
from core.messaging import avro_schema
from pydantic import BaseModel

@avro_schema(namespace="com.myapp.events")
class OrderEvent(BaseModel):
    order_id: int
    total: float

# Agora tem __avro_schema__()
schema = OrderEvent.__avro_schema__()
```

### Publicar com Avro (Confluent)

```python
from core.messaging import get_producer, AvroModel

class Event(AvroModel):
    event_id: str
    event_name: str

producer = get_producer()
await producer.start()

# Enviar com serialização Avro
await producer.send_avro(
    "events",
    {"event_id": "123", "event_name": "test"},
    schema=Event.__avro_schema__(),
)
```

## Workers

Sistema de workers para processar mensagens (inspirado no Celery).

### Decorator Style

```python
from core.messaging import worker

@worker(
    topic="events.raw",
    output_topic="events.enriched",
    concurrency=5,
    max_retries=3,
    retry_backoff="exponential",
)
async def enrich_event(event: dict) -> dict:
    """
    Processa evento e retorna resultado.
    Resultado é publicado automaticamente em output_topic.
    """
    geo = await geoip_lookup(event.get("ip_address"))
    return {**event, **geo, "enriched": True}
```

### Class Style

```python
from core.messaging import Worker
from pydantic import BaseModel

class RawEvent(BaseModel):
    event_id: str
    ip_address: str

class EnrichedEvent(BaseModel):
    event_id: str
    ip_address: str
    country: str
    city: str

class GeolocationWorker(Worker):
    input_topic = "events.raw"
    output_topic = "events.enriched"
    group_id = "geolocation-service"
    concurrency = 10
    max_retries = 3
    retry_backoff = "exponential"
    input_schema = RawEvent
    output_schema = EnrichedEvent
    dlq_topic = "events.dlq"  # Dead letter queue
    
    async def process(self, event: dict) -> dict:
        """Lógica de processamento."""
        geo = await self.lookup_geo(event["ip_address"])
        return {**event, **geo}
    
    async def lookup_geo(self, ip: str) -> dict:
        """Método auxiliar."""
        # Implementação...
        return {"country": "BR", "city": "São Paulo"}
    
    async def on_error(self, event: dict, error: Exception) -> None:
        """Chamado quando processamento falha após todos os retries."""
        logger.error(f"Failed to process event: {event}, error: {error}")
    
    async def on_success(self, event: dict, result: dict) -> None:
        """Chamado após processamento bem-sucedido."""
        logger.info(f"Processed event: {event['event_id']}")
```

### Parâmetros do Worker

| Parâmetro | Tipo | Padrão | Descrição |
|-----------|------|--------|-----------|
| `topic` / `input_topic` | str | - | Tópico de entrada (obrigatório) |
| `output_topic` | str | None | Tópico para publicar resultados |
| `group_id` | str | nome da função/classe | ID do consumer group |
| `concurrency` | int | 1 | Número de workers paralelos |
| `max_retries` | int | 3 | Tentativas antes de enviar para DLQ |
| `retry_backoff` | str | "exponential" | Estratégia: "linear", "exponential", "fixed" |
| `input_schema` | BaseModel | None | Schema para validar entrada |
| `output_schema` | BaseModel | None | Schema para validar saída |
| `dlq_topic` | str | None | Tópico para mensagens que falharam |

### Executar Workers

```bash
# Worker específico
core runworker enrich_event

# Todos os workers registrados
core runworker all

# Listar workers disponíveis
core workers
```

### Retry Policy

```python
from core.messaging import worker, RetryPolicy

@worker(
    topic="payments",
    max_retries=5,
    retry_backoff="exponential",  # 1s, 2s, 4s, 8s, 16s
)
async def process_payment(payment: dict) -> dict:
    result = await payment_gateway.charge(payment)
    if not result.success:
        raise Exception("Payment failed")  # Aciona retry
    return result
```

Estratégias de backoff:
- `"fixed"`: Sempre o mesmo delay (1s)
- `"linear"`: Delay aumenta linearmente (1s, 2s, 3s, 4s...)
- `"exponential"`: Delay dobra a cada tentativa (1s, 2s, 4s, 8s...)

## Consumers (Classe Tradicional)

Para consumo mais customizado:

```python
from core.messaging import consumer, on_event
from core.messaging.base import Event

@consumer("order-service", topics=["user-events", "payment-events"])
class OrderEventsConsumer:
    """
    Consumer baseado em classe.
    Agrupa handlers relacionados.
    """
    
    @on_event("user.created")
    async def handle_user_created(self, event: Event, db):
        """Cria pedido de boas-vindas para novo usuário."""
        await Order.create_welcome_order(
            user_id=event.data["id"],
            db=db,
        )
    
    @on_event("payment.completed")
    async def handle_payment(self, event: Event, db):
        """Marca pedido como pago."""
        await Order.mark_paid(
            order_id=event.data["order_id"],
            db=db,
        )
```

### Handler Simples

```python
from core.messaging import message_handler

@message_handler(topic="orders.created", max_retries=3, retry_delay=5)
async def handle_order(message: dict, db):
    """Handler baseado em função."""
    await send_confirmation_email(message["user_email"], message["order_id"])
```

### Executar Consumer

```bash
core consumer --group order-service --topic user-events --topic payment-events
```

## Alta Performance

### Configuração para Alto Throughput

```toml
# core.toml
[messaging]
message_broker = "kafka"
kafka_backend = "confluent"
kafka_fire_and_forget = true
kafka_linger_ms = 5
kafka_max_batch_size = 32768
kafka_compression_type = "lz4"
```

### Métodos de Alta Performance

```python
from core.messaging import get_producer

producer = get_producer()

# Fire-and-forget: ~15.000 msg/sec
for event in events:
    await producer.send_fire_and_forget("topic", event)

# Batch fire-and-forget: ~25.000 msg/sec
count = await producer.send_batch_fire_and_forget("topic", events)

# Flush no final
await producer.flush()
```

### Comparação de Performance

| Método | Latência P50 | Throughput |
|--------|--------------|------------|
| `send(wait=True)` | 15ms | ~100/sec |
| `send(wait=False)` | 0.5ms | ~5.000/sec |
| `send_fire_and_forget()` | 0.1ms | ~15.000/sec |
| `send_batch_fire_and_forget()` | 0.05ms/msg | ~25.000/sec |

### Exemplo: Endpoint de Tracking

```python
from core import ViewSet, action
from core.messaging import publish, Topic

class TrackingEvents(Topic):
    name = "tracking.events"

class TrackingViewSet(ViewSet):
    @action(methods=["POST"], detail=False)
    async def track(self, request, **kwargs):
        """
        POST /tracking/track
        
        Recebe milhares de eventos/segundo.
        """
        body = await request.json()
        events = body.get("events", [])
        
        producer = get_producer()
        count = await producer.send_batch_fire_and_forget(
            TrackingEvents.name,
            events,
        )
        
        return {"queued": count}
```

## Lifecycle Automático

O framework gerencia automaticamente o ciclo de vida dos producers:

```python
from core import CoreApp

app = CoreApp(title="My API")

# Producers são:
# - Criados automaticamente no primeiro uso
# - Reutilizados via singleton/pool
# - Flushed automaticamente no shutdown
```

Para controle manual:

```python
from core.messaging.registry import start_all_producers, stop_all_producers

# No startup
await start_all_producers()

# No shutdown
await stop_all_producers()
```

## Exemplos Completos

### Event Sourcing

```python
from core.messaging import Topic, AvroModel, publish, worker
from datetime import datetime

# Eventos
class OrderCreated(AvroModel):
    order_id: str
    user_id: int
    items: list[dict]
    total: float
    created_at: datetime

class OrderPaid(AvroModel):
    order_id: str
    payment_id: str
    paid_at: datetime

# Topics
class OrderEventsTopic(Topic):
    name = "order.events"
    partitions = 6

# Publicar eventos
async def create_order(user_id: int, items: list) -> str:
    order_id = str(uuid.uuid4())
    
    event = OrderCreated(
        order_id=order_id,
        user_id=user_id,
        items=items,
        total=sum(i["price"] for i in items),
        created_at=datetime.now(),
    )
    
    await publish(OrderEventsTopic, event.model_dump(), key=order_id)
    return order_id

# Processar eventos
@worker(topic="order.events", output_topic="order.projections")
async def project_order(event: dict) -> dict:
    """Projeta eventos em read model."""
    return {
        "order_id": event["order_id"],
        "status": "created",
        "total": event["total"],
    }
```

### CQRS com Kafka

```python
# Commands
class CreateOrderCommand(Topic):
    name = "orders.commands.create"
    schema = CreateOrderInput

# Events
class OrderCreatedEvent(Topic):
    name = "orders.events.created"
    schema = OrderCreatedOutput

# Command Handler
@worker(topic="orders.commands.create", output_topic="orders.events.created")
async def handle_create_order(command: dict) -> dict:
    # Validar
    # Criar order
    # Retornar evento
    return {"order_id": "123", "status": "created"}

# Event Handler (atualiza read model)
@worker(topic="orders.events.created")
async def update_read_model(event: dict) -> None:
    await OrderReadModel.upsert(event)
```

### Microserviços

```python
# Service A: User Service
class UserEvents(Topic):
    name = "user.events"

@worker(topic="user.commands.create", output_topic="user.events")
async def create_user(command: dict) -> dict:
    user = await User.create(**command)
    return {"event": "user.created", "user_id": user.id}

# Service B: Order Service
@worker(topic="user.events")
async def handle_user_event(event: dict) -> None:
    if event["event"] == "user.created":
        await create_welcome_order(event["user_id"])
```

## CLI Commands

```bash
# Workers
core runworker <name>       # Rodar worker específico
core runworker all          # Rodar todos os workers
core workers                # Listar workers registrados

# Consumers
core consumer -g <group> -t <topic>  # Rodar consumer

# Topics (Kafka)
core topics list            # Listar tópicos
core topics create <name>   # Criar tópico
core topics delete <name>   # Deletar tópico
```

## Troubleshooting

### "Producer not found"

```python
# Solução: Producer é criado automaticamente
from core.messaging import get_producer
producer = get_producer()  # Cria se não existir
```

### "aiokafka/confluent-kafka not installed"

```bash
# Para aiokafka (padrão)
pip install aiokafka

# Para confluent (recomendado para produção)
pip install confluent-kafka

# Para Avro
pip install fastavro
pip install confluent-kafka[avro]
```

### "Too many open files"

O framework usa singleton/pool automaticamente. Se ainda ocorrer:

```toml
# core.toml
[messaging]
kafka_backend = "confluent"  # Usa connection pooling melhor
```

### Schema Registry Connection Failed

```python
# Verificar URL
configure_messaging(
    kafka_schema_registry_url="http://schema-registry:8081",
)

# Ou via env
KAFKA_SCHEMA_REGISTRY_URL=http://schema-registry:8081
```

---

Próximo: [Multi-Service Architecture](05-multi-service.md)
