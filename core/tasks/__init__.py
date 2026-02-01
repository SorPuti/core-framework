"""
Core Framework - Background Tasks System.

Provides @task and @periodic_task decorators for background job processing,
integrated with the messaging system for distributed task execution.

Usage:
    from core.tasks import task, periodic_task
    
    # Define a background task
    @task(queue="emails", retry=3)
    async def send_email(to: str, subject: str, body: str):
        await EmailService.send(to, subject, body)
    
    # Call task (runs in background)
    await send_email.delay(to="user@example.com", subject="Welcome", body="...")
    
    # Define a periodic task
    @periodic_task(cron="0 0 * * *")  # Every day at midnight
    async def cleanup_expired_sessions():
        await Session.objects.filter(expired=True).delete()
    
    @periodic_task(interval=300)  # Every 5 minutes
    async def sync_external_data():
        await ExternalAPI.sync()

CLI Commands:
    core worker --queue default --concurrency 4
    core scheduler
"""

from core.tasks.base import (
    Task,
    PeriodicTask,
    TaskResult,
    TaskStatus,
)
from core.tasks.decorators import (
    task,
    periodic_task,
)
from core.tasks.registry import (
    get_task,
    get_all_tasks,
    get_periodic_tasks,
    register_task,
)
from core.tasks.config import (
    TaskSettings,
    get_task_settings,
    configure_tasks,
)

__all__ = [
    # Base classes
    "Task",
    "PeriodicTask",
    "TaskResult",
    "TaskStatus",
    # Decorators
    "task",
    "periodic_task",
    # Registry
    "get_task",
    "get_all_tasks",
    "get_periodic_tasks",
    "register_task",
    # Config
    "TaskSettings",
    "get_task_settings",
    "configure_tasks",
]
