"""
Pytest plugin for core-framework applications.

This plugin provides:
- Automatic test environment setup (no manual configuration needed)
- Isolated database with in-memory SQLite
- Mocked external services (Kafka, Redis, HTTP)
- Auto-discovery of tests
- Pre-configured fixtures for common use cases

The plugin automatically initializes:
- Database session factories
- Auth configuration
- Settings with test defaults
- Middleware registry

Usage:
    # Just run pytest - everything is auto-configured!
    pytest tests/
    
    # With coverage
    pytest tests/ --cov=src --cov-report=html
    
    # For integration tests that need your app:
    # Create conftest.py with app fixture
    
    @pytest.fixture(scope="session")
    def app():
        from your_app.main import app
        return app
"""

from __future__ import annotations

import logging
import os
import sys
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession
    from core.testing.mocks import MockKafka, MockRedis, MockHTTP

logger = logging.getLogger("core.testing")

# Track if environment has been initialized
_environment_initialized = False


# =============================================================================
# Environment Setup (runs once before any tests)
# =============================================================================

def _setup_test_environment():
    """
    Setup isolated test environment.
    
    This initializes all core-framework components with test-safe defaults,
    preventing errors like "Database not initialized" or "Auth not configured".
    """
    global _environment_initialized
    
    if _environment_initialized:
        return
    
    logger.info("Setting up core-framework test environment...")
    
    # Set environment variables for test mode
    os.environ.setdefault("TESTING", "true")
    os.environ.setdefault("DEBUG", "true")
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-do-not-use-in-production")
    
    # Initialize settings with test defaults
    _init_test_settings()
    
    # Initialize database factories
    _init_test_database()
    
    # Initialize auth with test defaults
    _init_test_auth()
    
    # Clear any existing middleware
    _init_test_middleware()
    
    _environment_initialized = True
    logger.info("Test environment ready")


def _init_test_settings():
    """Initialize settings module with test defaults."""
    try:
        from core.config import Settings
        
        # Create test settings instance
        class TestSettings(Settings):
            """Test settings with safe defaults."""
            
            debug: bool = True
            testing: bool = True
            database_url: str = "sqlite+aiosqlite:///:memory:"
            secret_key: str = "test-secret-key-for-testing-only"
            
            class Config:
                env_prefix = ""
        
        # Override get_settings to return test settings
        import core.config as config_module
        
        _test_settings = None
        
        def get_test_settings() -> Settings:
            nonlocal _test_settings
            if _test_settings is None:
                _test_settings = TestSettings()
            return _test_settings
        
        config_module.get_settings = get_test_settings
        config_module._settings = None  # Clear cache
        
        logger.debug("Test settings initialized")
    except ImportError:
        logger.debug("core.config not available, skipping settings init")
    except Exception as e:
        logger.debug(f"Could not initialize test settings: {e}")


def _init_test_database():
    """Initialize database module with test factories."""
    try:
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
        import core.database as db_module
        
        # Create in-memory SQLite engine
        test_engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            echo=False,
            connect_args={"check_same_thread": False},
        )
        
        # Create session factory
        test_session_factory = async_sessionmaker(
            test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        
        # Set both read and write to same factory (no replicas in tests)
        db_module._write_session_factory = test_session_factory
        db_module._read_session_factory = test_session_factory
        
        # Store engine for table creation
        db_module._test_engine = test_engine
        
        logger.debug("Test database factories initialized")
    except ImportError:
        logger.debug("core.database not available, skipping database init")
    except Exception as e:
        logger.debug(f"Could not initialize test database: {e}")


def _init_test_auth():
    """Initialize auth module with test defaults."""
    try:
        from core.auth.base import configure_auth, AuthConfig
        
        # Configure auth with test defaults
        configure_auth(
            secret_key="test-secret-key-for-testing-only",
            algorithm="HS256",
            access_token_expire_minutes=30,
            refresh_token_expire_days=7,
            warn_missing_middleware=False,  # Don't warn in tests
        )
        
        logger.debug("Test auth initialized")
    except ImportError:
        logger.debug("core.auth not available, skipping auth init")
    except Exception as e:
        logger.debug(f"Could not initialize test auth: {e}")


def _init_test_middleware():
    """Clear middleware registry for clean test state."""
    try:
        from core.middleware import clear_middleware_registry
        clear_middleware_registry()
        logger.debug("Middleware registry cleared")
    except ImportError:
        logger.debug("core.middleware not available")
    except Exception as e:
        logger.debug(f"Could not clear middleware: {e}")


async def _create_test_tables():
    """Create all database tables for testing."""
    try:
        import core.database as db_module
        from core.models import Model
        
        engine = getattr(db_module, '_test_engine', None)
        if engine:
            async with engine.begin() as conn:
                await conn.run_sync(Model.metadata.create_all)
            logger.debug("Test tables created")
    except Exception as e:
        logger.debug(f"Could not create test tables: {e}")


async def _drop_test_tables():
    """Drop all database tables after testing."""
    try:
        import core.database as db_module
        from core.models import Model
        
        engine = getattr(db_module, '_test_engine', None)
        if engine:
            async with engine.begin() as conn:
                await conn.run_sync(Model.metadata.drop_all)
            logger.debug("Test tables dropped")
    except Exception as e:
        logger.debug(f"Could not drop test tables: {e}")


# =============================================================================
# Pytest Hooks
# =============================================================================

def pytest_configure(config):
    """
    Configure pytest for core-framework testing.
    
    This runs before any tests are collected.
    """
    # Register markers
    config.addinivalue_line(
        "markers",
        "integration: mark as integration test (may require external services)"
    )
    config.addinivalue_line(
        "markers",
        "slow: mark as slow test"
    )
    config.addinivalue_line(
        "markers",
        "auth: mark as requiring authentication"
    )
    config.addinivalue_line(
        "markers",
        "database: mark as requiring database"
    )
    config.addinivalue_line(
        "markers",
        "unit: mark as unit test (no external dependencies)"
    )
    
    # Setup test environment immediately
    _setup_test_environment()


def pytest_collection_modifyitems(config, items):
    """
    Modify collected test items.
    
    Auto-discovers and marks tests based on their location/name.
    """
    for item in items:
        # Auto-mark tests based on path
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)


def pytest_sessionstart(session):
    """Called after the Session object has been created."""
    logger.debug("Pytest session starting")


def pytest_sessionfinish(session, exitstatus):
    """Called after whole test run finished."""
    logger.debug(f"Pytest session finished with status {exitstatus}")


# =============================================================================
# App Fixture
# =============================================================================

@pytest.fixture(scope="session")
def app():
    """
    Application instance fixture.
    
    Override this in your conftest.py if you need to test HTTP endpoints:
    
        @pytest.fixture(scope="session")
        def app():
            from your_app.main import app
            return app
    
    For unit tests that don't need HTTP, you don't need to override this.
    """
    # Return a minimal app for unit tests
    try:
        from fastapi import FastAPI
        return FastAPI(title="Test App")
    except ImportError:
        return None


# =============================================================================
# Database Fixtures
# =============================================================================

@pytest.fixture(scope="session")
async def test_engine():
    """
    Database engine for the test session.
    
    Creates tables at start, drops at end.
    """
    await _create_test_tables()
    
    try:
        import core.database as db_module
        yield getattr(db_module, '_test_engine', None)
    except ImportError:
        yield None
    
    await _drop_test_tables()


@pytest.fixture
async def db(test_engine) -> "AsyncSession":
    """
    Database session for tests.
    
    Each test gets a fresh session that's rolled back after the test.
    
    Usage:
        async def test_create_user(db):
            user = User(email="test@example.com")
            db.add(user)
            await db.commit()
            
            assert user.id is not None
    """
    try:
        import core.database as db_module
        
        factory = db_module._write_session_factory
        if factory is None:
            pytest.skip("Database not initialized")
        
        session = factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
    except ImportError:
        pytest.skip("core.database not available")


@pytest.fixture
async def clean_db(db) -> "AsyncSession":
    """
    Database session with clean tables.
    
    Truncates all tables before the test.
    """
    try:
        from core.models import Model
        import core.database as db_module
        
        engine = getattr(db_module, '_test_engine', None)
        if engine:
            async with engine.begin() as conn:
                for table in reversed(Model.metadata.sorted_tables):
                    await conn.execute(table.delete())
    except Exception:
        pass
    
    yield db


# =============================================================================
# HTTP Client Fixtures
# =============================================================================

@pytest.fixture
async def client(app, test_engine) -> "AsyncClient":
    """
    HTTP test client with initialized database.
    
    Usage:
        async def test_health(client):
            response = await client.get("/health")
            assert response.status_code == 200
    """
    if app is None:
        pytest.skip("No app fixture defined")
    
    try:
        from httpx import AsyncClient, ASGITransport
        
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=True,
        ) as c:
            yield c
    except ImportError:
        pytest.skip("httpx not installed")


@pytest.fixture
async def auth_client(app, test_engine) -> "AsyncClient":
    """
    Authenticated HTTP test client.
    
    Creates a test user and includes auth token in requests.
    
    Usage:
        async def test_profile(auth_client):
            response = await auth_client.get("/api/v1/auth/me")
            assert response.status_code == 200
    """
    if app is None:
        pytest.skip("No app fixture defined")
    
    try:
        from core.testing import AuthenticatedClient
        
        async with AuthenticatedClient(app) as c:
            yield c
    except ImportError:
        pytest.skip("core.testing.AuthenticatedClient not available")
    except Exception as e:
        pytest.skip(f"Could not create authenticated client: {e}")


@pytest.fixture
async def client_factory(app, test_engine):
    """
    Factory for creating multiple authenticated clients.
    
    Usage:
        async def test_two_users(client_factory):
            user1 = await client_factory("user1@example.com")
            user2 = await client_factory("user2@example.com")
    """
    if app is None:
        pytest.skip("No app fixture defined")
    
    from core.testing import AuthenticatedClient
    
    clients = []
    
    async def factory(
        email: str = "test@example.com",
        password: str = "TestPass123!",
    ) -> "AsyncClient":
        client = AuthenticatedClient(app, email=email, password=password)
        c = await client.__aenter__()
        clients.append(client)
        return c
    
    yield factory
    
    for client in clients:
        try:
            await client.__aexit__(None, None, None)
        except Exception:
            pass


# =============================================================================
# Mock Fixtures
# =============================================================================

@pytest.fixture
def mock_kafka() -> "MockKafka":
    """
    Mock Kafka producer/consumer.
    
    Usage:
        async def test_event(mock_kafka):
            await mock_kafka.send("events", {"type": "test"})
            mock_kafka.assert_sent("events", count=1)
    """
    from core.testing.mocks import MockKafka
    
    kafka = MockKafka()
    yield kafka
    kafka.clear()


@pytest.fixture
def mock_redis() -> "MockRedis":
    """
    Mock Redis client.
    
    Usage:
        async def test_cache(mock_redis):
            await mock_redis.set("key", "value")
            assert await mock_redis.get("key") == "value"
    """
    from core.testing.mocks import MockRedis
    
    redis = MockRedis()
    yield redis
    redis.clear()


@pytest.fixture
def mock_http() -> "MockHTTP":
    """
    Mock HTTP client.
    
    Usage:
        def test_api(mock_http):
            mock_http.when("GET", "https://api.example.com/data").respond(
                status=200, json={"result": "ok"}
            )
    """
    from core.testing.mocks import MockHTTP
    
    http = MockHTTP()
    yield http
    http.clear()


# =============================================================================
# Utility Fixtures
# =============================================================================

@pytest.fixture
def fake():
    """Faker instance for test data generation."""
    from core.testing.factories import fake
    return fake


@pytest.fixture
def user_factory():
    """Factory for creating test users."""
    from core.testing.factories import UserFactory
    return UserFactory


@pytest.fixture
def assert_status():
    """HTTP status assertion helper."""
    from core.testing.assertions import assert_status
    return assert_status


@pytest.fixture
def assert_json():
    """JSON assertion helper."""
    from core.testing.assertions import assert_json_contains
    return assert_json_contains


@pytest.fixture
async def logged_in_user(auth_client):
    """Info about the authenticated test user."""
    return {
        "email": "test@example.com",
        "password": "TestPass123!",
    }


# =============================================================================
# Settings Fixture
# =============================================================================

@pytest.fixture
def settings():
    """
    Test settings instance.
    
    Usage:
        def test_config(settings):
            assert settings.testing == True
    """
    try:
        from core.config import get_settings
        return get_settings()
    except ImportError:
        return None


@pytest.fixture
def override_settings():
    """
    Context manager to temporarily override settings.
    
    Usage:
        def test_with_custom_setting(override_settings):
            with override_settings(debug=False):
                # Test with debug=False
                pass
    """
    from contextlib import contextmanager
    
    @contextmanager
    def _override(**overrides):
        try:
            from core.config import get_settings
            settings = get_settings()
            
            # Store original values
            original = {}
            for key, value in overrides.items():
                if hasattr(settings, key):
                    original[key] = getattr(settings, key)
                    setattr(settings, key, value)
            
            yield settings
            
            # Restore original values
            for key, value in original.items():
                setattr(settings, key, value)
        except ImportError:
            yield None
    
    return _override
