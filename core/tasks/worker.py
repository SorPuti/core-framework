"""
Task worker for executing background tasks.

Consumes task messages from queues and executes them.
"""

from __future__ import annotations

from typing import Any, Callable
import asyncio
import logging
import signal
import traceback

from core.tasks.base import TaskMessage, TaskResult, TaskStatus
from core.tasks.config import get_task_settings
from core.tasks.registry import get_task, get_all_tasks
from core.datetime import timezone


logger = logging.getLogger(__name__)


class TaskWorker:
    """
    Worker that executes background tasks.
    
    Consumes task messages from Kafka queues and executes
    the corresponding task functions.
    
    Example:
        # Start worker for specific queues
        worker = TaskWorker(queues=["default", "emails"])
        await worker.start()
        
        # Wait for shutdown
        await worker.wait()
        
        # Or run until interrupted
        await worker.run_forever()
    """
    
    def __init__(
        self,
        queues: list[str] | None = None,
        concurrency: int | None = None,
        db_session_factory: Callable | None = None,
    ):
        """
        Initialize task worker.
        
        Args:
            queues: List of queues to consume from
            concurrency: Number of concurrent tasks
            db_session_factory: Factory for database sessions
        """
        self._settings = get_task_settings()
        self._queues = queues or [self._settings.task_default_queue]
        self._concurrency = concurrency or self._settings.task_worker_concurrency
        self._db_session_factory = db_session_factory
        
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._consumer = None
        self._semaphore: asyncio.Semaphore | None = None
        self._active_tasks: set[asyncio.Task] = set()
        self._tasks_processed = 0
    
    async def start(self) -> None:
        """Start the worker."""
        if self._running:
            return
        
        self._running = True
        self._semaphore = asyncio.Semaphore(self._concurrency)
        
        # Setup signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._handle_signal)
        
        # Start consumer with retry
        from core.messaging.kafka import KafkaConsumer
        
        topics = [f"tasks.{q}" for q in self._queues]
        
        # Retry connection with exponential backoff
        max_retries = 30  # More retries for slow Kafka startup
        retry_delay = 2
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # Create new consumer for each attempt
                self._consumer = KafkaConsumer(
                    group_id=f"worker-{'-'.join(self._queues)}",
                    topics=topics,
                    message_handler=self._handle_message,
                )
                
                if self._db_session_factory:
                    self._consumer.set_db_session_factory(self._db_session_factory)
                
                await self._consumer.start()
                logger.info(f"Successfully connected to Kafka on attempt {attempt + 1}")
                break
            except Exception as e:
                last_error = e
                # Try to clean up failed consumer
                if self._consumer:
                    try:
                        await self._consumer.stop()
                    except Exception:
                        pass
                    self._consumer = None
                
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Failed to connect to Kafka (attempt {attempt + 1}/{max_retries}): {e}. "
                        f"Retrying in {retry_delay}s..."
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 60)  # Max 60s delay
                else:
                    logger.error(f"Failed to connect to Kafka after {max_retries} attempts: {last_error}")
                    raise
        
        logger.info(
            f"Worker started: queues={self._queues}, concurrency={self._concurrency}"
        )
    
    async def stop(self) -> None:
        """Stop the worker gracefully."""
        if not self._running:
            return
        
        logger.info("Stopping worker...")
        self._running = False
        
        # Wait for active tasks to complete
        if self._active_tasks:
            logger.info(f"Waiting for {len(self._active_tasks)} active tasks...")
            await asyncio.gather(*self._active_tasks, return_exceptions=True)
        
        # Stop consumer
        if self._consumer:
            await self._consumer.stop()
            self._consumer = None
        
        self._shutdown_event.set()
        logger.info(f"Worker stopped. Processed {self._tasks_processed} tasks.")
    
    async def wait(self) -> None:
        """Wait for shutdown signal."""
        await self._shutdown_event.wait()
    
    async def run_forever(self) -> None:
        """Run worker until interrupted."""
        await self.start()
        await self.wait()
    
    def _handle_signal(self) -> None:
        """Handle shutdown signal."""
        logger.info("Received shutdown signal")
        asyncio.create_task(self.stop())
    
    async def _handle_message(self, message: dict[str, Any]) -> None:
        """Handle incoming task message."""
        # Parse message
        try:
            task_msg = TaskMessage.from_dict(message)
        except Exception as e:
            logger.error(f"Invalid task message: {e}")
            return
        
        # Check ETA
        if task_msg.eta and task_msg.eta > timezone.now():
            # Re-queue for later
            # TODO: Implement delayed queue
            logger.debug(f"Task {task_msg.task_id} scheduled for {task_msg.eta}")
            return
        
        # Execute with concurrency limit
        async with self._semaphore:
            task = asyncio.create_task(self._execute_task(task_msg))
            self._active_tasks.add(task)
            task.add_done_callback(self._active_tasks.discard)
    
    async def _execute_task(self, task_msg: TaskMessage) -> TaskResult:
        """Execute a single task."""
        result = TaskResult(
            task_id=task_msg.task_id,
            task_name=task_msg.task_name,
            status=TaskStatus.RUNNING,
            started_at=timezone.now(),
        )
        
        logger.info(f"Executing task: {task_msg.task_name} ({task_msg.task_id})")
        
        try:
            # Get task function
            task = get_task(task_msg.task_name)
            
            # Execute with timeout
            try:
                task_result = await asyncio.wait_for(
                    task(*task_msg.args, **task_msg.kwargs),
                    timeout=task_msg.timeout,
                )
                
                result.status = TaskStatus.SUCCESS
                result.result = task_result
                
                logger.info(
                    f"Task completed: {task_msg.task_name} ({task_msg.task_id})"
                )
                
            except asyncio.TimeoutError:
                result.status = TaskStatus.FAILURE
                result.error = f"Task timed out after {task_msg.timeout}s"
                logger.error(
                    f"Task timeout: {task_msg.task_name} ({task_msg.task_id})"
                )
                
        except KeyError:
            result.status = TaskStatus.FAILURE
            result.error = f"Task not found: {task_msg.task_name}"
            logger.error(f"Task not found: {task_msg.task_name}")
            
        except Exception as e:
            result.status = TaskStatus.FAILURE
            result.error = str(e)
            result.retries = task_msg.retry_count
            
            logger.error(
                f"Task failed: {task_msg.task_name} ({task_msg.task_id}): {e}",
                exc_info=True,
            )
            
            # Retry if possible
            if task_msg.retry_count < task_msg.max_retries:
                await self._retry_task(task_msg)
                result.status = TaskStatus.RETRY
        
        result.finished_at = timezone.now()
        self._tasks_processed += 1
        
        return result
    
    async def _retry_task(self, task_msg: TaskMessage) -> None:
        """Retry a failed task."""
        from core.tasks.registry import get_task_producer
        from datetime import timedelta
        
        settings = get_task_settings()
        
        # Calculate retry delay with exponential backoff
        delay = task_msg.retry_delay
        if settings.task_retry_backoff:
            delay = min(
                delay * (2 ** task_msg.retry_count),
                settings.task_retry_backoff_max,
            )
        
        # Create retry message
        retry_msg = TaskMessage(
            task_id=task_msg.task_id,
            task_name=task_msg.task_name,
            args=task_msg.args,
            kwargs=task_msg.kwargs,
            queue=task_msg.queue,
            retry_count=task_msg.retry_count + 1,
            max_retries=task_msg.max_retries,
            retry_delay=task_msg.retry_delay,
            timeout=task_msg.timeout,
            eta=timezone.now() + timedelta(seconds=delay),
        )
        
        producer = await get_task_producer()
        await producer.send(f"tasks.{retry_msg.queue}", retry_msg.to_dict())
        
        logger.info(
            f"Task scheduled for retry: {task_msg.task_name} "
            f"(attempt {retry_msg.retry_count}/{task_msg.max_retries}, "
            f"delay {delay}s)"
        )


async def run_worker(
    queues: list[str] | None = None,
    concurrency: int | None = None,
) -> None:
    """
    Run a task worker.
    
    Convenience function for CLI.
    
    Args:
        queues: Queues to consume from
        concurrency: Number of concurrent tasks
    """
    worker = TaskWorker(queues=queues, concurrency=concurrency)
    await worker.run_forever()
