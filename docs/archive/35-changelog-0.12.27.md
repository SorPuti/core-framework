# Changelog 0.12.27

**Data:** 2026-02-04

## Resumo

Refatoração completa do sistema de configuração e Kafka para ser verdadeiramente **plug-and-play**. Agora basta configurar o `.env` e tudo funciona automaticamente.

## Mudanças Principais

### 1. Configuração Centralizada

**Antes:** Múltiplas configurações separadas (`MessagingSettings`, `TaskSettings`, etc.)

**Agora:** Tudo em um único `Settings` que carrega automaticamente do `.env`

```env
# .env - tudo em um lugar
DATABASE_URL=postgresql+asyncpg://localhost/myapp
KAFKA_BACKEND=confluent
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
TASK_WORKER_CONCURRENCY=8
```

```python
# Funciona automaticamente - sem chamar configure()
from core.messaging import get_producer
producer = get_producer()  # Já usa o backend certo do .env
```

### 2. Kafka Backends Compatíveis (Plug-and-Play)

Os backends `aiokafka` e `confluent` agora são 100% compatíveis:

- **ConfluentConsumer**: Adicionado event routing igual ao KafkaConsumer
- **Comportamento de `wait`**: Padronizado via configuração `KAFKA_FIRE_AND_FORGET`
- **`flush()` do KafkaProducer**: Agora retorna `int` conforme interface base
- **Troca de backend**: Apenas mude `KAFKA_BACKEND` no `.env`

### 3. Worker Melhorado

```python
from core.messaging import Worker

class MyWorker(Worker):
    input_topic = "events"
    batch_size = 1000
    batch_timeout = 10.0
    
    async def process_batch(self, events):
        # Processa batch
        pass

# Acessar nome
print(MyWorker.name)  # "MyWorker"

# Rodar
await MyWorker.run()  # Mais simples
await run_worker(MyWorker)  # Passa classe, não string
```

### 4. Novas Configurações no Settings

| Configuração | Tipo | Padrão | Descrição |
|-------------|------|--------|-----------|
| `kafka_enabled` | bool | False | Habilita Kafka |
| `kafka_backend` | str | "aiokafka" | Backend: aiokafka ou confluent |
| `kafka_fire_and_forget` | bool | False | Não aguardar confirmação |
| `task_enabled` | bool | False | Habilita tasks |
| `task_worker_concurrency` | int | 4 | Workers paralelos |

## Breaking Changes

Nenhum. Código existente continua funcionando.

## Arquivos Modificados

- `core/config.py` - Settings centralizado com todas as configurações
- `core/messaging/config.py` - Simplificado, usa Settings global
- `core/tasks/config.py` - Simplificado, usa Settings global
- `core/messaging/registry.py` - Usa get_settings() diretamente
- `core/messaging/workers.py` - Worker.name, Worker.run(), batch support
- `core/messaging/confluent/consumer.py` - Event routing, logging, task management
- `core/messaging/confluent/producer.py` - wait padrão via settings
- `core/messaging/kafka/producer.py` - flush() retorna int, wait via settings

## Nova Documentação

- `docs/34-kafka-backends.md` - Guia completo dos backends Kafka
