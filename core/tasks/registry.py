"""
Task registry for managing registered tasks.

Provides a central place to register and retrieve tasks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.tasks.base import Task, PeriodicTask
    from core.messaging.base import Producer


# Global registries
_tasks: dict[str, "Task"] = {}
_periodic_tasks: dict[str, "PeriodicTask"] = {}
_task_producer: "Producer | None" = None


def register_task(task: "Task") -> None:
    """
    Register a task.
    
    Args:
        task: Task instance
    
    Example:
        @task(queue="emails")
        async def send_email(to, subject, body):
            ...
        
        # Automatically registered by @task decorator
    """
    _tasks[task.name] = task


def get_task(name: str) -> "Task":
    """
    Get a registered task by name.
    
    Args:
        name: Task name
    
    Returns:
        Task instance
    
    Raises:
        KeyError: If task not found
    """
    if name not in _tasks:
        raise KeyError(f"Task '{name}' not found. Available: {list(_tasks.keys())}")
    return _tasks[name]


def get_all_tasks() -> dict[str, "Task"]:
    """
    Get all registered tasks.
    
    Returns:
        Dictionary of name -> Task
    """
    return _tasks.copy()


def register_periodic_task(task: "PeriodicTask") -> None:
    """
    Register a periodic task.
    
    Args:
        task: PeriodicTask instance
    """
    _periodic_tasks[task.name] = task


def get_periodic_task(name: str) -> "PeriodicTask":
    """
    Get a registered periodic task by name.
    
    Args:
        name: Task name
    
    Returns:
        PeriodicTask instance
    
    Raises:
        KeyError: If task not found
    """
    if name not in _periodic_tasks:
        raise KeyError(f"Periodic task '{name}' not found. Available: {list(_periodic_tasks.keys())}")
    return _periodic_tasks[name]


def get_periodic_tasks() -> dict[str, "PeriodicTask"]:
    """
    Get all registered periodic tasks.
    
    Returns:
        Dictionary of name -> PeriodicTask
    """
    return _periodic_tasks.copy()


def set_task_producer(producer: "Producer") -> None:
    """
    Set the producer for sending task messages.
    
    Args:
        producer: Producer instance
    """
    global _task_producer
    _task_producer = producer


async def get_task_producer() -> "Producer":
    """
    Get the task producer.
    
    Creates a default Kafka producer if not set.
    
    Returns:
        Producer instance
    """
    global _task_producer
    
    if _task_producer is None:
        from core.messaging.kafka import KafkaProducer
        _task_producer = KafkaProducer()
        await _task_producer.start()
    
    return _task_producer


def clear_registry() -> None:
    """
    Clear all registries.
    
    Useful for testing.
    """
    global _task_producer
    _tasks.clear()
    _periodic_tasks.clear()
    _task_producer = None


def list_tasks() -> list[dict]:
    """
    List all tasks with their configuration.
    
    Returns:
        List of task info dictionaries
    """
    result = []
    
    for name, task in _tasks.items():
        result.append({
            "name": name,
            "type": "task",
            "queue": task.queue,
            "retry": task.retry,
            "timeout": task.timeout,
        })
    
    for name, task in _periodic_tasks.items():
        result.append({
            "name": name,
            "type": "periodic",
            "queue": task.queue,
            "cron": task.cron,
            "interval": task.interval,
            "enabled": task.enabled,
            "last_run": task.last_run.isoformat() if task.last_run else None,
            "next_run": task.next_run.isoformat() if task.next_run else None,
            "run_count": task.run_count,
        })
    
    return result
