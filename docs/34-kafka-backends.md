# Kafka Backends

O Core Framework suporta dois backends Kafka totalmente compatíveis e intercambiáveis: **aiokafka** e **confluent-kafka**. Esta documentação explica como escolher e configurar cada backend.

## Visão Geral

| Backend | Biblioteca | Características |
|---------|-----------|-----------------|
| `aiokafka` | aiokafka | Async nativo, leve, ideal para apps simples |
| `confluent` | confluent-kafka | librdkafka (C), alto desempenho, Schema Registry, Avro |

## Troca de Backend (Plug-and-Play)

Ambos os backends implementam a mesma interface, permitindo troca sem alteração de código.

### Via .env (Recomendado)

```env
KAFKA_ENABLED=true
KAFKA_BACKEND=confluent
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
```

### Via código (ANTES de iniciar a app)

```python
from core import configure

# Configura TUDO em um lugar só
configure(
    kafka_enabled=True,
    kafka_backend="confluent",
    kafka_bootstrap_servers="kafka:9092",
    database_url="postgresql+asyncpg://localhost/myapp",
)
```

## Quando Usar Cada Backend

### aiokafka (Padrão)

Ideal para:
- Aplicações FastAPI/Starlette simples
- Desenvolvimento local e testes
- Quando não precisa de Schema Registry
- Projetos que priorizam simplicidade

```bash
pip install aiokafka
```

### confluent-kafka

Ideal para:
- Alta performance (>10k msg/sec)
- Integração com Schema Registry (Avro)
- Ambientes enterprise
- Quando precisa de recursos avançados (transações, exactly-once)

```bash
# Básico
pip install confluent-kafka

# Com suporte Avro
pip install confluent-kafka[avro]
```

## Uso com Producer

Ambos os backends funcionam de forma idêntica:

```python
from core.messaging import get_producer, publish

# Método 1: Função publish (recomendado)
await publish("user-events", {"user_id": 1, "action": "created"})

# Método 2: Producer direto
producer = get_producer()  # Retorna o backend correto automaticamente
await producer.start()
await producer.send("user-events", {"user_id": 1})

# Fire-and-forget (máximo throughput)
await producer.send_fire_and_forget("events", {"id": 1})
await producer.flush()  # Garante entrega no final
```

### Comportamento de Wait

O comportamento padrão é controlado pela configuração `kafka_fire_and_forget`:

```toml
# core.toml
[messaging]
kafka_fire_and_forget = false  # Padrão: aguarda confirmação
```

Você também pode especificar por chamada:

```python
# Aguarda confirmação (mais confiável)
await publish("events", data, wait=True)

# Fire-and-forget (mais rápido)
await publish("events", data, wait=False)

# Usa configuração padrão
await publish("events", data)  # wait=None usa kafka_fire_and_forget
```

## Uso com Consumer

### Criação Automática

```python
from core.messaging import create_consumer

# Cria consumer com backend correto baseado nas configurações
consumer = create_consumer(
    group_id="my-service",
    topics=["user-events", "payment-events"],
)

await consumer.start()
```

### Criação Manual

```python
from core.messaging import get_kafka_consumer_class

# Obtém a classe correta baseada nas configurações
ConsumerClass = get_kafka_consumer_class()

consumer = ConsumerClass(
    group_id="my-service",
    topics=["user-events"],
)
await consumer.start()
```

### Com Handler Customizado

```python
async def my_handler(message: dict):
    print(f"Recebido: {message}")

consumer = create_consumer(
    group_id="my-service",
    topics=["user-events"],
    message_handler=my_handler,
)
await consumer.start()
```

### Com Event Routing (Decorators)

Ambos os backends suportam o sistema de event routing:

```python
from core.messaging import consumer, on_event
from core.messaging.base import Event

@consumer("order-service", topics=["user-events"])
class UserEventsConsumer:
    
    @on_event("user.created")
    async def handle_user_created(self, event: Event, db):
        print(f"Usuário criado: {event.data}")
    
    @on_event("user.updated")
    async def handle_user_updated(self, event: Event, db):
        print(f"Usuário atualizado: {event.data}")
```

## Avro e Schema Registry (Apenas Confluent)

O backend Confluent suporta serialização Avro com Schema Registry:

```python
from core.messaging import configure_messaging, AvroModel, get_producer

# Configurar Schema Registry
configure_messaging(
    kafka_backend="confluent",
    kafka_schema_registry_url="http://schema-registry:8081",
)

# Definir schema Avro
class UserEvent(AvroModel):
    __avro_namespace__ = "com.myapp.events"
    
    user_id: int
    email: str
    created_at: datetime

# Publicar com Avro
producer = get_producer()
await producer.start()
await producer.send_avro(
    "user-events",
    {"user_id": 1, "email": "user@example.com"},
    schema=UserEvent.__avro_schema__(),
)
```

## Configuração Completa

Todas as configurações ficam em **UM lugar só** (Settings centralizado).

### Via .env

```env
# Básico
KAFKA_ENABLED=true
KAFKA_BACKEND=confluent
KAFKA_BOOTSTRAP_SERVERS=kafka1:9092,kafka2:9092

# Performance
KAFKA_FIRE_AND_FORGET=true
KAFKA_COMPRESSION_TYPE=lz4
KAFKA_LINGER_MS=5
KAFKA_MAX_BATCH_SIZE=32768

# Schema Registry (apenas confluent)
KAFKA_SCHEMA_REGISTRY_URL=http://schema-registry:8081

# Segurança
KAFKA_SECURITY_PROTOCOL=SASL_SSL
KAFKA_SASL_MECHANISM=PLAIN
KAFKA_SASL_USERNAME=user
KAFKA_SASL_PASSWORD=password
KAFKA_SSL_CAFILE=/path/to/ca.pem

# Consumer
KAFKA_AUTO_OFFSET_RESET=earliest
KAFKA_ENABLE_AUTO_COMMIT=true
KAFKA_SESSION_TIMEOUT_MS=10000
```

### Via código

```python
from core import configure

configure(
    # Básico
    kafka_enabled=True,
    kafka_backend="confluent",
    kafka_bootstrap_servers="kafka1:9092,kafka2:9092",
    
    # Performance
    kafka_fire_and_forget=True,
    kafka_compression_type="lz4",
    kafka_linger_ms=5,
    
    # Schema Registry
    kafka_schema_registry_url="http://schema-registry:8081",
    
    # Segurança
    kafka_security_protocol="SASL_SSL",
    kafka_sasl_mechanism="PLAIN",
    kafka_sasl_username="user",
    kafka_sasl_password="password",
)
```

## Benchmarks

Performance aproximada em um ambiente típico:

| Operação | aiokafka | confluent |
|----------|----------|-----------|
| `send(wait=True)` | ~100/sec | ~150/sec |
| `send(wait=False)` | ~5,000/sec | ~8,000/sec |
| `send_fire_and_forget()` | ~15,000/sec | ~20,000/sec |
| `send_batch_fire_and_forget()` | ~25,000/sec | ~35,000/sec |

> **Nota:** Resultados variam conforme hardware, rede e configuração do Kafka.

## Migração Entre Backends

Para migrar de um backend para outro:

1. **Instale a biblioteca necessária:**
   ```bash
   pip install confluent-kafka  # ou aiokafka
   ```

2. **Altere a configuração:**
   ```toml
   kafka_backend = "confluent"  # ou "aiokafka"
   ```

3. **Reinicie a aplicação.** Não é necessário alterar código.

### Considerações

- Ambos os backends usam a mesma interface de Producer e Consumer
- O comportamento padrão de `wait` agora é consistente (usa `kafka_fire_and_forget`)
- Event routing funciona igual em ambos os backends
- Schema Registry e Avro são exclusivos do backend `confluent`

## Troubleshooting

### "aiokafka/confluent-kafka not installed"

Instale a biblioteca correspondente:

```bash
pip install aiokafka        # Para backend aiokafka
pip install confluent-kafka # Para backend confluent
```

### "Schema Registry not configured"

Configure a URL do Schema Registry:

```python
configure_messaging(
    kafka_backend="confluent",
    kafka_schema_registry_url="http://schema-registry:8081",
)
```

### Consumer não processa eventos

Verifique se:
1. O consumer está inscrito nos tópicos corretos
2. Os eventos têm o campo `name` para routing
3. Existem handlers registrados para o evento

```python
# Verificar handlers registrados
from core.messaging.registry import get_all_event_handlers

handlers = get_all_event_handlers()
print(handlers)
```

### Performance baixa

Para máxima performance:

```toml
[messaging]
kafka_backend = "confluent"
kafka_fire_and_forget = true
kafka_linger_ms = 5
kafka_compression_type = "lz4"
kafka_max_batch_size = 32768
```

E use métodos fire-and-forget:

```python
producer = get_producer()
await producer.send_batch_fire_and_forget("events", events)
await producer.flush()
```

---

Próximo: [Testing](32-testing.md)
