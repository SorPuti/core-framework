"""
Diretório base único para logs de runner (isolado + Ops).

Precedência: STRIDER_RUNNER_LOGS_DIR → settings.runner_logs_dir → temp/strider-runner-logs
Arquivo por sessão: {base}/{runner_name}/{safe_session_id}.log
"""

from __future__ import annotations

import os
import tempfile

RUNNER_LOGS_DIR_ENV = "STRIDER_RUNNER_LOGS_DIR"


def resolve_runner_logs_base_dir() -> str:
    d = os.environ.get(RUNNER_LOGS_DIR_ENV, "").strip()
    if d:
        return d
    try:
        from strider.config import get_settings

        cfg = str(getattr(get_settings(), "runner_logs_dir", "") or "").strip()
        if cfg:
            return cfg
    except Exception:
        pass
    return os.path.join(tempfile.gettempdir(), "strider-runner-logs")


def safe_session_segment(session_id: str) -> str:
    return session_id.replace("/", "_").replace("..", "__")


def get_isolated_session_log_path(runner_name: str, session_id: str) -> str:
    base = resolve_runner_logs_base_dir()
    d = os.path.join(base, runner_name)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{safe_session_segment(session_id)}.log")


def tail_text_file_lines(path: str, max_lines: int) -> list[str]:
    """Últimas N linhas de texto; leitura eficiente pelo fim do arquivo."""
    if max_lines <= 0 or not os.path.isfile(path):
        return []
    size = os.path.getsize(path)
    if size == 0:
        return []
    block = 8192
    with open(path, "rb") as f:
        buf = b""
        pos = size
        while pos > 0:
            step = min(block, pos)
            pos -= step
            f.seek(pos)
            buf = f.read(step) + buf
            if buf.count(b"\n") >= max_lines:
                break
        lines = buf.splitlines()
        if pos > 0 and lines:
            lines = lines[1:]
        tail = lines[-max_lines:]
        return [ln.decode("utf-8", errors="replace") for ln in tail]
