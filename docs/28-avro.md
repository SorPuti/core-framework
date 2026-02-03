# Avro Schemas

Geração automática de schemas Avro a partir de modelos Pydantic.

## Quick Start

```python
from core.messaging import AvroModel

class UserEvent(AvroModel):
    user_id: int
    email: str

# Schema Avro gerado automaticamente
schema = UserEvent.__avro_schema__()
```

## AvroModel

Classe base que adiciona geração de schema Avro a modelos Pydantic:

```python
from core.messaging import AvroModel
from datetime import datetime
from typing import Optional

class OrderCreatedEvent(AvroModel):
    __avro_namespace__ = "com.myapp.orders"
    
    order_id: str
    user_id: int
    total: float
    currency: str = "BRL"
    items: list[dict]
    created_at: datetime
    metadata: dict[str, str] | None = None
```

### Schema Gerado

```python
print(OrderCreatedEvent.avro_schema_json())
```

```json
{
  "type": "record",
  "name": "OrderCreatedEvent",
  "namespace": "com.myapp.orders",
  "fields": [
    {"name": "order_id", "type": "string"},
    {"name": "user_id", "type": "long"},
    {"name": "total", "type": "double"},
    {"name": "currency", "type": "string", "default": "BRL"},
    {"name": "items", "type": {"type": "array", "items": "string"}},
    {"name": "created_at", "type": {"type": "long", "logicalType": "timestamp-millis"}},
    {"name": "metadata", "type": ["null", {"type": "map", "values": "string"}], "default": null}
  ]
}
```

## Mapeamento de Tipos

### Tipos Básicos

| Python | Avro |
|--------|------|
| `str` | `"string"` |
| `int` | `"long"` |
| `float` | `"double"` |
| `bool` | `"boolean"` |
| `bytes` | `"bytes"` |
| `None` | `"null"` |

### Tipos Complexos

| Python | Avro |
|--------|------|
| `list[T]` | `{"type": "array", "items": T}` |
| `dict[str, T]` | `{"type": "map", "values": T}` |
| `T \| None` | `["null", T]` |
| `Optional[T]` | `["null", T]` |

### Tipos Temporais

| Python | Avro |
|--------|------|
| `datetime` | `{"type": "long", "logicalType": "timestamp-millis"}` |
| `date` | `{"type": "int", "logicalType": "date"}` |
| `time` | `{"type": "int", "logicalType": "time-millis"}` |

### Tipos Especiais

| Python | Avro |
|--------|------|
| `UUID` | `{"type": "string", "logicalType": "uuid"}` |
| `Decimal` | `{"type": "bytes", "logicalType": "decimal", "precision": 38, "scale": 9}` |
| `Enum` | `{"type": "enum", "symbols": [...]}` |

## Exemplos de Tipos

### Campos Opcionais

```python
class Event(AvroModel):
    required_field: str
    optional_field: str | None = None
    optional_with_default: str | None = "default"
```

Schema:
```json
{
  "fields": [
    {"name": "required_field", "type": "string"},
    {"name": "optional_field", "type": ["null", "string"], "default": null},
    {"name": "optional_with_default", "type": ["null", "string"], "default": "default"}
  ]
}
```

### Listas e Dicts

```python
class Event(AvroModel):
    tags: list[str]
    scores: list[float]
    metadata: dict[str, str]
    nested: dict[str, list[int]]
```

Schema:
```json
{
  "fields": [
    {"name": "tags", "type": {"type": "array", "items": "string"}},
    {"name": "scores", "type": {"type": "array", "items": "double"}},
    {"name": "metadata", "type": {"type": "map", "values": "string"}},
    {"name": "nested", "type": {"type": "map", "values": {"type": "array", "items": "long"}}}
  ]
}
```

### Enums

```python
from enum import Enum

class OrderStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class OrderEvent(AvroModel):
    order_id: str
    status: OrderStatus
```

Schema:
```json
{
  "fields": [
    {"name": "order_id", "type": "string"},
    {
      "name": "status",
      "type": {
        "type": "enum",
        "name": "OrderStatus",
        "symbols": ["pending", "processing", "completed", "cancelled"]
      }
    }
  ]
}
```

### Modelos Aninhados

```python
class Address(AvroModel):
    street: str
    city: str
    country: str = "BR"

class User(AvroModel):
    user_id: int
    name: str
    address: Address
    shipping_addresses: list[Address]
```

Schema:
```json
{
  "type": "record",
  "name": "User",
  "fields": [
    {"name": "user_id", "type": "long"},
    {"name": "name", "type": "string"},
    {
      "name": "address",
      "type": {
        "type": "record",
        "name": "Address",
        "fields": [
          {"name": "street", "type": "string"},
          {"name": "city", "type": "string"},
          {"name": "country", "type": "string", "default": "BR"}
        ]
      }
    },
    {
      "name": "shipping_addresses",
      "type": {"type": "array", "items": "Address"}
    }
  ]
}
```

## Serialização

### Para Bytes

```python
# Requer: pip install fastavro

event = OrderCreatedEvent(
    order_id="123",
    user_id=1,
    total=99.90,
    items=[{"product": "A", "qty": 2}],
    created_at=datetime.now(),
)

# Serializar
avro_bytes = event.to_avro()

# Deserializar
restored = OrderCreatedEvent.from_avro(avro_bytes)
```

### Com Confluent Kafka

```python
from core.messaging import get_producer, AvroModel

class Event(AvroModel):
    __avro_namespace__ = "com.myapp.events"
    
    event_id: str
    event_name: str
    data: dict[str, str]

producer = get_producer()
await producer.start()

# Publicar com Avro
await producer.send_avro(
    topic="events",
    message={"event_id": "123", "event_name": "test", "data": {}},
    schema=Event.__avro_schema__(),
)
```

## Decorator @avro_schema

Para adicionar schema Avro a modelos Pydantic existentes:

```python
from core.messaging import avro_schema
from pydantic import BaseModel

@avro_schema(namespace="com.myapp.events")
class UserCreatedEvent(BaseModel):
    user_id: int
    email: str
    created_at: datetime

# Agora tem __avro_schema__()
schema = UserCreatedEvent.__avro_schema__()
```

### Com Nome Customizado

```python
@avro_schema(namespace="com.myapp", name="UserCreated")
class UserCreatedEventV2(BaseModel):
    user_id: int
    email: str
```

Schema terá `"name": "UserCreated"` em vez de `"UserCreatedEventV2"`.

## Schema Registry

### Configuração

```toml
# core.toml
[messaging]
kafka_backend = "confluent"
kafka_schema_registry_url = "http://schema-registry:8081"
```

### Publicar com Schema Registry

```python
from core.messaging import get_producer, AvroModel

class Event(AvroModel):
    event_id: str
    data: dict[str, str]

producer = get_producer()
await producer.start()

# Schema é registrado automaticamente no Schema Registry
await producer.send_avro(
    topic="events",
    message={"event_id": "123", "data": {"key": "value"}},
    schema=Event.__avro_schema__(),
)
```

## Integração com Topics

```python
from core.messaging import Topic, AvroModel, publish

class UserCreatedEvent(AvroModel):
    __avro_namespace__ = "com.myapp.users"
    
    user_id: int
    email: str
    created_at: datetime

class UserEvents(Topic):
    name = "user-events"
    schema = UserCreatedEvent
    value_serializer = "avro"

# Publicar - usa Avro automaticamente
await publish(UserEvents, {
    "user_id": 1,
    "email": "user@example.com",
    "created_at": datetime.now(),
})
```

## Boas Práticas

### 1. Sempre Defina Namespace

```python
class Event(AvroModel):
    __avro_namespace__ = "com.company.service.events"
    ...
```

### 2. Use Defaults para Campos Opcionais

```python
class Event(AvroModel):
    required: str
    optional: str | None = None  # Tem default
    with_default: str = "default_value"
```

### 3. Versionamento de Schemas

```python
# V1
class UserEventV1(AvroModel):
    __avro_namespace__ = "com.myapp.users.v1"
    user_id: int
    email: str

# V2 - adiciona campo opcional (backward compatible)
class UserEventV2(AvroModel):
    __avro_namespace__ = "com.myapp.users.v2"
    user_id: int
    email: str
    phone: str | None = None  # Novo campo opcional
```

### 4. Documentação

```python
from pydantic import Field

class OrderEvent(AvroModel):
    """Evento emitido quando um pedido é criado."""
    
    order_id: str = Field(description="ID único do pedido")
    total: float = Field(description="Valor total em BRL")
    items: list[dict] = Field(description="Lista de itens do pedido")
```

O docstring e descriptions são incluídos no schema Avro como `"doc"`.

## Troubleshooting

### "fastavro not installed"

```bash
pip install fastavro
```

### "Schema Registry connection failed"

```python
# Verificar URL
configure_messaging(
    kafka_schema_registry_url="http://schema-registry:8081",
)
```

### "Schema incompatible"

O Schema Registry valida compatibilidade. Para schemas incompatíveis:

1. Crie nova versão do schema
2. Ou configure compatibility level:

```bash
curl -X PUT -H "Content-Type: application/json" \
  --data '{"compatibility": "NONE"}' \
  http://schema-registry:8081/config/my-topic-value
```

---

Próximo: [Topics](29-topics.md)
