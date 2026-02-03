"""
Tests for module imports.

These tests ensure there are no circular imports or missing dependencies.
Run these BEFORE committing any changes!
"""

import pytest


class TestCoreImports:
    """Test that core modules can be imported without errors."""
    
    def test_import_core(self):
        """Test importing the main core module."""
        import core
        assert hasattr(core, "__version__")
    
    def test_import_core_models(self):
        """Test importing core.models."""
        from core.models import Model, Field
        assert Model is not None
        assert Field is not None
    
    def test_import_core_views(self):
        """Test importing core.views."""
        from core.views import ViewSet, ModelViewSet, action
        assert ViewSet is not None
        assert ModelViewSet is not None
        assert action is not None
    
    def test_import_core_permissions(self):
        """Test importing core.permissions."""
        from core.permissions import (
            Permission,
            AllowAny,
            DenyAll,
            IsAuthenticated,
            IsAuthenticatedOrReadOnly,
            IsAdmin,
            IsOwner,
            HasRole,
            check_permissions,
        )
        assert Permission is not None
        assert IsAuthenticated is not None
    
    def test_import_core_exceptions(self):
        """Test importing core.exceptions."""
        from core.exceptions import (
            CoreException,
            ValidationException,
            DatabaseException,
            AuthException,
            InvalidToken,
            TokenExpired,
            PermissionDenied,
            NotFound,
            Unauthorized,
        )
        assert CoreException is not None
        assert InvalidToken is not None


class TestAuthImports:
    """Test that auth modules can be imported without circular import errors."""
    
    def test_import_auth_module(self):
        """Test importing the main auth module."""
        from core.auth import (
            configure_auth,
            get_auth_config,
            AuthBackend,
            TokenBackend,
        )
        assert configure_auth is not None
    
    def test_import_auth_models(self):
        """Test importing auth models."""
        from core.auth.models import (
            AbstractUser,
            AbstractUUIDUser,
            PermissionsMixin,
            Group,
            Permission,
        )
        assert AbstractUser is not None
        assert AbstractUUIDUser is not None
    
    def test_import_auth_tokens(self):
        """Test importing auth tokens."""
        from core.auth.tokens import (
            create_access_token,
            create_refresh_token,
            decode_token,
            verify_token,
            JWTBackend,
        )
        assert create_access_token is not None
        assert JWTBackend is not None
    
    def test_import_auth_middleware(self):
        """Test importing auth middleware."""
        from core.auth.middleware import (
            AuthenticationMiddleware,
            OptionalAuthenticationMiddleware,
            JWTAuthBackend,
            AuthenticatedUser,
        )
        assert AuthenticationMiddleware is not None
        assert JWTAuthBackend is not None
    
    def test_import_auth_decorators(self):
        """Test importing auth decorators."""
        from core.auth.decorators import (
            HasPermission,
            IsInGroup,
            IsSuperuser,
            IsStaff,
            IsActive,
            require_permission,
            require_group,
            login_required,
        )
        assert HasPermission is not None
        assert login_required is not None
    
    def test_import_auth_helpers(self):
        """Test importing auth helpers."""
        from core.auth.helpers import (
            get_request_user,
            is_authenticated,
            set_request_user,
        )
        assert get_request_user is not None
        assert is_authenticated is not None
    
    def test_import_auth_schemas(self):
        """Test importing auth schemas."""
        from core.auth.schemas import (
            BaseRegisterInput,
            BaseLoginInput,
            TokenResponse,
            BaseUserOutput,
        )
        assert BaseRegisterInput is not None
        assert TokenResponse is not None
    
    def test_import_auth_views(self):
        """Test importing auth views."""
        from core.auth.views import AuthViewSet
        assert AuthViewSet is not None


class TestMiddlewareImports:
    """Test that middleware modules can be imported."""
    
    def test_import_middleware(self):
        """Test importing core.middleware."""
        from core.middleware import (
            BaseMiddleware,
            configure_middleware,
            apply_middlewares,
            TimingMiddleware,
            RequestIDMiddleware,
            LoggingMiddleware,
        )
        assert BaseMiddleware is not None
        assert configure_middleware is not None


class TestDependenciesImports:
    """Test that dependencies can be imported."""
    
    def test_import_dependencies(self):
        """Test importing core.dependencies."""
        from core.dependencies import (
            get_db,
            get_current_user,
            get_optional_user,
            DatabaseSession,
            CurrentUser,
        )
        assert get_db is not None
        assert get_current_user is not None


class TestTenancyImports:
    """Test that tenancy modules can be imported."""
    
    def test_import_tenancy(self):
        """Test importing core.tenancy."""
        from core.tenancy import (
            TenantMixin,
            set_tenant,
            get_tenant,
            clear_tenant,
        )
        assert TenantMixin is not None
        assert set_tenant is not None


class TestMigrationsImports:
    """Test that migrations modules can be imported."""
    
    def test_import_migrations(self):
        """Test importing core.migrations."""
        from core.migrations import (
            MigrationEngine,
            Operation,
            CreateTable,
            DropTable,
        )
        assert MigrationEngine is not None
        assert CreateTable is not None


class TestImportOrder:
    """Test that imports work in various orders (to catch hidden circular deps)."""
    
    def test_permissions_before_auth(self):
        """Test importing permissions before auth."""
        from core.permissions import IsAuthenticated
        from core.auth import AuthViewSet
        assert IsAuthenticated is not None
        assert AuthViewSet is not None
    
    def test_auth_before_permissions(self):
        """Test importing auth before permissions."""
        from core.auth import AuthViewSet
        from core.permissions import IsAuthenticated
        assert AuthViewSet is not None
        assert IsAuthenticated is not None
    
    def test_views_before_auth(self):
        """Test importing views before auth."""
        from core.views import ViewSet
        from core.auth import AuthViewSet
        assert ViewSet is not None
        assert AuthViewSet is not None
    
    def test_all_together(self):
        """Test importing everything at once."""
        from core import (
            Model,
            ViewSet,
            ModelViewSet,
        )
        from core.auth import (
            AbstractUser,
            AuthViewSet,
            configure_auth,
        )
        from core.permissions import (
            IsAuthenticated,
            AllowAny,
        )
        from core.middleware import (
            BaseMiddleware,
        )
        assert Model is not None
        assert AuthViewSet is not None
        assert IsAuthenticated is not None
