"""
Tests for auth helpers.

These tests validate the get_request_user helper works correctly
with both Starlette and legacy patterns.
"""

import pytest
from unittest.mock import MagicMock, PropertyMock


class TestGetRequestUser:
    """Test get_request_user helper function."""
    
    def test_returns_none_when_no_user(self):
        """Test returns None when no user is set."""
        from core.auth.helpers import get_request_user
        
        request = MagicMock()
        request.user = None
        request.state = MagicMock()
        request.state.user = None
        
        result = get_request_user(request)
        assert result is None
    
    def test_returns_user_from_starlette_pattern(self):
        """Test returns user from request.user (Starlette pattern)."""
        from core.auth.helpers import get_request_user
        
        # Create a mock user that looks like AuthenticatedUser
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user._user = MagicMock()  # The underlying model
        mock_user._user.email = "test@example.com"
        
        request = MagicMock()
        request.user = mock_user
        
        result = get_request_user(request)
        assert result == mock_user._user
    
    def test_returns_user_from_legacy_pattern(self):
        """Test returns user from request.state.user (legacy pattern)."""
        from core.auth.helpers import get_request_user
        
        mock_user = MagicMock()
        mock_user.email = "test@example.com"
        
        request = MagicMock()
        request.user = MagicMock()
        request.user.is_authenticated = False  # Not authenticated via Starlette
        request.state = MagicMock()
        request.state.user = mock_user
        
        result = get_request_user(request)
        assert result == mock_user
    
    def test_prefers_starlette_over_legacy(self):
        """Test prefers request.user over request.state.user."""
        from core.auth.helpers import get_request_user
        
        starlette_user = MagicMock()
        starlette_user.is_authenticated = True
        starlette_user._user = MagicMock()
        starlette_user._user.email = "starlette@example.com"
        
        legacy_user = MagicMock()
        legacy_user.email = "legacy@example.com"
        
        request = MagicMock()
        request.user = starlette_user
        request.state = MagicMock()
        request.state.user = legacy_user
        
        result = get_request_user(request)
        # Should return the Starlette user
        assert result.email == "starlette@example.com"
    
    def test_handles_missing_state(self):
        """Test handles request without state attribute."""
        from core.auth.helpers import get_request_user
        
        request = MagicMock(spec=[])  # No attributes by default
        request.user = None
        
        # This should not raise an error
        result = get_request_user(request)
        assert result is None


class TestIsAuthenticated:
    """Test is_authenticated helper function."""
    
    def test_returns_false_when_no_user(self):
        """Test returns False when no user."""
        from core.auth.helpers import is_authenticated
        
        request = MagicMock()
        request.user = None
        request.state = MagicMock()
        request.state.user = None
        
        assert is_authenticated(request) is False
    
    def test_returns_true_for_starlette_user(self):
        """Test returns True for Starlette authenticated user."""
        from core.auth.helpers import is_authenticated
        
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        
        request = MagicMock()
        request.user = mock_user
        
        assert is_authenticated(request) is True
    
    def test_returns_true_for_legacy_user(self):
        """Test returns True for legacy user."""
        from core.auth.helpers import is_authenticated
        
        mock_user = MagicMock()
        
        request = MagicMock()
        request.user = MagicMock()
        request.user.is_authenticated = False
        request.state = MagicMock()
        request.state.user = mock_user
        
        assert is_authenticated(request) is True


class TestSetRequestUser:
    """Test set_request_user helper function."""
    
    def test_sets_user_on_state(self):
        """Test sets user on request.state."""
        from core.auth.helpers import set_request_user
        
        mock_user = MagicMock()
        request = MagicMock()
        request.state = MagicMock()
        
        set_request_user(request, mock_user)
        
        assert request.state.user == mock_user
    
    def test_clears_user_when_none(self):
        """Test clears user when None is passed."""
        from core.auth.helpers import set_request_user
        
        request = MagicMock()
        request.state = MagicMock()
        request.state.user = MagicMock()  # Previous user
        
        set_request_user(request, None)
        
        assert request.state.user is None


class TestAuthenticatedUserWrapper:
    """Test AuthenticatedUser wrapper class."""
    
    def test_is_authenticated_property(self):
        """Test is_authenticated returns True."""
        from core.auth.middleware import AuthenticatedUser
        
        mock_model = MagicMock()
        wrapper = AuthenticatedUser(mock_model)
        
        assert wrapper.is_authenticated is True
    
    def test_proxies_attributes(self):
        """Test proxies attribute access to underlying model."""
        from core.auth.middleware import AuthenticatedUser
        
        mock_model = MagicMock()
        mock_model.email = "test@example.com"
        mock_model.id = 123
        
        wrapper = AuthenticatedUser(mock_model)
        
        assert wrapper.email == "test@example.com"
        assert wrapper.id == 123
    
    def test_display_name(self):
        """Test display_name returns email."""
        from core.auth.middleware import AuthenticatedUser
        
        mock_model = MagicMock()
        mock_model.email = "test@example.com"
        
        wrapper = AuthenticatedUser(mock_model)
        
        assert wrapper.display_name == "test@example.com"
    
    def test_identity(self):
        """Test identity returns string id."""
        from core.auth.middleware import AuthenticatedUser
        
        mock_model = MagicMock()
        mock_model.id = 123
        
        wrapper = AuthenticatedUser(mock_model)
        
        assert wrapper.identity == "123"


class TestAuthViewSetExtraFields:
    """Test AuthViewSet._get_extra_field_names() auto-detection."""
    
    def test_detects_extra_fields_from_custom_schema(self):
        """Extra fields should be auto-detected from custom register_schema."""
        from core.auth.views import AuthViewSet
        from core.auth.schemas import BaseRegisterInput
        from pydantic import create_model
        from typing import Optional
        
        # Create custom schema with extra fields
        CustomRegisterInput = create_model(
            "CustomRegisterInput",
            __base__=BaseRegisterInput,
            name=(str, ...),
            phone=(Optional[str], None),
        )
        
        class TestAuthViewSet(AuthViewSet):
            register_schema = CustomRegisterInput
            # extra_register_fields NOT defined - should be auto-detected
        
        viewset = TestAuthViewSet()
        extra_names = viewset._get_extra_field_names()
        
        assert "name" in extra_names
        assert "phone" in extra_names
        assert "email" not in extra_names
        assert "password" not in extra_names
    
    def test_returns_empty_for_base_schema(self):
        """Should return empty list when using base schema."""
        from core.auth.views import AuthViewSet
        
        class TestAuthViewSet(AuthViewSet):
            # Using default BaseRegisterInput
            pass
        
        viewset = TestAuthViewSet()
        extra_names = viewset._get_extra_field_names()
        
        assert extra_names == []
    
    def test_explicit_extra_register_fields_takes_precedence(self):
        """Explicit extra_register_fields should take precedence over auto-detect."""
        from core.auth.views import AuthViewSet
        from core.auth.schemas import BaseRegisterInput
        from pydantic import create_model
        from typing import Optional
        
        # Create custom schema with extra fields
        CustomRegisterInput = create_model(
            "CustomRegisterInput",
            __base__=BaseRegisterInput,
            name=(str, ...),
            phone=(Optional[str], None),
            company=(Optional[str], None),
        )
        
        class TestAuthViewSet(AuthViewSet):
            register_schema = CustomRegisterInput
            # Explicitly define only some fields
            extra_register_fields = ["name"]
        
        viewset = TestAuthViewSet()
        
        # Should use explicit list, not auto-detect
        assert viewset.extra_register_fields == ["name"]
        
        # Auto-detect should still return all extra fields
        auto_detected = viewset._get_extra_field_names()
        assert "name" in auto_detected
        assert "phone" in auto_detected
        assert "company" in auto_detected
    
    def test_dynamic_schema_with_extra_register_fields(self):
        """Dynamic schema creation via extra_register_fields should work."""
        from core.auth.views import AuthViewSet
        from core.auth.schemas import BaseRegisterInput
        from unittest.mock import MagicMock, patch
        
        class TestAuthViewSet(AuthViewSet):
            extra_register_fields = ["name", "phone"]
        
        viewset = TestAuthViewSet()
        
        # Mock User model to avoid "user_model not configured" error
        mock_user = MagicMock()
        mock_user.__name__ = "MockUser"
        mock_user.__annotations__ = {
            "name": "Mapped[str]",
            "phone": "Mapped[str | None]",
        }
        
        # Patch _get_user_model and also mock sqlalchemy.inspect to avoid errors
        with patch.object(viewset, "_get_user_model", return_value=mock_user):
            with patch("sqlalchemy.inspect", side_effect=Exception("No mapper")):
                schema = viewset._get_register_schema()
        
        # Dynamic schema should have the extra fields
        assert "name" in schema.model_fields
        assert "phone" in schema.model_fields
        assert "email" in schema.model_fields
        assert "password" in schema.model_fields
