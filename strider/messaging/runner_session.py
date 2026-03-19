"""
runner_session.py — entrypoint do processo filho isolado.

Invocado pelo controlador como:
    python -m strider.messaging.runner_session <RunnerName> <session_id> <payload_path>

Responsabilidades:
1. Configura logger DEDICADO (não mistura com a API)
2. Inicializa DB/Redis próprios (sem compartilhar com o controlador)
3. Instancia o Runner e chama run_session(payload)
4. Mantém o processo vivo enquanto run_session() não retornar
5. Encerra limpo ao detectar .stop flag ou SIGTERM
6. Remove flags de controle ao sair

O processo filho NÃO deve encerrar espontaneamente enquanto a sessão
estiver ativa — use um loop interno em run_session que checa is_stop_flag().
"""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import os
import signal
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Ensure the package is importable when invoked as -m
# ---------------------------------------------------------------------------
# (no sys.path manipulation needed if installed; add only as fallback)

logger: logging.Logger  # will be reassigned after setup


def _setup_logging(runner_name: str, session_id: str) -> logging.Logger:
    """
    Configure a dedicated logger for this isolated session.
    Deliberately does NOT propagate to the root logger to avoid mixing with API logs.
    """
    # Import here (after package is importable)
    from strider.messaging.runner import setup_isolated_session_logging
    return setup_isolated_session_logging(runner_name, session_id)


# ---------------------------------------------------------------------------
# Signal handling
# ---------------------------------------------------------------------------

_stop_event: asyncio.Event | None = None
_stop_flag_was_sigterm = False


def _handle_sigterm(signum: int, frame: Any) -> None:
    """SIGTERM: set stop event so run_loop can exit cleanly."""
    global _stop_flag_was_sigterm
    _stop_flag_was_sigterm = True
    if _stop_event is not None:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # noinspection PyTypeChecker
                loop.call_soon_threadsafe(_stop_event.set)
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# Main async entrypoint
# ---------------------------------------------------------------------------

# noinspection PyTypeChecker
async def _run(runner_name: str, session_id: str, payload: dict[str, Any]) -> int:
    """
    Returns the exit code:
        0  → clean exit (stop flag, SIGTERM, or run_session completed normally after flag)
        1  → error in run_session
        2  → runner class not found
    """
    global _stop_event

    _stop_event = asyncio.Event()
    log = _setup_logging(runner_name, session_id)
    from strider.messaging.runner import (
        bind_runner_session_context,
        configure_isolated_process_logging,
    )

    configure_isolated_process_logging(runner_name, session_id)
    bind_runner_session_context(runner_name, session_id)

    log.info(
        "Session process started: runner=%s session_id=%s pid=%s",
        runner_name, session_id, os.getpid(),
    )

    # Register signal handler (use asyncio-safe approach)
    loop = asyncio.get_event_loop()
    try:
        loop.add_signal_handler(signal.SIGTERM, lambda: _stop_event.set())
        loop.add_signal_handler(signal.SIGINT, lambda: _stop_event.set())
    except NotImplementedError:
        # Windows fallback
        signal.signal(signal.SIGTERM, _handle_sigterm)

    # Initialize DB and Redis for this child process
    try:
        await _init_child_resources(log)
    except Exception as exc:
        log.error("Failed to initialize child resources: %s", exc, exc_info=True)
        return 1

    # Registrar classes Runner (env ou settings.runners_module)
    _raw = os.environ.get("STRIDER_RUNNER_MODULES", "").strip()
    if _raw:
        for part in _raw.split(","):
            p = part.strip()
            if p:
                importlib.import_module(p)
    else:
        try:
            from strider.config import get_settings

            rm = getattr(get_settings(), "runners_module", None)
            if rm:
                importlib.import_module(rm)
        except Exception:
            pass

    # Resolve runner class
    try:
        from strider.messaging.runner import get_runner
        runner_cls = get_runner(runner_name)
        if runner_cls is None:
            log.error("Runner class not found: %s", runner_name)
            return 2
    except Exception as exc:
        log.error("Failed to import runner: %s", exc, exc_info=True)
        return 1

    # Instantiate runner
    runner = runner_cls()

    from strider.messaging.runner import (
        check_stop_flag,
        clear_runner_session_context,
        clear_stop_flag,
    )

    exit_code = 0
    try:
        log.info("Calling run_session for session_id=%s", session_id)

        # Run session in a task so we can also wait on the stop event
        session_task = asyncio.create_task(runner.run_session(payload))

        # Wait for either: session completes, stop flag, or stop event (SIGTERM)
        while not session_task.done():
            # Check stop flag (set by controller via filesystem)
            if check_stop_flag(session_id):
                log.info(
                    "Stop flag detected for session_id=%s — requesting stop", session_id
                )
                runner.request_stop()
                # Give run_session time to exit cleanly
                try:
                    await asyncio.wait_for(asyncio.shield(session_task), timeout=10.0)
                except asyncio.TimeoutError:
                    log.warning(
                        "run_session did not exit within 10s after stop flag; cancelling"
                    )
                    session_task.cancel()
                    try:
                        await session_task
                    except asyncio.CancelledError:
                        pass
                break

            # Check SIGTERM/asyncio stop event
            if _stop_event.is_set():
                log.info("Stop event set (SIGTERM) for session_id=%s — requesting stop", session_id)
                runner.request_stop()
                try:
                    await asyncio.wait_for(asyncio.shield(session_task), timeout=10.0)
                except asyncio.TimeoutError:
                    log.warning(
                        "run_session did not exit within 10s after SIGTERM; cancelling"
                    )
                    session_task.cancel()
                    try:
                        await session_task
                    except asyncio.CancelledError:
                        pass
                break

            # Poll every 0.5s to check flags without busy-looping
            try:
                await asyncio.wait_for(asyncio.shield(session_task), timeout=0.5)
            except asyncio.TimeoutError:
                pass  # session still running, loop again

        # Retrieve exception if any
        if not session_task.cancelled():
            exc = session_task.exception()
            if exc is not None:
                log.error(
                    "run_session raised exception for session_id=%s: %s",
                    session_id, exc, exc_info=exc,
                )
                exit_code = 1

    except asyncio.CancelledError:
        log.info("Session task cancelled for session_id=%s", session_id)
        exit_code = 0
    except Exception as exc:
        log.error(
            "Unexpected error in session loop session_id=%s: %s", session_id, exc, exc_info=True
        )
        exit_code = 1
    finally:
        log.info(
            "Session process exiting: runner=%s session_id=%s exit_code=%s",
            runner_name, session_id, exit_code,
        )
        clear_stop_flag(session_id)
        clear_runner_session_context()

        # Close child DB/Redis connections
        try:
            await _teardown_child_resources(log)
        except Exception as exc:
            log.debug("Child resource teardown failed: %s", exc)

    return exit_code


async def _init_child_resources(log: logging.Logger) -> None:
    """Initialize DB and Redis connections for the child process."""
    from strider.config import get_settings
    settings = get_settings()

    # DB
    try:
        if getattr(settings, "has_read_replica", False):
            from strider.database import init_replicas
            await init_replicas()
        else:
            from strider.models import init_database
            db_url = getattr(settings, "database_url", None)
            if db_url:
                pool_size = int(getattr(settings, "database_pool_size", 5) or 5)
                max_overflow = int(getattr(settings, "database_max_overflow", 10) or 10)
                await init_database(db_url, pool_size=pool_size, max_overflow=max_overflow)
        log.debug("Child DB initialized")
    except Exception as exc:
        log.warning("Child DB init failed (non-fatal): %s", exc)

    # Redis (optional)
    try:
        from strider.cache import init_cache  # type: ignore[import]
        await init_cache()
        log.debug("Child Redis initialized")
    except ImportError:
        pass
    except Exception as exc:
        log.warning("Child Redis init failed (non-fatal): %s", exc)


async def _teardown_child_resources(log: logging.Logger) -> None:
    """Close DB and Redis connections for the child process."""
    try:
        from strider.models import close_database  # type: ignore[import]
        await close_database()
        log.debug("Child DB closed")
    except Exception:
        pass

    try:
        from strider.cache import close_cache  # type: ignore[import]
        await close_cache()
        log.debug("Child Redis closed")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) != 4:
        sys.stderr.write(
            "Usage: python -m strider.messaging.runner_session "
            "<RunnerName> <session_id> <payload_path>\n"
        )
        sys.exit(1)

    runner_name = sys.argv[1]
    session_id = sys.argv[2]
    payload_path = sys.argv[3]

    try:
        with open(payload_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as exc:
        sys.stderr.write(f"[runner_session] Failed to read payload: {exc}\n")
        sys.exit(1)
    finally:
        # Best-effort cleanup of payload file immediately
        try:
            os.remove(payload_path)
        except OSError:
            pass

    exit_code = asyncio.run(_run(runner_name, session_id, payload))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()