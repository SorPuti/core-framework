"""Lightweight entrypoint for isolated runner session processes."""

from __future__ import annotations

import asyncio
import builtins
import importlib
import json
import logging
import os
import signal
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _attach_session_logging(session_id: str) -> None:
    class _SessionIdFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            setattr(record, "runner_session_id", session_id)
            return True

    class _SessionIdFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            out = super().format(record)
            sid = getattr(record, "runner_session_id", None)
            return f"[{sid}] {out}" if sid else out

    for handler in logging.root.handlers:
        handler.addFilter(_SessionIdFilter())
        prev = handler.formatter
        handler.setFormatter(
            _SessionIdFormatter(
                prev._fmt if prev else "%(message)s",
                prev.datefmt if prev else None,
            )
        )
    logging.getLogger().addFilter(_SessionIdFilter())

    try:
        from strider.admin.runner_logs import RunnerLogsFileHandler

        logging.getLogger().addHandler(RunnerLogsFileHandler(session_id))
    except Exception as exc:
        logger.debug("Failed to attach RunnerLogsFileHandler: %s", exc)


def _patch_print_to_logger() -> None:
    """Route print() calls to logger so they appear in runner session logs."""
    if getattr(builtins, "_strider_runner_print_patched", False):
        return

    original_print = builtins.print

    def _logged_print(*args, **kwargs):
        sep = kwargs.get("sep", " ")
        end = kwargs.get("end", "\n")
        text = sep.join(str(a) for a in args)
        if end and end != "\n":
            text = f"{text}{end}"
        text = text.rstrip("\n")
        if text:
            logging.getLogger("runner.print").info(text)
        # Do not write to stdout in isolated child; logs are persisted via handler.

    builtins.print = _logged_print
    builtins._strider_runner_print_patched = True  # type: ignore[attr-defined]
    builtins._strider_runner_original_print = original_print  # type: ignore[attr-defined]


def _discover_and_import_runners() -> None:
    from strider.config import get_settings

    settings = get_settings()
    imported: set[str] = set()

    for mod in (
        getattr(settings, "workers_module", None),
        getattr(settings, "runners_module", None),
        "workers",
        "src.workers",
        "app.workers",
        "runners",
        "src.runners",
        "app.runners",
    ):
        if not mod or mod in imported:
            continue
        try:
            importlib.import_module(mod)
            imported.add(mod)
        except Exception:
            pass

    cwd = Path(os.getcwd())
    for pattern in ("runners.py", "src/runners.py", "src/*/runners.py", "app/runners.py"):
        for path in cwd.glob(pattern):
            if not path.is_file():
                continue
            module_name = str(path.relative_to(cwd)).replace("/", ".").replace("\\", ".").replace(".py", "")
            if module_name in imported:
                continue
            try:
                importlib.import_module(module_name)
                imported.add(module_name)
            except Exception:
                pass


async def _run_session_process(runner_name: str, session_id: str, payload_file: str) -> int:
    _attach_session_logging(session_id)
    _patch_print_to_logger()

    try:
        with open(payload_file, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as exc:
        print(f"Failed to load payload file {payload_file}: {exc}", file=sys.stderr)
        return 1
    finally:
        try:
            os.remove(payload_file)
        except OSError:
            pass

    from strider.config import get_settings
    settings = get_settings()
    db_url = getattr(settings, "database_url", "")
    if not db_url:
        print("runrunner-session requires database_url in config", file=sys.stderr)
        return 1

    _discover_and_import_runners()
    from strider.messaging.runner import get_runner

    runner_class = get_runner(runner_name)
    if runner_class is None:
        print(f"Runner '{runner_name}' not found.", file=sys.stderr)
        return 1

    from strider.models import init_database

    pool_size = int(getattr(settings, "runner_session_pool_size", 2) or 2)
    max_overflow = int(getattr(settings, "database_max_overflow", 2) or 2)
    await init_database(db_url, pool_size=pool_size, max_overflow=max_overflow)

    instance = runner_class()
    instance._current_session_id = session_id

    def _on_sigterm() -> None:
        instance.request_stop()

    try:
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, _on_sigterm)
    except NotImplementedError:
        pass

    try:
        await instance.run_session(payload)
    finally:
        try:
            await instance.after_stop()
        except Exception as exc:
            logger.exception("Runner after_stop failed in isolated session: %s", exc)

    return 0


def main() -> int:
    if len(sys.argv) != 4:
        print("Usage: python -m strider.messaging.runner_session <runner_name> <session_id> <payload_file>", file=sys.stderr)
        return 2

    runner_name, session_id, payload_file = sys.argv[1], sys.argv[2], sys.argv[3]

    try:
        return asyncio.run(_run_session_process(runner_name, session_id, payload_file))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
