"""
Base classes for the tasks system.

Defines Task, PeriodicTask, and related data structures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, TypeVar
from enum import Enum
from datetime import datetime
import uuid
import json

from core.datetime import timezone


F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


class TaskStatus(str, Enum):
    """Task execution status."""
    
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    RETRY = "retry"
    CANCELLED = "cancelled"


@dataclass
class TaskResult:
    """
    Result of a task execution.
    
    Attributes:
        task_id: Unique task execution ID
        task_name: Name of the task
        status: Execution status
        result: Return value (if successful)
        error: Error message (if failed)
        started_at: When execution started
        finished_at: When execution finished
        retries: Number of retries attempted
    """
    
    task_id: str
    task_name: str
    status: TaskStatus
    result: Any = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    retries: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "retries": self.retries,
        }
    
    @property
    def duration(self) -> float | None:
        """Get execution duration in seconds."""
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None


@dataclass
class TaskMessage:
    """
    Message sent to task queue.
    
    Contains all information needed to execute a task.
    """
    
    task_id: str
    task_name: str
    args: tuple = field(default_factory=tuple)
    kwargs: dict[str, Any] = field(default_factory=dict)
    queue: str = "default"
    retry_count: int = 0
    max_retries: int = 3
    retry_delay: int = 60
    timeout: int = 300
    created_at: datetime = field(default_factory=timezone.now)
    eta: datetime | None = None  # Earliest time to execute
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "args": list(self.args),
            "kwargs": self.kwargs,
            "queue": self.queue,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "timeout": self.timeout,
            "created_at": self.created_at.isoformat(),
            "eta": self.eta.isoformat() if self.eta else None,
        }
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskMessage":
        """Create from dictionary."""
        return cls(
            task_id=data["task_id"],
            task_name=data["task_name"],
            args=tuple(data.get("args", [])),
            kwargs=data.get("kwargs", {}),
            queue=data.get("queue", "default"),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            retry_delay=data.get("retry_delay", 60),
            timeout=data.get("timeout", 300),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else timezone.now(),
            eta=datetime.fromisoformat(data["eta"]) if data.get("eta") else None,
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> "TaskMessage":
        """Create from JSON string."""
        return cls.from_dict(json.loads(json_str))


class Task:
    """
    Represents a background task.
    
    Created by the @task decorator. Provides methods to
    execute the task immediately or schedule it for background execution.
    
    Example:
        @task(queue="emails", retry=3)
        async def send_email(to: str, subject: str, body: str):
            await EmailService.send(to, subject, body)
        
        # Execute immediately (blocking)
        result = await send_email("user@example.com", "Hello", "World")
        
        # Schedule for background execution
        task_id = await send_email.delay("user@example.com", "Hello", "World")
        
        # Schedule with delay
        task_id = await send_email.apply_async(
            args=("user@example.com", "Hello", "World"),
            eta=timezone.now() + timedelta(hours=1),
        )
    """
    
    def __init__(
        self,
        func: Callable[..., Awaitable[Any]],
        name: str | None = None,
        queue: str = "default",
        retry: int = 3,
        retry_delay: int = 60,
        timeout: int = 300,
        bind: bool = False,
    ):
        """
        Initialize task.
        
        Args:
            func: The async function to execute
            name: Task name (defaults to function name)
            queue: Queue to send task to
            retry: Number of retry attempts
            retry_delay: Delay between retries in seconds
            timeout: Task timeout in seconds
            bind: Whether to pass task instance as first argument
        """
        self.func = func
        self.name = name or f"{func.__module__}.{func.__name__}"
        self.queue = queue
        self.retry = retry
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.bind = bind
        
        # Copy function metadata
        self.__name__ = func.__name__
        self.__doc__ = func.__doc__
        self.__module__ = func.__module__
    
    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Execute task immediately (blocking)."""
        if self.bind:
            return await self.func(self, *args, **kwargs)
        return await self.func(*args, **kwargs)
    
    async def delay(self, *args: Any, **kwargs: Any) -> str:
        """
        Schedule task for background execution.
        
        Returns:
            Task ID
        """
        return await self.apply_async(args=args, kwargs=kwargs)
    
    async def apply_async(
        self,
        args: tuple = (),
        kwargs: dict[str, Any] | None = None,
        queue: str | None = None,
        eta: datetime | None = None,
        countdown: int | None = None,
    ) -> str:
        """
        Schedule task with full options.
        
        Args:
            args: Positional arguments
            kwargs: Keyword arguments
            queue: Override default queue
            eta: Earliest time to execute
            countdown: Delay in seconds before execution
        
        Returns:
            Task ID
        """
        from core.tasks.registry import get_task_producer
        
        task_id = str(uuid.uuid4())
        
        # Calculate ETA
        if countdown and not eta:
            from datetime import timedelta
            eta = timezone.now() + timedelta(seconds=countdown)
        
        message = TaskMessage(
            task_id=task_id,
            task_name=self.name,
            args=args,
            kwargs=kwargs or {},
            queue=queue or self.queue,
            max_retries=self.retry,
            retry_delay=self.retry_delay,
            timeout=self.timeout,
            eta=eta,
        )
        
        producer = await get_task_producer()
        await producer.send(
            f"tasks.{message.queue}",
            message.to_dict(),
            headers={
                "event_id": task_id,
                "event_name": f"task.{self.name}",
            },
        )
        
        return task_id
    
    def __repr__(self) -> str:
        return f"<Task {self.name}>"


class PeriodicTask:
    """
    Represents a periodic/scheduled task.
    
    Created by the @periodic_task decorator. Automatically
    scheduled by the task scheduler.
    
    Example:
        @periodic_task(cron="0 0 * * *")  # Every day at midnight
        async def cleanup_expired_sessions():
            await Session.objects.filter(expired=True).delete()
        
        @periodic_task(interval=300)  # Every 5 minutes
        async def sync_external_data():
            await ExternalAPI.sync()
    """
    
    def __init__(
        self,
        func: Callable[..., Awaitable[Any]],
        name: str | None = None,
        cron: str | None = None,
        interval: int | None = None,
        queue: str = "scheduled",
        enabled: bool = True,
    ):
        """
        Initialize periodic task.
        
        Args:
            func: The async function to execute
            name: Task name (defaults to function name)
            cron: Cron expression (e.g., "0 0 * * *")
            interval: Interval in seconds
            queue: Queue to send task to
            enabled: Whether task is enabled
        """
        if not cron and not interval:
            raise ValueError("Either 'cron' or 'interval' must be specified")
        
        self.func = func
        self.name = name or f"{func.__module__}.{func.__name__}"
        self.cron = cron
        self.interval = interval
        self.queue = queue
        self.enabled = enabled
        
        # Copy function metadata
        self.__name__ = func.__name__
        self.__doc__ = func.__doc__
        self.__module__ = func.__module__
        
        # Tracking
        self.last_run: datetime | None = None
        self.next_run: datetime | None = None
        self.run_count: int = 0
    
    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Execute task immediately."""
        return await self.func(*args, **kwargs)
    
    def get_next_run(self, after: datetime | None = None) -> datetime:
        """
        Calculate next run time.
        
        Args:
            after: Calculate next run after this time
        
        Returns:
            Next run datetime
        """
        from datetime import timedelta
        
        base = after or timezone.now()
        
        if self.interval:
            return base + timedelta(seconds=self.interval)
        
        if self.cron:
            try:
                from croniter import croniter
                cron = croniter(self.cron, base)
                return cron.get_next(datetime)
            except ImportError:
                raise ImportError(
                    "croniter is required for cron expressions. "
                    "Install with: pip install croniter"
                )
        
        raise ValueError("No schedule defined")
    
    def should_run(self, now: datetime | None = None) -> bool:
        """
        Check if task should run now.
        
        Args:
            now: Current time (defaults to timezone.now())
        
        Returns:
            True if task should run
        """
        if not self.enabled:
            return False
        
        now = now or timezone.now()
        
        if self.next_run is None:
            self.next_run = self.get_next_run()
        
        return now >= self.next_run
    
    def mark_run(self) -> None:
        """Mark task as having run."""
        self.last_run = timezone.now()
        self.next_run = self.get_next_run(self.last_run)
        self.run_count += 1
    
    def __repr__(self) -> str:
        schedule = self.cron or f"every {self.interval}s"
        return f"<PeriodicTask {self.name} ({schedule})>"
