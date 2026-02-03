"""
Testing utilities for core-framework applications.

This module provides a complete testing toolkit for applications built
with core-framework, including:

- TestClient: HTTP client with automatic test database setup
- AuthenticatedClient: Pre-authenticated HTTP client
- TestDatabase: Database utilities for testing
- MockKafka, MockRedis, MockHTTP: Mock services
- Factory: Data factory pattern for test data generation

Usage:
    # In your conftest.py
    import pytest
    from your_app import app as _app
    
    @pytest.fixture(scope="session")
    def app():
        return _app.app
    
    # In your tests
    class TestUsers:
        async def test_register(self, client):
            response = await client.post("/auth/register", json={...})
            assert response.status_code == 201
        
        async def test_profile(self, auth_client):
            response = await auth_client.get("/auth/me")
            assert response.status_code == 200

Quick Start:
    1. Install test dependencies: pip install core-framework[testing]
    2. Add to pyproject.toml:
       [tool.pytest.ini_options]
       asyncio_mode = "auto"
       plugins = ["core.testing.plugin"]
    3. Create conftest.py with your app fixture
    4. Write tests using provided fixtures
"""

from core.testing.client import (
    TestClient,
    AuthenticatedClient,
    create_test_client,
    create_auth_client,
)
from core.testing.database import (
    TestDatabase,
    setup_test_db,
    teardown_test_db,
    get_test_session,
)
from core.testing.mocks import (
    MockKafka,
    MockRedis,
    MockHTTP,
    MockMessage,
    MockHTTPResponse,
)
from core.testing.factories import (
    Factory,
    UserFactory,
    fake,
)
from core.testing.assertions import (
    assert_status,
    assert_json_contains,
    assert_error_code,
    assert_validation_error,
)

__all__ = [
    # Client
    "TestClient",
    "AuthenticatedClient",
    "create_test_client",
    "create_auth_client",
    # Database
    "TestDatabase",
    "setup_test_db",
    "teardown_test_db",
    "get_test_session",
    # Mocks
    "MockKafka",
    "MockRedis",
    "MockHTTP",
    "MockMessage",
    "MockHTTPResponse",
    # Factories
    "Factory",
    "UserFactory",
    "fake",
    # Assertions
    "assert_status",
    "assert_json_contains",
    "assert_error_code",
    "assert_validation_error",
]
