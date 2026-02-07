"""
Worker system for message processing.

Celery-inspired worker pattern for consuming and processing messages.

Example:
    from core.messaging import Worker
    
    class GeolocationWorker(Worker):
        input_topic = "events.raw"
        output_topic = "events.enriched"
        concurrency = 5
        
        async def process(self, event: dict) -> dict:
            geo = await geoip_lookup(event["ip"])
            return {**event, **geo}
    
    # Usar o nome da classe
    print(GeolocationWorker.name)  # "GeolocationWorker"
    
    # Rodar - várias formas
    await GeolocationWorker.run()            # Mais simples
    await run_worker(GeolocationWorker)      # Passa a classe
    await run_worker("GeolocationWorker")    # Passa string (compatibilidade)
    
    # Batch processing
    class BatchWorker(Worker):
        input_topic = "events"
        batch_size = 1000
        batch_timeout = 10.0
        
        async def process_batch(self, events: list[dict]):
            # Processa batch de eventos
            for event in events:
                await self.handle(event)
"""

from __future__ import annotations

from typing import Any, Callable, Awaitable, TypeVar, Generic
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
import asyncio
import functools

from pydantic import BaseModel


# Type vars
T = TypeVar("T")
InputT = TypeVar("InputT", bound=BaseModel | dict)
OutputT = TypeVar("OutputT", bound=BaseModel | dict)

# Worker registry
_worker_registry: dict[str, "WorkerConfig"] = {}


class classproperty:
    """Descriptor for class-level properties."""
    
    def __init__(self, func):
        self.func = func
    
    def __get__(self, obj, objtype=None):
        return self.func(objtype)


@dataclass
class RetryPolicy:
    """Retry policy configuration."""
    
    max_retries: int = 3
    backoff: str = "exponential"  # "linear", "exponential", "fixed"
    initial_delay: float = 1.0
    max_delay: float = 60.0
    
    def get_delay(self, attempt: int) -> float:
        """Calculate delay for attempt number."""
        if self.backoff == "fixed":
            return self.initial_delay
        elif self.backoff == "linear":
            return min(self.initial_delay * attempt, self.max_delay)
        else:  # exponential
            return min(self.initial_delay * (2 ** attempt), self.max_delay)


@dataclass
class WorkerConfig:
    """Worker configuration."""
    
    name: str
    handler: Callable[..., Awaitable[Any]]
    input_topic: str
    output_topic: str | None = None
    group_id: str | None = None
    concurrency: int = 1
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    input_schema: type[BaseModel] | None = None
    output_schema: type[BaseModel] | None = None
    dlq_topic: str | None = None
    
    # Batch processing
    batch_size: int = 1
    batch_timeout: float = 0.0
    batch_handler: Callable[..., Awaitable[Any]] | None = None
    
    # Worker class reference
    _worker_class: type | None = None
    
    # Runtime state
    _running: bool = False
    _tasks: list[asyncio.Task] = field(default_factory=list)


def worker(
    topic: str,
    output_topic: str | None = None,
    group_id: str | None = None,
    concurrency: int = 1,
    max_retries: int = 3,
    retry_backoff: str = "exponential",
    input_schema: type[BaseModel] | None = None,
    output_schema: type[BaseModel] | None = None,
    dlq_topic: str | None = None,
):
    """
    Decorator to create a worker from a function.
    
    Example:
        @worker(
            topic="events.raw",
            output_topic="events.enriched",
            concurrency=5,
            max_retries=3,
        )
        async def process_event(event: dict) -> dict:
            # Process and return enriched event
            return {**event, "processed": True}
    
    Args:
        topic: Input topic to consume from
        output_topic: Optional output topic to publish results
        group_id: Consumer group ID (defaults to function name)
        concurrency: Number of concurrent workers
        max_retries: Maximum retry attempts
        retry_backoff: Backoff strategy ("linear", "exponential", "fixed")
        input_schema: Optional Pydantic model for input validation
        output_schema: Optional Pydantic model for output validation
        dlq_topic: Dead letter queue topic for failed messages
    
    Returns:
        Decorated function registered as worker
    """
    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        # Resolve Topic classes (TopicMeta) para strings — Issue #15
        _resolve = Worker._resolve_topic
        config = WorkerConfig(
            name=func.__name__,
            handler=func,
            input_topic=_resolve(topic),
            output_topic=_resolve(output_topic) if output_topic else None,
            group_id=group_id or func.__name__,
            concurrency=concurrency,
            retry_policy=RetryPolicy(
                max_retries=max_retries,
                backoff=retry_backoff,
            ),
            input_schema=input_schema,
            output_schema=output_schema,
            dlq_topic=_resolve(dlq_topic) if dlq_topic else None,
        )
        
        # Register worker
        _worker_registry[func.__name__] = config
        
        # Add config to function
        func._worker_config = config
        
        return func
    
    return decorator


class Worker(ABC):
    """
    Base class for message workers.
    
    Abstração de Consumer + Producer para processamento de mensagens.
    
    Example:
        class OrderProcessor(Worker):
            input_topic = "orders.created"
            output_topic = "orders.processed"
            concurrency = 3
            
            async def process(self, order: dict) -> dict:
                return {**order, "processed": True}
        
        # Acessar nome
        print(OrderProcessor.name)  # "OrderProcessor"
        
        # Rodar worker
        await OrderProcessor.run()
        
        # Batch processing
        class BatchProcessor(Worker):
            input_topic = "events"
            batch_size = 1000
            batch_timeout = 10.0
            
            async def process_batch(self, events: list[dict]):
                # Processa batch
                pass
    """
    
    # Configuration (override in subclass)
    input_topic: str | Any = ""  # Pode ser string ou Topic class
    output_topic: str | Any | None = None
    group_id: str | None = None
    concurrency: int = 1
    max_retries: int = 3
    retry_backoff: str = "exponential"
    input_schema: type[BaseModel] | None = None
    output_schema: type[BaseModel] | None = None
    dlq_topic: str | Any | None = None
    
    # Batch processing
    batch_size: int = 1
    batch_timeout: float = 0.0
    
    # Runtime state
    _running: bool = False
    _consumer = None
    _producer = None
    _config: WorkerConfig | None = None
    
    def __init_subclass__(cls, **kwargs):
        """Auto-register worker subclasses."""
        super().__init_subclass__(**kwargs)
        
        # Don't register the base class
        if cls.__name__ == "Worker":
            return
        
        # Resolve topic names (pode ser string ou Topic class)
        input_topic = cls._resolve_topic(cls.input_topic)
        output_topic = cls._resolve_topic(cls.output_topic) if cls.output_topic else None
        dlq_topic = cls._resolve_topic(cls.dlq_topic) if cls.dlq_topic else None
        
        # Check if has batch handler
        has_batch = hasattr(cls, 'process_batch') and cls.process_batch is not Worker.process_batch
        
        # Create config
        config = WorkerConfig(
            name=cls.__name__,
            handler=cls._create_handler(cls),
            input_topic=input_topic,
            output_topic=output_topic,
            group_id=cls.group_id or cls.__name__,
            concurrency=cls.concurrency,
            retry_policy=RetryPolicy(
                max_retries=cls.max_retries,
                backoff=cls.retry_backoff,
            ),
            input_schema=cls.input_schema,
            output_schema=cls.output_schema,
            dlq_topic=dlq_topic,
            batch_size=cls.batch_size,
            batch_timeout=cls.batch_timeout,
            batch_handler=cls._create_batch_handler(cls) if has_batch else None,
            _worker_class=cls,
        )
        
        # Store config on class
        cls._config = config
        
        # Register
        _worker_registry[cls.__name__] = config
    
    @classmethod
    def _resolve_topic(cls, topic: str | Any) -> str:
        """Resolve topic name from string or Topic class."""
        if topic is None:
            return ""
        if isinstance(topic, str):
            return topic
        if hasattr(topic, 'name'):
            return topic.name
        if hasattr(topic, 'value'):
            return topic.value
        return str(topic)
    
    @classmethod
    def _create_handler(cls, worker_cls: type["Worker"]) -> Callable[..., Awaitable[Any]]:
        """Create handler function from worker class."""
        async def handler(message: dict) -> Any:
            instance = worker_cls()
            return await instance.process(message)
        return handler
    
    @classmethod
    def _create_batch_handler(cls, worker_cls: type["Worker"]) -> Callable[..., Awaitable[Any]]:
        """Create batch handler function from worker class."""
        async def handler(messages: list[dict]) -> Any:
            instance = worker_cls()
            return await instance.process_batch(messages)
        return handler
    
    # =========================================================================
    # Class properties and methods
    # =========================================================================
    
    @classproperty
    def name(cls) -> str:
        """Nome do worker (nome da classe)."""
        return cls.__name__
    
    @classmethod
    async def run(cls) -> None:
        """
        Roda o worker.
        
        Forma mais simples de iniciar:
            await MyWorker.run()
        """
        await run_worker(cls)
    
    @classmethod
    def get_config(cls) -> WorkerConfig | None:
        """Retorna configuração do worker."""
        return cls._config
    
    # =========================================================================
    # Instance methods (override in subclass)
    # =========================================================================
    
    async def process(self, message: dict[str, Any]) -> Any:
        """
        Process a single message.
        
        Override this OR process_batch in your worker.
        
        Args:
            message: Deserialized message payload
        
        Returns:
            Processed result (sent to output_topic if configured)
        """
        # Default: não faz nada se process_batch está definido
        pass
    
    async def process_batch(self, messages: list[dict[str, Any]]) -> Any:
        """
        Process a batch of messages.
        
        Override this for batch processing.
        
        Args:
            messages: List of deserialized message payloads
        
        Returns:
            Processed result
        """
        # Default: processa um por um
        for message in messages:
            await self.process(message)
    
    async def on_error(self, message: dict[str, Any], error: Exception) -> None:
        """
        Handle processing error.
        
        Override to customize error handling.
        
        Args:
            message: Original message
            error: Exception that occurred
        """
        pass
    
    async def on_success(self, message: dict[str, Any], result: Any) -> None:
        """
        Handle successful processing.
        
        Override to add post-processing logic.
        
        Args:
            message: Original message
            result: Processing result
        """
        pass


def get_worker(name_or_class: str | type) -> WorkerConfig | None:
    """
    Get a registered worker by name or class.
    
    Args:
        name_or_class: Worker name (string) ou Worker class
    
    Returns:
        WorkerConfig or None if not found
    
    Example:
        config = get_worker("MyWorker")
        config = get_worker(MyWorker)
    """
    if isinstance(name_or_class, str):
        return _worker_registry.get(name_or_class)
    
    # É uma classe Worker
    if hasattr(name_or_class, '_config'):
        return name_or_class._config
    
    # Tenta pelo nome da classe
    return _worker_registry.get(name_or_class.__name__)


def get_all_workers() -> dict[str, WorkerConfig]:
    """
    Get all registered workers.
    
    Returns:
        Dict of worker name -> WorkerConfig
    """
    return _worker_registry.copy()


def list_workers() -> list[str]:
    """
    List all registered worker names.
    
    Returns:
        List of worker names
    """
    return list(_worker_registry.keys())


async def run_worker(worker: str | type) -> None:
    """
    Run a worker by name or class.
    
    Args:
        worker: Worker name (string) ou Worker class
    
    Raises:
        ValueError: If worker not found
    
    Example:
        # Por string
        await run_worker("MyWorker")
        
        # Por classe (recomendado)
        await run_worker(MyWorker)
        
        # Ou diretamente
        await MyWorker.run()
    """
    config = get_worker(worker)
    
    if config is None:
        name = worker if isinstance(worker, str) else worker.__name__
        raise ValueError(f"Worker '{name}' not found. Available: {list_workers()}")
    
    await _run_worker_config(config)


async def run_all_workers() -> None:
    """Run all registered workers."""
    tasks = []
    for name, config in _worker_registry.items():
        task = asyncio.create_task(_run_worker_config(config))
        tasks.append(task)
    
    await asyncio.gather(*tasks)


async def _run_worker_config(config: WorkerConfig) -> None:
    """
    Run a worker from its config.
    
    Includes heartbeat reporting to admin_worker_heartbeats for the
    Operations Center (same pattern as TaskWorker). Zero overhead on
    the hot path — counters are in-memory, DB writes happen in a
    separate asyncio task every N seconds.
    
    Args:
        config: Worker configuration
    """
    import logging
    import os
    import socket
    import uuid
    from core.messaging import get_producer
    from core.messaging.registry import create_consumer
    
    logger = logging.getLogger(f"worker.{config.name}")
    
    _db_available = False
    try:
        from core.config import get_settings
        _settings = get_settings()
        db_url = getattr(_settings, "database_url", None)
        if db_url:
            if getattr(_settings, "has_read_replica", False):
                from core.database import init_replicas
                await init_replicas()
            else:
                from core.models import init_database
                await init_database(db_url)
            _db_available = True
            logger.debug("Database initialized for heartbeat reporting")
    except Exception as e:
        logger.warning("Could not initialize database for heartbeats: %s", e)
    
    # ── Heartbeat state (in-memory counters, zero I/O overhead) ──
    worker_id = str(uuid.uuid4())
    _total_processed = 0
    _total_errors = 0
    _active = 0
    _running = True
    
    # Heartbeat settings
    try:
        _hb_interval = getattr(_settings, "ops_worker_heartbeat_interval", 30)
    except Exception:
        _hb_interval = 30
    
    async def _get_session():
        """Get a DB session, trying both session factories. (Issue #18)"""
        try:
            from core.database import get_write_session
            return await get_write_session()
        except (RuntimeError, Exception):
            pass
        from core.models import get_session
        return await get_session()
    
    async def _register_heartbeat() -> None:
        """Register this worker in the heartbeat table. Fire-and-forget."""
        if not _db_available:
            return
        try:
            import json as _json
            from core.admin.models import WorkerHeartbeat
            
            db = await _get_session()
            async with db:
                hb = WorkerHeartbeat(
                    worker_id=worker_id,
                    worker_type="message",
                    worker_name=config.name,
                    hostname=socket.gethostname(),
                    pid=os.getpid(),
                    status="ONLINE",
                    concurrency=config.concurrency,
                    queues_json=_json.dumps([config.input_topic]),
                )
                await hb.save(db)
                await db.commit()
            logger.info(f"Heartbeat registered: {worker_id[:12]}...")
        except Exception as e:
            logger.warning("Failed to register heartbeat: %s", e)
    
    async def _heartbeat_loop() -> None:
        """Periodic heartbeat update. Isolated task, fire-and-forget writes."""
        while _running:
            try:
                await asyncio.sleep(_hb_interval)
                await _update_heartbeat()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("Heartbeat update failed: %s", e)
    
    async def _update_heartbeat() -> None:
        """Flush in-memory counters to DB. Non-blocking, fire-and-forget."""
        if not _db_available:
            return
        try:
            from core.admin.models import WorkerHeartbeat
            from core.datetime import timezone
            from sqlalchemy import update
            
            db = await _get_session()
            async with db:
                stmt = (
                    update(WorkerHeartbeat)
                    .where(WorkerHeartbeat.worker_id == worker_id)
                    .values(
                        active_tasks=_active,
                        total_processed=_total_processed,
                        total_errors=_total_errors,
                        last_heartbeat=timezone.now(),
                        status="ONLINE",
                    )
                )
                await db.execute(stmt)
                await db.commit()
        except Exception:
            pass  # Fire-and-forget — never affect consumer
    
    async def _mark_offline() -> None:
        """Mark this worker as OFFLINE in the heartbeat table."""
        if not _db_available:
            return
        try:
            from core.admin.models import WorkerHeartbeat
            from sqlalchemy import update
            
            db = await _get_session()
            async with db:
                stmt = (
                    update(WorkerHeartbeat)
                    .where(WorkerHeartbeat.worker_id == worker_id)
                    .values(
                        status="OFFLINE",
                        total_processed=_total_processed,
                        total_errors=_total_errors,
                    )
                )
                await db.execute(stmt)
                await db.commit()
            logger.info(f"Worker marked OFFLINE. Processed {_total_processed}, errors {_total_errors}")
        except Exception:
            pass
    
    # Get producer if output topic or DLQ configured
    producer = None
    if config.output_topic or config.dlq_topic:
        producer = get_producer()
        await producer.start()
    
    # Batch state
    batch: list[dict] = []
    batch_lock = asyncio.Lock()
    last_batch_time = asyncio.get_event_loop().time()
    
    async def flush_batch() -> None:
        """Flush accumulated batch."""
        nonlocal batch, last_batch_time, _total_processed, _total_errors
        
        if not batch:
            return
        
        async with batch_lock:
            messages_to_process = batch.copy()
            batch = []
            last_batch_time = asyncio.get_event_loop().time()
        
        if not messages_to_process:
            return
        
        # Process batch with retries
        last_error = None
        for attempt in range(config.retry_policy.max_retries + 1):
            try:
                if config.batch_handler:
                    await config.batch_handler(messages_to_process)
                else:
                    for msg in messages_to_process:
                        await config.handler(msg)
                _total_processed += len(messages_to_process)
                return  # Success
                
            except Exception as e:
                last_error = e
                if attempt < config.retry_policy.max_retries:
                    delay = config.retry_policy.get_delay(attempt)
                    logger.warning(f"Batch retry {attempt + 1}/{config.retry_policy.max_retries} in {delay}s: {e}")
                    await asyncio.sleep(delay)
        
        # All retries failed
        _total_errors += len(messages_to_process)
        logger.error(f"Batch failed after {config.retry_policy.max_retries} retries: {last_error}")
        
        if config.dlq_topic and producer:
            for msg in messages_to_process:
                await producer.send(config.dlq_topic, {
                    "original": msg,
                    "error": str(last_error),
                    "worker": config.name,
                })
    
    async def batch_timer() -> None:
        """Timer to flush batch on timeout."""
        while True:
            await asyncio.sleep(1)
            if config.batch_timeout > 0 and batch:
                elapsed = asyncio.get_event_loop().time() - last_batch_time
                if elapsed >= config.batch_timeout:
                    await flush_batch()
    
    async def process_message(message: dict) -> None:
        """Process single message or add to batch. Counters are in-memory only."""
        nonlocal batch, _total_processed, _total_errors, _active
        
        # Validate input
        if config.input_schema:
            try:
                validated = config.input_schema.model_validate(message)
                message = validated.model_dump()
            except Exception as e:
                _total_errors += 1
                logger.error(f"Input validation failed: {e}")
                if config.dlq_topic and producer:
                    await producer.send(config.dlq_topic, {
                        "original": message,
                        "error": str(e),
                        "worker": config.name,
                    })
                return
        
        # Batch mode
        if config.batch_size > 1 or config.batch_handler:
            async with batch_lock:
                batch.append(message)
                if len(batch) >= config.batch_size:
                    await flush_batch()
            return
        
        # Single message mode with retries
        _active += 1
        last_error = None
        try:
            for attempt in range(config.retry_policy.max_retries + 1):
                try:
                    result = await config.handler(message)
                    
                    # Validate output
                    if config.output_schema and result:
                        result = config.output_schema.model_validate(result).model_dump()
                    
                    # Publish result
                    if config.output_topic and producer and result:
                        await producer.send(config.output_topic, result)
                    
                    _total_processed += 1
                    return  # Success
                    
                except Exception as e:
                    last_error = e
                    if attempt < config.retry_policy.max_retries:
                        delay = config.retry_policy.get_delay(attempt)
                        logger.warning(f"Retry {attempt + 1}/{config.retry_policy.max_retries} in {delay}s: {e}")
                        await asyncio.sleep(delay)
            
            # All retries failed
            _total_errors += 1
            logger.error(f"Failed after {config.retry_policy.max_retries} retries: {last_error}")
            
            if config.dlq_topic and producer:
                await producer.send(config.dlq_topic, {
                    "original": message,
                    "error": str(last_error),
                    "worker": config.name,
                    "retries": config.retry_policy.max_retries,
                })
        finally:
            _active -= 1
    
    # Create consumer with message handler
    consumer = create_consumer(
        group_id=config.group_id,
        topics=[config.input_topic],
        message_handler=process_message,
    )
    
    # Log startup
    logger.info(f"Starting worker: {config.name}")
    logger.info(f"  Worker ID: {worker_id[:12]}...")
    logger.info(f"  Input topic: {config.input_topic}")
    logger.info(f"  Output topic: {config.output_topic or 'None'}")
    logger.info(f"  Concurrency: {config.concurrency}")
    logger.info(f"  Heartbeat interval: {_hb_interval}s")
    if config.batch_size > 1:
        logger.info(f"  Batch size: {config.batch_size}")
        logger.info(f"  Batch timeout: {config.batch_timeout}s")
    
    # Start batch timer if needed
    timer_task = None
    if config.batch_timeout > 0 and (config.batch_size > 1 or config.batch_handler):
        timer_task = asyncio.create_task(batch_timer())
    
    # Register heartbeat & start heartbeat loop (separate task, fire-and-forget)
    await _register_heartbeat()
    heartbeat_task = asyncio.create_task(_heartbeat_loop())
    
    # Start consumer
    await consumer.start()
    
    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        _running = False
        
        # Flush remaining batch
        if batch:
            await flush_batch()
        
        if timer_task:
            timer_task.cancel()
        
        heartbeat_task.cancel()
        await _mark_offline()
        
        await consumer.stop()
        
        if producer:
            await producer.stop()
