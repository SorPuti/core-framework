"""
HTTP test clients with automatic app setup.

Provides TestClient and AuthenticatedClient for testing core-framework
applications with minimal boilerplate.

Usage:
    # Basic client
    async with TestClient(app) as client:
        response = await client.get("/health")
        assert response.status_code == 200
    
    # Authenticated client
    async with AuthenticatedClient(app) as client:
        response = await client.get("/auth/me")
        assert response.status_code == 200
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from contextlib import asynccontextmanager

if TYPE_CHECKING:
    from httpx import AsyncClient
    from collections.abc import AsyncGenerator

logger = logging.getLogger("core.testing")


class TestClient:
    """
    Test client that auto-initializes the test environment.
    
    Features:
    - Automatic database setup with in-memory SQLite
    - Automatic table creation
    - Proper cleanup on exit
    - Full async support
    
    Example:
        async with TestClient(app) as client:
            response = await client.post(
                "/api/v1/users",
                json={"email": "test@example.com"}
            )
            assert response.status_code == 201
    
    Args:
        app: FastAPI/Starlette application instance
        database_url: Database URL for tests (default: in-memory SQLite)
        base_url: Base URL for requests (default: "http://test")
        auto_create_tables: Whether to create tables automatically
    """
    
    def __init__(
        self,
        app: Any,
        database_url: str = "sqlite+aiosqlite:///:memory:",
        base_url: str = "http://test",
        auto_create_tables: bool = True,
    ) -> None:
        self.app = app
        self.database_url = database_url
        self.base_url = base_url
        self.auto_create_tables = auto_create_tables
        self._client: "AsyncClient | None" = None
        self._engine: Any = None
    
    async def __aenter__(self) -> "AsyncClient":
        """Setup test environment and return HTTP client."""
        from httpx import ASGITransport, AsyncClient
        
        # Setup database
        await self._setup_database()
        
        # Create HTTP client
        self._client = AsyncClient(
            transport=ASGITransport(app=self.app),
            base_url=self.base_url,
            follow_redirects=True,
        )
        
        logger.debug(f"TestClient initialized with database: {self.database_url}")
        return self._client
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Cleanup test environment."""
        if self._client:
            await self._client.aclose()
            self._client = None
        
        await self._teardown_database()
        logger.debug("TestClient cleaned up")
    
    async def _setup_database(self) -> None:
        """Initialize test database."""
        from core.testing.database import setup_test_db
        self._engine = await setup_test_db(
            self.database_url,
            create_tables=self.auto_create_tables,
        )
    
    async def _teardown_database(self) -> None:
        """Cleanup test database."""
        from core.testing.database import teardown_test_db
        await teardown_test_db()
        self._engine = None


class AuthenticatedClient(TestClient):
    """
    Test client with automatic user registration and authentication.
    
    Creates a test user on setup and includes the authentication token
    in all subsequent requests.
    
    Example:
        async with AuthenticatedClient(app) as client:
            # Already authenticated!
            response = await client.get("/api/v1/auth/me")
            assert response.status_code == 200
            assert response.json()["email"] == "test@example.com"
    
    Args:
        app: FastAPI/Starlette application instance
        email: Email for test user (default: "test@example.com")
        password: Password for test user (default: "TestPass123!")
        register_url: URL for registration endpoint
        login_url: URL for login endpoint
        extra_register_data: Additional data for registration
        **kwargs: Additional arguments for TestClient
    """
    
    def __init__(
        self,
        app: Any,
        email: str = "test@example.com",
        password: str = "TestPass123!",
        register_url: str = "/api/v1/auth/register",
        login_url: str = "/api/v1/auth/login",
        extra_register_data: dict[str, Any] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(app, **kwargs)
        self.email = email
        self.password = password
        self.register_url = register_url
        self.login_url = login_url
        self.extra_register_data = extra_register_data or {}
        self._user_data: dict[str, Any] | None = None
        self._token: str | None = None
    
    @property
    def user(self) -> dict[str, Any] | None:
        """Get authenticated user data."""
        return self._user_data
    
    @property
    def token(self) -> str | None:
        """Get authentication token."""
        return self._token
    
    async def __aenter__(self) -> "AsyncClient":
        """Setup, register user, and authenticate."""
        client = await super().__aenter__()
        
        # Register user
        register_data = {
            "email": self.email,
            "password": self.password,
            **self.extra_register_data,
        }
        
        register_response = await client.post(
            self.register_url,
            json=register_data,
        )
        
        if register_response.status_code not in (200, 201):
            # User might already exist, try login directly
            logger.debug(f"Registration returned {register_response.status_code}, trying login")
        
        # Login
        login_response = await client.post(
            self.login_url,
            json={"email": self.email, "password": self.password},
        )
        
        if login_response.status_code != 200:
            raise RuntimeError(
                f"Failed to authenticate test user: {login_response.status_code} "
                f"{login_response.text}"
            )
        
        # Extract token
        login_data = login_response.json()
        self._token = login_data.get("access_token") or login_data.get("token")
        self._user_data = login_data.get("user", {"email": self.email})
        
        if not self._token:
            raise RuntimeError(f"No token in login response: {login_data}")
        
        # Set authorization header
        client.headers["Authorization"] = f"Bearer {self._token}"
        
        logger.debug(f"AuthenticatedClient ready with user: {self.email}")
        return client


@asynccontextmanager
async def create_test_client(
    app: Any,
    **kwargs,
) -> "AsyncGenerator[AsyncClient, None]":
    """
    Context manager to create a test client.
    
    Convenience function for creating TestClient.
    
    Example:
        async with create_test_client(app) as client:
            response = await client.get("/health")
    """
    async with TestClient(app, **kwargs) as client:
        yield client


@asynccontextmanager
async def create_auth_client(
    app: Any,
    email: str = "test@example.com",
    password: str = "TestPass123!",
    **kwargs,
) -> "AsyncGenerator[AsyncClient, None]":
    """
    Context manager to create an authenticated test client.
    
    Convenience function for creating AuthenticatedClient.
    
    Example:
        async with create_auth_client(app) as client:
            response = await client.get("/auth/me")
    """
    async with AuthenticatedClient(app, email=email, password=password, **kwargs) as client:
        yield client
