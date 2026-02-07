"""
Admin Log Buffer — captures Python logging for streaming in the admin panel.

Uses a ring buffer (deque) with configurable max size.
Supports SSE subscribers for real-time log streaming.

Thread-safety: emit() is called from any thread (uvicorn, background workers).
We use loop.call_soon_threadsafe() to push entries to asyncio.Queue subscribers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from core.datetime import timezone


@dataclass
class LogEntry:
    """Single log entry captured from Python logging."""

    timestamp: str
    level: str
    level_no: int
    logger: str
    message: str
    module: str = ""
    funcName: str = ""
    lineno: int = 0
    exc_text: str | None = None

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(asdict(self), default=str)


class AdminLogBuffer(logging.Handler):
    """
    Custom logging handler that buffers log entries for the admin panel.

    Features:
    - Ring buffer with configurable max size
    - Async subscriber queues for SSE streaming
    - Thread-safe: uses threading.Lock for buffer + call_soon_threadsafe for queues

    Usage:
        buffer = AdminLogBuffer(max_size=5000)
        logging.getLogger().addHandler(buffer)

        # Get recent logs
        recent = buffer.get_recent(limit=100)

        # Subscribe for streaming
        queue = buffer.subscribe()
        entry = await queue.get()  # blocks until new log
        buffer.unsubscribe(queue)
    """

    def __init__(self, max_size: int = 5000, level: int = logging.DEBUG) -> None:
        super().__init__(level)
        self._buffer: deque[LogEntry] = deque(maxlen=max_size)
        self._subscribers: dict[asyncio.Queue[LogEntry], asyncio.AbstractEventLoop] = {}
        self._max_size = max_size
        self._total_count = 0
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        """
        Process a log record — called by Python logging from ANY thread.
        
        Thread-safe: uses threading.Lock for buffer access and
        loop.call_soon_threadsafe() for asyncio queue notification.
        """
        try:
            entry = LogEntry(
                timestamp=datetime.fromtimestamp(record.created).isoformat(),
                level=record.levelname,
                level_no=record.levelno,
                logger=record.name,
                message=self.format(record) if self.formatter else record.getMessage(),
                module=record.module or "",
                funcName=record.funcName or "",
                lineno=record.lineno or 0,
                exc_text=record.exc_text,
            )
            
            with self._lock:
                self._buffer.append(entry)
                self._total_count += 1
                # Snapshot subscribers to avoid holding lock during notification
                subs = dict(self._subscribers)

            # Notify SSE subscribers — thread-safe via call_soon_threadsafe
            dead: list[asyncio.Queue[LogEntry]] = []
            for q, loop in subs.items():
                try:
                    loop.call_soon_threadsafe(self._safe_put, q, entry)
                except RuntimeError:
                    # Event loop closed
                    dead.append(q)
                except Exception:
                    dead.append(q)

            if dead:
                with self._lock:
                    for q in dead:
                        self._subscribers.pop(q, None)

        except Exception:
            self.handleError(record)

    @staticmethod
    def _safe_put(q: asyncio.Queue[LogEntry], entry: LogEntry) -> None:
        """Put entry into queue, dropping oldest if full. Runs in event loop thread."""
        try:
            q.put_nowait(entry)
        except asyncio.QueueFull:
            try:
                q.get_nowait()
                q.put_nowait(entry)
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                pass

    def subscribe(self, max_queue: int = 500) -> asyncio.Queue[LogEntry]:
        """
        Create a subscriber queue for SSE streaming.

        Returns an asyncio.Queue that receives new LogEntry objects.
        Must be called from within an async context (event loop running).
        """
        q: asyncio.Queue[LogEntry] = asyncio.Queue(maxsize=max_queue)
        loop = asyncio.get_event_loop()
        with self._lock:
            self._subscribers[q] = loop
        return q

    def unsubscribe(self, queue: asyncio.Queue[LogEntry]) -> None:
        """Remove a subscriber queue."""
        with self._lock:
            self._subscribers.pop(queue, None)

    def get_recent(
        self,
        limit: int = 200,
        level_filter: str | None = None,
        logger_filter: str | None = None,
        search: str | None = None,
    ) -> list[LogEntry]:
        """
        Get recent log entries with optional filtering.

        Args:
            limit: Maximum entries to return
            level_filter: Filter by log level (e.g. "WARNING")
            logger_filter: Filter by logger name prefix
            search: Search in message text
        """
        level_no = 0
        if level_filter:
            level_no = getattr(logging, level_filter.upper(), 0)

        results: list[LogEntry] = []
        for entry in reversed(self._buffer):
            if level_no and entry.level_no < level_no:
                continue
            if logger_filter and not entry.logger.startswith(logger_filter):
                continue
            if search and search.lower() not in entry.message.lower():
                continue
            results.append(entry)
            if len(results) >= limit:
                break

        results.reverse()  # chronological order
        return results

    @property
    def total_count(self) -> int:
        """Total log entries captured since start."""
        return self._total_count

    @property
    def buffer_size(self) -> int:
        """Current buffer size."""
        return len(self._buffer)

    @property
    def subscriber_count(self) -> int:
        """Active SSE subscriber count."""
        return len(self._subscribers)


# ── Global singleton ──
_log_buffer: AdminLogBuffer | None = None


def get_log_buffer() -> AdminLogBuffer:
    """Get or create the global log buffer singleton."""
    global _log_buffer
    if _log_buffer is None:
        try:
            from core.config import get_settings
            settings = get_settings()
            max_size = getattr(settings, "ops_log_buffer_size", 5000)
        except Exception:
            max_size = 5000
        _log_buffer = AdminLogBuffer(max_size=max_size)
        # Attach to root logger
        root = logging.getLogger()
        root.addHandler(_log_buffer)
    return _log_buffer


def setup_log_buffer() -> AdminLogBuffer:
    """Initialize the log buffer on admin startup."""
    return get_log_buffer()
