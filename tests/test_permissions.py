"""
Tests for permissions system.

These tests validate permission classes work correctly with
both Starlette and legacy user patterns.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock


def create_mock_request(user=None, is_authenticated=False, method="GET"):
    """Create a mock request with optional user."""
    request = MagicMock()
    request.method = method
    
    # Starlette pattern
    if user and is_authenticated:
        request.user = MagicMock()
        request.user.is_authenticated = True
        request.user._user = user
    else:
        request.user = MagicMock()
        request.user.is_authenticated = False
    
    # Legacy pattern
    request.state = MagicMock()
    request.state.user = user
    
    return request


class TestAllowAny:
    """Test AllowAny permission."""
    
    @pytest.mark.asyncio
    async def test_allows_anonymous(self):
        """Test allows anonymous users."""
        from core.permissions import AllowAny
        
        perm = AllowAny()
        request = create_mock_request()
        
        result = await perm.has_permission(request)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_allows_authenticated(self):
        """Test allows authenticated users."""
        from core.permissions import AllowAny
        
        perm = AllowAny()
        user = MagicMock()
        request = create_mock_request(user=user, is_authenticated=True)
        
        result = await perm.has_permission(request)
        assert result is True


class TestDenyAll:
    """Test DenyAll permission."""
    
    @pytest.mark.asyncio
    async def test_denies_anonymous(self):
        """Test denies anonymous users."""
        from core.permissions import DenyAll
        
        perm = DenyAll()
        request = create_mock_request()
        
        result = await perm.has_permission(request)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_denies_authenticated(self):
        """Test denies authenticated users."""
        from core.permissions import DenyAll
        
        perm = DenyAll()
        user = MagicMock()
        request = create_mock_request(user=user, is_authenticated=True)
        
        result = await perm.has_permission(request)
        assert result is False


class TestIsAuthenticated:
    """Test IsAuthenticated permission."""
    
    @pytest.mark.asyncio
    async def test_denies_anonymous(self):
        """Test denies anonymous users."""
        from core.permissions import IsAuthenticated
        
        perm = IsAuthenticated()
        request = create_mock_request()
        
        result = await perm.has_permission(request)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_allows_authenticated_starlette(self):
        """Test allows Starlette authenticated users."""
        from core.permissions import IsAuthenticated
        
        perm = IsAuthenticated()
        user = MagicMock()
        request = create_mock_request(user=user, is_authenticated=True)
        
        result = await perm.has_permission(request)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_allows_authenticated_legacy(self):
        """Test allows legacy authenticated users."""
        from core.permissions import IsAuthenticated
        
        perm = IsAuthenticated()
        user = MagicMock()
        
        # Only set legacy pattern
        request = MagicMock()
        request.user = MagicMock()
        request.user.is_authenticated = False
        request.state = MagicMock()
        request.state.user = user
        
        result = await perm.has_permission(request)
        assert result is True


class TestIsAuthenticatedOrReadOnly:
    """Test IsAuthenticatedOrReadOnly permission."""
    
    @pytest.mark.asyncio
    async def test_allows_anonymous_read(self):
        """Test allows anonymous users for GET requests."""
        from core.permissions import IsAuthenticatedOrReadOnly
        
        perm = IsAuthenticatedOrReadOnly()
        request = create_mock_request(method="GET")
        
        result = await perm.has_permission(request)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_denies_anonymous_write(self):
        """Test denies anonymous users for POST requests."""
        from core.permissions import IsAuthenticatedOrReadOnly
        
        perm = IsAuthenticatedOrReadOnly()
        request = create_mock_request(method="POST")
        
        result = await perm.has_permission(request)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_allows_authenticated_write(self):
        """Test allows authenticated users for POST requests."""
        from core.permissions import IsAuthenticatedOrReadOnly
        
        perm = IsAuthenticatedOrReadOnly()
        user = MagicMock()
        request = create_mock_request(user=user, is_authenticated=True, method="POST")
        
        result = await perm.has_permission(request)
        assert result is True


class TestIsAdmin:
    """Test IsAdmin permission."""
    
    @pytest.mark.asyncio
    async def test_denies_anonymous(self):
        """Test denies anonymous users."""
        from core.permissions import IsAdmin
        
        perm = IsAdmin()
        request = create_mock_request()
        
        result = await perm.has_permission(request)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_denies_non_admin(self):
        """Test denies non-admin users."""
        from core.permissions import IsAdmin
        
        perm = IsAdmin()
        user = MagicMock()
        user.is_admin = False
        user.is_superuser = False
        request = create_mock_request(user=user, is_authenticated=True)
        
        result = await perm.has_permission(request)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_allows_admin(self):
        """Test allows admin users."""
        from core.permissions import IsAdmin
        
        perm = IsAdmin()
        user = MagicMock()
        user.is_admin = True
        request = create_mock_request(user=user, is_authenticated=True)
        
        result = await perm.has_permission(request)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_allows_superuser(self):
        """Test allows superuser."""
        from core.permissions import IsAdmin
        
        perm = IsAdmin()
        user = MagicMock()
        user.is_admin = False
        user.is_superuser = True
        request = create_mock_request(user=user, is_authenticated=True)
        
        result = await perm.has_permission(request)
        assert result is True


class TestIsOwner:
    """Test IsOwner permission."""
    
    @pytest.mark.asyncio
    async def test_general_permission_always_true(self):
        """Test has_permission always returns True."""
        from core.permissions import IsOwner
        
        perm = IsOwner()
        request = create_mock_request()
        
        result = await perm.has_permission(request)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_allows_owner(self):
        """Test allows object owner."""
        from core.permissions import IsOwner
        
        perm = IsOwner()
        user = MagicMock()
        user.id = 123
        
        obj = MagicMock()
        obj.user_id = 123
        
        request = create_mock_request(user=user, is_authenticated=True)
        
        result = await perm.has_object_permission(request, obj=obj)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_denies_non_owner(self):
        """Test denies non-owner."""
        from core.permissions import IsOwner
        
        perm = IsOwner()
        user = MagicMock()
        user.id = 123
        
        obj = MagicMock()
        obj.user_id = 456  # Different user
        
        request = create_mock_request(user=user, is_authenticated=True)
        
        result = await perm.has_object_permission(request, obj=obj)
        assert result is False


class TestHasRole:
    """Test HasRole permission."""
    
    @pytest.mark.asyncio
    async def test_denies_anonymous(self):
        """Test denies anonymous users."""
        from core.permissions import HasRole
        
        perm = HasRole("admin")
        request = create_mock_request()
        
        result = await perm.has_permission(request)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_allows_user_with_role(self):
        """Test allows user with required role."""
        from core.permissions import HasRole
        
        perm = HasRole("admin")
        user = MagicMock()
        user.roles = ["admin", "user"]
        request = create_mock_request(user=user, is_authenticated=True)
        
        result = await perm.has_permission(request)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_denies_user_without_role(self):
        """Test denies user without required role."""
        from core.permissions import HasRole
        
        perm = HasRole("admin")
        user = MagicMock()
        user.roles = ["user"]
        request = create_mock_request(user=user, is_authenticated=True)
        
        result = await perm.has_permission(request)
        assert result is False


class TestPermissionCombination:
    """Test permission combination operators."""
    
    @pytest.mark.asyncio
    async def test_and_permission(self):
        """Test AND combination."""
        from core.permissions import IsAuthenticated, IsAdmin
        
        perm = IsAuthenticated() & IsAdmin()
        
        # Authenticated but not admin - should fail
        user = MagicMock()
        user.is_admin = False
        user.is_superuser = False
        request = create_mock_request(user=user, is_authenticated=True)
        
        result = await perm.has_permission(request)
        assert result is False
        
        # Authenticated and admin - should pass
        user.is_admin = True
        request = create_mock_request(user=user, is_authenticated=True)
        
        result = await perm.has_permission(request)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_or_permission(self):
        """Test OR combination."""
        from core.permissions import IsAuthenticated, AllowAny
        
        perm = IsAuthenticated() | AllowAny()
        
        # Anonymous - should pass (AllowAny)
        request = create_mock_request()
        
        result = await perm.has_permission(request)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_not_permission(self):
        """Test NOT combination."""
        from core.permissions import IsAuthenticated
        
        perm = ~IsAuthenticated()
        
        # Anonymous - should pass (NOT authenticated)
        request = create_mock_request()
        
        result = await perm.has_permission(request)
        assert result is True
        
        # Authenticated - should fail
        user = MagicMock()
        request = create_mock_request(user=user, is_authenticated=True)
        
        result = await perm.has_permission(request)
        assert result is False
