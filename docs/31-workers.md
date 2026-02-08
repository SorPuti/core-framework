# Workers

Background task processing.

## Setup

```python
# src/settings.py
class AppSettings(Settings):
    kafka_enabled: bool = True
    kafka_bootstrap_servers: str = "localhost:9092"
```

## Decorator Worker

```python
from core.messaging import worker

@worker(
    topic="tasks",
    group_id="task-processor",
)
async def process_task(message: dict) -> dict:
    """Process a single task."""
    result = await do_work(message["data"])
    return {"status": "completed", "result": result}
```

## Class-Based Worker

```python
from core.messaging import Worker

class EmailWorker(Worker):
    input_topic = "emails"
    group_id = "email-sender"
    concurrency = 4
    max_retries = 3
    
    async def process(self, message: dict) -> dict:
        """Process single message."""
        await send_email(
            to=message["to"],
            subject=message["subject"],
            body=message["body"],
        )
        return {"sent": True}
    
    async def on_error(self, message: dict, error: Exception):
        """Called on processing error."""
        logger.error(f"Failed to send email: {error}")
    
    async def on_success(self, message: dict, result):
        """Called on success."""
        logger.info(f"Email sent: {result}")
```

## Worker Options

```python
class MyWorker(Worker):
    input_topic = "tasks"
    output_topic = "results"      # Optional: publish results
    group_id = "my-worker"
    
    # Concurrency
    concurrency = 4               # Parallel processing
    
    # Retry
    max_retries = 3
    retry_backoff = "exponential"  # "linear", "fixed"
    
    # Batching
    batch_size = 10               # Process N messages at once
    batch_timeout = 5.0           # Max wait for batch (seconds)
    
    # Dead Letter Queue
    dlq_topic = "tasks-dlq"       # Failed messages go here
```

## Batch Processing

```python
class BatchWorker(Worker):
    input_topic = "events"
    batch_size = 100
    batch_timeout = 10.0
    
    async def process_batch(self, messages: list[dict]) -> list:
        """Process multiple messages at once."""
        results = []
        for msg in messages:
            result = await process_single(msg)
            results.append(result)
        return results
```

## Retry Policy

```python
from core.messaging import worker, RetryPolicy

@worker(
    topic="tasks",
    max_retries=5,
    retry_backoff="exponential",
    dlq_topic="tasks-dlq",
)
async def process_task(message: dict):
    # If this fails, it will retry with exponential backoff
    # After max_retries, message goes to dlq_topic
    ...
```

Backoff calculation:
- `"fixed"`: Always `initial_delay` seconds
- `"linear"`: `initial_delay * attempt` seconds
- `"exponential"`: `initial_delay * (2 ** attempt)` seconds

## Output Topic

```python
@worker(
    topic="orders",
    output_topic="order-results",
    group_id="order-processor",
)
async def process_order(message: dict) -> dict:
    # Return value is published to output_topic
    return {"order_id": message["id"], "status": "processed"}
```

## Run Workers

### Single Worker

```bash
core kafka worker EmailWorker
```

### All Workers

```bash
core kafka worker --all
```

### With Options

```bash
core kafka worker EmailWorker --concurrency 8
```

## Publish Tasks

```python
from core.messaging import get_producer

producer = get_producer("kafka")

# Publish task
await producer.send(
    topic="tasks",
    message={"type": "process", "data": {...}},
    key="task-123"
)
```

## Worker Registry

```python
from core.messaging import (
    get_worker,
    get_all_workers,
    list_workers,
    run_worker,
    run_all_workers,
)

# Get worker config
config = get_worker("EmailWorker")

# List all workers
names = list_workers()

# Run programmatically
await run_worker(EmailWorker)
await run_all_workers()
```

## Error Handling

```python
class MyWorker(Worker):
    input_topic = "tasks"
    dlq_topic = "tasks-dlq"
    
    async def process(self, message: dict):
        try:
            return await do_work(message)
        except TemporaryError:
            # Re-raise to trigger retry
            raise
        except PermanentError as e:
            # Log and don't retry
            logger.error(f"Permanent error: {e}")
            return {"error": str(e)}
    
    async def on_error(self, message: dict, error: Exception):
        # Called after all retries exhausted
        # Message will be sent to dlq_topic
        await notify_admin(error)
```

## Graceful Shutdown

Workers handle SIGTERM/SIGINT:

1. Stop accepting new messages
2. Finish processing current batch
3. Commit offsets
4. Exit cleanly

## Monitoring

```python
class MyWorker(Worker):
    async def on_success(self, message: dict, result):
        metrics.increment("worker.success")
    
    async def on_error(self, message: dict, error: Exception):
        metrics.increment("worker.error")
```

## Complete Example

```python
# src/workers/email.py
from core.messaging import Worker
from src.services.email import EmailService

class EmailWorker(Worker):
    input_topic = "emails"
    group_id = "email-sender"
    concurrency = 4
    max_retries = 3
    retry_backoff = "exponential"
    dlq_topic = "emails-dlq"
    
    def __init__(self):
        self.email_service = EmailService()
    
    async def process(self, message: dict) -> dict:
        await self.email_service.send(
            to=message["to"],
            subject=message["subject"],
            template=message["template"],
            context=message.get("context", {}),
        )
        return {"sent": True, "to": message["to"]}
    
    async def on_error(self, message: dict, error: Exception):
        logger.error(f"Email failed: {message['to']} - {error}")
    
    async def on_success(self, message: dict, result):
        logger.info(f"Email sent: {result['to']}")
```

```bash
# Run worker
core kafka worker EmailWorker
```

## Next

- [Messaging](30-messaging.md) — Kafka/Redis integration
- [Settings](02-settings.md) — Configuration
