"""
Log de runner via Redis (lista) — opcional quando API e worker não partilham filesystem.

Ativar: STRIDER_RUNNER_LOG_REDIS=1 no processo filho + redis_url em settings.
Chave: strider:runner_log:{session_id} (RPUSH + LTRIM, últimas ~8000 linhas).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

REDIS_KEY_PREFIX = "strider:runner_log:"
MAX_LINES = 8000


def _redis_url() -> str:
    try:
        from strider.config import get_settings

        s = get_settings()
        u = str(getattr(s, "runner_logs_redis_url", "") or "").strip()
        if u:
            return u
        return str(getattr(s, "redis_url", "") or "").strip()
    except Exception:
        return ""


class RunnerRedisListHandler(logging.Handler):
    """Empurra cada linha formatada para uma lista Redis (ordem cronológica)."""

    def __init__(self, redis_url: str, session_id: str) -> None:
        super().__init__(level=logging.DEBUG)
        import redis as redis_mod  # type: ignore[import-untyped]

        self._r = redis_mod.Redis.from_url(redis_url, decode_responses=True)
        self._key = f"{REDIS_KEY_PREFIX}{session_id}"

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self._r.rpush(self._key, msg)
            self._r.ltrim(self._key, -MAX_LINES, -1)
        except Exception:
            self.handleError(record)


def attach_runner_redis_handler_to_root(runner_name: str, session_id: str) -> None:
    """Adiciona handler Redis ao root (só no processo filho, se STRIDER_RUNNER_LOG_REDIS)."""
    url = _redis_url()
    if not url:
        return
    root = logging.getLogger()
    h = RunnerRedisListHandler(url, session_id)
    h.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root.addHandler(h)


def read_tail_from_redis(session_id: str, limit: int) -> list[str]:
    """Últimas N linhas da lista Redis (API)."""
    url = _redis_url()
    if not url:
        return []
    try:
        import redis as redis_mod  # type: ignore[import-untyped]

        r = redis_mod.Redis.from_url(url, decode_responses=True)
        key = f"{REDIS_KEY_PREFIX}{session_id}"
        n = max(1, min(limit, MAX_LINES))
        if not r.exists(key):
            return []
        total = r.llen(key)
        if total == 0:
            return []
        start = max(0, total - n)
        return list(r.lrange(key, start, -1))
    except Exception:
        return []


def stream_redis_keys_exist(session_id: str) -> bool:
    url = _redis_url()
    if not url:
        return False
    try:
        import redis as redis_mod  # type: ignore[import-untyped]

        r = redis_mod.Redis.from_url(url, decode_responses=True)
        return bool(r.exists(f"{REDIS_KEY_PREFIX}{session_id}"))
    except Exception:
        return False
