"""
Resource Inventory — auto-detection of all framework resources.

Collects registered tasks, workers, models, brokers, middleware, and routes
into a unified inventory for the Operations Center.
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.admin.site import AdminSite

logger = logging.getLogger("core.admin.ops")


class ResourceInventory:
    """
    Unified inventory of all framework resources.

    Collects from in-memory registries and configuration.
    """

    @staticmethod
    async def collect(site: "AdminSite") -> dict[str, Any]:
        """Collect full resource inventory."""
        return {
            "tasks": _collect_tasks(),
            "periodic_tasks": _collect_periodic_tasks(),
            "workers": _collect_workers(),
            "models": _collect_models(site),
            "brokers": _collect_brokers(),
            "middleware": _collect_middleware(),
        }


def _collect_tasks() -> list[dict[str, Any]]:
    """Collect registered tasks."""
    try:
        from core.tasks.registry import get_all_tasks
        tasks = get_all_tasks()
        return [
            {
                "name": name,
                "queue": t.queue,
                "retry": t.retry,
                "retry_delay": t.retry_delay,
                "timeout": t.timeout,
                "module": t.__module__,
                "actions": ["retry", "cancel", "view_result"],
            }
            for name, t in tasks.items()
        ]
    except Exception:
        return []


def _collect_periodic_tasks() -> list[dict[str, Any]]:
    """Collect registered periodic tasks."""
    try:
        from core.tasks.registry import get_periodic_tasks
        tasks = get_periodic_tasks()
        return [
            {
                "name": name,
                "cron": t.cron,
                "interval": t.interval,
                "queue": t.queue,
                "enabled": t.enabled,
                "last_run": t.last_run.isoformat() if t.last_run else None,
                "next_run": t.next_run.isoformat() if t.next_run else None,
                "run_count": t.run_count,
                "actions": ["enable_disable", "run_now", "edit_schedule"],
            }
            for name, t in tasks.items()
        ]
    except Exception:
        return []


def _collect_workers() -> list[dict[str, Any]]:
    """Collect registered message workers."""
    try:
        from core.messaging.workers import get_all_workers
        workers = get_all_workers()
        return [
            {
                "name": name,
                "input_topic": cfg.input_topic,
                "output_topic": cfg.output_topic,
                "concurrency": cfg.concurrency,
                "group_id": cfg.group_id,
                "actions": ["drain", "view_stats"],
            }
            for name, cfg in workers.items()
        ]
    except Exception:
        return []


def _collect_models(site: "AdminSite") -> list[dict[str, Any]]:
    """Collect registered admin models."""
    result = []
    for model, admin_instance in site.get_registry().items():
        result.append({
            "name": model.__name__,
            "app_label": admin_instance._app_label,
            "model_name": admin_instance._model_name,
            "display_name": admin_instance.display_name,
            "permissions": list(admin_instance.permissions),
        })
    return result


def _collect_brokers() -> list[dict[str, Any]]:
    """Collect configured message brokers."""
    brokers = []
    try:
        from core.config import get_settings
        settings = get_settings()

        # Kafka
        kafka_servers = getattr(settings, "kafka_bootstrap_servers", "")
        if kafka_servers:
            brokers.append({
                "name": "Kafka",
                "type": "broker",
                "servers": kafka_servers,
                "backend": getattr(settings, "kafka_backend", "aiokafka"),
                "actions": ["view_topics", "consumer_lag"],
            })

        # Redis
        redis_url = getattr(settings, "redis_url", "") or getattr(settings, "cache_url", "")
        if redis_url:
            brokers.append({
                "name": "Redis",
                "type": "cache",
                "url": _mask_password(redis_url),
                "actions": ["view_keys", "memory_stats"],
            })

        # RabbitMQ
        amqp_url = getattr(settings, "rabbitmq_url", "") or getattr(settings, "amqp_url", "")
        if amqp_url:
            brokers.append({
                "name": "RabbitMQ",
                "type": "broker",
                "url": _mask_password(amqp_url),
                "actions": ["view_queues"],
            })
    except Exception:
        pass
    return brokers


def _collect_middleware() -> list[dict[str, Any]]:
    """Collect configured middleware."""
    try:
        from core.config import get_settings
        settings = get_settings()
        middleware_list = getattr(settings, "middleware", [])
        return [{"name": m, "type": "middleware"} for m in middleware_list]
    except Exception:
        return []


def _mask_password(url: str) -> str:
    """Mask password in connection URLs for display."""
    try:
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(url)
        if parsed.password:
            masked = parsed._replace(
                netloc=f"{parsed.username}:****@{parsed.hostname}"
                + (f":{parsed.port}" if parsed.port else "")
            )
            return urlunparse(masked)
    except Exception:
        pass
    return url
