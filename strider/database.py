"""
Database connection management with read/write replica support.

Separates read queries to replica and write queries to primary.
"""

from __future__ import annotations

import logging
from typing import Any, Annotated, TYPE_CHECKING
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from fastapi import Depends

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# =============================================================================
# Global State
# =============================================================================

_write_engine: AsyncEngine | None = None
_read_engine: AsyncEngine | None = None
_write_session_factory: async_sessionmaker[AsyncSession] | None = None
_read_session_factory: async_sessionmaker[AsyncSession] | None = None


# =============================================================================
# DatabaseSession Container
# =============================================================================

class DatabaseSession:
    """
    Container holding read and write database sessions.

    Provides separate access for query optimization.
    """
    # db.read for SELECT, db.write for INSERT/UPDATE/DELETE

    __slots__ = ("_write", "_read", "_owns_sessions")

    def __init__(
        self,
        write: AsyncSession,
        read: AsyncSession | None = None,
        owns_sessions: bool = True,
    ) -> None:
        """
        Initialize with write and optional read session.

        Falls back to write session if read not provided.
        """
        self._write = write
        self._read = read if read is not None else write
        self._owns_sessions = owns_sessions

    @property
    def write(self) -> AsyncSession:
        """Return write session for mutations."""
        return self._write

    @property
    def read(self) -> AsyncSession:
        """Return read session for queries."""
        return self._read

    @property
    def primary(self) -> AsyncSession:
        """Alias for write session."""
        return self._write

    @property
    def replica(self) -> AsyncSession:
        """Alias for read session."""
        return self._read

    def is_using_replica(self) -> bool:
        """Check if separate replica is configured."""
        return self._read is not self._write

    async def commit(self) -> None:
        """Commit write session transaction."""
        await self._write.commit()

    async def rollback(self) -> None:
        """Rollback write session transaction."""
        await self._write.rollback()

    async def close(self) -> None:
        """Close sessions if owned by this container."""
        if self._owns_sessions:
            await self._write.close()
            if self._read is not self._write:
                await self._read.close()


# =============================================================================
# Initialization - Single entry point
# =============================================================================

async def init_db(
    settings: Any = None,
    database_url: str | None = None,
    *,
    echo: bool | None = None,
    pool_size: int | None = None,
    max_overflow: int | None = None,
    **kwargs: Any,
) -> None:
    """
    Single entry point for database initialization.

    Uses Settings (settings.py + .env) when settings not provided.
    - If has_read_replica: calls init_replicas (write + read engines).
    - Else: calls init_database (single engine from strider.models).

    After init_db(), use Depends(get_db) in route handlers for session.
    """
    from strider.citus import asyncpg_connect_args_from_settings, merge_asyncpg_connect_args
    from strider.config import get_settings

    s = settings or get_settings()
    url = database_url or s.database_url
    connect_args = merge_asyncpg_connect_args(
        kwargs.get("connect_args"),
        asyncpg_connect_args_from_settings(s),
    )
    engine_kwargs = dict(kwargs)
    if connect_args is not None:
        engine_kwargs["connect_args"] = connect_args

    if getattr(s, "has_read_replica", False):
        await init_replicas(
            write_url=url,
            read_url=getattr(s, "database_read_url", None),
            echo=echo if echo is not None else s.database_echo,
            pool_size=pool_size or s.database_pool_size,
            max_overflow=max_overflow or s.database_max_overflow,
            pool_recycle=getattr(s, "database_pool_recycle", None),
            **engine_kwargs,
        )
    else:
        from strider.models import init_database as _init_database

        await _init_database(
            database_url=url,
            echo=echo if echo is not None else getattr(s, "database_echo", False),
            pool_size=pool_size or getattr(s, "database_pool_size", 5),
            max_overflow=max_overflow or getattr(s, "database_max_overflow", 10),
            connect_args=connect_args,
        )
        if "sqlite" not in url.lower():
            from strider.models import _engine as single_engine

            if single_engine is not None:
                ok = await _ping_engine(single_engine, "database")
                if not ok:
                    raise RuntimeError(
                        "Database unreachable. Services will not start. "
                        "Check DATABASE_URL and that PostgreSQL is running."
                    )
                logger.info("Database connectivity check: OK")
                from strider.citus import run_citus_startup_checks

                probe = getattr(s, "database_citus_probe_on_startup", False)
                require = getattr(s, "database_citus_require", False)
                if probe or require:
                    await run_citus_startup_checks(
                        engine=single_engine,
                        database_url=url,
                        probe=probe,
                        require=require,
                    )


async def init_replicas(
    write_url: str | None = None,
    read_url: str | None = None,
    *,
    echo: bool | None = None,
    pool_size: int | None = None,
    max_overflow: int | None = None,
    pool_pre_ping: bool = True,
    pool_recycle: int | None = None,
    **kwargs: Any,
) -> None:
    """
    Initialize database engines for write and read.

    Uses settings values when parameters not provided.
    """
    # await init_replicas()  # Uses settings
    # await init_replicas(write_url="...", read_url="...")

    citus_probe = False
    citus_require = False
    try:
        from strider.citus import asyncpg_connect_args_from_settings, merge_asyncpg_connect_args
        from strider.config import get_settings

        settings = get_settings()

        write_url = write_url or settings.database_url
        read_url = read_url or settings.database_read_url
        echo = echo if echo is not None else settings.database_echo
        pool_size = pool_size or settings.database_pool_size
        max_overflow = max_overflow or settings.database_max_overflow
        pool_recycle = pool_recycle or settings.database_pool_recycle
        citus_probe = settings.database_citus_probe_on_startup
        citus_require = settings.database_citus_require
        merged_kwargs = dict(kwargs)
        ca = merge_asyncpg_connect_args(
            merged_kwargs.get("connect_args"),
            asyncpg_connect_args_from_settings(settings),
        )
        if ca:
            merged_kwargs["connect_args"] = ca
        kwargs = merged_kwargs
    except Exception:
        if write_url is None:
            raise ValueError("write_url is required when settings not available")
        echo = echo if echo is not None else False
        pool_size = pool_size or 5
        max_overflow = max_overflow or 10
        pool_recycle = pool_recycle or 3600

    global _write_engine, _read_engine, _write_session_factory, _read_session_factory

    is_sqlite = "sqlite" in write_url.lower()

    engine_kwargs = {
        "echo": echo,
        **kwargs,
    }

    if not is_sqlite:
        engine_kwargs.update({
            "pool_size": pool_size,
            "max_overflow": max_overflow,
            "pool_pre_ping": pool_pre_ping,
            "pool_recycle": pool_recycle,
        })

    _write_engine = create_async_engine(write_url, **engine_kwargs)
    _write_session_factory = async_sessionmaker(
        _write_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    if read_url and read_url != write_url:
        read_engine_kwargs = engine_kwargs.copy()

        if not is_sqlite:
            read_engine_kwargs["pool_size"] = pool_size * 2
            read_engine_kwargs["max_overflow"] = max_overflow * 2

        try:
            u = make_url(read_url)
            logger.debug(
                "Read replica engine: host=%s port=%s database=%s",
                u.host,
                u.port,
                u.database,
            )
        except Exception:
            logger.debug("Read replica engine: url configured (masked)")
        _read_engine = create_async_engine(read_url, **read_engine_kwargs)
        _read_session_factory = async_sessionmaker(
            _read_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    else:
        _read_engine = _write_engine
        _read_session_factory = _write_session_factory

    try:
        import strider.models as _cm
        if _cm._engine is None:
            _cm._engine = _write_engine
            _cm._session_factory = _write_session_factory
    except Exception:
        pass

    # Teste A/B: validar conectividade write e read antes de autorizar serviços
    await _check_replicas_connectivity(
        _write_engine,
        _read_engine if (read_url and read_url != write_url) else None,
        is_sqlite=is_sqlite,
    )

    if citus_probe or citus_require:
        from strider.citus import run_citus_startup_checks

        await run_citus_startup_checks(
            engine=_write_engine,
            database_url=write_url,
            probe=citus_probe,
            require=citus_require,
        )


async def _check_replicas_connectivity(
    write_engine: AsyncEngine,
    read_engine: AsyncEngine | None,
    *,
    is_sqlite: bool = False,
) -> None:
    """
    Testa conectividade do primary (write) e da réplica (read) antes de
    autorizar os serviços. Write obrigatório; read opcional (fallback para write
    se réplica inacessível).
    """
    # A: Primary (write) — obrigatório
    ok_write = await _ping_engine(write_engine, "write")
    if not ok_write:
        raise RuntimeError(
            "Database primary (write) unreachable. Services will not start. "
            "Check DATABASE_URL and that PostgreSQL is running."
        )
    logger.info("Database A/B check: write (primary) OK")

    # B: Réplica (read) — opcional; se falhar, usa write para leitura
    if read_engine is not None and read_engine is not write_engine:
        ok_read = await _ping_engine(read_engine, "read")
        if not ok_read:
            logger.warning(
                "Database A/B check: read replica unreachable. "
                "Using primary for reads until replica is available. "
                "Check DATABASE_READ_URL (e.g. in Docker use host reachable from container)."
            )
            global _read_engine, _read_session_factory
            _read_engine = write_engine
            _read_session_factory = _write_session_factory
        else:
            logger.info("Database A/B check: read (replica) OK")
    elif not is_sqlite:
        logger.debug("Database A/B check: no separate replica configured")


async def _ping_engine(engine: AsyncEngine, label: str) -> bool:
    """Executa SELECT 1 no engine. Retorna True se OK."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.debug("Database %s ping failed: %s", label, e)
        return False


async def close_replicas() -> None:
    """
    Dispose all database connections.

    Call during application shutdown.
    """
    # await close_replicas()
    global _write_engine, _read_engine, _write_session_factory, _read_session_factory

    if _write_engine is not None:
        await _write_engine.dispose()

    if _read_engine is not None and _read_engine is not _write_engine:
        await _read_engine.dispose()

    _write_engine = None
    _read_engine = None
    _write_session_factory = None
    _read_session_factory = None


def is_replica_configured() -> bool:
    """
    Check if separate read replica is active.

    Returns True when read_url differs from write_url.
    """
    return _read_engine is not None and _read_engine is not _write_engine


# =============================================================================
# Session Factories
# =============================================================================

async def get_write_session() -> AsyncSession:
    """
    Create new write session from primary.

    Raises RuntimeError if not initialized.
    """
    if _write_session_factory is None:
        raise RuntimeError(
            "Database not initialized. Call init_replicas() first."
        )
    return _write_session_factory()


async def get_read_session() -> AsyncSession:
    """
    Create new read session from replica.

    Falls back to primary if replica not configured.
    """
    if _read_session_factory is None:
        raise RuntimeError(
            "Database not initialized. Call init_replicas() first."
        )
    return _read_session_factory()


# =============================================================================
# FastAPI Dependencies
# =============================================================================

async def get_db_replicas() -> AsyncGenerator[DatabaseSession, None]:
    """
    Dependency providing DatabaseSession with read/write.

    Handles commit, rollback, and cleanup automatically.
    """
    # async def handler(db: DatabaseSession = Depends(get_db_replicas)): ...
    write_session = await get_write_session()

    if is_replica_configured():
        read_session = await get_read_session()
    else:
        read_session = write_session

    db = DatabaseSession(write=write_session, read=read_session)

    try:
        yield db
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()


async def get_write_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency providing write-only session.

    Use for endpoints that only perform mutations.
    """
    # async def handler(db: AsyncSession = Depends(get_write_db)): ...
    session = await get_write_session()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_read_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency providing read-only session.

    More efficient than get_db_replicas for query-only endpoints.
    """
    # async def handler(db: AsyncSession = Depends(get_read_db)): ...
    session = await get_read_session()
    try:
        yield session
    finally:
        await session.close()


# =============================================================================
# Type Aliases
# =============================================================================

DBSession = Annotated[DatabaseSession, Depends(get_db_replicas)]
WriteSession = Annotated[AsyncSession, Depends(get_write_db)]
ReadSession = Annotated[AsyncSession, Depends(get_read_db)]


# =============================================================================
# Manager Extension
# =============================================================================

class ReplicaManagerMixin:
    """
    Mixin adding for_read and for_write to Manager.

    Enables explicit session selection in queries.
    """
    # users = await User.objects.for_read(db).all()

    def for_read(self, db: DatabaseSession) -> "ReplicaManagerMixin":
        """Return manager using read session."""
        return self.using(db.read)

    def for_write(self, db: DatabaseSession) -> "ReplicaManagerMixin":
        """Return manager using write session."""
        return self.using(db.write)


# =============================================================================
# Health Check
# =============================================================================

async def check_database_health() -> dict[str, Any]:
    """
    Verify database connection health.

    Returns status dict for monitoring endpoints.
    """
    # return await check_database_health()
    result = {
        "write": {"status": "unknown"},
        "read": {"status": "unknown"},
        "replica_configured": is_replica_configured(),
    }

    try:
        async with await get_write_session() as session:
            await session.execute("SELECT 1")
            result["write"]["status"] = "healthy"
    except Exception as e:
        result["write"]["status"] = "unhealthy"
        result["write"]["error"] = str(e)

    try:
        async with await get_read_session() as session:
            await session.execute("SELECT 1")
            result["read"]["status"] = "healthy"
    except Exception as e:
        result["read"]["status"] = "unhealthy"
        result["read"]["error"] = str(e)

    return result


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "DatabaseSession",
    "init_db",
    "init_replicas",
    "close_replicas",
    "is_replica_configured",
    "get_write_session",
    "get_read_session",
    "get_db_replicas",
    "get_write_db",
    "get_read_db",
    "DBSession",
    "WriteSession",
    "ReadSession",
    "ReplicaManagerMixin",
    "check_database_health",
]
