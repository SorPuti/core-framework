"""
Task system configuration.

All task-related settings are defined here and can be
configured via environment variables or .env file.
"""

from __future__ import annotations

from typing import Literal
from pydantic import Field as PydanticField
from pydantic_settings import BaseSettings


class TaskSettings(BaseSettings):
    """
    Task system configuration.
    
    All settings can be overridden via environment variables:
        TASK_DEFAULT_QUEUE=default
        TASK_WORKER_CONCURRENCY=4
    """
    
    # ==========================================================================
    # QUEUE SETTINGS
    # ==========================================================================
    
    task_default_queue: str = PydanticField(
        default="default",
        description="Default queue for tasks without explicit queue",
    )
    task_scheduled_queue: str = PydanticField(
        default="scheduled",
        description="Queue for periodic/scheduled tasks",
    )
    task_dead_letter_queue: str = PydanticField(
        default="dead-letter",
        description="Queue for failed tasks after all retries",
    )
    
    # ==========================================================================
    # RETRY SETTINGS
    # ==========================================================================
    
    task_default_retry: int = PydanticField(
        default=3,
        description="Default number of retry attempts",
    )
    task_default_retry_delay: int = PydanticField(
        default=60,
        description="Default delay between retries in seconds",
    )
    task_retry_backoff: bool = PydanticField(
        default=True,
        description="Use exponential backoff for retries",
    )
    task_retry_backoff_max: int = PydanticField(
        default=3600,
        description="Maximum retry delay in seconds",
    )
    
    # ==========================================================================
    # TIMEOUT SETTINGS
    # ==========================================================================
    
    task_default_timeout: int = PydanticField(
        default=300,
        description="Default task timeout in seconds",
    )
    task_soft_timeout: int = PydanticField(
        default=240,
        description="Soft timeout (warning) in seconds",
    )
    
    # ==========================================================================
    # WORKER SETTINGS
    # ==========================================================================
    
    task_worker_concurrency: int = PydanticField(
        default=4,
        description="Number of concurrent tasks per worker",
    )
    task_worker_prefetch: int = PydanticField(
        default=4,
        description="Number of tasks to prefetch",
    )
    task_worker_max_tasks: int = PydanticField(
        default=0,
        description="Max tasks before worker restarts (0 = unlimited)",
    )
    task_worker_max_memory: int = PydanticField(
        default=0,
        description="Max memory in MB before worker restarts (0 = unlimited)",
    )
    
    # ==========================================================================
    # SCHEDULER SETTINGS
    # ==========================================================================
    
    task_scheduler_interval: int = PydanticField(
        default=1,
        description="Scheduler check interval in seconds",
    )
    task_scheduler_max_interval: int = PydanticField(
        default=300,
        description="Maximum scheduler interval in seconds",
    )
    
    # ==========================================================================
    # RESULT SETTINGS
    # ==========================================================================
    
    task_result_backend: Literal["none", "redis", "database"] = PydanticField(
        default="none",
        description="Where to store task results",
    )
    task_result_expires: int = PydanticField(
        default=86400,
        description="Task result expiration in seconds",
    )
    task_track_started: bool = PydanticField(
        default=True,
        description="Track when tasks start executing",
    )
    
    # ==========================================================================
    # LOGGING SETTINGS
    # ==========================================================================
    
    task_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = PydanticField(
        default="INFO",
        description="Task logging level",
    )
    task_log_format: str = PydanticField(
        default="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        description="Task log format",
    )
    
    model_config = {
        "env_prefix": "",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# Global settings instance
_task_settings: TaskSettings | None = None


def get_task_settings() -> TaskSettings:
    """
    Get the global task settings instance.
    
    Returns:
        TaskSettings instance
    """
    global _task_settings
    if _task_settings is None:
        _task_settings = TaskSettings()
    return _task_settings


def configure_tasks(**kwargs) -> TaskSettings:
    """
    Configure task settings programmatically.
    
    Args:
        **kwargs: Settings to override
    
    Returns:
        Updated TaskSettings instance
    
    Example:
        configure_tasks(
            task_worker_concurrency=8,
            task_default_retry=5,
        )
    """
    global _task_settings
    _task_settings = TaskSettings(**kwargs)
    return _task_settings
