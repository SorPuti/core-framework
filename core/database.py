"""
Database connection management with read/write replica support.

Separates read queries to replica and write queries to primary.
"""

from __future__ import annotations

from typing import Any, Annotated, TYPE_CHECKING
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from fastapi import Depends

if TYPE_CHECKING:
    pass


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
# Initialization
# =============================================================================

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

    try:
        from core.config import get_settings
        settings = get_settings()

        write_url = write_url or settings.database_url
        read_url = read_url or settings.database_read_url
        echo = echo if echo is not None else settings.database_echo
        pool_size = pool_size or settings.database_pool_size
        max_overflow = max_overflow or settings.database_max_overflow
        pool_recycle = pool_recycle or settings.database_pool_recycle
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
        import core.models as _cm
        if _cm._engine is None:
            _cm._engine = _write_engine
            _cm._session_factory = _write_session_factory
    except Exception:
        pass


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
