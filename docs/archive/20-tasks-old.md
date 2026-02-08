# Background Tasks

Run code asynchronously outside request/response cycle.

## Setup

```python
# src/settings.py
class AppSettings(Settings):
    task_enabled: bool = True
    task_default_queue: str = "default"
```

## Define Task

```python
# src/apps/emails/tasks.py
from core.tasks import task

@task
async def send_email(to: str, subject: str, body: str):
    """Send email asynchronously."""
    # Your email sending logic
    await email_service.send(to, subject, body)
    return {"sent": True}

@task(queue="high-priority")
async def send_urgent_notification(user_id: int, message: str):
    """High priority task."""
    await notify_user(user_id, message)
```

## Call Task

```python
# From view or anywhere
from src.apps.emails.tasks import send_email

# Async call (returns immediately)
await send_email.delay("user@example.com", "Hello", "Welcome!")

# With options
await send_email.delay(
    "user@example.com",
    "Hello",
    "Welcome!",
    countdown=60,  # Delay 60 seconds
)
```

## Periodic Tasks

```python
from core.tasks import periodic_task

@periodic_task(cron="0 * * * *")  # Every hour
async def cleanup_expired_tokens():
    """Run every hour."""
    await Token.objects.filter(expired=True).delete()

@periodic_task(interval=300)  # Every 5 minutes
async def sync_external_data():
    """Run every 5 minutes."""
    await external_api.sync()
```

## Run Worker

```bash
# Start worker
core runworker

# With specific queue
core runworker --queue high-priority

# Multiple workers
core runworker --concurrency 4
```

## Run Scheduler

```bash
# Start scheduler (for periodic tasks)
core scheduler start

# Stop scheduler
core scheduler stop
```

## Task Options

```python
@task(
    queue="emails",           # Queue name
    max_retries=3,            # Retry on failure
    retry_delay=60,           # Seconds between retries
    timeout=300,              # Max execution time
)
async def send_email(to: str, subject: str, body: str):
    ...
```

## Error Handling

```python
from core.tasks import task, TaskError

@task(max_retries=3)
async def risky_task(data: dict):
    try:
        await process(data)
    except TemporaryError:
        raise TaskError("Retry later")  # Will retry
    except PermanentError:
        # Don't retry, log and fail
        logger.error("Permanent failure")
        raise
```

## Task Status

```python
# Get task result
result = await send_email.delay("user@example.com", "Hi", "Hello")

# Check status
status = await result.status()  # pending, running, success, failed

# Get result (blocks until done)
data = await result.get()
```

## Next

- [Messaging](21-messaging.md) — Kafka integration
- [CLI](07-cli.md) — Worker commands
