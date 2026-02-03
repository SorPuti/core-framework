"""
Worker system for message processing.

Celery-inspired worker pattern for consuming and processing messages.

Example:
    from core.messaging import worker, Worker
    
    # Decorator style (simple)
    @worker(
        topic="events.raw",
        output_topic="events.enriched",
        concurrency=5,
    )
    async def enrich_event(event: dict) -> dict:
        geo = await geoip_lookup(event["ip"])
        return {**event, **geo}
    
    # Class style (complex)
    class GeolocationWorker(Worker):
        input_topic = "events.raw"
        output_topic = "events.enriched"
        concurrency = 5
        
        async def process(self, event: dict) -> dict:
            geo = await geoip_lookup(event["ip"])
            return {**event, **geo}
    
    # Run workers
    # core runworker enrich_event
    # core runworker GeolocationWorker
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
        config = WorkerConfig(
            name=func.__name__,
            handler=func,
            input_topic=topic,
            output_topic=output_topic,
            group_id=group_id or func.__name__,
            concurrency=concurrency,
            retry_policy=RetryPolicy(
                max_retries=max_retries,
                backoff=retry_backoff,
            ),
            input_schema=input_schema,
            output_schema=output_schema,
            dlq_topic=dlq_topic,
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
    
    Provides a class-based alternative to the @worker decorator
    for more complex processing logic.
    
    Example:
        class OrderProcessor(Worker):
            input_topic = "orders.created"
            output_topic = "orders.processed"
            concurrency = 3
            
            async def process(self, order: dict) -> dict:
                # Complex processing with access to self
                validated = await self.validate_order(order)
                enriched = await self.enrich_order(validated)
                return enriched
            
            async def validate_order(self, order: dict) -> dict:
                # Validation logic
                return order
            
            async def enrich_order(self, order: dict) -> dict:
                # Enrichment logic
                return order
    """
    
    # Configuration (override in subclass)
    input_topic: str = ""
    output_topic: str | None = None
    group_id: str | None = None
    concurrency: int = 1
    max_retries: int = 3
    retry_backoff: str = "exponential"
    input_schema: type[BaseModel] | None = None
    output_schema: type[BaseModel] | None = None
    dlq_topic: str | None = None
    
    # Runtime state
    _running: bool = False
    _consumer = None
    _producer = None
    
    def __init_subclass__(cls, **kwargs):
        """Auto-register worker subclasses."""
        super().__init_subclass__(**kwargs)
        
        # Don't register the base class
        if cls.__name__ == "Worker":
            return
        
        # Create config
        config = WorkerConfig(
            name=cls.__name__,
            handler=cls._create_handler(cls),
            input_topic=cls.input_topic,
            output_topic=cls.output_topic,
            group_id=cls.group_id or cls.__name__,
            concurrency=cls.concurrency,
            retry_policy=RetryPolicy(
                max_retries=cls.max_retries,
                backoff=cls.retry_backoff,
            ),
            input_schema=cls.input_schema,
            output_schema=cls.output_schema,
            dlq_topic=cls.dlq_topic,
        )
        
        # Store class reference
        config._worker_class = cls
        
        # Register
        _worker_registry[cls.__name__] = config
    
    @classmethod
    def _create_handler(cls, worker_cls: type["Worker"]) -> Callable[..., Awaitable[Any]]:
        """Create handler function from worker class."""
        async def handler(message: dict) -> Any:
            instance = worker_cls()
            return await instance.process(message)
        return handler
    
    @abstractmethod
    async def process(self, message: dict[str, Any]) -> Any:
        """
        Process a single message.
        
        Override this method in your worker.
        
        Args:
            message: Deserialized message payload
        
        Returns:
            Processed result (sent to output_topic if configured)
        """
        ...
    
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


def get_worker(name: str) -> WorkerConfig | None:
    """
    Get a registered worker by name.
    
    Args:
        name: Worker name (function or class name)
    
    Returns:
        WorkerConfig or None if not found
    """
    return _worker_registry.get(name)


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


async def run_worker(name: str) -> None:
    """
    Run a worker by name.
    
    Args:
        name: Worker name
    
    Raises:
        ValueError: If worker not found
    """
    config = get_worker(name)
    if config is None:
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
    
    Args:
        config: Worker configuration
    """
    from core.messaging import get_producer
    from core.messaging.config import get_messaging_settings
    
    settings = get_messaging_settings()
    
    # Get appropriate consumer based on backend
    kafka_backend = getattr(settings, "kafka_backend", "aiokafka")
    
    if kafka_backend == "confluent":
        from core.messaging.confluent import ConfluentConsumer
        consumer_class = ConfluentConsumer
    else:
        from core.messaging.kafka import KafkaConsumer
        consumer_class = KafkaConsumer
    
    # Create consumer
    consumer = consumer_class(
        group_id=config.group_id,
        topics=[config.input_topic],
    )
    
    # Get producer if output topic configured
    producer = None
    if config.output_topic:
        producer = get_producer()
        await producer.start()
    
    async def process_with_retry(message: dict) -> None:
        """Process message with retry logic."""
        # Validate input
        if config.input_schema:
            try:
                validated = config.input_schema.model_validate(message)
                message = validated.model_dump()
            except Exception as e:
                print(f"Input validation failed: {e}")
                if config.dlq_topic and producer:
                    await producer.send(config.dlq_topic, {
                        "original": message,
                        "error": str(e),
                        "worker": config.name,
                    })
                return
        
        # Process with retries
        last_error = None
        for attempt in range(config.retry_policy.max_retries + 1):
            try:
                result = await config.handler(message)
                
                # Validate output
                if config.output_schema and result:
                    result = config.output_schema.model_validate(result).model_dump()
                
                # Publish result
                if config.output_topic and producer and result:
                    await producer.send(config.output_topic, result)
                
                return  # Success
                
            except Exception as e:
                last_error = e
                if attempt < config.retry_policy.max_retries:
                    delay = config.retry_policy.get_delay(attempt)
                    print(f"Worker {config.name} retry {attempt + 1}/{config.retry_policy.max_retries} in {delay}s: {e}")
                    await asyncio.sleep(delay)
        
        # All retries failed
        print(f"Worker {config.name} failed after {config.retry_policy.max_retries} retries: {last_error}")
        
        if config.dlq_topic and producer:
            await producer.send(config.dlq_topic, {
                "original": message,
                "error": str(last_error),
                "worker": config.name,
                "retries": config.retry_policy.max_retries,
            })
    
    # Start consumer
    print(f"Starting worker: {config.name}")
    print(f"  Input topic: {config.input_topic}")
    print(f"  Output topic: {config.output_topic or 'None'}")
    print(f"  Concurrency: {config.concurrency}")
    
    await consumer.start(process_with_retry)
    
    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        await consumer.stop()
        if producer:
            await producer.stop()
