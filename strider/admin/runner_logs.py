"""
Leitura de logs de runner (arquivo texto por sessão, mesmo path que o processo isolado).

Usa strider.runner_log_paths (diretório base unificado).
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, AsyncIterator

from strider.runner_log_paths import get_isolated_session_log_path, tail_text_file_lines


def _line_entries(lines: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "timestamp": "",
            "level": "INFO",
            "level_no": logging.INFO,
            "message": ln,
        }
        for ln in lines
    ]


async def read_runner_log_tail(
    runner_name: str,
    session_id: str,
    *,
    log_path: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    path = log_path or get_isolated_session_log_path(runner_name, session_id)

    def _read() -> list[str]:
        return tail_text_file_lines(path, limit)

    lines = await asyncio.to_thread(_read)
    return _line_entries(lines)


async def stream_runner_text_log(
    path: str,
    poll_interval: float = 0.5,
) -> AsyncIterator[dict[str, Any]]:
    """Segue arquivo em crescimento (uma linha = uma entrada). O arquivo deve existir; quem chama aguarda criação."""
    if not os.path.isfile(path):
        return
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            f.seek(0, os.SEEK_END)
            while True:
                line = f.readline()
                if not line:
                    await asyncio.sleep(poll_interval)
                    continue
                yield {
                    "timestamp": "",
                    "level": "INFO",
                    "level_no": logging.INFO,
                    "message": line.rstrip("\n"),
                }
    except asyncio.CancelledError:
        return
    except OSError:
        return
