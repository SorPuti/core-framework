# Workers

Sistema de workers para processamento de mensagens, inspirado no Celery.

## Quick Start

```python
from core.messaging import worker

@worker(topic="events.raw", output_topic="events.processed")
async def process_event(event: dict) -> dict:
    return {**event, "processed": True}
```

```bash
# Executar
core runworker process_event
```

## Decorator Style

O decorator `@worker` é a forma mais simples de criar um worker:

```python
from core.messaging import worker

@worker(
    topic="orders.created",
    output_topic="orders.notifications",
    concurrency=5,
    max_retries=3,
)
async def notify_order(order: dict) -> dict:
    """
    Processa pedido e envia notificação.
    
    Args:
        order: Payload da mensagem do tópico de entrada
    
    Returns:
        Resultado publicado no output_topic
    """
    await send_email(order["user_email"], f"Order {order['id']} confirmed!")
    return {"order_id": order["id"], "notified": True}
```

### Parâmetros do Decorator

```python
@worker(
    # Obrigatório
    topic="input.topic",
    
    # Opcional - se definido, resultado é publicado aqui
    output_topic="output.topic",
    
    # Consumer group ID (padrão: nome da função)
    group_id="my-service",
    
    # Número de workers paralelos
    concurrency=5,
    
    # Retry configuration
    max_retries=3,
    retry_backoff="exponential",  # "linear", "exponential", "fixed"
    
    # Schema validation (Pydantic models)
    input_schema=OrderInput,
    output_schema=OrderOutput,
    
    # Dead letter queue para mensagens que falharam
    dlq_topic="orders.dlq",
)
async def my_worker(event: dict) -> dict:
    ...
```

## Class Style

Para lógica mais complexa, use a classe `Worker`:

```python
from core.messaging import Worker
from pydantic import BaseModel

class OrderInput(BaseModel):
    order_id: str
    user_id: int
    items: list[dict]
    total: float

class OrderOutput(BaseModel):
    order_id: str
    status: str
    processed_at: datetime

class OrderProcessor(Worker):
    """
    Worker para processar pedidos.
    
    Vantagens da classe:
    - Métodos auxiliares
    - Estado compartilhado
    - Hooks on_error/on_success
    - Melhor testabilidade
    """
    
    # Configuração
    input_topic = "orders.created"
    output_topic = "orders.processed"
    group_id = "order-processor"
    concurrency = 10
    max_retries = 3
    retry_backoff = "exponential"
    input_schema = OrderInput
    output_schema = OrderOutput
    dlq_topic = "orders.dlq"
    
    async def process(self, order: dict) -> dict:
        """
        Método principal de processamento.
        
        Args:
            order: Mensagem validada contra input_schema
        
        Returns:
            Resultado validado contra output_schema
        """
        # Validar estoque
        await self.validate_inventory(order["items"])
        
        # Processar pagamento
        payment = await self.process_payment(order)
        
        # Retornar resultado
        return {
            "order_id": order["order_id"],
            "status": "processed",
            "processed_at": datetime.now(),
        }
    
    async def validate_inventory(self, items: list) -> None:
        """Método auxiliar para validar estoque."""
        for item in items:
            available = await Inventory.check(item["product_id"])
            if available < item["quantity"]:
                raise ValueError(f"Insufficient stock for {item['product_id']}")
    
    async def process_payment(self, order: dict) -> dict:
        """Método auxiliar para processar pagamento."""
        return await PaymentGateway.charge(
            amount=order["total"],
            user_id=order["user_id"],
        )
    
    async def on_error(self, order: dict, error: Exception) -> None:
        """
        Chamado quando processamento falha após todos os retries.
        
        Use para:
        - Logging detalhado
        - Alertas
        - Compensação
        """
        logger.error(f"Failed to process order {order.get('order_id')}: {error}")
        await AlertService.send(
            level="critical",
            message=f"Order processing failed: {order}",
        )
    
    async def on_success(self, order: dict, result: dict) -> None:
        """
        Chamado após processamento bem-sucedido.
        
        Use para:
        - Métricas
        - Logging
        - Side effects
        """
        logger.info(f"Order {result['order_id']} processed successfully")
        metrics.increment("orders.processed")
```

## Retry Policy

### Estratégias de Backoff

```python
from core.messaging import worker, RetryPolicy

# Exponential (padrão): 1s, 2s, 4s, 8s, 16s...
@worker(topic="payments", max_retries=5, retry_backoff="exponential")
async def process_payment(payment: dict) -> dict:
    ...

# Linear: 1s, 2s, 3s, 4s, 5s...
@worker(topic="emails", max_retries=3, retry_backoff="linear")
async def send_email(email: dict) -> None:
    ...

# Fixed: 5s, 5s, 5s, 5s...
@worker(topic="webhooks", max_retries=10, retry_backoff="fixed")
async def call_webhook(webhook: dict) -> None:
    ...
```

### Configuração Avançada

```python
from core.messaging.workers import RetryPolicy

policy = RetryPolicy(
    max_retries=5,
    backoff="exponential",
    initial_delay=1.0,  # Delay inicial em segundos
    max_delay=60.0,     # Delay máximo
)

# Calcular delay para tentativa N
delay = policy.get_delay(attempt=3)  # 4.0 segundos
```

### Quando Acionar Retry

```python
@worker(topic="orders", max_retries=3)
async def process_order(order: dict) -> dict:
    try:
        result = await external_api.call(order)
        return result
    except TemporaryError:
        # Levantar exceção aciona retry
        raise
    except PermanentError as e:
        # Retornar None não publica em output_topic
        # mas também não aciona retry
        logger.error(f"Permanent error: {e}")
        return None
```

## Dead Letter Queue (DLQ)

Mensagens que falham após todos os retries são enviadas para DLQ:

```python
@worker(
    topic="payments",
    max_retries=3,
    dlq_topic="payments.dlq",
)
async def process_payment(payment: dict) -> dict:
    ...
```

Estrutura da mensagem na DLQ:

```json
{
    "original": {"payment_id": "123", "amount": 100.00},
    "error": "Connection timeout",
    "worker": "process_payment",
    "retries": 3
}
```

### Processar DLQ

```python
@worker(topic="payments.dlq")
async def handle_failed_payments(dlq_message: dict) -> None:
    """Processa mensagens que falharam."""
    original = dlq_message["original"]
    error = dlq_message["error"]
    
    # Notificar equipe
    await AlertService.send(
        level="warning",
        message=f"Payment failed: {original['payment_id']}, error: {error}",
    )
    
    # Tentar compensação
    await refund_if_charged(original["payment_id"])
```

## Schema Validation

### Input Validation

```python
from pydantic import BaseModel, field_validator

class PaymentInput(BaseModel):
    payment_id: str
    amount: float
    currency: str = "BRL"
    
    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v):
        if v <= 0:
            raise ValueError("Amount must be positive")
        return v

@worker(topic="payments", input_schema=PaymentInput)
async def process_payment(payment: dict) -> dict:
    # payment já foi validado contra PaymentInput
    # Se inválido, vai para DLQ automaticamente
    ...
```

### Output Validation

```python
class PaymentOutput(BaseModel):
    payment_id: str
    status: str
    processed_at: datetime

@worker(
    topic="payments",
    output_topic="payments.processed",
    output_schema=PaymentOutput,
)
async def process_payment(payment: dict) -> dict:
    # Resultado é validado contra PaymentOutput antes de publicar
    return {
        "payment_id": payment["payment_id"],
        "status": "completed",
        "processed_at": datetime.now(),
    }
```

## Concurrency

### Múltiplos Workers Paralelos

```python
@worker(topic="events", concurrency=10)
async def process_event(event: dict) -> dict:
    """
    10 instâncias deste worker rodam em paralelo.
    Cada uma consome de partições diferentes.
    """
    ...
```

### Considerações

- `concurrency` define quantas instâncias do worker rodam
- Kafka distribui partições entre workers do mesmo `group_id`
- Para máxima paralelização: `concurrency <= número de partições`

## CLI Commands

```bash
# Listar workers registrados
core workers

# Output:
#   OrderProcessor
#     Input:  orders.created
#     Output: orders.processed
#     Concurrency: 10
#     Retries: 3
#
#   process_event
#     Input:  events.raw
#     Output: events.enriched
#     Concurrency: 5
#     Retries: 3

# Rodar worker específico
core runworker OrderProcessor
core runworker process_event

# Rodar todos os workers
core runworker all
```

## Testando Workers

### Unit Test

```python
import pytest
from myapp.workers import OrderProcessor

@pytest.mark.asyncio
async def test_order_processor():
    worker = OrderProcessor()
    
    order = {
        "order_id": "123",
        "user_id": 1,
        "items": [{"product_id": "A", "quantity": 2}],
        "total": 100.00,
    }
    
    result = await worker.process(order)
    
    assert result["order_id"] == "123"
    assert result["status"] == "processed"
```

### Integration Test

```python
import pytest
from core.messaging import get_producer, publish
from myapp.workers import OrderProcessor

@pytest.mark.asyncio
async def test_order_flow():
    # Publicar mensagem
    await publish("orders.created", {
        "order_id": "test-123",
        "user_id": 1,
        "items": [],
        "total": 50.00,
    })
    
    # Verificar resultado (mock consumer ou verificar DB)
    ...
```

## Exemplos Práticos

### ETL Pipeline

```python
# Extract
@worker(topic="raw.data", output_topic="transformed.data")
async def transform_data(raw: dict) -> dict:
    return {
        "id": raw["id"],
        "value": raw["value"] * 2,
        "transformed_at": datetime.now().isoformat(),
    }

# Load
@worker(topic="transformed.data")
async def load_data(data: dict) -> None:
    await Database.insert("processed_data", data)
```

### Saga Pattern

```python
# Step 1: Reserve inventory
@worker(topic="orders.created", output_topic="inventory.reserve")
async def reserve_inventory(order: dict) -> dict:
    return {"order_id": order["order_id"], "items": order["items"]}

# Step 2: Process payment
@worker(topic="inventory.reserved", output_topic="payments.process")
async def process_payment(reservation: dict) -> dict:
    return {"order_id": reservation["order_id"], "amount": reservation["total"]}

# Step 3: Confirm order
@worker(topic="payments.completed", output_topic="orders.confirmed")
async def confirm_order(payment: dict) -> dict:
    return {"order_id": payment["order_id"], "status": "confirmed"}

# Compensation
@worker(topic="payments.failed")
async def compensate_inventory(failure: dict) -> None:
    await release_inventory(failure["order_id"])
```

### Fan-out

```python
@worker(topic="user.created")
async def fan_out_user_created(user: dict) -> None:
    """Publica para múltiplos tópicos."""
    producer = get_producer()
    
    # Notificação
    await producer.send("notifications.welcome", {
        "user_id": user["id"],
        "email": user["email"],
    })
    
    # Analytics
    await producer.send("analytics.user.created", {
        "user_id": user["id"],
        "created_at": user["created_at"],
    })
    
    # CRM
    await producer.send("crm.contacts.create", {
        "email": user["email"],
        "name": user["name"],
    })
```

---

Próximo: [Avro Schemas](28-avro.md)
