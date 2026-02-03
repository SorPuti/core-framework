"""
Test database utilities.

Provides functions for setting up and tearing down test databases,
with support for both SQLite (in-memory) and PostgreSQL.

Usage:
    # Setup
    engine = await setup_test_db("sqlite+aiosqlite:///:memory:")
    
    # Get session
    async with get_test_session() as session:
        user = User(email="test@example.com")
        session.add(user)
        await session.commit()
    
    # Cleanup
    await teardown_test_db()
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from contextlib import asynccontextmanager

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
    from collections.abc import AsyncGenerator

logger = logging.getLogger("core.testing")

# Global test database state
_test_engine: "AsyncEngine | None" = None
_test_session_factory: Any = None


class TestDatabase:
    """
    Test database manager.
    
    Manages test database lifecycle including setup, session management,
    and cleanup. Supports both SQLite and PostgreSQL.
    
    Example:
        db = TestDatabase("sqlite+aiosqlite:///:memory:")
        await db.setup()
        
        async with db.session() as session:
            # Use session
            pass
        
        await db.teardown()
    
    Args:
        database_url: Database URL
        echo: Whether to log SQL statements
        create_tables: Whether to create tables on setup
    """
    
    def __init__(
        self,
        database_url: str = "sqlite+aiosqlite:///:memory:",
        echo: bool = False,
        create_tables: bool = True,
    ) -> None:
        self.database_url = database_url
        self.echo = echo
        self.create_tables = create_tables
        self._engine: "AsyncEngine | None" = None
        self._session_factory: Any = None
    
    async def setup(self) -> "AsyncEngine":
        """
        Initialize test database.
        
        Creates engine, session factory, and optionally creates all tables.
        
        Returns:
            The database engine
        """
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
        
        # Create engine with test-specific settings
        self._engine = create_async_engine(
            self.database_url,
            echo=self.echo,
            # SQLite-specific settings
            connect_args={"check_same_thread": False} if "sqlite" in self.database_url else {},
        )
        
        # Create session factory
        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        
        # Create tables if requested
        if self.create_tables:
            await self._create_tables()
        
        logger.debug(f"Test database initialized: {self.database_url}")
        return self._engine
    
    async def teardown(self) -> None:
        """
        Cleanup test database.
        
        Drops all tables and disposes of the engine.
        """
        if self._engine:
            # Drop tables
            await self._drop_tables()
            
            # Dispose engine
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
        
        logger.debug("Test database cleaned up")
    
    async def _create_tables(self) -> None:
        """Create all tables from registered models."""
        try:
            from core.models import Model
            metadata = Model.metadata
        except ImportError:
            logger.warning("Could not import Model, tables not created")
            return
        
        async with self._engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
        
        logger.debug("Test database tables created")
    
    async def _drop_tables(self) -> None:
        """Drop all tables."""
        try:
            from core.models import Model
            metadata = Model.metadata
        except ImportError:
            return
        
        async with self._engine.begin() as conn:
            await conn.run_sync(metadata.drop_all)
    
    @asynccontextmanager
    async def session(self) -> "AsyncGenerator[AsyncSession, None]":
        """
        Get a database session.
        
        Session is automatically committed on success and rolled back on error.
        
        Yields:
            Database session
        """
        if not self._session_factory:
            raise RuntimeError("Database not initialized. Call setup() first.")
        
        session = self._session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
    
    async def truncate_all(self) -> None:
        """
        Truncate all tables (faster than drop/create for resetting between tests).
        """
        try:
            from core.models import Model
            metadata = Model.metadata
        except ImportError:
            return
        
        async with self._engine.begin() as conn:
            for table in reversed(metadata.sorted_tables):
                await conn.execute(table.delete())
        
        logger.debug("Test database tables truncated")
    
    async def __aenter__(self) -> "TestDatabase":
        """Setup on context enter."""
        await self.setup()
        return self
    
    async def __aexit__(self, *args) -> None:
        """Teardown on context exit."""
        await self.teardown()


# =============================================================================
# Module-level functions for simpler usage
# =============================================================================

async def setup_test_db(
    database_url: str = "sqlite+aiosqlite:///:memory:",
    create_tables: bool = True,
    echo: bool = False,
) -> "AsyncEngine":
    """
    Setup test database.
    
    Initializes the global test database state.
    
    Args:
        database_url: Database URL
        create_tables: Whether to create tables
        echo: Whether to log SQL
    
    Returns:
        Database engine
        
    Example:
        engine = await setup_test_db()
        # ... run tests ...
        await teardown_test_db()
    """
    global _test_engine, _test_session_factory
    
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    
    _test_engine = create_async_engine(
        database_url,
        echo=echo,
        connect_args={"check_same_thread": False} if "sqlite" in database_url else {},
    )
    
    _test_session_factory = async_sessionmaker(
        _test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    if create_tables:
        try:
            from core.models import Model
            async with _test_engine.begin() as conn:
                await conn.run_sync(Model.metadata.create_all)
        except ImportError:
            pass
    
    # Also register with core.database for dependencies
    try:
        from core import database
        database._write_session_factory = _test_session_factory
        database._read_session_factory = _test_session_factory
    except (ImportError, AttributeError):
        pass
    
    logger.debug(f"Test database setup: {database_url}")
    return _test_engine


async def teardown_test_db() -> None:
    """
    Teardown test database.
    
    Cleans up the global test database state.
    """
    global _test_engine, _test_session_factory
    
    if _test_engine:
        # Drop tables
        try:
            from core.models import Model
            async with _test_engine.begin() as conn:
                await conn.run_sync(Model.metadata.drop_all)
        except ImportError:
            pass
        
        await _test_engine.dispose()
        _test_engine = None
        _test_session_factory = None
    
    logger.debug("Test database teardown complete")


@asynccontextmanager
async def get_test_session() -> "AsyncGenerator[AsyncSession, None]":
    """
    Get a test database session.
    
    Yields:
        Database session
        
    Example:
        async with get_test_session() as session:
            user = await User.objects.using(session).get(id=1)
    """
    if not _test_session_factory:
        raise RuntimeError("Test database not initialized. Call setup_test_db() first.")
    
    session = _test_session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
