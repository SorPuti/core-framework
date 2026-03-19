"""
Logs dedicados por instância do Runner (Redis Stream).

Cada processo filho (runrunner-session) envia seus logs para o stream
runner_logs:{session_id}. O Admin lê apenas esse stream, evitando mistura
com logs da API (uvicorn.access, etc.).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, AsyncIterator

STREAM_KEY_PREFIX = "runner_logs:"


def _stream_key(session_id: str) -> str:
    return f"{STREAM_KEY_PREFIX}{session_id}"


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


class RunnerLogsRedisHandler(logging.Handler):
    """
    Envia cada log do processo da instância para Redis Stream runner_logs:{session_id}.
    Usado apenas no processo filho (runrunner-session); não bloqueia com timeout curto.
    """

    def __init__(
        self,
        session_id: str,
        redis_url: str,
        stream_max_len: int = 2000,
    ) -> None:
        super().__init__(level=logging.DEBUG)
        self._session_id = session_id
        self._redis_url = redis_url
        self._stream_max_len = stream_max_len
        self._client: Any = None

    def _get_client(self) -> Any | None:
        if self._client is not None:
            return self._client
        try:
            import redis
            self._client = redis.from_url(
                self._redis_url,
                socket_connect_timeout=2,
                decode_responses=True,
            )
            return self._client
        except Exception:
            return None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            client = self._get_client()
            if not client:
                return
            entry = _record_to_entry(record)
            key = _stream_key(self._session_id)
            # XADD com MAXLEN ~ para limitar tamanho do stream
            client.xadd(
                key,
                {"payload": json.dumps(entry, default=str)},
                maxlen=self._stream_max_len,
                approximate=True,
            )
        except Exception:
            self.handleError(record)


async def get_runner_logs_from_redis(
    session_id: str,
    limit: int = 500,
    redis_url: str | None = None,
) -> list[dict[str, Any]]:
    """
    Lê entradas recentes do stream runner_logs:{session_id}.
    Retorna lista vazia se Redis indisponível ou stream inexistente.
    """
    try:
        from strider.config import get_settings
        import redis.asyncio as aioredis
    except ImportError:
        return []

    url = redis_url
    if not url:
        try:
            settings = get_settings()
            url = getattr(settings, "runner_logs_redis_url", "") or getattr(settings, "redis_url", "")
        except Exception:
            url = ""
    if not url:
        return []

    try:
        client = aioredis.from_url(url, socket_connect_timeout=2, decode_responses=True)
        try:
            key = _stream_key(session_id)
            # XREVRANGE + XRANGE order: mais recentes primeiro, depois invertemos para cronológico
            raw = await client.xrevrange(key, count=limit)
            entries = []
            for _mid, data in reversed(raw):
                payload = data.get("payload")
                if payload:
                    try:
                        entries.append(json.loads(payload))
                    except json.JSONDecodeError:
                        pass
            return entries
        finally:
            await client.aclose()
    except Exception:
        return []


async def stream_runner_logs(
    session_id: str,
    redis_url: str | None = None,
    block_ms: int = 2000,
) -> AsyncIterator[dict[str, Any]]:
    """
    Gera entradas do stream runner_logs:{session_id} em tempo real (XREAD BLOCK).
    """
    try:
        from strider.config import get_settings
        import redis.asyncio as aioredis
    except ImportError:
        return

    url = redis_url
    if not url:
        try:
            settings = get_settings()
            url = getattr(settings, "runner_logs_redis_url", "") or getattr(settings, "redis_url", "")
        except Exception:
            url = ""
    if not url:
        return

    try:
        client = aioredis.from_url(url, socket_connect_timeout=2, decode_responses=True)
    except Exception:
        return

    key = _stream_key(session_id)
    last_id = "$"  # só mensagens novas

    try:
        while True:
            try:
                result = await client.xread(streams={key: last_id}, block=block_ms, count=50)
                if not result:
                    continue
                for stream_name, messages in result:
                    for msg_id, data in messages:
                        last_id = msg_id
                        payload = data.get("payload")
                        if payload:
                            try:
                                yield json.loads(payload)
                            except json.JSONDecodeError:
                                pass
            except asyncio.CancelledError:
                break
            except Exception:
                break
    finally:
        await client.aclose()
