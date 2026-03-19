"""
Runner: controlador de sessões longas com limites de recursos e lifecycle hooks.

O Runner é o CONTROLADOR: consome comandos start/stop via Kafka e cria/encerra
INSTÂNCIAS isoladas (um processo por sessão). Cada instância tem:
- Conexões de DB e Redis próprias (sem vazar com a API)
- Logs separados (session_id no contexto)
- Stop imediato via SIGTERM (sem depender de loop reativo no mesmo processo)

Com runner_isolated_instances=False (legado), sessões rodam in-process.
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
from typing import Any

from strider.config import get_settings

logger = logging.getLogger(__name__)


def _get_process_metrics() -> dict[str, float]:
    """CPU, memory and optional IO for current process."""
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
    """Terminate a process group by PID with SIGTERM then SIGKILL fallback."""
    try:
        # Envia SIGTERM para o grupo
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except ProcessLookupError:
        return

    # Aguarda encerramento
    for _ in range(int(grace * 2)):
        try:
            os.kill(pid, 0)
            time.sleep(0.5)
        except ProcessLookupError:
            return

    # Se ainda estiver vivo, força kill
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


async def cleanup_orphan_processes() -> None:
    """Mark running RunnerInstance rows as stopped when PID no longer exists."""
    try:
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
                if not isinstance(pid, int) or pid <= 0:
                    inst.status = "stopped"
                    inst.stopped_at = timezone.now()
                    inst.pid = None
                    await inst.save(db)
                    changed = True
                    continue
                if process_exists(pid):
                    continue
                inst.status = "stopped"
                inst.stopped_at = timezone.now()
                inst.pid = None
                await inst.save(db)
                changed = True
            if changed:
                await db.commit()
    except Exception as exc:
        logger.debug("cleanup_orphan_processes failed: %s", exc)


class Runner(ABC):
    """
    Controlador de sessões longas: consome start/stop via Kafka e cria/encerra
    instâncias isoladas (um processo por sessão quando runner_isolated_instances=True).

    Cada instância (processo filho) tem seu próprio DB, Redis e recursos;
    não compartilha conexões com a API nem com o controlador, evitando
    vazamento de contexto e degradação. Stop é imediato via SIGTERM.

    Subclasse e implemente run_session(payload); opcionalmente on_start, on_stop,
    after_stop, on_resource_exceeded. Com isolated=True, run_session roda
    no processo filho; o controlador apenas espawana e termina processos.
    """

    input_topic: str = "runner.commands"
    group_id: str | None = None
    cpu_limit_percent: float = 0.0
    memory_mb_limit: float = 0.0
    io_read_mb_limit: float = 0.0
    check_interval_seconds: float = 5.0
    shutdown_grace_seconds: float = 5.0

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.__name__ != "Runner":
            _runner_registry[cls.__name__] = cls

    def __init__(self) -> None:
        self._stop_requested = False
        self._paused = False
        self._current_session_id: str | None = None
        self._session_task: asyncio.Task | None = None
        self._session_processes: dict[str, subprocess.Popen] = {}  # session_id -> Popen (modo isolado)
        self._consumer: Any = None
        self._resource_task: asyncio.Task | None = None
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._signal_count = 0

    def request_stop(self) -> None:
        """Sinaliza parada; run_session deve checar _stop_requested e retornar."""
        self._stop_requested = True

    @property
    def is_stop_requested(self) -> bool:
        return self._stop_requested

    @property
    def is_paused(self) -> bool:
        """Subclasse pode checar em run_session para pausar o loop."""
        return self._paused

    @property
    def current_session_id(self) -> str | None:
        return self._current_session_id

    # -------------------------------------------------------------------------
    # Lifecycle hooks (override no app)
    # -------------------------------------------------------------------------

    async def on_start(self) -> None:
        """Chamado antes de iniciar o loop de consumo."""
        pass

    @abstractmethod
    async def run_session(self, payload: dict[str, Any]) -> None:
        """
        Executa uma sessão (ex.: session_id em payload).
        Deve respeitar self._stop_requested e encerrar quando setado.
        """
        ...

    async def on_stop(self) -> None:
        """Chamado quando parada foi solicitada (stop ou limite)."""
        pass

    async def after_stop(self) -> None:
        """Chamado após encerramento (cleanup, persistência, eventos)."""
        pass

    async def on_resource_exceeded(self, metrics: dict[str, float]) -> None:
        """Chamado quando CPU/memory/IO excedem limite. Default: log e request_stop."""
        logger.warning(
            "Runner resource limit exceeded: %s (requesting stop)",
            metrics,
        )
        self.request_stop()

    # -------------------------------------------------------------------------
    # Config from Settings
    # -------------------------------------------------------------------------

    session_stop_timeout_seconds: float = 5.0

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

    # -------------------------------------------------------------------------
    # Resource check loop
    # -------------------------------------------------------------------------

    async def _resource_check_loop(self, config: dict[str, Any]) -> None:
        cpu_limit = config.get("cpu_limit") or self.cpu_limit_percent
        memory_mb_limit = config.get("memory_mb_limit") or self.memory_mb_limit
        io_read_mb_limit = config.get("io_read_mb_limit") or self.io_read_mb_limit
        interval = config.get("check_interval") or self.check_interval_seconds

        if cpu_limit <= 0 and memory_mb_limit <= 0 and io_read_mb_limit <= 0:
            return

        while self._running and not self._stop_requested:
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            if not self._running or self._stop_requested:
                break

            metrics = _get_process_metrics()
            exceeded = False
            if cpu_limit > 0 and metrics.get("cpu_percent", 0) >= cpu_limit:
                exceeded = True
            if memory_mb_limit > 0 and metrics.get("memory_mb", 0) >= memory_mb_limit:
                exceeded = True
            if io_read_mb_limit > 0 and metrics.get("io_read_mb", 0) >= io_read_mb_limit:
                exceeded = True

            if exceeded:
                try:
                    await self.on_resource_exceeded(metrics)
                except Exception as e:
                    logger.exception("Runner on_resource_exceeded failed: %s", e)
                self.request_stop()
                break

    # -------------------------------------------------------------------------
    # Command handler (Kafka message)
    # -------------------------------------------------------------------------

    async def _spawn_isolated_session(self, session_id: str, message: dict[str, Any]) -> None:
        """Cria processo filho isolado para esta sessão (DB/Redis próprios, stop via SIGTERM)."""
        runner_name = self.__class__.__name__
        if session_id in self._session_processes:
            proc = self._session_processes[session_id]
            if proc.poll() is None:
                logger.warning("Runner already has isolated process for session_id=%s, ignoring start", session_id)
                return
            del self._session_processes[session_id]

        fd, payload_path = tempfile.mkstemp(suffix=".runner.json", prefix="strider_runner_")
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
            os.remove(payload_path)
            raise

        cmd = [
            sys.executable,
            "-m",
            "strider",
            "runrunner-session",
            runner_name,
            session_id,
            payload_path,
        ]
        env = os.environ.copy()
        env["STRIDER_RUNNER_SESSION"] = "1"
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=os.getcwd(),
                env=env,
                preexec_fn=os.setsid,
            )
            pid = proc.pid
            self._session_processes[session_id] = proc
            logger.info("Runner started isolated process for session_id=%s pid=%s", session_id, pid)
        except Exception as e:
            logger.exception("Runner failed to spawn isolated process for session_id=%s: %s", session_id, e)
            try:
                os.remove(payload_path)
            except OSError:
                pass
            raise

        try:
            from strider.models import get_session
            from strider.admin.models import RunnerInstance
            from strider.querysets import QuerySet

            async with get_session() as db:
                qs = QuerySet(RunnerInstance, db)
                inst = await qs.filter(
                    runner_name=runner_name,
                    session_id=session_id,
                ).first()
                if inst:
                    inst.status = "running"
                    inst.pid = pid
                    inst.stopped_at = None
                    await inst.save(db)
                else:
                    payload = dict(message)
                    payload.pop("action", None)
                    user_id = payload.get("user_id")
                    payload_json = json.dumps(payload) if payload else None
                    inst = RunnerInstance(
                        runner_name=runner_name,
                        session_id=session_id,
                        user_id=str(user_id) if user_id is not None else None,
                        status="running",
                        pid=pid,
                        payload_json=payload_json,
                        stopped_at=None,
                    )
                    await inst.save(db)
                await db.commit()
        except Exception as exc:
            logger.debug("Runner failed to persist pid for session_id=%s: %s", session_id, exc)

        def _cleanup_payload() -> None:
            try:
                os.remove(payload_path)
            except OSError:
                pass

        asyncio.get_event_loop().call_later(30.0, _cleanup_payload)

    async def _stop_isolated_session(self, session_id: str, config: dict[str, Any]) -> None:
        """Stop isolated session by persisted PID (DB source of truth)."""
        runner_name = self.__class__.__name__
        grace = max(1.0, config.get("shutdown_grace", self.shutdown_grace_seconds))
        proc = self._session_processes.get(session_id)
        try:
            from strider.models import get_session
            from strider.admin.models import RunnerInstance
            from strider.querysets import QuerySet
            from strider.datetime import timezone

            async with get_session() as db:
                qs = QuerySet(RunnerInstance, db)
                inst = await qs.filter(
                    runner_name=runner_name,
                    session_id=session_id,
                ).first()
                if not inst:
                    # Compatibilidade: se não há linha no DB, tente matar pelo processo em memória.
                    if proc is not None and proc.poll() is None:
                        kill_process_by_pid(proc.pid, grace=grace)
                        logger.debug("Runner stop fallback by in-memory pid for session_id=%s pid=%s", session_id, proc.pid)
                    else:
                        logger.debug("Runner stop: no RunnerInstance for session_id=%s", session_id)
                    return

                pid = getattr(inst, "pid", None)
                if isinstance(pid, int) and pid > 0:
                    kill_process_by_pid(pid, grace=grace)
                elif proc is not None and proc.poll() is None:
                    # Fallback para sessões antigas sem pid persistido.
                    kill_process_by_pid(proc.pid, grace=grace)
                inst.status = "stopped"
                inst.pid = None
                inst.stopped_at = timezone.now()
                await inst.save(db)
                await db.commit()
        except Exception as e:
            logger.warning("Runner stop isolated session_id=%s: %s", session_id, e)
        finally:
            self._session_processes.pop(session_id, None)

    async def _stop_all_isolated_sessions(self, config: dict[str, Any]) -> None:
        """Stop all running sessions for this runner using persisted PIDs."""
        runner_name = self.__class__.__name__
        grace = max(1.0, config.get("shutdown_grace", self.shutdown_grace_seconds))
        try:
            from strider.models import get_session
            from strider.admin.models import RunnerInstance
            from strider.querysets import QuerySet
            from strider.datetime import timezone

            async with get_session() as db:
                qs = QuerySet(RunnerInstance, db)
                running = await qs.filter(
                    runner_name=runner_name,
                    status="running",
                ).all()
                changed = False
                for inst in running:
                    pid = getattr(inst, "pid", None)
                    if isinstance(pid, int) and pid > 0:
                        kill_process_by_pid(pid, grace=grace)
                    inst.status = "stopped"
                    inst.pid = None
                    inst.stopped_at = timezone.now()
                    await inst.save(db)
                    changed = True
                    self._session_processes.pop(inst.session_id, None)
                if changed:
                    await db.commit()

            # Compatibilidade: encerra qualquer processo ainda vivo só no cache local.
            for sid, proc in list(self._session_processes.items()):
                if proc.poll() is None:
                    kill_process_by_pid(proc.pid, grace=grace)
                self._session_processes.pop(sid, None)
        except Exception as exc:
            logger.warning("Runner stop all isolated sessions failed: %s", exc)

    async def _reap_dead_processes(self, runner_name: str) -> None:
        """
        Remove processos que já terminaram de _session_processes e atualiza
        RunnerInstance para stopped (vínculo forte: processo morto = status stopped).
        """
        dead = []
        for sid, proc in list(self._session_processes.items()):
            if proc.poll() is not None:
                dead.append(sid)
                self._session_processes.pop(sid, None)
                logger.info("Runner reaped dead process session_id=%s exitcode=%s", sid, proc.returncode)
        for session_id in dead:
            try:
                from strider.models import get_session
                from strider.admin.models import RunnerInstance
                from strider.querysets import QuerySet
                from strider.datetime import timezone
                async with get_session() as db:
                    qs = QuerySet(RunnerInstance, db)
                    inst = await qs.filter(
                        runner_name=runner_name,
                        session_id=session_id,
                    ).first()
                    if inst and inst.status == "running":
                        inst.status = "stopped"
                        inst.pid = None
                        inst.stopped_at = timezone.now()
                        await inst.save(db)
                        await db.commit()
                        logger.debug("RunnerInstance session_id=%s marked stopped after process exit", session_id)
            except Exception as exc:
                logger.debug("reap: update RunnerInstance for session_id=%s failed: %s", session_id, exc)

        await cleanup_orphan_processes()

    async def _handle_message(self, message: dict[str, Any], config: dict[str, Any]) -> None:
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
                    logger.warning("Runner isolated mode requires session_id for start")
                return

            if self._session_task is not None and not self._session_task.done():
                logger.warning("Runner already has active session, ignoring start session_id=%s", session_id)
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

            stop_timeout = max(1.0, config.get("session_stop_timeout", self.session_stop_timeout_seconds))
            if self._session_task is not None and not self._session_task.done():
                logger.info("Runner stop: cancelling stuck session task for session_id=%s", session_id)
                self._session_task.cancel()
                try:
                    await asyncio.wait_for(self._session_task, timeout=2.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
                self._session_task = None
                self._current_session_id = None
            try:
                await asyncio.wait_for(self.run_session(message), timeout=stop_timeout)
            except asyncio.TimeoutError:
                logger.warning(
                    "Runner run_session(stop) timed out after %.1fs (session_id=%s); DB may be updated later",
                    stop_timeout, session_id,
                )
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.exception("Runner run_session(stop) failed: %s", e)
            if session_id is None or session_id == self._current_session_id:
                self.request_stop()
            return

        if action == "pause":
            if not isolated and (session_id is None or session_id == self._current_session_id):
                self._paused = True
                logger.info("Runner paused for session_id=%s", session_id)
            elif isolated:
                logger.debug("Pause not sent to isolated process (session_id=%s); use stop to end", session_id)
            return

        if action == "resume":
            if not isolated and (session_id is None or session_id == self._current_session_id):
                self._paused = False
                logger.info("Runner resumed for session_id=%s", session_id)
            return

    def _on_session_done(self, task: asyncio.Task) -> None:
        self._current_session_id = None
        self._session_task = None
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            logger.exception("Runner run_session failed: %s", exc)

    # -------------------------------------------------------------------------
    # Run / shutdown
    # -------------------------------------------------------------------------

    async def run(self) -> None:
        """Run runner until shutdown (SIGTERM/SIGINT or stop command)."""
        await self.run_forever()

    async def run_forever(self) -> None:
        """Start consumer and resource check, wait until stop then cleanup."""
        from strider.messaging.registry import create_consumer

        settings = get_settings()
        if not getattr(settings, "kafka_enabled", False):
            raise RuntimeError("Runner requires kafka_enabled=True")

        config = self._get_config()
        self._running = True
        self._stop_requested = False

        # Signal handlers
        loop = asyncio.get_event_loop()
        def _sig() -> None:
            self._handle_signal()

        try:
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, _sig)
        except NotImplementedError:
            pass

        await self.on_start()

        async def message_handler(msg: dict[str, Any]) -> None:
            await self._handle_message(msg, config)

        self._consumer = create_consumer(
            group_id=config["group_id"],
            topics=[config["input_topic"]],
            message_handler=message_handler,
        )
        await self._consumer.start()

        if config.get("check_interval"):
            self._resource_task = asyncio.create_task(self._resource_check_loop(config))

        logger.info("Runner started: topic=%s group_id=%s", config["input_topic"], config["group_id"])

        reap_interval = 5.0
        last_reap = asyncio.get_event_loop().time()
        runner_name = self.__class__.__name__
        try:
            await cleanup_orphan_processes()
            while self._running and not self._stop_requested:
                await asyncio.sleep(1)
                now = asyncio.get_event_loop().time()
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

        for sid, proc in list(self._session_processes.items()):
            if proc.poll() is None:
                try:
                    kill_process_by_pid(proc.pid, grace=max(2.0, config.get("shutdown_grace", self.shutdown_grace_seconds)))
                except (subprocess.TimeoutExpired, Exception):
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
        except Exception as e:
            logger.exception("Runner on_stop failed: %s", e)

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
        except Exception as e:
            logger.exception("Runner after_stop failed: %s", e)

        self._shutdown_event.set()
        logger.info("Runner stopped")

    def _handle_signal(self) -> None:
        self._signal_count += 1
        if self._signal_count == 1:
            logger.info("Runner received shutdown signal")
            self.request_stop()
            return
        logger.warning("Runner received second signal, forcing stop")
        self.request_stop()
        self._shutdown_event.set()

    async def wait(self) -> None:
        """Wait for shutdown event."""
        await self._shutdown_event.wait()


def get_runner(name: str | type[Runner]) -> type[Runner] | None:
    """Get a registered Runner class by name."""
    if isinstance(name, type) and issubclass(name, Runner):
        return name
    return _runner_registry.get(name) if isinstance(name, str) else None


def list_runners() -> list[str]:
    """List registered Runner class names."""
    return list(_runner_registry.keys())


async def run_runner_async(runner_class: str | type[Runner]) -> None:
    """
    Run a Runner class (async). Use from CLI or asyncio.run(run_runner_async(...)).
    """
    if isinstance(runner_class, str):
        resolved = get_runner(runner_class)
        if resolved is None:
            raise ValueError(f"Runner '{runner_class}' not found. Available: {list_runners()}")
        runner_class = resolved
    instance = runner_class()
    await instance.run_forever()


def run_runner(runner_class: str | type[Runner]) -> None:
    """
    Run a Runner class (blocking). Uses asyncio.run() if no loop.

    Example:
        run_runner(StrategySessionRunner)
        run_runner("StrategySessionRunner")
    """
    import asyncio
    asyncio.run(run_runner_async(runner_class))


# =============================================================================
# RunnerController — interface simples para comandos (sem publish manual)
# A framework registra RunnerInstance (Admin Ops) para controle e desempenho;
# o app pode enviar user_id/contexto no payload para enriquecer a listagem.
# =============================================================================

async def send_start(
    runner_name: str,
    session_id: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """
    Envia comando start para um runner (publica no tópico Kafka do runner).
    A framework registra RunnerInstance para o Admin Ops (controle e desempenho).
    O app pode passar user_id (e outros dados) no payload para enriquecer a listagem.

    Args:
        runner_name: Nome da classe do Runner (ex.: StrategySessionRunner)
        session_id: Identificador da sessão/instância (ex.: user_id ou composite)
        payload: Dados extras enviados ao run_session(payload); user_id aparece no Admin
    """
    runner_cls = get_runner(runner_name)
    if runner_cls is None:
        raise ValueError(f"Runner '{runner_name}' não encontrado. Disponíveis: {list_runners()}")
    # Framework regista instância no Admin Ops (best-effort)
    try:
        from strider.models import get_session
        from strider.admin.models import RunnerInstance
        from strider.querysets import QuerySet
        import json

        payload = payload or {}
        user_id = payload.get("user_id")
        uid = str(user_id) if user_id is not None else None
        payload_json = json.dumps(payload) if payload else None

        async with get_session() as db:
            qs = QuerySet(RunnerInstance, db)
            existing = await qs.filter(
                runner_name=runner_name,
                session_id=session_id,
            ).first()
            if existing:
                existing.status = "running"
                existing.user_id = uid
                existing.payload_json = payload_json
                existing.pid = None
                existing.stopped_at = None
                await existing.save(db)
            else:
                inst = RunnerInstance(
                    runner_name=runner_name,
                    session_id=session_id,
                    user_id=uid,
                    status="running",
                    payload_json=payload_json,
                    pid=None,
                )
                await inst.save(db)
            await db.commit()
    except Exception as exc:
        logger.debug("RunnerInstance start register (best-effort): %s", exc)

    instance = runner_cls()
    config = instance._get_config()
    topic = config["input_topic"]
    from strider.messaging.registry import publish
    msg = {"action": "start", "session_id": session_id, **(payload or {})}
    await publish(topic, msg, key=session_id)


async def send_stop(runner_name: str, session_id: str) -> None:
    """
    Envia comando stop para uma instância do runner.
    A framework atualiza RunnerInstance (status stopped) no Admin Ops.
    """
    runner_cls = get_runner(runner_name)
    if runner_cls is None:
        raise ValueError(f"Runner '{runner_name}' não encontrado. Disponíveis: {list_runners()}")

    try:
        from strider.models import get_session
        from strider.admin.models import RunnerInstance
        from strider.querysets import QuerySet
        from strider.datetime import timezone

        async with get_session() as db:
            qs = QuerySet(RunnerInstance, db)
            inst = await qs.filter(
                runner_name=runner_name,
                session_id=session_id,
            ).first()
            if inst:
                inst.status = "stopped"
                inst.pid = None
                inst.stopped_at = timezone.now()
                await inst.save(db)
                await db.commit()
    except Exception as exc:
        logger.debug("RunnerInstance stop register (best-effort): %s", exc)

    instance = runner_cls()
    config = instance._get_config()
    topic = config["input_topic"]
    from strider.messaging.registry import publish
    await publish(topic, {"action": "stop", "session_id": session_id}, key=session_id)


async def send_pause(runner_name: str, session_id: str) -> None:
    """Envia comando pause (o Runner pode tratar em run_session)."""
    runner_cls = get_runner(runner_name)
    if runner_cls is None:
        raise ValueError(f"Runner '{runner_name}' não encontrado.")
    instance = runner_cls()
    config = instance._get_config()
    topic = config["input_topic"]
    from strider.messaging.registry import publish
    await publish(topic, {"action": "pause", "session_id": session_id}, key=session_id)


async def send_resume(runner_name: str, session_id: str) -> None:
    """Envia comando resume (o Runner pode tratar em run_session)."""
    runner_cls = get_runner(runner_name)
    if runner_cls is None:
        raise ValueError(f"Runner '{runner_name}' não encontrado.")
    instance = runner_cls()
    config = instance._get_config()
    topic = config["input_topic"]
    from strider.messaging.registry import publish
    await publish(topic, {"action": "resume", "session_id": session_id}, key=session_id)
