# Topics

Sistema de definição de tópicos como classes para organização e validação.

## Quick Start

```python
from core.messaging import Topic, publish

class UserEvents(Topic):
    name = "user-events"

await publish(UserEvents, {"user_id": 1})
```

## Definindo Topics

### Topic Básico

```python
from core.messaging import Topic

class OrderEvents(Topic):
    name = "order-events"
```

### Com Schema (Validação)

```python
from core.messaging import Topic
from pydantic import BaseModel

class OrderCreatedEvent(BaseModel):
    order_id: str
    user_id: int
    total: float
    items: list[dict]

class OrderEvents(Topic):
    name = "order-events"
    schema = OrderCreatedEvent  # Valida mensagens automaticamente
```

### Configuração Completa

```python
class OrderEvents(Topic):
    # Nome do tópico (obrigatório)
    name = "order-events"
    
    # Schema Pydantic para validação
    schema = OrderCreatedEvent
    
    # Configuração Kafka
    partitions = 6
    replication_factor = 3
    retention_ms = 7 * 24 * 60 * 60 * 1000  # 7 dias
    cleanup_policy = "delete"  # "delete", "compact", "delete,compact"
    
    # Serialização
    key_serializer = "string"  # "string", "json", "avro"
    value_serializer = "json"  # "json", "avro"
```

## Tipos de Topics

O framework fornece classes base para padrões comuns:

### EventTopic

Para eventos (fatos imutáveis):

```python
from core.messaging import EventTopic

class UserCreated(EventTopic):
    """Eventos são fatos que aconteceram."""
    name = "user.created"
    schema = UserCreatedEvent
```

Características:
- `cleanup_policy = "delete"` (padrão)
- Eventos são imutáveis
- Ordenação por partição

### CommandTopic

Para comandos (requisições de ação):

```python
from core.messaging import CommandTopic

class SendEmail(CommandTopic):
    """Commands são requisições para executar ação."""
    name = "email.send"
    schema = SendEmailCommand
```

Características:
- `cleanup_policy = "delete"` (padrão)
- Processados uma vez
- Podem falhar/retry

### StateTopic

Para state (compacted topics):

```python
from core.messaging import StateTopic

class UserState(StateTopic):
    """State topics mantêm último valor por chave."""
    name = "user.state"
    schema = UserStateModel
```

Características:
- `cleanup_policy = "compact"`
- Mantém apenas último valor por chave
- Ideal para materialized views

## Publicando

### Com Topic Class

```python
from core.messaging import publish

# Valida contra schema automaticamente
await publish(OrderEvents, {
    "order_id": "123",
    "user_id": 1,
    "total": 99.90,
    "items": [{"product": "A", "qty": 2}],
})

# Com Pydantic model
event = OrderCreatedEvent(
    order_id="123",
    user_id=1,
    total=99.90,
    items=[{"product": "A", "qty": 2}],
)
await publish(OrderEvents, event)
```

### Com Chave de Partição

```python
# Garante ordenação por order_id
await publish(OrderEvents, event, key="order-123")
```

### Validação de Schema

```python
class StrictOrderEvents(Topic):
    name = "order-events"
    schema = OrderCreatedEvent

# Isso levanta ValidationError
await publish(StrictOrderEvents, {"invalid": "data"})
```

## Registry de Topics

### Listar Topics

```python
from core.messaging import get_all_topics

topics = get_all_topics()
for name, topic_class in topics.items():
    print(f"{name}: partitions={topic_class.partitions}")
```

### Obter Topic

```python
from core.messaging import get_topic

order_topic = get_topic("order-events")
if order_topic:
    print(f"Schema: {order_topic.schema}")
```

### Registro Manual

```python
from core.messaging import register_topic

@register_topic
class MyTopic(Topic):
    name = "my-topic"
```

## Configuração de Tópicos

### Retention

```python
class LogEvents(Topic):
    name = "logs"
    retention_ms = 24 * 60 * 60 * 1000  # 24 horas
```

### Compaction

```python
class UserCache(Topic):
    name = "user.cache"
    cleanup_policy = "compact"
    # Mantém apenas último valor por chave
```

### Partições

```python
class HighThroughputEvents(Topic):
    name = "events"
    partitions = 12  # Mais partições = mais paralelismo
    replication_factor = 3  # Redundância
```

## Padrões de Uso

### Domínio por Namespace

```python
# users/topics.py
class UserCreated(EventTopic):
    name = "users.created"
    schema = UserCreatedEvent

class UserUpdated(EventTopic):
    name = "users.updated"
    schema = UserUpdatedEvent

# orders/topics.py
class OrderCreated(EventTopic):
    name = "orders.created"
    schema = OrderCreatedEvent

class OrderShipped(EventTopic):
    name = "orders.shipped"
    schema = OrderShippedEvent
```

### Versionamento

```python
class UserEventsV1(Topic):
    name = "users.events.v1"
    schema = UserEventV1

class UserEventsV2(Topic):
    name = "users.events.v2"
    schema = UserEventV2
```

### Dead Letter Queue

```python
class OrderEvents(Topic):
    name = "orders.events"
    schema = OrderEvent

class OrderEventsDLQ(Topic):
    name = "orders.events.dlq"
    retention_ms = 30 * 24 * 60 * 60 * 1000  # 30 dias
```

## Integração com Workers

```python
from core.messaging import Topic, worker

class RawEvents(Topic):
    name = "events.raw"

class EnrichedEvents(Topic):
    name = "events.enriched"
    schema = EnrichedEvent

@worker(
    topic=RawEvents.name,
    output_topic=EnrichedEvents.name,
)
async def enrich_event(event: dict) -> dict:
    return {**event, "enriched": True}
```

## Integração com Avro

```python
from core.messaging import Topic, AvroModel

class OrderEvent(AvroModel):
    __avro_namespace__ = "com.myapp.orders"
    
    order_id: str
    total: float

class OrderEvents(Topic):
    name = "order-events"
    schema = OrderEvent
    value_serializer = "avro"

# Publicar com Avro
await publish(OrderEvents, {"order_id": "123", "total": 99.90})
```

## CLI

```bash
# Listar tópicos no Kafka
core topics list

# Criar tópico
core topics create order-events --partitions 6 --replication 3

# Deletar tópico
core topics delete order-events --yes
```

## Boas Práticas

### 1. Convenção de Nomes

```python
# Bom: domínio.entidade.ação
class UserCreated(EventTopic):
    name = "users.user.created"

class OrderShipped(EventTopic):
    name = "orders.order.shipped"

# Evitar: nomes genéricos
class Events(Topic):
    name = "events"  # Muito genérico
```

### 2. Um Schema por Topic

```python
# Bom: schema específico
class UserCreated(EventTopic):
    name = "users.created"
    schema = UserCreatedEvent

# Evitar: múltiplos tipos de evento no mesmo topic
class UserEvents(Topic):
    name = "users.events"
    # Sem schema - aceita qualquer coisa
```

### 3. Partições Adequadas

```python
# Para alto throughput
class HighVolumeEvents(Topic):
    name = "analytics.events"
    partitions = 12  # Permite 12 consumers paralelos

# Para baixo volume
class ConfigChanges(Topic):
    name = "config.changes"
    partitions = 1  # Garante ordenação global
```

### 4. Documentação

```python
class OrderCreated(EventTopic):
    """
    Emitido quando um novo pedido é criado.
    
    Producers:
        - order-service
    
    Consumers:
        - notification-service
        - analytics-service
        - inventory-service
    """
    name = "orders.created"
    schema = OrderCreatedEvent
```

---

Próximo: [Settings Reference](09-settings.md)
