"""
Logs dedicados por instância do Runner (arquivo local por sessão).

Cada processo filho (runrunner-session) envia seus logs para um arquivo JSONL:
<runner_logs_dir>/<session_id>.log

O Admin lê e faz stream apenas desse arquivo, evitando mistura com logs da API.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime
from collections import deque
from typing import Any, AsyncIterator

RUNNER_LOGS_DIR_ENV = "STRIDER_RUNNER_LOGS_DIR"


def _resolve_logs_dir() -> str:
    """Resolve directory for per-session runner log files."""
    env_dir = os.getenv(RUNNER_LOGS_DIR_ENV, "").strip()
    if env_dir:
        return env_dir
    try:
        from strider.config import get_settings

        settings = get_settings()
        cfg_dir = str(getattr(settings, "runner_logs_dir", "") or "").strip()
        if cfg_dir:
            return cfg_dir
    except Exception:
        pass
    return os.path.join(tempfile.gettempdir(), "strider-runner-logs")


def _safe_session_id(session_id: str) -> str:
    return "".join(c for c in session_id if c.isalnum() or c in ("-", "_"))[:128] or "unknown"


def _session_log_path(session_id: str) -> str:
    base_dir = _resolve_logs_dir()
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, f"{_safe_session_id(session_id)}.log")


def _record_to_entry(record: logging.LogRecord) -> dict[str, Any]:
    return {
        "timestamp": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
        "level": record.levelname,
        "level_no": record.levelno,
        "logger": record.name,
        "message": record.getMessage() if record.msg else "",
        "module": getattr(record, "module", "") or "",
        "funcName": getattr(record, "funcName", "") or "",
        "lineno": getattr(record, "lineno", 0) or 0,
        "exc_text": record.exc_text if record.exc_text else None,
    }


class RunnerLogsFileHandler(logging.Handler):
    """Append each log record as JSONL to a dedicated per-session file."""

    def __init__(self, session_id: str) -> None:
        super().__init__(level=logging.DEBUG)
        self._session_id = session_id
        self._path = _session_log_path(session_id)

    @property
    def path(self) -> str:
        return self._path

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = _record_to_entry(record)
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, default=str, ensure_ascii=False) + "\n")
        except Exception:
            self.handleError(record)


async def get_runner_logs_from_file(
    session_id: str,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Read most recent JSONL entries for a runner session file."""
    path = _session_log_path(session_id)
    if not os.path.exists(path):
        return []

    def _read_tail() -> list[dict[str, Any]]:
        entries: deque[dict[str, Any]] = deque(maxlen=limit)
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        parsed = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(parsed, dict):
                        entries.append(parsed)
        except OSError:
            return []
        return list(entries)

    return await asyncio.to_thread(_read_tail)


async def stream_runner_logs_from_file(
    session_id: str,
    poll_interval: float = 0.5,
) -> AsyncIterator[dict[str, Any]]:
    """Yield new JSONL entries appended to a runner session log file."""
    path = _session_log_path(session_id)

    # Espera arquivo aparecer por um tempo para sessões recém-iniciadas.
    waited = 0.0
    while not os.path.exists(path) and waited < 30.0:
        await asyncio.sleep(poll_interval)
        waited += poll_interval

    if not os.path.exists(path):
        return

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(0, os.SEEK_END)
            while True:
                line = f.readline()
                if not line:
                    await asyncio.sleep(poll_interval)
                    continue
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(entry, dict):
                    yield entry
    except asyncio.CancelledError:
        return
    except OSError:
        return
