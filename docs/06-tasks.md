# Background Tasks

Async task execution with workers.

## Define Task

```python
# src/apps/reports/tasks.py
from core.tasks import task

@task(queue="default")
async def generate_report(user_id: int, report_type: str):
    """Generate report in background."""
    # Heavy processing
    data = await fetch_report_data(user_id, report_type)
    pdf = await create_pdf(data)
    await save_report(user_id, pdf)
    return {"status": "completed", "user_id": user_id}
```

## Call Task

```python
from src.apps.reports.tasks import generate_report

# Async call - returns immediately
await generate_report.delay(user_id=1, report_type="monthly")

# With options
await generate_report.delay(
    user_id=1,
    report_type="monthly",
    countdown=60,  # Delay 60 seconds
)
```

## Task in ViewSet

```python
from core import ModelViewSet, action
from .tasks import generate_report

class ReportViewSet(ModelViewSet):
    model = Report
    
    @action(methods=["POST"], detail=False)
    async def generate(self, request, db, **kwargs):
        user = request.state.user
        body = await request.json()
        
        # Queue task
        await generate_report.delay(
            user_id=user.id,
            report_type=body["type"],
        )
        
        return {"message": "Report generation started"}
```

## Periodic Tasks

```python
from core.tasks import periodic_task

@periodic_task(cron="0 0 * * *")  # Daily at midnight
async def cleanup_old_sessions():
    """Delete expired sessions."""
    from core.models import get_session
    async with get_session() as db:
        await Session.objects.using(db).filter(
            expired_at__lt=datetime.utcnow()
        ).delete()

@periodic_task(interval=300)  # Every 5 minutes
async def sync_inventory():
    """Sync inventory with external system."""
    pass
```

## Run Workers

```bash
# Single worker
core worker --queue default

# Multiple queues
core worker --queue default --queue high-priority

# With concurrency
core worker --queue default --concurrency 4
```

## Run Scheduler

```bash
core scheduler
```

## Task Options

```python
@task(
    queue="high-priority",
    max_retries=3,
    retry_delay=10,
    timeout=300,
)
async def critical_task(data: dict):
    pass
```

| Option | Type | Description |
|--------|------|-------------|
| queue | str | Queue name |
| max_retries | int | Retry count on failure |
| retry_delay | int | Seconds between retries |
| timeout | int | Max execution time |

## Error Handling

```python
from core.tasks import task, TaskError

@task(queue="default", max_retries=3)
async def risky_task(item_id: int):
    try:
        result = await external_api.process(item_id)
        return result
    except ExternalAPIError as e:
        # Will retry
        raise TaskError(f"API failed: {e}")
    except ValidationError as e:
        # Won't retry - permanent failure
        raise TaskError(f"Invalid data: {e}", retry=False)
```

## Task with Database

```python
@task(queue="default")
async def update_user_stats(user_id: int):
    from core.models import get_session
    
    async with get_session() as db:
        user = await User.objects.using(db).get(id=user_id)
        user.login_count += 1
        await user.save(db)
```

## Docker Deployment

```yaml
services:
  api:
    build: .
    command: core run
    
  worker:
    build: .
    command: core worker --queue default --concurrency 4
    deploy:
      replicas: 2
    
  scheduler:
    build: .
    command: core scheduler
```

Next: [Deployment](07-deployment.md)
