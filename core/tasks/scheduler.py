"""
Task scheduler for periodic tasks.

Monitors periodic tasks and schedules them for execution
when their time comes.
"""

from __future__ import annotations

from typing import Any
import asyncio
import logging
import signal
import sys

from core.tasks.base import PeriodicTask, TaskMessage
from core.config import get_settings
from core.tasks.registry import get_periodic_tasks, get_task_producer
from core.datetime import timezone


logger = logging.getLogger(__name__)


class TaskScheduler:
    """
    Scheduler for periodic tasks.
    
    Monitors all registered periodic tasks and sends them
    to the task queue when they should run.
    
    Example:
        scheduler = TaskScheduler()
        await scheduler.start()
        
        # Run until interrupted
        await scheduler.run_forever()
    """
    
    def __init__(self):
        """Initialize scheduler."""
        self._settings = get_settings()
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._signal_received = False
    
    async def start(self) -> None:
        """Start the scheduler."""
        if self._running:
            return
        
        self._running = True
        self._signal_received = False
        
        # Initialize database for persistence
        try:
            from core.models import init_database
            from core.config import get_settings
            settings = get_settings()
            await init_database(settings.database_url)
            logger.info("Database initialized for scheduler")
        except Exception as e:
            logger.warning(f"Failed to initialize database: {e}")
        
        # Setup signal handlers - use threadsafe approach
        loop = asyncio.get_running_loop()
        
        try:
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, self._handle_signal)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass
        
        # Start scheduler loop
        self._task = asyncio.create_task(self._scheduler_loop())
        
        # Log registered periodic tasks
        periodic_tasks = get_periodic_tasks()
        logger.info(f"Scheduler started with {len(periodic_tasks)} periodic task(s)")
        
        for name, task in periodic_tasks.items():
            schedule = task.cron or f"every {task.interval}s"
            status = "enabled" if task.enabled else "disabled"
            logger.info(f"  - {name}: {schedule} ({status})")
    
    async def stop(self) -> None:
        """Stop the scheduler."""
        if not self._running:
            return
        
        logger.info("Stopping scheduler...")
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        
        self._shutdown_event.set()
        logger.info("Scheduler stopped")
    
    async def wait(self) -> None:
        """Wait for shutdown signal."""
        await self._shutdown_event.wait()
    
    async def run_forever(self) -> None:
        """Run scheduler until interrupted."""
        await self.start()
        await self.wait()
    
    def _handle_signal(self) -> None:
        """Handle shutdown signal."""
        if self._signal_received:
            # Second signal - force exit
            logger.warning("Forced shutdown")
            sys.exit(1)
        
        self._signal_received = True
        logger.info("Received shutdown signal (press Ctrl+C again to force)")
        
        # Schedule stop in the event loop
        asyncio.get_running_loop().call_soon_threadsafe(
            lambda: asyncio.create_task(self.stop())
        )
    
    async def _scheduler_loop(self) -> None:
        """Main scheduler loop."""
        while self._running:
            try:
                await self._check_tasks()
                await asyncio.sleep(self._settings.task_scheduler_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}", exc_info=True)
                await asyncio.sleep(self._settings.task_scheduler_interval)
    
    async def _check_tasks(self) -> None:
        """Check all periodic tasks and schedule if needed."""
        now = timezone.now()
        periodic_tasks = get_periodic_tasks()
        
        for name, task in periodic_tasks.items():
            if task.should_run(now):
                await self._schedule_task(task)
    
    async def _schedule_task(self, task: PeriodicTask) -> None:
        """Schedule a periodic task for execution."""
        import uuid
        
        task_msg = TaskMessage(
            task_id=str(uuid.uuid4()),
            task_name=task.name,
            queue=task.queue,
        )
        
        try:
            producer = await get_task_producer()
            await producer.send(
                f"tasks.{task_msg.queue}",
                task_msg.to_dict(),
                headers={
                    "event_id": task_msg.task_id,
                    "event_name": f"periodic.{task.name}",
                },
            )
            
            task.mark_run()
            
            logger.info(
                f"Scheduled periodic task: {task.name} "
                f"(next run: {task.next_run})"
            )
            
        except Exception as e:
            logger.error(f"Failed to schedule task {task.name}: {e}")


class CombinedWorkerScheduler:
    """
    Combined worker and scheduler in one process.
    
    Useful for simple deployments where you don't need
    separate worker and scheduler processes.
    
    Example:
        combined = CombinedWorkerScheduler(queues=["default"])
        await combined.run_forever()
    """
    
    def __init__(
        self,
        queues: list[str] | None = None,
        concurrency: int | None = None,
    ):
        """
        Initialize combined worker/scheduler.
        
        Args:
            queues: Queues for worker to consume
            concurrency: Worker concurrency
        """
        from core.tasks.worker import TaskWorker
        
        self._worker = TaskWorker(queues=queues, concurrency=concurrency)
        self._scheduler = TaskScheduler()
        self._running = False
    
    async def start(self) -> None:
        """Start both worker and scheduler."""
        if self._running:
            return
        
        self._running = True
        await self._worker.start()
        await self._scheduler.start()
    
    async def stop(self) -> None:
        """Stop both worker and scheduler."""
        if not self._running:
            return
        
        self._running = False
        await self._scheduler.stop()
        await self._worker.stop()
    
    async def run_forever(self) -> None:
        """Run until interrupted."""
        await self.start()
        
        # Wait for either to stop
        done, pending = await asyncio.wait(
            [
                asyncio.create_task(self._worker.wait()),
                asyncio.create_task(self._scheduler.wait()),
            ],
            return_when=asyncio.FIRST_COMPLETED,
        )
        
        # Stop the other
        for task in pending:
            task.cancel()
        
        await self.stop()


async def run_scheduler() -> None:
    """
    Run the task scheduler.
    
    Convenience function for CLI.
    """
    scheduler = TaskScheduler()
    await scheduler.run_forever()
