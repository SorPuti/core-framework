"""
Task worker for executing background tasks.

Consumes task messages from queues and executes them.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Any, Callable

from core.datetime import timezone
from core.tasks.base import TaskMessage, TaskResult, TaskStatus
from core.config import get_settings
from core.tasks.registry import get_task

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
        self._settings = get_settings()
        self._queues = queues or [self._settings.task_default_queue]
        self._concurrency = concurrency or self._settings.task_worker_concurrency
        self._db_session_factory = db_session_factory
        
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._consumer = None
        self._semaphore: asyncio.Semaphore | None = None
        self._active_tasks: set[asyncio.Task] = set()
        self._tasks_processed = 0
        self._tasks_errors = 0
        
        # Worker identity for heartbeat
        import uuid
        self._worker_id = str(uuid.uuid4())
        self._persist_enabled = getattr(self._settings, "ops_task_persist", True)
        self._heartbeat_interval = getattr(self._settings, "ops_worker_heartbeat_interval", 30)
        self._offline_ttl_hours = getattr(self._settings, "ops_worker_offline_ttl", 24)
        self._heartbeat_task: asyncio.Task | None = None
        self._cleanup_counter = 0
        
        # Registry para lazy loading de modelos (carregado apenas quando necessário)
        self._registry = None
    
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
        
        # Start consumer with retry — respects kafka_backend setting
        from core.messaging.registry import create_consumer
        
        topics = [f"tasks.{q}" for q in self._queues]
        
        # Retry connection with exponential backoff
        max_retries = 30  # More retries for slow Kafka startup
        retry_delay = 2
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # Create consumer using the configured backend (aiokafka or confluent)
                self._consumer = create_consumer(
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
        
        # Register heartbeat
        await self._register_heartbeat()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
    
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
        
        # Stop heartbeat
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        await self._mark_offline()
        
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
        import json as _json
        import traceback as _tb
        
        result = TaskResult(
            task_id=task_msg.task_id,
            task_name=task_msg.task_name,
            status=TaskStatus.RUNNING,
            started_at=timezone.now(),
        )
        
        logger.info(f"Executing task: {task_msg.task_name} ({task_msg.task_id})")
        
        # ── Persist start (ops) ──
        # Lazy load de modelos apenas se necessário
        await self._ensure_models_loaded()
        await self._persist_task_start(task_msg)
        
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
            result.error = f"{type(e).__name__}: {e}\n{_tb.format_exc()}"
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
        if result.status == TaskStatus.FAILURE:
            self._tasks_errors += 1
        
        # ── Persist finish (ops) ──
        duration_ms = None
        if result.started_at and result.finished_at:
            duration_ms = int((result.finished_at - result.started_at).total_seconds() * 1000)
        
        result_json = None
        if result.result is not None:
            try:
                result_json = _json.dumps(result.result, default=str)[:5000]
            except Exception:
                result_json = str(result.result)[:5000]
        
        await self._persist_task_finish(
            task_id=task_msg.task_id,
            status=result.status.value.upper(),
            result_json=result_json,
            error=result.error,
            retries=result.retries,
            duration_ms=duration_ms,
        )
        
        return result
    
    # ─── Ops: Task Persistence ────────────────────────────────────
    
    async def _ensure_models_loaded(self) -> None:
        """
        Lazy load de modelos via registry apenas quando necessário.
        
        Carrega modelos apenas se persistência estiver habilitada.
        """
        if not self._persist_enabled:
            return
        
        if self._registry is None:
            from core.registry import ModelRegistry
            self._registry = ModelRegistry.get_instance()
            
            # Carrega modelos apenas se necessário para persistência
            # Registry usa cache, então não há overhead se já foram carregados
            models_module = getattr(self._settings, "models_module", None)
            self._registry.discover_models(models_module=models_module)
    
    async def _persist_task_start(self, task_msg: TaskMessage) -> None:
        """Persist task execution start to the database."""
        if not self._persist_enabled:
            return
        try:
            import json as _json
            from core.models import get_session
            from core.admin.models import TaskExecution
            
            db = await get_session()
            async with db:
                await TaskExecution.record_start(
                    db,
                    task_name=task_msg.task_name,
                    task_id=task_msg.task_id,
                    queue=task_msg.queue,
                    args_json=_json.dumps(list(task_msg.args), default=str)[:5000] if task_msg.args else None,
                    kwargs_json=_json.dumps(task_msg.kwargs, default=str)[:5000] if task_msg.kwargs else None,
                    max_retries=task_msg.max_retries,
                    worker_id=self._worker_id,
                )
                await db.commit()
        except Exception as e:
            logger.debug("Failed to persist task start: %s", e)
    
    async def _persist_task_finish(
        self,
        *,
        task_id: str,
        status: str,
        result_json: str | None = None,
        error: str | None = None,
        retries: int = 0,
        duration_ms: int | None = None,
    ) -> None:
        """Persist task execution finish to the database."""
        if not self._persist_enabled:
            return
        try:
            from core.models import get_session
            from core.admin.models import TaskExecution
            
            db = await get_session()
            async with db:
                await TaskExecution.record_finish(
                    db,
                    task_id=task_id,
                    status=status,
                    result_json=result_json,
                    error=error[:5000] if error else None,
                    retries=retries,
                    duration_ms=duration_ms,
                )
        except Exception as e:
            logger.debug("Failed to persist task finish: %s", e)
    
    # ─── Ops: Worker Heartbeat ──────────────────────────────────
    
    async def _register_heartbeat(self) -> None:
        """
        Register this worker via UPSERT using a deterministic hash.
        
        Restarts/redeploys reuse the same row instead of creating
        duplicates (Issue #19).
        """
        try:
            import json as _json
            import socket
            from core.models import get_session
            from core.admin.models import WorkerHeartbeat
            from core.datetime import timezone
            from sqlalchemy import select
            
            worker_name = f"task-worker-{'-'.join(self._queues)}"
            identity_key = ":".join(sorted(self._queues))
            w_hash = WorkerHeartbeat.compute_hash(worker_name, "task_worker", identity_key)
            
            db = await get_session()
            async with db:
                # Try to find existing row by hash
                stmt = select(WorkerHeartbeat).where(WorkerHeartbeat.worker_hash == w_hash)
                result = await db.execute(stmt)
                existing = result.scalar_one_or_none()
                
                if existing:
                    # UPSERT: reuse existing row
                    existing.worker_id = self._worker_id
                    existing.hostname = socket.gethostname()
                    existing.pid = __import__("os").getpid()
                    existing.status = "ONLINE"
                    existing.concurrency = self._concurrency
                    existing.queues_json = _json.dumps(self._queues)
                    existing.total_processed = 0
                    existing.total_errors = 0
                    existing.active_tasks = 0
                    existing.started_at = timezone.now()
                    existing.last_heartbeat = timezone.now()
                    await db.commit()
                    logger.info(f"Heartbeat reused (hash={w_hash[:12]}...): {self._worker_id[:12]}...")
                else:
                    # First time: insert new row
                    hb = WorkerHeartbeat(
                        worker_id=self._worker_id,
                        worker_hash=w_hash,
                        worker_type="task_worker",
                        worker_name=worker_name,
                        hostname=socket.gethostname(),
                        pid=__import__("os").getpid(),
                        status="ONLINE",
                        concurrency=self._concurrency,
                        queues_json=_json.dumps(self._queues),
                    )
                    await hb.save(db)
                    await db.commit()
                    logger.info(f"Heartbeat registered (hash={w_hash[:12]}...): {self._worker_id[:12]}...")
        except Exception as e:
            logger.debug("Failed to register heartbeat: %s", e)
    
    async def _heartbeat_loop(self) -> None:
        """Periodic heartbeat update loop."""
        while self._running:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                await self._update_heartbeat()
                # Cleanup stale OFFLINE workers every 10 cycles
                self._cleanup_counter += 1
                if self._cleanup_counter >= 10:
                    self._cleanup_counter = 0
                    await self._cleanup_stale_workers()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("Heartbeat update failed: %s", e)
    
    async def _update_heartbeat(self) -> None:
        """Update heartbeat record."""
        try:
            from core.models import get_session
            from core.admin.models import WorkerHeartbeat
            from core.datetime import timezone
            from sqlalchemy import update
            
            db = await get_session()
            async with db:
                stmt = (
                    update(WorkerHeartbeat)
                    .where(WorkerHeartbeat.worker_id == self._worker_id)
                    .values(
                        active_tasks=len(self._active_tasks),
                        total_processed=self._tasks_processed,
                        total_errors=self._tasks_errors,
                        last_heartbeat=timezone.now(),
                        status="ONLINE",
                    )
                )
                await db.execute(stmt)
                await db.commit()
        except Exception:
            pass
    
    async def _mark_offline(self) -> None:
        """Mark this worker as offline."""
        try:
            from core.models import get_session
            from core.admin.models import WorkerHeartbeat
            from sqlalchemy import update
            
            db = await get_session()
            async with db:
                stmt = (
                    update(WorkerHeartbeat)
                    .where(WorkerHeartbeat.worker_id == self._worker_id)
                    .values(
                        status="OFFLINE",
                        total_processed=self._tasks_processed,
                        total_errors=self._tasks_errors,
                    )
                )
                await db.execute(stmt)
                await db.commit()
        except Exception:
            pass

    async def _cleanup_stale_workers(self) -> None:
        """Remove OFFLINE workers older than the configured TTL (Issue #19)."""
        if self._offline_ttl_hours <= 0:
            return
        try:
            from core.models import get_session
            from core.admin.models import WorkerHeartbeat
            from core.datetime import timezone
            from datetime import timedelta
            from sqlalchemy import delete as sa_delete
            
            cutoff = timezone.now() - timedelta(hours=self._offline_ttl_hours)
            
            db = await get_session()
            async with db:
                stmt = (
                    sa_delete(WorkerHeartbeat)
                    .where(WorkerHeartbeat.status == "OFFLINE")
                    .where(WorkerHeartbeat.last_heartbeat < cutoff)
                )
                result = await db.execute(stmt)
                await db.commit()
                if result.rowcount > 0:
                    logger.info(f"Cleaned up {result.rowcount} stale OFFLINE worker(s) (TTL={self._offline_ttl_hours}h)")
        except Exception:
            pass  # Fire-and-forget

    async def _retry_task(self, task_msg: TaskMessage) -> None:
        """Retry a failed task."""
        from core.tasks.registry import get_task_producer
        from datetime import timedelta
        
        settings = get_settings()
        
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
