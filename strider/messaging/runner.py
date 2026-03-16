"""
Runner: base para sessões longas com limites de recursos e lifecycle hooks.

Consome comandos start/stop via Kafka e executa run_session() até parada
ou exceder limites de CPU/memória/IO. Integrado ao plug-and-play Kafka.
"""

from __future__ import annotations

import asyncio
import logging
import signal
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


class Runner(ABC):
    """
    Base para sessões longas com limites de recursos e lifecycle hooks.

    Consome comandos start/stop (Kafka) e executa run_session() até
    parada ou limite de CPU/memória/IO. Uma sessão por instância por vez
    (concurrency=1). Subclasse e implemente run_session(); opcionalmente
    on_start, on_stop, after_stop, on_resource_exceeded.
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
        self._current_session_id: str | None = None
        self._session_task: asyncio.Task | None = None
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

    async def _handle_message(self, message: dict[str, Any], config: dict[str, Any]) -> None:
        action = (message.get("action") or "").strip().lower()
        session_id = message.get("session_id")
        if isinstance(session_id, str):
            session_id = session_id.strip() or None
        elif session_id is not None:
            session_id = str(session_id).strip() or None

        if action == "start":
            if self._session_task is not None and not self._session_task.done():
                logger.warning("Runner already has active session, ignoring start session_id=%s", session_id)
                return
            self._stop_requested = False
            self._current_session_id = session_id
            self._session_task = asyncio.create_task(self.run_session(message))
            self._session_task.add_done_callback(self._on_session_done)
            return

        if action == "stop":
            if session_id is None or session_id == self._current_session_id:
                self.request_stop()
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

        try:
            while self._running and not self._stop_requested:
                await asyncio.sleep(1)
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
