"""
Runner — controlador de sessões longas com lifecycle hooks e limites de recursos.

ARQUITETURA
───────────
O Runner é o CONTROLADOR: consome start/stop/pause/resume via Kafka e gerencia
processos filhos isolados (um por sessão quando runner_isolated_instances=True).

Cada instância (processo filho) tem:
  • DB e Redis próprios — sem vazar conexões com a API
  • Logger dedicado    — sem misturar com logs da API  (propagate=False)
  • Stop via flag .stop no filesystem + SIGTERM
  • Pause/Resume via SIGSTOP/SIGCONT (OS suspende o processo, zero CPU)

FLAGS DE CONTROLE (processo filho checa no keepalive loop)
──────────────────────────────────────────────────────────
  /tmp/strider_runner_{session_id}.stop  → keepalive loop sai, cleanup roda

PAUSE/RESUME — SIGSTOP/SIGCONT
──────────────────────────────
  Controlador envia SIGSTOP → processo filho suspenso pelo kernel (zero CPU)
  Controlador envia SIGCONT → processo filho retoma exatamente onde parou
  O asyncio event loop fica congelado durante a suspensão.
  O stream WebSocket (market_svc) bufferiza ticks externamente durante pausa.
  O processo filho não precisa saber nada sobre pause — transparente.

SEMÂNTICA DE EXIT (reap auditado)
──────────────────────────────────
  exit 0  + stop_flag setada → stop_command     (limpo)
  exit 0  sem stop_flag      → spontaneous_exit (crash → on_session_crash)
  exit -15 (SIGTERM)         → sigterm          (limpo)
  exit -9  (SIGKILL)         → sigkill_or_oom   (crash → on_session_crash)
  exit > 0                   → error_exit       (crash → on_session_crash)

LOGS DEDICADOS
──────────────
  {runner_log_dir}/{RunnerName}/{session_id}.log  — arquivo por sessão
  Tabela RunnerLog (DB)                           — Admin Panel + streaming
  log.propagate = False                           — não mistura com a API
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import tempfile
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from strider.config import get_settings

logger = logging.getLogger(__name__)


# =============================================================================
# Filesystem stop flag
# =============================================================================

def _runner_flag_dir() -> str:
    return os.environ.get("STRIDER_RUNNER_FLAG_DIR", "/tmp")


def _flag_path(session_id: str) -> str:
    safe = session_id.replace("/", "_").replace("..", "__")
    return os.path.join(_runner_flag_dir(), f"strider_runner_{safe}.stop")


def set_stop_flag(session_id: str) -> None:
    """Create the .stop flag file — child's keepalive loop will exit on next check."""
    try:
        Path(_flag_path(session_id)).touch()
        logger.debug("Runner stop flag set: session_id=%s", session_id)
    except OSError as exc:
        logger.warning("Runner set_stop_flag failed session_id=%s: %s", session_id, exc)


def clear_stop_flag(session_id: str) -> None:
    """Remove the .stop flag (called on session end to keep /tmp clean)."""
    try:
        p = _flag_path(session_id)
        if os.path.exists(p):
            os.remove(p)
    except OSError:
        pass


def check_stop_flag(session_id: str) -> bool:
    """Return True if the .stop flag exists (used inside isolated child process)."""
    return os.path.exists(_flag_path(session_id))


# =============================================================================
# Dedicated runner logging — isolated from API logs
# =============================================================================

def _runner_log_dir() -> str:
    settings = get_settings()
    return str(getattr(settings, "runner_log_dir", None) or "/var/log/strider/runners")


def get_runner_file_handler(runner_name: str, session_id: str) -> logging.FileHandler:
    """FileHandler → {runner_log_dir}/{runner_name}/{session_id}.log"""
    log_dir = os.path.join(_runner_log_dir(), runner_name)
    os.makedirs(log_dir, exist_ok=True)
    safe = session_id.replace("/", "_").replace("..", "__")
    handler = logging.FileHandler(
        os.path.join(log_dir, f"{safe}.log"), encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    ))
    return handler


def setup_isolated_session_logging(runner_name: str, session_id: str) -> logging.Logger:
    """
    Return a dedicated logger for an isolated session process.

    Key properties:
      • propagate=False  → does NOT bubble up to root/API logger
      • FileHandler      → one file per session in runner_log_dir
      • StreamHandler    → stdout with [runner:Name:session] prefix (journald/docker)

    Call this at the top of runner_session.py before importing anything else.
    """
    log = logging.getLogger(f"runner.{runner_name}.{session_id}")
    log.setLevel(logging.DEBUG)
    log.propagate = False  # ← no mixing with the API logger

    try:
        log.addHandler(get_runner_file_handler(runner_name, session_id))
    except OSError as exc:
        sys.stderr.write(f"[runner] Cannot open log file: {exc}\n")

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter(
        f"[runner:{runner_name}:{session_id}] %(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    ))
    log.addHandler(sh)
    return log


class RunnerDBLogHandler(logging.Handler):
    """
    Batch log handler that persists records to RunnerLog table.
    Use inside the isolated child process.

    Usage:
        handler = RunnerDBLogHandler(runner_name, session_id)
        session_log.addHandler(handler)
        await handler.start()
        # ... session runs ...
        await handler.stop()
    """

    def __init__(
        self,
        runner_name: str,
        session_id: str,
        batch_size: int = 20,
        flush_interval: float = 5.0,
    ) -> None:
        super().__init__()
        self.runner_name = runner_name
        self.session_id = session_id
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._queue: list[dict[str, Any]] = []
        self._task: asyncio.Task | None = None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._queue.append({
                "runner_name": self.runner_name,
                "session_id": self.session_id,
                "level": record.levelname,
                "logger": record.name,
                "message": self.format(record),
            })
            if len(self._queue) >= self.batch_size:
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(self._flush())
                except RuntimeError:
                    pass
        except Exception:
            self.handleError(record)

    async def _flush(self) -> None:
        if not self._queue:
            return
        batch, self._queue = self._queue[:], []
        try:
            from strider.models import get_session
            from strider.admin.models import RunnerLog
            async with get_session() as db:
                for e in batch:
                    await RunnerLog(
                        runner_name=e["runner_name"],
                        session_id=e["session_id"],
                        level=e["level"],
                        logger=e["logger"],
                        message=e["message"],
                    ).save(db)
                await db.commit()
        except Exception as exc:
            sys.stderr.write(f"[RunnerDBLogHandler] flush failed: {exc}\n")

    async def start(self) -> None:
        self._task = asyncio.create_task(self._flush_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._flush()

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(self.flush_interval)
            await self._flush()


def get_runner_log_path(runner_name: str, session_id: str) -> str:
    """Return the expected log file path for a session (Admin Panel use)."""
    safe = session_id.replace("/", "_").replace("..", "__")
    return os.path.join(_runner_log_dir(), runner_name, f"{safe}.log")


# =============================================================================
# Process utilities
# =============================================================================

def _get_process_metrics() -> dict[str, float]:
    try:
        import psutil  # type: ignore[import-untyped]
        proc = psutil.Process()
        out: dict[str, float] = {
            "cpu_percent": round(proc.cpu_percent(interval=0) or 0, 1),
            "memory_mb": round(proc.memory_info().rss / (1024 * 1024), 1),
        }
        try:
            io = proc.io_counters()
            if io:
                out["io_read_mb"] = round(io.read_bytes / (1024 * 1024), 1)
                out["io_write_mb"] = round(io.write_bytes / (1024 * 1024), 1)
        except (AttributeError, PermissionError):
            pass
        return out
    except ImportError:
        return {}


_runner_registry: dict[str, type["Runner"]] = {}


def kill_process_by_pid(pid: int, grace: float = 5.0) -> None:
    """Send SIGTERM to process group; SIGKILL after grace seconds if still alive."""
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
            time.sleep(0.25)
        except ProcessLookupError:
            return
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except ProcessLookupError:
        pass


def process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


# =============================================================================
# Exit classification
# =============================================================================

def _classify_exit(exit_code: int | None, stop_flag_was_set: bool) -> tuple[str, bool]:
    """
    Returns (reason, is_clean).

    is_clean=True  → expected stop; on_stop + after_stop only.
    is_clean=False → unexpected death; on_session_crash + on_stop + after_stop.

    Rules:
      exit 0  + stop_flag → stop_command      (clean)
      exit 0  no flag     → spontaneous_exit  (crash — process must not self-exit)
      exit -15 SIGTERM    → sigterm           (clean)
      exit -9  SIGKILL    → sigkill_or_oom    (crash)
      exit < 0 other      → signal_exit       (crash)
      exit > 0            → error_exit        (crash)
    """
    if exit_code == -signal.SIGTERM:
        return "sigterm", True
    if exit_code == 0 and stop_flag_was_set:
        return "stop_command", True
    if exit_code == 0 and not stop_flag_was_set:
        return "spontaneous_exit", False
    if exit_code == -signal.SIGKILL:
        return "sigkill_or_oom", False
    if isinstance(exit_code, int) and exit_code < 0:
        return "signal_exit", False
    if isinstance(exit_code, int) and exit_code > 0:
        return "error_exit", False
    return "unknown", False


# =============================================================================
# DB helpers
# =============================================================================

async def cleanup_orphan_processes() -> None:
    """Mark running RunnerInstance rows as stopped when their PID no longer exists."""
    try:
        await ensure_runner_database_initialized()
        from strider.models import get_session
        from strider.admin.models import RunnerInstance
        from strider.querysets import QuerySet
        from strider.datetime import timezone

        async with get_session() as db:
            qs = QuerySet(RunnerInstance, db)
            running = await qs.filter(status="running").all()
            changed = False
            for inst in running:
                pid = getattr(inst, "pid", None)
                if not isinstance(pid, int) or pid <= 0 or not process_exists(pid):
                    inst.status = "stopped"
                    inst.stopped_at = timezone.now()
                    inst.pid = None
                    inst.stop_reason = (
                        "orphan_cleanup_missing_pid"
                        if not isinstance(pid, int) or pid <= 0
                        else "orphan_cleanup_process_missing"
                    )
                    inst.exit_code = None
                    await inst.save(db)
                    changed = True
            if changed:
                await db.commit()
    except Exception as exc:
        logger.debug("cleanup_orphan_processes failed: %s", exc)


async def ensure_runner_database_initialized() -> None:
    """Ensure DB is initialized for controller-side metadata operations."""
    try:
        from strider.models import get_session
        async with get_session() as db:
            _ = db
            return
    except Exception as exc:
        msg = str(exc)
        if not (
            "Database não inicializado" in msg
            or "init_database" in msg
            or "not initialized" in msg.lower()
        ):
            logger.debug("Runner DB check non-init error: %s", exc)
            return

    settings = get_settings()
    try:
        if getattr(settings, "has_read_replica", False):
            from strider.database import init_replicas
            await init_replicas()
            logger.info("Runner DB reinitialized via replicas")
            return
        from strider.models import init_database
        db_url = getattr(settings, "database_url", None)
        if not db_url:
            logger.warning("Runner DB reinit skipped: missing database_url")
            return
        await init_database(
            db_url,
            pool_size=int(getattr(settings, "database_pool_size", 5) or 5),
            max_overflow=int(getattr(settings, "database_max_overflow", 10) or 10),
        )
        logger.info("Runner DB reinitialized")
    except Exception as exc:
        logger.warning("Runner DB reinit failed: %s", exc)


async def _get_session_pid(runner_name: str, session_id: str) -> int | None:
    """
    Resolve PID for a session.
    DB is the source of truth; in-memory process cache is the fallback.
    Returns None if no live PID found.
    """
    try:
        await ensure_runner_database_initialized()
        from strider.models import get_session
        from strider.admin.models import RunnerInstance
        from strider.querysets import QuerySet

        async with get_session() as db:
            qs = QuerySet(RunnerInstance, db)
            inst = await qs.filter(
                runner_name=runner_name, session_id=session_id
            ).first()
            if inst:
                pid = getattr(inst, "pid", None)
                if isinstance(pid, int) and pid > 0:
                    return pid
    except Exception as exc:
        logger.debug("_get_session_pid DB lookup failed: %s", exc)
    return None


# =============================================================================
# Runner base class
# =============================================================================

class Runner(ABC):
    """
    Controlador de sessões longas: consome start/stop/pause/resume via Kafka.

    SUBCLASSE
    ─────────
    Implemente run_session(payload) com um keepalive loop que checa:
      check_stop_flag(session_id)  → encerrar (sair do loop, fazer cleanup)
      self.is_stop_requested       → encerrar (resource exceeded)

    Pause/Resume são transparentes para o processo filho — o OS suspende e
    retoma via SIGSTOP/SIGCONT sem nenhuma participação do código do filho.

    LIFECYCLE HOOKS (override no app para integração externa)
    ─────────────────────────────────────────────────────────
      on_start()             → controlador pronto para receber comandos Kafka
      on_stop()              → sessão encerrada; disponível current_session_id,
                               last_session_stop_reason, last_session_exit_code
      after_stop()           → controlador encerrando (shutdown total)
      on_resource_exceeded() → CPU/mem excedidos (default: request_stop)
      on_session_crash()     → processo filho morreu inesperadamente
    """

    input_topic: str = "runner.commands"
    group_id: str | None = None
    cpu_limit_percent: float = 0.0
    memory_mb_limit: float = 0.0
    io_read_mb_limit: float = 0.0
    check_interval_seconds: float = 5.0
    shutdown_grace_seconds: float = 5.0
    session_stop_timeout_seconds: float = 5.0

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.__name__ != "Runner":
            _runner_registry[cls.__name__] = cls

    def __init__(self) -> None:
        self._stop_requested = False
        self._paused = False
        self._current_session_id: str | None = None
        self._session_task: asyncio.Task | None = None
        # session_id → (Popen, stop_flag_was_set)
        self._session_processes: dict[str, tuple[subprocess.Popen, bool]] = {}
        self._consumer: Any = None
        self._resource_task: asyncio.Task | None = None
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._signal_count = 0
        self._last_session_stop_reason: str | None = None
        self._last_session_exit_code: int | None = None

    # ── Public API ───────────────────────────────────────────────────────

    def request_stop(self) -> None:
        self._stop_requested = True

    @property
    def is_stop_requested(self) -> bool:
        return self._stop_requested

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def current_session_id(self) -> str | None:
        return self._current_session_id

    @property
    def last_session_stop_reason(self) -> str | None:
        return self._last_session_stop_reason

    @property
    def last_session_exit_code(self) -> int | None:
        return self._last_session_exit_code

    # ── Lifecycle hooks ──────────────────────────────────────────────────

    async def on_start(self) -> None:
        """Called in the controller process before the Kafka loop starts."""
        pass

    @abstractmethod
    async def run_session(self, payload: dict[str, Any]) -> None:
        """
        Child process entrypoint. Must contain a keepalive loop.

        The loop must check:
          check_stop_flag(session_id)  → break and clean up
          self.is_stop_requested       → break (resource exceeded)

        Pause/Resume: transparent — OS-level SIGSTOP/SIGCONT, no code needed here.
        """
        ...

    async def on_stop(self) -> None:
        """
        Called in controller after each isolated session ends.
        self.current_session_id, self.last_session_stop_reason,
        self.last_session_exit_code are available here.
        """
        pass

    async def after_stop(self) -> None:
        """Called in controller after the Kafka consumer shuts down."""
        pass

    async def on_resource_exceeded(self, metrics: dict[str, float]) -> None:
        """CPU/memory/IO exceeded. Default: log + request_stop."""
        logger.warning("Runner resource limit exceeded: %s", metrics)
        self.request_stop()

    async def on_session_crash(
        self, session_id: str, exit_code: int | None, reason: str
    ) -> None:
        """
        Called in controller when a child process dies unexpectedly.
        Override to send alerts, trigger restarts, etc.
        """
        logger.error(
            "Runner session crashed: session_id=%s exit_code=%s reason=%s",
            session_id, exit_code, reason,
        )

    # ── Internal: trigger controller hooks ──────────────────────────────

    async def _trigger_stop_hooks(
        self,
        session_id: str,
        reason: str,
        exit_code: int | None = None,
        is_clean: bool = True,
    ) -> None:
        prev_sid = self._current_session_id
        prev_reason = self._last_session_stop_reason
        prev_exit = self._last_session_exit_code
        self._current_session_id = session_id
        self._last_session_stop_reason = reason
        self._last_session_exit_code = exit_code
        try:
            if not is_clean:
                try:
                    await self.on_session_crash(session_id, exit_code, reason)
                except Exception as exc:
                    logger.exception(
                        "on_session_crash raised session_id=%s: %s", session_id, exc
                    )
            await self.on_stop()
        except Exception as exc:
            logger.exception(
                "on_stop raised session_id=%s reason=%s: %s", session_id, reason, exc
            )
        try:
            await self.after_stop()
        except Exception as exc:
            logger.exception("after_stop raised session_id=%s: %s", session_id, exc)
        finally:
            self._current_session_id = prev_sid
            self._last_session_stop_reason = prev_reason
            self._last_session_exit_code = prev_exit

    # ── Config ───────────────────────────────────────────────────────────

    def _get_config(self) -> dict[str, Any]:
        s = get_settings()
        return {
            "input_topic": getattr(s, "runner_default_topic", None) or self.input_topic,
            "group_id": self.group_id or self.__class__.__name__,
            "cpu_limit": float(getattr(s, "runner_cpu_limit_percent", 0) or 0),
            "memory_mb_limit": float(getattr(s, "runner_memory_mb_limit", 0) or 0),
            "io_read_mb_limit": float(getattr(s, "runner_io_read_mb_limit", 0) or 0),
            "check_interval": float(getattr(s, "runner_check_interval_seconds", 5) or 5),
            "shutdown_grace": float(getattr(s, "runner_shutdown_grace_seconds", 5) or 5),
            "session_stop_timeout": float(
                getattr(s, "runner_session_stop_timeout_seconds", 15) or 15
            ),
        }

    # ── Resource check ───────────────────────────────────────────────────

    async def _resource_check_loop(self, config: dict[str, Any]) -> None:
        cpu = config.get("cpu_limit") or self.cpu_limit_percent
        mem = config.get("memory_mb_limit") or self.memory_mb_limit
        io = config.get("io_read_mb_limit") or self.io_read_mb_limit
        interval = config.get("check_interval") or self.check_interval_seconds
        if cpu <= 0 and mem <= 0 and io <= 0:
            return
        while self._running and not self._stop_requested:
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            if not self._running or self._stop_requested:
                break
            metrics = _get_process_metrics()
            if (
                (cpu > 0 and metrics.get("cpu_percent", 0) >= cpu)
                or (mem > 0 and metrics.get("memory_mb", 0) >= mem)
                or (io > 0 and metrics.get("io_read_mb", 0) >= io)
            ):
                try:
                    await self.on_resource_exceeded(metrics)
                except Exception as exc:
                    logger.exception("on_resource_exceeded raised: %s", exc)
                self.request_stop()
                break

    # ── Spawn ────────────────────────────────────────────────────────────

    async def _spawn_isolated_session(
        self, session_id: str, message: dict[str, Any]
    ) -> None:
        runner_name = self.__class__.__name__

        if session_id in self._session_processes:
            proc, _ = self._session_processes[session_id]
            if proc.poll() is None:
                logger.warning(
                    "Runner already running session_id=%s, ignoring start", session_id
                )
                return
            del self._session_processes[session_id]

        # Clear any leftover stop flag from a previous run
        clear_stop_flag(session_id)

        # Write payload to temp file (removed after 30s)
        fd, payload_path = tempfile.mkstemp(
            suffix=".runner.json", prefix="strider_runner_"
        )
        try:
            os.write(fd, json.dumps(message).encode("utf-8"))
            os.close(fd)
            fd = None
        except Exception:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            _safe_remove(payload_path)
            raise

        cmd = [
            sys.executable, "-m",
            "strider.messaging.runner_session",
            runner_name, session_id, payload_path,
        ]
        env = os.environ.copy()
        env["STRIDER_RUNNER_SESSION"] = "1"
        env["STRIDER_RUNNER_FLAG_DIR"] = _runner_flag_dir()

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=os.getcwd(),
                env=env,
                preexec_fn=os.setsid,
            )
            pid = proc.pid
            self._session_processes[session_id] = (proc, False)
            logger.info(
                "Runner spawned: runner=%s session_id=%s pid=%d",
                runner_name, session_id, pid,
            )
        except Exception as exc:
            _safe_remove(payload_path)
            logger.exception("Runner spawn failed session_id=%s: %s", session_id, exc)
            raise

        # Persist RunnerInstance (best-effort)
        try:
            await ensure_runner_database_initialized()
            from strider.models import get_session
            from strider.admin.models import RunnerInstance
            from strider.querysets import QuerySet

            payload_copy = {k: v for k, v in message.items() if k != "action"}
            user_id = payload_copy.get("user_id")

            async with get_session() as db:
                qs = QuerySet(RunnerInstance, db)
                inst = await qs.filter(
                    runner_name=runner_name, session_id=session_id
                ).first()
                if inst:
                    inst.status = "running"
                    inst.pid = pid
                    inst.stop_reason = None
                    inst.exit_code = None
                    inst.stopped_at = None
                    await inst.save(db)
                else:
                    inst = RunnerInstance(
                        runner_name=runner_name,
                        session_id=session_id,
                        user_id=str(user_id) if user_id is not None else None,
                        status="running",
                        pid=pid,
                        stop_reason=None,
                        exit_code=None,
                        payload_json=json.dumps(payload_copy) if payload_copy else None,
                        stopped_at=None,
                    )
                    await inst.save(db)
                await db.commit()
        except Exception as exc:
            logger.debug(
                "Runner persist RunnerInstance failed session_id=%s: %s", session_id, exc
            )

        asyncio.get_event_loop().call_later(30.0, lambda: _safe_remove(payload_path))

    # ── Stop ─────────────────────────────────────────────────────────────

    async def _stop_isolated_session(
        self, session_id: str, config: dict[str, Any]
    ) -> None:
        """
        Clean stop flow:
          1. Set .stop flag → child's keepalive loop exits on next check (clean exit 0)
          2. Mark stop_flag_was_set=True so reap treats exit 0 as clean
          3. Wait 2s for graceful exit
          4. If still alive, SIGTERM → SIGKILL fallback (kill_process_by_pid)
          5. Update DB + trigger lifecycle hooks
        """
        runner_name = self.__class__.__name__
        grace = max(1.0, config.get("shutdown_grace", self.shutdown_grace_seconds))

        # 1-2: flag + memory marker
        set_stop_flag(session_id)
        if session_id in self._session_processes:
            proc, _ = self._session_processes[session_id]
            self._session_processes[session_id] = (proc, True)

        # 3: grace window for clean exit
        await asyncio.sleep(2.0)

        try:
            await ensure_runner_database_initialized()
            from strider.models import get_session
            from strider.admin.models import RunnerInstance
            from strider.querysets import QuerySet
            from strider.datetime import timezone

            async with get_session() as db:
                qs = QuerySet(RunnerInstance, db)
                inst = await qs.filter(
                    runner_name=runner_name, session_id=session_id
                ).first()

                # Resolve PID: DB first (source of truth), memory cache fallback
                pid: int | None = getattr(inst, "pid", None) if inst else None
                if not isinstance(pid, int) or pid <= 0:
                    entry = self._session_processes.get(session_id)
                    if entry:
                        p, _ = entry
                        pid = p.pid if p.poll() is None else None

                # 4: SIGTERM if still alive
                if isinstance(pid, int) and pid > 0:
                    if process_exists(pid):
                        logger.info(
                            "Runner stop: SIGTERM session_id=%s pid=%d", session_id, pid
                        )
                        kill_process_by_pid(pid, grace=grace)
                    else:
                        logger.debug(
                            "Runner stop: process already exited session_id=%s pid=%d",
                            session_id, pid,
                        )

                # 5: DB
                if inst:
                    inst.status = "stopped"
                    inst.pid = None
                    inst.stop_reason = "stop_command"
                    inst.exit_code = None
                    inst.stopped_at = timezone.now()
                    await inst.save(db)
                    await db.commit()

            await self._trigger_stop_hooks(
                session_id, reason="stop_command", is_clean=True
            )

        except Exception as exc:
            logger.warning(
                "Runner _stop_isolated_session failed session_id=%s: %s", session_id, exc
            )
        finally:
            self._session_processes.pop(session_id, None)
            clear_stop_flag(session_id)

    # ── Pause / Resume via SIGSTOP / SIGCONT ────────────────────────────

    async def _pause_isolated_session(self, session_id: str) -> None:
        """
        Pause an isolated session by sending SIGSTOP to its process group.

        Effect:
          • OS suspends all threads in the process — zero CPU
          • asyncio event loop is frozen: no ticks, no DB ops, no timers
          • External WebSocket (market_svc) buffers ticks during suspension
          • Child process needs no code changes — pause is entirely transparent
          • SIGCONT resumes the process exactly where it was frozen
        """
        runner_name = self.__class__.__name__
        pid = await _get_session_pid(runner_name, session_id)

        # Fallback to in-memory cache if DB has no PID yet
        if pid is None:
            entry = self._session_processes.get(session_id)
            if entry:
                proc, _ = entry
                if proc.poll() is None:
                    pid = proc.pid

        if pid is None:
            logger.warning(
                "Runner pause: no PID found for session_id=%s", session_id
            )
            return

        try:
            os.killpg(os.getpgid(pid), signal.SIGSTOP)
            logger.info(
                "Runner SIGSTOP sent: session_id=%s pid=%d (process suspended)",
                session_id, pid,
            )
        except ProcessLookupError:
            logger.warning(
                "Runner pause: process already gone session_id=%s pid=%d", session_id, pid
            )
            return
        except PermissionError as exc:
            logger.error(
                "Runner pause: permission denied for pid=%d: %s", pid, exc
            )
            return

        # Update DB status (best-effort)
        try:
            await ensure_runner_database_initialized()
            from strider.models import get_session
            from strider.admin.models import RunnerInstance
            from strider.querysets import QuerySet

            async with get_session() as db:
                qs = QuerySet(RunnerInstance, db)
                inst = await qs.filter(
                    runner_name=runner_name, session_id=session_id
                ).first()
                if inst and inst.status == "running":
                    inst.status = "paused"
                    await inst.save(db)
                    await db.commit()
        except Exception as exc:
            logger.debug(
                "Runner pause DB update failed session_id=%s: %s", session_id, exc
            )

    async def _resume_isolated_session(self, session_id: str) -> None:
        """
        Resume a paused session by sending SIGCONT to its process group.
        The process resumes exactly where SIGSTOP froze it.
        """
        runner_name = self.__class__.__name__
        pid = await _get_session_pid(runner_name, session_id)

        if pid is None:
            entry = self._session_processes.get(session_id)
            if entry:
                proc, _ = entry
                if proc.poll() is None:
                    pid = proc.pid

        if pid is None:
            logger.warning(
                "Runner resume: no PID found for session_id=%s", session_id
            )
            return

        try:
            os.killpg(os.getpgid(pid), signal.SIGCONT)
            logger.info(
                "Runner SIGCONT sent: session_id=%s pid=%d (process resumed)",
                session_id, pid,
            )
        except ProcessLookupError:
            logger.warning(
                "Runner resume: process already gone session_id=%s pid=%d", session_id, pid
            )
            return
        except PermissionError as exc:
            logger.error(
                "Runner resume: permission denied for pid=%d: %s", pid, exc
            )
            return

        try:
            await ensure_runner_database_initialized()
            from strider.models import get_session
            from strider.admin.models import RunnerInstance
            from strider.querysets import QuerySet

            async with get_session() as db:
                qs = QuerySet(RunnerInstance, db)
                inst = await qs.filter(
                    runner_name=runner_name, session_id=session_id
                ).first()
                if inst and inst.status == "paused":
                    inst.status = "running"
                    await inst.save(db)
                    await db.commit()
        except Exception as exc:
            logger.debug(
                "Runner resume DB update failed session_id=%s: %s", session_id, exc
            )

    # ── Stop all ─────────────────────────────────────────────────────────

    async def _stop_all_isolated_sessions(self, config: dict[str, Any]) -> None:
        runner_name = self.__class__.__name__
        grace = max(1.0, config.get("shutdown_grace", self.shutdown_grace_seconds))
        try:
            await ensure_runner_database_initialized()
            from strider.models import get_session
            from strider.admin.models import RunnerInstance
            from strider.querysets import QuerySet
            from strider.datetime import timezone

            async with get_session() as db:
                qs = QuerySet(RunnerInstance, db)
                running = await qs.filter(
                    runner_name=runner_name, status="running"
                ).all()
                changed = False
                for inst in running:
                    sid = str(inst.session_id)
                    set_stop_flag(sid)
                    if sid in self._session_processes:
                        proc, _ = self._session_processes[sid]
                        self._session_processes[sid] = (proc, True)
                    pid = getattr(inst, "pid", None)
                    if isinstance(pid, int) and pid > 0 and process_exists(pid):
                        kill_process_by_pid(pid, grace=grace)
                    inst.status = "stopped"
                    inst.pid = None
                    inst.stop_reason = "stop_all"
                    inst.exit_code = None
                    inst.stopped_at = timezone.now()
                    await inst.save(db)
                    changed = True
                    self._session_processes.pop(sid, None)
                    clear_stop_flag(sid)
                    await self._trigger_stop_hooks(
                        sid, reason="stop_all", is_clean=True
                    )
                if changed:
                    await db.commit()

            # Fallback: kill any process only in memory cache
            for sid, (proc, _) in list(self._session_processes.items()):
                if proc.poll() is None:
                    set_stop_flag(sid)
                    kill_process_by_pid(proc.pid, grace=grace)
                    await self._trigger_stop_hooks(
                        sid, reason="stop_all_fallback", is_clean=True
                    )
                self._session_processes.pop(sid, None)
                clear_stop_flag(sid)

        except Exception as exc:
            logger.warning("_stop_all_isolated_sessions failed: %s", exc)

    # ── Reap dead processes (audited) ────────────────────────────────────

    async def _reap_dead_processes(self, runner_name: str) -> None:
        """
        Collect processes that have exited, update RunnerInstance, fire hooks.

        Audit trail:
          clean  → INFO log, on_stop + after_stop
          crash  → WARNING log, on_session_crash + on_stop + after_stop
        """
        dead: list[tuple[str, int | None, bool]] = []

        for sid, (proc, stop_flag_was_set) in list(self._session_processes.items()):
            if proc.poll() is not None:
                dead.append((sid, proc.returncode, stop_flag_was_set))
                self._session_processes.pop(sid, None)
                reason, is_clean = _classify_exit(proc.returncode, stop_flag_was_set)
                if is_clean:
                    logger.info(
                        "Runner reaped (clean): runner=%s session_id=%s "
                        "exit=%s reason=%s",
                        runner_name, sid, proc.returncode, reason,
                    )
                else:
                    logger.warning(
                        "Runner reaped (UNEXPECTED): runner=%s session_id=%s "
                        "exit=%s reason=%s stop_flag=%s — check session log",
                        runner_name, sid, proc.returncode, reason, stop_flag_was_set,
                    )

        for session_id, exit_code, stop_flag_was_set in dead:
            reason, is_clean = _classify_exit(exit_code, stop_flag_was_set)

            try:
                await ensure_runner_database_initialized()
                from strider.models import get_session
                from strider.admin.models import RunnerInstance
                from strider.querysets import QuerySet
                from strider.datetime import timezone

                async with get_session() as db:
                    qs = QuerySet(RunnerInstance, db)
                    inst = await qs.filter(
                        runner_name=runner_name, session_id=session_id
                    ).first()
                    if inst and inst.status in ("running", "paused"):
                        inst.status = "stopped"
                        inst.pid = None
                        inst.stop_reason = reason
                        inst.exit_code = exit_code
                        inst.stopped_at = timezone.now()
                        await inst.save(db)
                        await db.commit()
                        logger.debug(
                            "RunnerInstance updated: session_id=%s reason=%s exit=%s",
                            session_id, reason, exit_code,
                        )
            except Exception as exc:
                logger.debug(
                    "reap DB update session_id=%s failed: %s", session_id, exc
                )

            clear_stop_flag(session_id)
            await self._trigger_stop_hooks(
                session_id, reason=reason, exit_code=exit_code, is_clean=is_clean
            )

        if dead:
            await cleanup_orphan_processes()

    # ── Message handler ──────────────────────────────────────────────────

    async def _handle_message(
        self, message: dict[str, Any], config: dict[str, Any]
    ) -> None:
        action = (message.get("action") or "").strip().lower()
        session_id = message.get("session_id")
        if isinstance(session_id, str):
            session_id = session_id.strip() or None
        elif session_id is not None:
            session_id = str(session_id).strip() or None

        settings = get_settings()
        isolated = getattr(settings, "runner_isolated_instances", True)

        if action == "start":
            if isolated:
                if session_id:
                    await self._spawn_isolated_session(session_id, message)
                else:
                    logger.warning("Runner start: session_id required in isolated mode")
                return
            if self._session_task and not self._session_task.done():
                logger.warning(
                    "Runner already active, ignoring start session_id=%s", session_id
                )
                return
            self._stop_requested = False
            self._current_session_id = session_id
            self._session_task = asyncio.create_task(self.run_session(message))
            self._session_task.add_done_callback(self._on_session_done)
            return

        if action == "stop":
            if isolated:
                if session_id:
                    await self._stop_isolated_session(session_id, config)
                else:
                    await self._stop_all_isolated_sessions(config)
                return
            stop_timeout = max(
                1.0, config.get("session_stop_timeout", self.session_stop_timeout_seconds)
            )
            if self._session_task and not self._session_task.done():
                self._session_task.cancel()
                try:
                    await asyncio.wait_for(self._session_task, timeout=2.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
                self._session_task = None
                self._current_session_id = None
            try:
                await asyncio.wait_for(self.run_session(message), timeout=stop_timeout)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            except Exception as exc:
                logger.exception("run_session(stop) failed: %s", exc)
            if session_id is None or session_id == self._current_session_id:
                self.request_stop()
            return

        if action == "pause":
            if isolated:
                if session_id:
                    await self._pause_isolated_session(session_id)
                else:
                    logger.warning(
                        "Runner pause: session_id required in isolated mode"
                    )
            else:
                if session_id is None or session_id == self._current_session_id:
                    self._paused = True
                    logger.info("Runner paused session_id=%s", session_id)
            return

        if action == "resume":
            if isolated:
                if session_id:
                    await self._resume_isolated_session(session_id)
                else:
                    logger.warning(
                        "Runner resume: session_id required in isolated mode"
                    )
            else:
                if session_id is None or session_id == self._current_session_id:
                    self._paused = False
                    logger.info("Runner resumed session_id=%s", session_id)
            return

        logger.debug("Runner unknown action=%s session_id=%s", action, session_id)

    def _on_session_done(self, task: asyncio.Task) -> None:
        self._current_session_id = None
        self._session_task = None
        if not task.cancelled() and task.exception():
            logger.exception("run_session failed: %s", task.exception())

    # ── Main loop ────────────────────────────────────────────────────────

    async def run(self) -> None:
        await self.run_forever()

    async def run_forever(self) -> None:
        from strider.messaging.registry import create_consumer

        settings = get_settings()
        if not getattr(settings, "kafka_enabled", False):
            raise RuntimeError("Runner requires kafka_enabled=True")

        isolated = bool(getattr(settings, "runner_isolated_instances", True))
        call_on_start = bool(
            getattr(settings, "runner_call_on_start_when_isolated", False)
        )
        config = self._get_config()
        self._running = True
        self._stop_requested = False

        loop = asyncio.get_event_loop()
        try:
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, self._handle_signal)
        except NotImplementedError:
            pass

        if isolated and not call_on_start:
            logger.info(
                "Runner isolated mode: on_start skipped in controller "
                "(set runner_call_on_start_when_isolated=True to override)"
            )
        else:
            await self.on_start()

        self._consumer = create_consumer(
            group_id=config["group_id"],
            topics=[config["input_topic"]],
            message_handler=lambda msg: self._handle_message(msg, config),
        )
        await self._consumer.start()

        if config.get("check_interval"):
            self._resource_task = asyncio.create_task(
                self._resource_check_loop(config)
            )

        logger.info(
            "Runner started: topic=%s group_id=%s isolated=%s",
            config["input_topic"], config["group_id"], isolated,
        )

        reap_interval = 5.0
        last_reap = loop.time()
        runner_name = self.__class__.__name__

        try:
            await cleanup_orphan_processes()
            while self._running and not self._stop_requested:
                await asyncio.sleep(1)
                now = loop.time()
                if now - last_reap >= reap_interval:
                    last_reap = now
                    await self._reap_dead_processes(runner_name)
        except asyncio.CancelledError:
            self._stop_requested = True

        self._running = False

        if self._resource_task:
            self._resource_task.cancel()
            try:
                await self._resource_task
            except asyncio.CancelledError:
                pass
            self._resource_task = None

        # Kill memory-cached processes before DB-based stop_all
        grace = max(2.0, config.get("shutdown_grace", self.shutdown_grace_seconds))
        for sid, (proc, _) in list(self._session_processes.items()):
            if proc.poll() is None:
                try:
                    kill_process_by_pid(proc.pid, grace=grace)
                except Exception:
                    try:
                        kill_process_by_pid(proc.pid, grace=0.1)
                    except Exception:
                        pass
            self._session_processes.pop(sid, None)

        await self._stop_all_isolated_sessions(config)

        if self._session_task and not self._session_task.done():
            self._session_task.cancel()
            try:
                await asyncio.wait_for(
                    self._session_task,
                    timeout=max(0.1, config.get("shutdown_grace", self.shutdown_grace_seconds)),
                )
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            self._session_task = None
            self._current_session_id = None

        try:
            await self.on_stop()
        except Exception as exc:
            logger.exception("on_stop failed during shutdown: %s", exc)

        if self._consumer:
            try:
                await asyncio.wait_for(
                    self._consumer.stop(),
                    timeout=max(0.1, config.get("shutdown_grace", self.shutdown_grace_seconds)),
                )
            except asyncio.TimeoutError:
                logger.warning("Runner consumer stop timeout")
            self._consumer = None

        try:
            await self.after_stop()
        except Exception as exc:
            logger.exception("after_stop failed during shutdown: %s", exc)

        self._shutdown_event.set()
        logger.info("Runner stopped")

    def _handle_signal(self) -> None:
        self._signal_count += 1
        if self._signal_count == 1:
            logger.info("Runner shutdown signal received")
            self.request_stop()
        else:
            logger.warning("Runner second signal — forcing stop")
            self.request_stop()
            self._shutdown_event.set()

    async def wait(self) -> None:
        await self._shutdown_event.wait()


# =============================================================================
# Utilities
# =============================================================================

def _safe_remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def get_runner(name: str | type[Runner]) -> type[Runner] | None:
    if isinstance(name, type) and issubclass(name, Runner):
        return name
    return _runner_registry.get(name) if isinstance(name, str) else None


def list_runners() -> list[str]:
    return list(_runner_registry.keys())


async def run_runner_async(runner_class: str | type[Runner]) -> None:
    if isinstance(runner_class, str):
        resolved = get_runner(runner_class)
        if resolved is None:
            raise ValueError(
                f"Runner '{runner_class}' not found. Available: {list_runners()}"
            )
        runner_class = resolved
    await runner_class().run_forever()


def run_runner(runner_class: str | type[Runner]) -> None:
    asyncio.run(run_runner_async(runner_class))


# =============================================================================
# send_* helpers
# =============================================================================

async def send_start(
    runner_name: str,
    session_id: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Publish start command and pre-register RunnerInstance."""
    runner_cls = get_runner(runner_name)
    if runner_cls is None:
        raise ValueError(
            f"Runner '{runner_name}' not found. Available: {list_runners()}"
        )
    try:
        await ensure_runner_database_initialized()
        from strider.models import get_session
        from strider.admin.models import RunnerInstance
        from strider.querysets import QuerySet

        p = payload or {}
        user_id = p.get("user_id")
        async with get_session() as db:
            qs = QuerySet(RunnerInstance, db)
            inst = await qs.filter(
                runner_name=runner_name, session_id=session_id
            ).first()
            if inst:
                inst.status = "running"
                inst.user_id = str(user_id) if user_id is not None else None
                inst.payload_json = json.dumps(p) if p else None
                inst.pid = None
                inst.stop_reason = None
                inst.exit_code = None
                inst.stopped_at = None
                await inst.save(db)
            else:
                await RunnerInstance(
                    runner_name=runner_name,
                    session_id=session_id,
                    user_id=str(user_id) if user_id is not None else None,
                    status="running",
                    payload_json=json.dumps(p) if p else None,
                    pid=None,
                    stop_reason=None,
                    exit_code=None,
                ).save(db)
            await db.commit()
    except Exception as exc:
        logger.debug("send_start RunnerInstance register: %s", exc)

    instance = runner_cls()
    config = instance._get_config()
    from strider.messaging.registry import publish
    await publish(
        config["input_topic"],
        {"action": "start", "session_id": session_id, **(payload or {})},
        key=session_id,
    )


async def send_stop(runner_name: str, session_id: str) -> None:
    """Publish stop command and update RunnerInstance status."""
    runner_cls = get_runner(runner_name)
    if runner_cls is None:
        raise ValueError(
            f"Runner '{runner_name}' not found. Available: {list_runners()}"
        )
    try:
        await ensure_runner_database_initialized()
        from strider.models import get_session
        from strider.admin.models import RunnerInstance
        from strider.querysets import QuerySet
        from strider.datetime import timezone

        async with get_session() as db:
            qs = QuerySet(RunnerInstance, db)
            inst = await qs.filter(
                runner_name=runner_name, session_id=session_id
            ).first()
            if inst:
                inst.status = "stopped"
                inst.pid = None
                inst.stop_reason = "stop_command_sent"
                inst.exit_code = None
                inst.stopped_at = timezone.now()
                await inst.save(db)
                await db.commit()
    except Exception as exc:
        logger.debug("send_stop RunnerInstance update: %s", exc)

    instance = runner_cls()
    config = instance._get_config()
    from strider.messaging.registry import publish
    await publish(
        config["input_topic"],
        {"action": "stop", "session_id": session_id},
        key=session_id,
    )


async def send_pause(runner_name: str, session_id: str) -> None:
    """Publish pause command (controller will send SIGSTOP to child process)."""
    runner_cls = get_runner(runner_name)
    if runner_cls is None:
        raise ValueError(f"Runner '{runner_name}' not found.")
    instance = runner_cls()
    config = instance._get_config()
    from strider.messaging.registry import publish
    await publish(
        config["input_topic"],
        {"action": "pause", "session_id": session_id},
        key=session_id,
    )


async def send_resume(runner_name: str, session_id: str) -> None:
    """Publish resume command (controller will send SIGCONT to child process)."""
    runner_cls = get_runner(runner_name)
    if runner_cls is None:
        raise ValueError(f"Runner '{runner_name}' not found.")
    instance = runner_cls()
    config = instance._get_config()
    from strider.messaging.registry import publish
    await publish(
        config["input_topic"],
        {"action": "resume", "session_id": session_id},
        key=session_id,
    )