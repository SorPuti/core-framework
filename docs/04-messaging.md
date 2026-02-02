# Messaging

Sistema de mensageria assincrona para comunicacao entre servicos. Suporta Kafka, RabbitMQ e Redis como brokers.

## Configuracao

A configuracao define qual broker usar e como conectar. Deve ser chamada antes de usar qualquer funcionalidade de messaging.

```python
# src/main.py
from core.messaging import configure_messaging

configure_messaging(
    # Broker a ser usado: "kafka", "rabbitmq" ou "redis"
    # Cada broker tem caracteristicas diferentes (ver tabela abaixo)
    broker="kafka",
    
    # Endereco do broker - formato depende do broker escolhido
    bootstrap_servers="localhost:9092",
)
```

**Comparacao de brokers**:

| Broker | Persistencia | Ordenacao | Throughput | Complexidade |
|--------|--------------|-----------|------------|--------------|
| Kafka | Sim | Por particao | Muito alto | Alta |
| RabbitMQ | Configuravel | Por fila | Alto | Media |
| Redis | Nao (padrao) | Por stream | Medio | Baixa |

Configuracao via variaveis de ambiente (alternativa):

```env
# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# RabbitMQ
RABBITMQ_URL=amqp://guest:guest@localhost:5672/

# Redis
REDIS_URL=redis://localhost:6379/0
```

**Nota**: Se ambos (codigo e .env) estiverem configurados, o codigo tem precedencia.

## @event - Publicacao Automatica

O decorator `@event` publica eventos automaticamente quando uma acao do ViewSet e executada com sucesso. O evento e disparado APOS a resposta ser enviada ao cliente (fire-and-forget).

```python
from core import ModelViewSet, action
from core.messaging import event

class UserViewSet(ModelViewSet):
    model = User
    
    @action(methods=["POST"], detail=False)
    @event("user.created", topic="user-events", key_field="id")
    async def register(self, request, db, **kwargs):
        """
        POST /users/register
        
        Fluxo:
        1. Metodo executa e retorna resposta ao cliente
        2. Resposta e enviada
        3. Evento e publicado em background (nao bloqueia)
        
        Se o metodo levantar excecao, evento NAO e publicado.
        """
        body = await request.json()
        user = await User.create_user(
            email=body["email"],
            password=body["password"],
            db=db,
        )
        # O retorno deste metodo se torna o "data" do evento
        return {"id": user.id, "email": user.email}
```

Estrutura do evento publicado:

```json
{
  "name": "user.created",
  "data": {"id": 1, "email": "user@example.com"},
  "timestamp": "2026-02-01T12:00:00Z",
  "source": "my-service"
}
```

**Parametros do @event**:

| Parametro | Tipo | Descricao |
|-----------|------|-----------|
| `event_name` | str | Nome do evento. Convencao: `entidade.acao` (ex: `user.created`) |
| `topic` | str | Topico/fila destino. Se None, usa topico padrao configurado. |
| `key_field` | str | Campo do retorno usado como chave de particao (Kafka). Garante ordenacao por chave. |
| `include_result` | bool | Se True (padrao), inclui retorno do metodo em `data`. Se False, `data` fica vazio. |

**Trade-off do @event**: Simplicidade vs controle. O decorator nao permite customizar o payload alem do retorno do metodo. Para payloads complexos, use `get_producer()`.

## Publicacao Manual

Para controle total sobre o que e quando publicar.

```python
from core.messaging import get_producer

async def send_order_created(order_id: int, user_id: int):
    """
    Publicacao manual permite:
    - Payload customizado
    - Publicacao condicional
    - Multiplos eventos em sequencia
    - Tratamento de erro especifico
    """
    producer = get_producer()
    
    # send() e async - aguarda confirmacao do broker
    # Em caso de falha, levanta excecao
    await producer.send(
        topic="orders.created",
        message={
            "order_id": order_id,
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )
```

**Diferenca entre @event e get_producer()**:
- `@event`: Fire-and-forget, falhas sao silenciosas, nao bloqueia resposta
- `get_producer()`: Sincrono (aguarda ACK), falhas levantam excecao, bloqueia ate confirmacao

## publish_event - Helper Direto

Funcao de conveniencia para publicar eventos sem instanciar producer.

```python
from core.messaging import publish_event

async def notify_user_updated(user_id: int, email: str):
    """
    Equivalente a get_producer().send(), mas com interface de evento.
    Util para publicar de qualquer lugar do codigo.
    """
    await publish_event(
        event_name="user.updated",
        data={"id": user_id, "email": email},
        topic="user-events",
    )
```

## @consumer + @on_event - Handlers em Classe

Agrupa handlers relacionados em uma classe. Util quando multiplos eventos compartilham contexto ou dependencias.

```python
from core.messaging import consumer, on_event
from core.messaging.base import Event

@consumer("order-service", topics=["user-events", "payment-events"])
class OrderEventsConsumer:
    """
    @consumer registra a classe como consumidor.
    
    group_id="order-service": Identificador do grupo de consumidores.
        Mensagens sao distribuidas entre instancias do mesmo grupo.
        Grupos diferentes recebem copia de todas as mensagens.
    
    topics: Lista de topicos que este consumidor escuta.
    """
    
    @on_event("user.created")
    async def handle_user_created(self, event: Event, db):
        """
        Chamado quando evento "user.created" e recebido.
        
        event.name: Nome do evento
        event.data: Payload do evento (dict)
        event.timestamp: Quando foi publicado
        event.source: Servico que publicou
        
        db: Sessao de banco injetada automaticamente
        """
        await Order.create_welcome_order(
            user_id=event.data["id"],
            db=db,
        )
    
    @on_event("payment.completed")
    async def handle_payment_completed(self, event: Event, db):
        """
        Metodos da mesma classe podem compartilhar estado e metodos auxiliares.
        """
        await Order.mark_paid(
            order_id=event.data["order_id"],
            db=db,
        )
```

**Parametros do @consumer**:

| Parametro | Tipo | Descricao |
|-----------|------|-----------|
| `group_id` | str | ID do grupo. Instancias com mesmo ID dividem carga. |
| `topics` | list[str] | Topicos a consumir. Handler so recebe eventos dos topicos listados. |
| `auto_start` | bool | Se True (padrao), inicia automaticamente com `core consumer`. |

## @message_handler - Handler Simples

Para handlers isolados que nao precisam de contexto compartilhado.

```python
from core.messaging import message_handler

@message_handler(topic="orders.created")
async def handle_order_created(message: dict, db):
    """
    Handler baseado em funcao.
    
    message: Payload da mensagem (dict, nao Event)
    db: Sessao de banco injetada
    
    Mais simples que @consumer, mas sem agrupamento.
    """
    order_id = message["order_id"]
    
    await send_email(
        to=message["user_email"],
        subject="Order Confirmed",
        body=f"Order #{order_id} received.",
    )
```

## Retry em Handlers

Configure retentativas automaticas para handlers que podem falhar temporariamente.

```python
@message_handler(
    topic="payments.process",
    max_retries=3,      # Numero maximo de tentativas
    retry_delay=5,      # Segundos entre tentativas (backoff linear)
)
async def process_payment(message: dict, db):
    """
    Se o handler levantar excecao:
    1. Aguarda retry_delay segundos
    2. Tenta novamente
    3. Repete ate max_retries
    4. Apos max_retries, mensagem vai para dead letter queue (se configurada)
    """
    result = await payment_gateway.charge(
        amount=message["amount"],
        card_token=message["card_token"],
    )
    
    if not result.success:
        # Levantar excecao aciona retry
        raise Exception("Payment failed")
```

**Comportamento de retry**: O delay e linear (sempre `retry_delay` segundos). Para backoff exponencial, implemente logica customizada no handler.

## Multiplos Topicos

Um handler pode escutar multiplos topicos.

```python
@message_handler(topic=["orders.created", "orders.updated"])
async def sync_inventory(message: dict, db):
    """
    Recebe mensagens de ambos os topicos.
    Use message.get("event_name") ou estrutura do payload para diferenciar.
    """
    pass
```

## Executar Consumer

```bash
# Consumir topico especifico
core consumer --topic orders.created

# Multiplos topicos
core consumer --topic orders.created --topic orders.updated

# Todos os handlers registrados (via @message_handler e @consumer)
core consumer
```

**Em producao**: Execute consumers como processos separados. Use Docker Compose ou Kubernetes para escalar.

## Exemplo Completo em ViewSet

Comparacao entre `@event` (automatico) e `get_producer()` (manual):

```python
from core import ModelViewSet, action
from core.messaging import event, get_producer

class OrderViewSet(ModelViewSet):
    model = Order
    
    # Abordagem 1: @event (recomendado para casos simples)
    @event("order.created", topic="order-events", key_field="id")
    async def perform_create(self, data: dict, db) -> Order:
        """
        Evento publicado automaticamente com o retorno do metodo.
        Limitacao: payload e exatamente o retorno, sem customizacao.
        """
        order = await super().perform_create(data, db)
        return order  # Este objeto e serializado e enviado como evento
    
    # Abordagem 2: get_producer() (para payloads customizados)
    async def perform_create_manual(self, data: dict, db) -> Order:
        """
        Controle total sobre o payload do evento.
        Util quando evento precisa de dados que nao estao no retorno.
        """
        order = await super().perform_create(data, db)
        
        producer = get_producer()
        await producer.send("orders.created", {
            "order_id": order.id,
            "user_id": order.user_id,
            "total": float(order.total),
            "items_count": len(order.items),  # Dado adicional
            "created_at": order.created_at.isoformat(),
        })
        
        return order
```

## Mensagens Tipadas

Use Pydantic para validacao automatica de mensagens recebidas.

```python
from pydantic import BaseModel
from core.messaging import message_handler

class OrderCreatedEvent(BaseModel):
    """Schema da mensagem esperada."""
    order_id: int
    user_id: int
    total: float

@message_handler(topic="orders.created", schema=OrderCreatedEvent)
async def handle_order(message: OrderCreatedEvent, db):
    """
    message ja e instancia de OrderCreatedEvent, validada.
    Se payload nao corresponder ao schema, mensagem e rejeitada.
    """
    print(f"Order {message.order_id} total: {message.total}")
```

**Comportamento com schema invalido**: Mensagem e logada como erro e descartada (nao vai para retry). Configure dead letter queue para inspecionar mensagens rejeitadas.

## Resumo de Abordagens

| Abordagem | Quando Usar |
|-----------|-------------|
| `@event` | Publicar apos acao do ViewSet, payload simples |
| `publish_event()` | Publicar de qualquer lugar, interface de evento |
| `get_producer()` | Controle total, payload customizado, tratamento de erro |
| `@consumer` + `@on_event` | Handlers relacionados, estado compartilhado |
| `@message_handler` | Handler isolado, casos simples |

---

Proximo: [Multi-Service Architecture](05-multi-service.md) - Duas APIs comunicando via messaging.
