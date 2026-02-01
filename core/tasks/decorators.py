"""
Task decorators for defining background and periodic tasks.

Provides @task and @periodic_task decorators for DRF-style
task definition.
"""

from __future__ import annotations

from typing import Any, Callable, Awaitable, TypeVar, overload

from core.tasks.base import Task, PeriodicTask
from core.tasks.registry import register_task, register_periodic_task


F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


@overload
def task(func: F) -> Task: ...

@overload
def task(
    *,
    name: str | None = None,
    queue: str = "default",
    retry: int = 3,
    retry_delay: int = 60,
    timeout: int = 300,
    bind: bool = False,
) -> Callable[[F], Task]: ...


def task(
    func: F | None = None,
    *,
    name: str | None = None,
    queue: str = "default",
    retry: int = 3,
    retry_delay: int = 60,
    timeout: int = 300,
    bind: bool = False,
) -> Task | Callable[[F], Task]:
    """
    Decorator to define a background task.
    
    Can be used with or without arguments:
        
        @task
        async def simple_task():
            ...
        
        @task(queue="emails", retry=5)
        async def send_email(to: str, subject: str, body: str):
            await EmailService.send(to, subject, body)
    
    Args:
        func: The async function (when used without parentheses)
        name: Task name (defaults to module.function_name)
        queue: Queue to send task to
        retry: Number of retry attempts on failure
        retry_delay: Delay between retries in seconds
        timeout: Task timeout in seconds
        bind: Pass task instance as first argument
    
    Returns:
        Task instance
    
    Usage:
        # Define task
        @task(queue="emails", retry=3)
        async def send_email(to: str, subject: str, body: str):
            await EmailService.send(to, subject, body)
        
        # Execute immediately (blocking)
        await send_email("user@example.com", "Hello", "World")
        
        # Schedule for background execution
        task_id = await send_email.delay("user@example.com", "Hello", "World")
        
        # Schedule with options
        task_id = await send_email.apply_async(
            args=("user@example.com", "Hello", "World"),
            countdown=60,  # Execute after 60 seconds
        )
    """
    def decorator(f: F) -> Task:
        task_instance = Task(
            func=f,
            name=name,
            queue=queue,
            retry=retry,
            retry_delay=retry_delay,
            timeout=timeout,
            bind=bind,
        )
        register_task(task_instance)
        return task_instance
    
    if func is not None:
        # Called without parentheses: @task
        return decorator(func)
    
    # Called with parentheses: @task(...)
    return decorator


@overload
def periodic_task(func: F) -> PeriodicTask: ...

@overload
def periodic_task(
    *,
    name: str | None = None,
    cron: str | None = None,
    interval: int | None = None,
    queue: str = "scheduled",
    enabled: bool = True,
) -> Callable[[F], PeriodicTask]: ...


def periodic_task(
    func: F | None = None,
    *,
    name: str | None = None,
    cron: str | None = None,
    interval: int | None = None,
    queue: str = "scheduled",
    enabled: bool = True,
) -> PeriodicTask | Callable[[F], PeriodicTask]:
    """
    Decorator to define a periodic/scheduled task.
    
    Must specify either 'cron' or 'interval'.
    
    Args:
        func: The async function
        name: Task name (defaults to module.function_name)
        cron: Cron expression (e.g., "0 0 * * *" for daily at midnight)
        interval: Interval in seconds
        queue: Queue to send task to
        enabled: Whether task is enabled
    
    Returns:
        PeriodicTask instance
    
    Cron Expression Format:
        ┌───────────── minute (0 - 59)
        │ ┌───────────── hour (0 - 23)
        │ │ ┌───────────── day of month (1 - 31)
        │ │ │ ┌───────────── month (1 - 12)
        │ │ │ │ ┌───────────── day of week (0 - 6) (Sunday = 0)
        │ │ │ │ │
        * * * * *
    
    Examples:
        # Every day at midnight
        @periodic_task(cron="0 0 * * *")
        async def daily_cleanup():
            await Session.objects.filter(expired=True).delete()
        
        # Every 5 minutes
        @periodic_task(interval=300)
        async def sync_data():
            await ExternalAPI.sync()
        
        # Every Monday at 9 AM
        @periodic_task(cron="0 9 * * 1")
        async def weekly_report():
            await ReportService.generate_weekly()
        
        # Every hour
        @periodic_task(cron="0 * * * *")
        async def hourly_check():
            await HealthCheck.run()
    """
    def decorator(f: F) -> PeriodicTask:
        task_instance = PeriodicTask(
            func=f,
            name=name,
            cron=cron,
            interval=interval,
            queue=queue,
            enabled=enabled,
        )
        register_periodic_task(task_instance)
        return task_instance
    
    if func is not None:
        # Called without parentheses - need either cron or interval
        raise ValueError(
            "@periodic_task requires either 'cron' or 'interval' argument. "
            "Example: @periodic_task(cron='0 0 * * *') or @periodic_task(interval=300)"
        )
    
    # Called with parentheses: @periodic_task(...)
    return decorator
