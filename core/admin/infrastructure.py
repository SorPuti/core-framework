"""
Infrastructure detection and system monitoring.

Detects runtime environment (Docker, Kubernetes, PM2, Systemd, Bare Metal)
and collects system metrics, service health, and process information.
"""

from __future__ import annotations

import logging
import os
import platform
import socket
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from core.datetime import timezone

logger = logging.getLogger("core.admin.infrastructure")

# ── Process start time (captured at import) ──
_PROCESS_START_TIME = time.time()


class RuntimeEnvironment:
    """Known runtime environments."""
    DOCKER = "docker"
    KUBERNETES = "kubernetes"
    PM2 = "pm2"
    SYSTEMD = "systemd"
    BARE_METAL = "bare_metal"

    LABELS = {
        "docker": "Docker Container",
        "kubernetes": "Kubernetes Pod",
        "pm2": "PM2 Process",
        "systemd": "Systemd Service",
        "bare_metal": "Direct Execution",
    }
    ICONS = {
        "docker": "container",
        "kubernetes": "cloud",
        "pm2": "layers",
        "systemd": "server",
        "bare_metal": "monitor",
    }


class InfraDetector:
    """
    Detects and reports infrastructure state.

    Provides:
    - Runtime environment detection
    - System metrics (CPU, RAM, disk)
    - Connected service health checks
    - Process information
    """

    # ─── Runtime Detection ───────────────────────────────────────

    @staticmethod
    def detect_runtime() -> str:
        """
        Detect the runtime environment.

        Order of checks (most specific first):
        1. Kubernetes (KUBERNETES_SERVICE_HOST env var)
        2. Docker (/.dockerenv file or /proc/1/cgroup)
        3. PM2 (PM2_HOME env var)
        4. Systemd (INVOCATION_ID env var)
        5. Bare Metal (fallback)
        """
        # K8s — every pod has this injected
        if os.environ.get("KUBERNETES_SERVICE_HOST"):
            return RuntimeEnvironment.KUBERNETES

        # Docker — /.dockerenv exists in every Docker container
        if Path("/.dockerenv").exists():
            return RuntimeEnvironment.DOCKER
        try:
            cgroup = Path("/proc/1/cgroup").read_text(errors="ignore")
            if "docker" in cgroup or "containerd" in cgroup:
                return RuntimeEnvironment.DOCKER
        except (OSError, PermissionError):
            pass

        # PM2
        if os.environ.get("PM2_HOME") or os.environ.get("pm_id") is not None:
            return RuntimeEnvironment.PM2

        # Systemd
        if os.environ.get("INVOCATION_ID"):
            return RuntimeEnvironment.SYSTEMD

        return RuntimeEnvironment.BARE_METAL

    # ─── System Info ─────────────────────────────────────────────

    @staticmethod
    def get_system_info() -> dict[str, Any]:
        """
        Collect system-level information.

        Returns CPU, memory, disk metrics (via psutil if available,
        fallback to /proc on Linux).
        """
        info: dict[str, Any] = {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "os": platform.system(),
            "os_release": platform.release(),
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
        }

        # Try psutil first (most accurate, cross-platform)
        try:
            import psutil  # type: ignore[import-untyped]

            # CPU
            info["cpu_count"] = psutil.cpu_count(logical=True)
            info["cpu_count_physical"] = psutil.cpu_count(logical=False)
            info["cpu_percent"] = psutil.cpu_percent(interval=0.1)

            # Memory
            mem = psutil.virtual_memory()
            info["memory_total_mb"] = round(mem.total / (1024 * 1024))
            info["memory_used_mb"] = round(mem.used / (1024 * 1024))
            info["memory_percent"] = mem.percent

            # Disk
            disk = psutil.disk_usage("/")
            info["disk_total_gb"] = round(disk.total / (1024**3), 1)
            info["disk_used_gb"] = round(disk.used / (1024**3), 1)
            info["disk_percent"] = disk.percent

            info["_source"] = "psutil"

        except ImportError:
            # Fallback: parse /proc on Linux
            info["_source"] = "proc"
            info["cpu_count"] = os.cpu_count() or 0

            try:
                meminfo = Path("/proc/meminfo").read_text()
                mem_lines = {
                    l.split(":")[0].strip(): int(l.split(":")[1].strip().split()[0])
                    for l in meminfo.splitlines()
                    if ":" in l
                }
                total_kb = mem_lines.get("MemTotal", 0)
                available_kb = mem_lines.get("MemAvailable", 0)
                used_kb = total_kb - available_kb
                info["memory_total_mb"] = round(total_kb / 1024)
                info["memory_used_mb"] = round(used_kb / 1024)
                info["memory_percent"] = round(used_kb / total_kb * 100, 1) if total_kb else 0
            except (OSError, ValueError):
                info["memory_total_mb"] = 0
                info["memory_used_mb"] = 0
                info["memory_percent"] = 0

            try:
                statvfs = os.statvfs("/")
                total = statvfs.f_blocks * statvfs.f_frsize
                used = (statvfs.f_blocks - statvfs.f_bfree) * statvfs.f_frsize
                info["disk_total_gb"] = round(total / (1024**3), 1)
                info["disk_used_gb"] = round(used / (1024**3), 1)
                info["disk_percent"] = round(used / total * 100, 1) if total else 0
            except (OSError, AttributeError):
                info["disk_total_gb"] = 0
                info["disk_used_gb"] = 0
                info["disk_percent"] = 0

        return info

    # ─── Process Info ────────────────────────────────────────────

    @staticmethod
    def get_process_info() -> dict[str, Any]:
        """Get information about the current process."""
        import threading

        uptime_seconds = time.time() - _PROCESS_START_TIME

        info: dict[str, Any] = {
            "pid": os.getpid(),
            "ppid": os.getppid(),
            "uptime_seconds": round(uptime_seconds),
            "uptime_human": _format_uptime(uptime_seconds),
            "started_at": datetime.fromtimestamp(_PROCESS_START_TIME).isoformat(),
            "thread_count": threading.active_count(),
            "working_directory": os.getcwd(),
        }

        # Framework version
        try:
            from core import __version__
            info["framework_version"] = __version__
        except ImportError:
            info["framework_version"] = "unknown"

        # psutil extras
        try:
            import psutil  # type: ignore[import-untyped]
            proc = psutil.Process(os.getpid())
            info["memory_rss_mb"] = round(proc.memory_info().rss / (1024 * 1024), 1)
            info["open_files"] = len(proc.open_files())
            info["connections"] = len(proc.net_connections())
        except (ImportError, Exception):
            pass

        return info

    # ─── Service Health ──────────────────────────────────────────

    @staticmethod
    async def get_service_health() -> list[dict[str, Any]]:
        """
        Check health of connected services (DB, Kafka, Redis, RabbitMQ).

        Returns list of service status dicts.
        """
        services: list[dict[str, Any]] = []

        # ── PostgreSQL / Database ──
        services.append(await _check_database())

        # ── Kafka ──
        services.append(await _check_kafka())

        # ── Redis ──
        services.append(await _check_redis())

        # ── RabbitMQ ──
        services.append(await _check_rabbitmq())

        return services

    # ─── Full Report ─────────────────────────────────────────────

    @classmethod
    async def collect(cls) -> dict[str, Any]:
        """Collect full infrastructure report."""
        runtime = cls.detect_runtime()
        return {
            "runtime": {
                "environment": runtime,
                "label": RuntimeEnvironment.LABELS.get(runtime, runtime),
                "icon": RuntimeEnvironment.ICONS.get(runtime, "server"),
            },
            "system": cls.get_system_info(),
            "process": cls.get_process_info(),
            "services": await cls.get_service_health(),
            "collected_at": timezone.now().isoformat(),
        }


# ─── Private helpers ─────────────────────────────────────────────


def _format_uptime(seconds: float) -> str:
    """Format seconds into human-readable uptime string."""
    days, remainder = divmod(int(seconds), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


async def _check_database() -> dict[str, Any]:
    """Check database connectivity."""
    svc: dict[str, Any] = {
        "name": "Database",
        "type": "database",
        "icon": "database",
    }
    start = time.monotonic()
    try:
        from core.config import get_settings
        settings = get_settings()
        db_url = getattr(settings, "database_url", "")

        # Detect driver
        if "postgresql" in db_url or "postgres" in db_url:
            svc["driver"] = "PostgreSQL"
        elif "mysql" in db_url:
            svc["driver"] = "MySQL"
        elif "sqlite" in db_url:
            svc["driver"] = "SQLite"
        else:
            svc["driver"] = "Unknown"

        from core.models import get_session
        db = await get_session()
        async with db:
            from sqlalchemy import text
            result = await db.execute(text("SELECT 1"))
            result.scalar()

        latency = round((time.monotonic() - start) * 1000, 1)
        svc.update({"status": "healthy", "latency_ms": latency})
    except Exception as e:
        latency = round((time.monotonic() - start) * 1000, 1)
        svc.update({"status": "unhealthy", "latency_ms": latency, "error": str(e)})
    return svc


async def _check_kafka() -> dict[str, Any]:
    """Check Kafka connectivity."""
    svc: dict[str, Any] = {
        "name": "Kafka",
        "type": "broker",
        "icon": "radio",
    }
    start = time.monotonic()
    try:
        from core.config import get_settings
        settings = get_settings()
        servers = getattr(settings, "kafka_bootstrap_servers", "")
        if not servers:
            svc.update({"status": "not_configured", "latency_ms": 0})
            return svc

        svc["servers"] = servers

        # Quick TCP check instead of full Kafka connection
        host_port = servers.split(",")[0].strip()
        host, port_str = host_port.rsplit(":", 1) if ":" in host_port else (host_port, "9092")
        port = int(port_str)

        import asyncio
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=3.0
            )
            writer.close()
            await writer.wait_closed()
            latency = round((time.monotonic() - start) * 1000, 1)
            svc.update({"status": "healthy", "latency_ms": latency})
        except (asyncio.TimeoutError, OSError) as e:
            latency = round((time.monotonic() - start) * 1000, 1)
            svc.update({"status": "unhealthy", "latency_ms": latency, "error": str(e)})

    except ImportError:
        svc.update({"status": "not_configured", "latency_ms": 0})
    except Exception as e:
        latency = round((time.monotonic() - start) * 1000, 1)
        svc.update({"status": "unhealthy", "latency_ms": latency, "error": str(e)})
    return svc


async def _check_redis() -> dict[str, Any]:
    """Check Redis connectivity."""
    svc: dict[str, Any] = {
        "name": "Redis",
        "type": "cache",
        "icon": "zap",
    }
    start = time.monotonic()
    try:
        from core.config import get_settings
        settings = get_settings()
        redis_url = getattr(settings, "redis_url", "") or getattr(settings, "cache_url", "")
        if not redis_url:
            svc.update({"status": "not_configured", "latency_ms": 0})
            return svc

        import redis.asyncio as aioredis  # type: ignore[import-untyped]
        client = aioredis.from_url(redis_url, socket_connect_timeout=3)
        await client.ping()
        await client.aclose()
        latency = round((time.monotonic() - start) * 1000, 1)
        svc.update({"status": "healthy", "latency_ms": latency})

    except ImportError:
        svc.update({"status": "not_configured", "latency_ms": 0})
    except Exception as e:
        latency = round((time.monotonic() - start) * 1000, 1)
        svc.update({"status": "unhealthy", "latency_ms": latency, "error": str(e)})
    return svc


async def _check_rabbitmq() -> dict[str, Any]:
    """Check RabbitMQ connectivity."""
    svc: dict[str, Any] = {
        "name": "RabbitMQ",
        "type": "broker",
        "icon": "mail",
    }
    start = time.monotonic()
    try:
        from core.config import get_settings
        settings = get_settings()
        amqp_url = getattr(settings, "rabbitmq_url", "") or getattr(settings, "amqp_url", "")
        if not amqp_url:
            svc.update({"status": "not_configured", "latency_ms": 0})
            return svc

        import aio_pika  # type: ignore[import-untyped]
        connection = await aio_pika.connect_robust(amqp_url, timeout=3)
        await connection.close()
        latency = round((time.monotonic() - start) * 1000, 1)
        svc.update({"status": "healthy", "latency_ms": latency})

    except ImportError:
        svc.update({"status": "not_configured", "latency_ms": 0})
    except Exception as e:
        latency = round((time.monotonic() - start) * 1000, 1)
        svc.update({"status": "unhealthy", "latency_ms": latency, "error": str(e)})
    return svc
