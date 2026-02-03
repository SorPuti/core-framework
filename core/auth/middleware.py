"""
Authentication Middleware for Core Framework.

Bug #8 Fix: Provides built-in middleware for populating request.state.user.

This middleware automatically authenticates requests using the configured
authentication backend and populates request.state.user.

Usage:
    from core.auth.middleware import AuthenticationMiddleware
    
    app = CoreApp(
        middlewares=[(AuthenticationMiddleware, {})],
    )
    
    # Or configure via configure_auth()
    from core.auth import configure_auth
    configure_auth(
        user_model=User,
        auto_middleware=True,  # Automatically adds middleware
    )

The middleware will:
1. Extract Bearer token from Authorization header
2. Validate the token
3. Fetch the user from database
4. Set request.state.user to the authenticated user (or None)
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

if TYPE_CHECKING:
    from collections.abc import Callable, Awaitable


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """
    Middleware that authenticates requests and populates request.state.user.
    
    This middleware:
    1. Initializes request.state.user to None
    2. Extracts Bearer token from Authorization header
    3. Validates the token using configured backend
    4. Fetches user from database
    5. Sets request.state.user to authenticated user
    
    Example:
        from core.auth.middleware import AuthenticationMiddleware
        
        app = CoreApp(
            middlewares=[(AuthenticationMiddleware, {})],
        )
        
        # In your view
        @router.get("/me")
        async def me(request: Request):
            user = request.state.user  # User or None
            if user is None:
                raise HTTPException(401, "Not authenticated")
            return {"id": user.id, "email": user.email}
    
    Configuration via kwargs:
        - user_model: User model class (uses global config if None)
        - header_name: Header to extract token from (default: "Authorization")
        - scheme: Expected scheme (default: "Bearer")
        - skip_paths: List of paths to skip authentication (e.g., ["/health"])
    """
    
    def __init__(
        self,
        app: "Callable[[Request], Awaitable[Response]]",
        user_model: type | None = None,
        header_name: str = "Authorization",
        scheme: str = "Bearer",
        skip_paths: list[str] | None = None,
    ) -> None:
        super().__init__(app)
        self._user_model = user_model
        self.header_name = header_name
        self.scheme = scheme
        self.skip_paths = skip_paths or []
    
    @property
    def user_model(self) -> type | None:
        """Get user model from instance or global config."""
        if self._user_model is not None:
            return self._user_model
        
        try:
            from core.auth.models import get_user_model
            return get_user_model()
        except Exception:
            return None
    
    async def dispatch(
        self,
        request: Request,
        call_next: "Callable[[Request], Awaitable[Response]]",
    ) -> Response:
        """
        Process request and authenticate user.
        
        Always sets request.state.user (to User or None).
        """
        # Initialize user to None
        request.state.user = None
        
        # Skip authentication for configured paths
        if self._should_skip(request.url.path):
            return await call_next(request)
        
        # Try to authenticate
        try:
            user = await self._authenticate(request)
            request.state.user = user
        except Exception:
            # Authentication failed, keep user as None
            pass
        
        return await call_next(request)
    
    def _should_skip(self, path: str) -> bool:
        """Check if path should skip authentication."""
        for skip_path in self.skip_paths:
            if path.startswith(skip_path):
                return True
        return False
    
    def _extract_token(self, request: Request) -> str | None:
        """Extract token from Authorization header."""
        auth_header = request.headers.get(self.header_name)
        
        if not auth_header:
            return None
        
        parts = auth_header.split()
        
        if len(parts) != 2:
            return None
        
        scheme, token = parts
        
        if scheme.lower() != self.scheme.lower():
            return None
        
        return token
    
    async def _authenticate(self, request: Request) -> Any | None:
        """
        Authenticate request and return user.
        
        Returns:
            User instance if authenticated, None otherwise
        """
        token = self._extract_token(request)
        
        if not token:
            return None
        
        # Verify token
        from core.auth.tokens import verify_token
        
        payload = verify_token(token, token_type="access")
        
        if payload is None:
            return None
        
        # Get user_id from token
        user_id = payload.get("sub") or payload.get("user_id")
        
        if not user_id:
            return None
        
        # Get user from database
        User = self.user_model
        if User is None:
            return None
        
        # Bug #3 & #4 Fix: Get database session correctly
        # The middleware runs outside FastAPI DI context, so we need to
        # handle database session creation carefully
        db = await self._get_db_session()
        if db is None:
            return None
        
        try:
            # Convert user_id to correct type
            user_id_converted = self._convert_user_id(user_id, User)
            
            user = await User.objects.using(db).filter(id=user_id_converted).first()
            
            if user is None:
                return None
            
            # Check if user is active
            if hasattr(user, "is_active") and not user.is_active:
                return None
            
            return user
        except Exception:
            return None
        finally:
            await db.close()
    
    async def _get_db_session(self) -> Any | None:
        """
        Get a database session for authentication.
        
        Bug #3 & #4 Fix: Handles both initialized and uninitialized database states.
        Creates session directly from engine if normal path fails.
        
        Returns:
            AsyncSession or None if database not available
        """
        # Try 1: Use the standard get_read_session (if database is initialized)
        try:
            from core.database import get_read_session, _read_session_factory
            
            if _read_session_factory is not None:
                return _read_session_factory()
        except (RuntimeError, ImportError):
            pass
        
        # Try 2: Create session from settings (lazy initialization)
        try:
            from core.config import get_settings
            from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
            
            settings = get_settings()
            db_url = getattr(settings, 'database_read_url', None) or getattr(settings, 'database_url', None)
            
            if db_url:
                engine = create_async_engine(db_url, echo=False)
                session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
                return session_factory()
        except Exception:
            pass
        
        return None
    
    def _convert_user_id(self, user_id: str, User: type) -> Any:
        """
        Convert user_id string to the correct type based on model.
        
        Handles INTEGER, UUID, and string IDs.
        """
        from uuid import UUID
        
        # Try to detect PK type
        try:
            from core.auth.models import _get_pk_column_type
            from sqlalchemy.dialects.postgresql import UUID as PG_UUID
            from sqlalchemy import Integer, BigInteger
            
            pk_type = _get_pk_column_type(User)
            
            if pk_type == PG_UUID:
                return UUID(user_id)
            elif pk_type in (Integer, BigInteger):
                return int(user_id)
        except Exception:
            pass
        
        # Try UUID first, then int, then string
        try:
            return UUID(user_id)
        except (ValueError, TypeError):
            pass
        
        try:
            return int(user_id)
        except (ValueError, TypeError):
            pass
        
        return user_id


class OptionalAuthenticationMiddleware(AuthenticationMiddleware):
    """
    Same as AuthenticationMiddleware but never raises errors.
    
    Always proceeds with the request, setting user to None on any failure.
    Useful for endpoints that work both with and without authentication.
    """
    
    async def dispatch(
        self,
        request: Request,
        call_next: "Callable[[Request], Awaitable[Response]]",
    ) -> Response:
        """Process request, never failing on auth errors."""
        request.state.user = None
        
        if not self._should_skip(request.url.path):
            try:
                user = await self._authenticate(request)
                request.state.user = user
            except Exception:
                pass  # Silently ignore all errors
        
        return await call_next(request)


# =============================================================================
# Auto-configuration helper
# =============================================================================

_middleware_registered = False


def ensure_auth_middleware(app: Any) -> None:
    """
    Ensure AuthenticationMiddleware is registered on the app.
    
    Call this from configure_auth() when auto_middleware=True.
    
    Args:
        app: FastAPI or CoreApp instance
    """
    global _middleware_registered
    
    if _middleware_registered:
        return
    
    # Try to add middleware
    try:
        if hasattr(app, "add_middleware"):
            app.add_middleware(AuthenticationMiddleware)
            _middleware_registered = True
    except Exception:
        pass


def reset_middleware_state() -> None:
    """Reset middleware registration state (for testing)."""
    global _middleware_registered
    _middleware_registered = False


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "AuthenticationMiddleware",
    "OptionalAuthenticationMiddleware",
    "ensure_auth_middleware",
    "reset_middleware_state",
]
