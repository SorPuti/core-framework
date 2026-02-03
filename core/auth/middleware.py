"""
Authentication Middleware for Core Framework.

Uses Starlette's AuthenticationMiddleware pattern which correctly propagates
user to views via scope["user"] (accessed as request.user).

IMPORTANT: Use request.user (not request.state.user) in your views!

Usage:
    from core.auth.middleware import AuthenticationMiddleware
    
    app = CoreApp(
        middlewares=[(AuthenticationMiddleware, {})],
    )
    
    # In your view - use request.user
    @router.get("/me")
    async def me(request: Request):
        if not request.user.is_authenticated:
            raise HTTPException(401, "Not authenticated")
        return {"id": request.user.id, "email": request.user.email}
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING
from uuid import UUID

from starlette.authentication import (
    AuthenticationBackend,
    AuthCredentials,
    BaseUser,
    UnauthenticatedUser,
)
from starlette.middleware.authentication import AuthenticationMiddleware as StarletteAuthMiddleware
from starlette.requests import HTTPConnection

from core.exceptions import (
    InvalidToken,
    TokenExpired,
    UserNotFound,
    UserInactive,
    DatabaseException,
    ConfigurationError,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Logger for authentication - NEVER silent!
logger = logging.getLogger("core.auth")


# =============================================================================
# Authenticated User Wrapper
# =============================================================================

class AuthenticatedUser(BaseUser):
    """
    Wrapper for authenticated user that implements Starlette's BaseUser.
    
    Provides access to the underlying database user model while implementing
    the required Starlette interface.
    
    Usage in views:
        user = request.user
        if user.is_authenticated:
            print(user.email)  # Access model attributes
            print(user.id)     # Access model attributes
    """
    
    def __init__(self, user: Any) -> None:
        self._user = user
    
    @property
    def is_authenticated(self) -> bool:
        return True
    
    @property
    def display_name(self) -> str:
        return getattr(self._user, "email", str(self._user))
    
    @property
    def identity(self) -> str:
        return str(getattr(self._user, "id", ""))
    
    def __getattr__(self, name: str) -> Any:
        """Proxy attribute access to underlying user model."""
        return getattr(self._user, name)
    
    def __repr__(self) -> str:
        return f"<AuthenticatedUser {self.display_name}>"


# =============================================================================
# Authentication Backend
# =============================================================================

class JWTAuthBackend(AuthenticationBackend):
    """
    JWT Authentication Backend for Starlette.
    
    This backend:
    1. Extracts Bearer token from Authorization header
    2. Verifies the token using core.auth.tokens
    3. Fetches user from database
    4. Returns AuthCredentials and AuthenticatedUser
    
    IMPORTANT: All errors are logged, NEVER silenced!
    
    Configuration:
        - user_model: User model class (uses global config if None)
        - header_name: Header to extract token from (default: "Authorization")
        - scheme: Expected scheme (default: "Bearer")
    """
    
    def __init__(
        self,
        user_model: type | None = None,
        header_name: str = "Authorization",
        scheme: str = "Bearer",
    ) -> None:
        self._user_model = user_model
        self.header_name = header_name
        self.scheme = scheme
    
    @property
    def user_model(self) -> type | None:
        """Get user model from instance or global config."""
        if self._user_model is not None:
            return self._user_model
        
        try:
            from core.auth.models import get_user_model
            return get_user_model()
        except Exception as e:
            logger.error(f"Failed to get user model: {e}")
            return None
    
    async def authenticate(self, conn: HTTPConnection) -> tuple[AuthCredentials, BaseUser] | None:
        """
        Authenticate the request.
        
        Returns:
            Tuple of (AuthCredentials, AuthenticatedUser) if authenticated
            None if no credentials provided
            
        Note: Returns None for missing credentials, but LOGS all errors!
        """
        # Extract token from header
        auth_header = conn.headers.get(self.header_name)
        
        if not auth_header:
            logger.debug("No Authorization header present")
            return None
        
        # Parse header
        parts = auth_header.split()
        if len(parts) != 2:
            logger.warning(f"Malformed Authorization header: expected 2 parts, got {len(parts)}")
            return None
        
        scheme, token = parts
        if scheme.lower() != self.scheme.lower():
            logger.warning(f"Unexpected auth scheme: expected '{self.scheme}', got '{scheme}'")
            return None
        
        logger.debug(f"Token extracted: {token[:20]}...")
        
        # Verify token
        try:
            user = await self._verify_and_get_user(token)
            if user is None:
                return None
            
            logger.info(f"User authenticated: {getattr(user, 'email', user)}")
            return AuthCredentials(["authenticated"]), AuthenticatedUser(user)
            
        except InvalidToken as e:
            logger.warning(f"Invalid token: {e.message}")
            return None
        except TokenExpired as e:
            logger.warning(f"Token expired: {e.message}")
            return None
        except UserNotFound as e:
            logger.warning(f"User not found: {e.message}")
            return None
        except UserInactive as e:
            logger.warning(f"User inactive: {e.message}")
            return None
        except DatabaseException as e:
            logger.error(f"Database error during authentication: {e.message}", exc_info=True)
            raise  # Re-raise database errors - these are critical!
        except ConfigurationError as e:
            logger.error(f"Configuration error: {e.message}", exc_info=True)
            raise  # Re-raise configuration errors - these need to be fixed!
        except Exception as e:
            # Log unexpected errors with full stack trace
            logger.exception(f"Unexpected error during authentication: {e}")
            raise  # NEVER silence unexpected errors!
    
    async def _verify_and_get_user(self, token: str) -> Any | None:
        """
        Verify token and fetch user from database.
        
        Raises:
            InvalidToken: If token is invalid or malformed
            TokenExpired: If token has expired
            UserNotFound: If user doesn't exist
            UserInactive: If user is inactive
            DatabaseException: If database query fails
            ConfigurationError: If auth is not properly configured
        """
        from core.auth.tokens import verify_token, decode_token
        from core.auth.base import TokenError
        
        # Verify token
        try:
            payload = verify_token(token, token_type="access")
        except TokenError as e:
            raise InvalidToken(f"Token verification failed: {e}")
        
        if payload is None:
            # verify_token returns None for various reasons - let's be more specific
            try:
                # Try to decode to get more info
                raw_payload = decode_token(token)
                token_type = raw_payload.get("type")
                if token_type != "access":
                    raise InvalidToken(f"Token type mismatch: expected 'access', got '{token_type}'")
            except Exception as e:
                raise InvalidToken(f"Token decode failed: {e}")
            raise InvalidToken("Token verification returned None")
        
        logger.debug(f"Token payload: {payload}")
        
        # Get user_id from token
        user_id = payload.get("sub") or payload.get("user_id")
        if not user_id:
            raise InvalidToken("Token missing 'sub' or 'user_id' claim")
        
        logger.debug(f"User ID from token: {user_id}")
        
        # Get user model
        User = self.user_model
        if User is None:
            raise ConfigurationError(
                "No user model configured. "
                "Set user_model in AuthenticationMiddleware or call configure_auth(user_model=...)"
            )
        
        # Get database session
        db = await self._get_db_session()
        if db is None:
            raise DatabaseException(
                "Could not obtain database session. "
                "Ensure database is initialized with init_replicas() or database_url is set in settings."
            )
        
        try:
            # Convert user_id to correct type
            user_id_converted = self._convert_user_id(user_id, User)
            logger.debug(f"User ID converted: {user_id_converted} (type: {type(user_id_converted).__name__})")
            
            # Fetch user
            user = await User.objects.using(db).filter(id=user_id_converted).first()
            
            if user is None:
                raise UserNotFound(f"User with id={user_id} not found")
            
            # Check if user is active
            if hasattr(user, "is_active") and not user.is_active:
                raise UserInactive(f"User {user_id} is inactive")
            
            logger.debug(f"User found: {getattr(user, 'email', user)}")
            return user
            
        except (UserNotFound, UserInactive):
            raise  # Re-raise our exceptions
        except Exception as e:
            raise DatabaseException(f"Database query failed: {e}")
        finally:
            await db.close()
    
    async def _get_db_session(self) -> "AsyncSession | None":
        """
        Get a database session for authentication.
        
        Tries multiple strategies and logs each attempt.
        
        Returns:
            AsyncSession or None if all strategies fail
        """
        errors: list[str] = []
        
        # Strategy 1: Use initialized session factory
        try:
            from core.database import _read_session_factory
            
            if _read_session_factory is not None:
                logger.debug("Using initialized session factory")
                return _read_session_factory()
            else:
                errors.append("Session factory not initialized (init_replicas not called)")
        except ImportError as e:
            errors.append(f"Could not import database module: {e}")
        except Exception as e:
            errors.append(f"Session factory error: {e}")
        
        # Strategy 2: Create session from settings
        try:
            from core.config import get_settings
            from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
            
            settings = get_settings()
            db_url = getattr(settings, 'database_read_url', None) or getattr(settings, 'database_url', None)
            
            if db_url:
                logger.debug(f"Creating session from settings: {db_url[:30]}...")
                engine = create_async_engine(db_url, echo=False)
                session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
                return session_factory()
            else:
                errors.append("No database_url in settings")
        except ImportError as e:
            errors.append(f"Could not import config module: {e}")
        except Exception as e:
            errors.append(f"Settings engine error: {e}")
        
        # All strategies failed - log detailed error
        logger.error(
            f"Could not obtain database session. Attempted strategies:\n" +
            "\n".join(f"  - {err}" for err in errors)
        )
        return None
    
    def _convert_user_id(self, user_id: str, User: type) -> Any:
        """
        Convert user_id string to the correct type based on model.
        
        Handles INTEGER, UUID, and string IDs.
        """
        # Try to detect PK type from model
        try:
            from core.auth.models import _get_pk_column_type
            from sqlalchemy.dialects.postgresql import UUID as PG_UUID
            from sqlalchemy import Integer, BigInteger
            
            pk_type = _get_pk_column_type(User)
            
            if pk_type == PG_UUID:
                logger.debug(f"Converting user_id to UUID: {user_id}")
                return UUID(user_id)
            elif pk_type in (Integer, BigInteger):
                logger.debug(f"Converting user_id to int: {user_id}")
                return int(user_id)
        except Exception as e:
            logger.debug(f"Could not detect PK type, trying heuristics: {e}")
        
        # Fallback: Try UUID first (common in modern systems)
        try:
            return UUID(user_id)
        except (ValueError, TypeError):
            pass
        
        # Try int
        try:
            return int(user_id)
        except (ValueError, TypeError):
            pass
        
        # Return as string
        logger.debug(f"Using user_id as string: {user_id}")
        return user_id


# =============================================================================
# Middleware Factory
# =============================================================================

class AuthenticationMiddleware(StarletteAuthMiddleware):
    """
    Authentication Middleware using Starlette's proper pattern.
    
    This middleware correctly propagates user to views via request.user
    (not request.state.user which doesn't work with BaseHTTPMiddleware).
    
    Usage:
        app = CoreApp(
            middlewares=[(AuthenticationMiddleware, {})],
        )
        
        # Or with shortcut:
        app = CoreApp(middleware=["auth"])
        
        # In views, use request.user:
        @router.get("/me")
        async def me(request: Request):
            if not request.user.is_authenticated:
                raise HTTPException(401, "Not authenticated")
            return {"email": request.user.email}
    
    Note: Also sets request.state.user for backward compatibility.
    """
    
    def __init__(
        self,
        app: Any,
        user_model: type | None = None,
        header_name: str = "Authorization",
        scheme: str = "Bearer",
        on_error: Any = None,
    ) -> None:
        backend = JWTAuthBackend(
            user_model=user_model,
            header_name=header_name,
            scheme=scheme,
        )
        super().__init__(app, backend=backend, on_error=on_error)
        logger.info("AuthenticationMiddleware initialized")


class OptionalAuthenticationMiddleware(AuthenticationMiddleware):
    """
    Same as AuthenticationMiddleware but doesn't require authentication.
    
    Useful for endpoints that work both with and without authentication.
    User will be UnauthenticatedUser if no valid token provided.
    """
    pass


# =============================================================================
# Legacy Compatibility
# =============================================================================

def ensure_auth_middleware(app: Any) -> None:
    """
    Ensure AuthenticationMiddleware is registered on the app.
    
    DEPRECATED: Use middleware=["auth"] instead.
    """
    logger.warning(
        "ensure_auth_middleware is deprecated. "
        "Use middleware=['auth'] or add AuthenticationMiddleware directly."
    )
    try:
        if hasattr(app, "add_middleware"):
            app.add_middleware(AuthenticationMiddleware)
            logger.info("AuthenticationMiddleware added to app")
    except Exception as e:
        logger.error(f"Failed to add AuthenticationMiddleware: {e}")
        raise


def reset_middleware_state() -> None:
    """Reset middleware state (for testing)."""
    pass  # No longer needed with new implementation


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "AuthenticationMiddleware",
    "OptionalAuthenticationMiddleware",
    "JWTAuthBackend",
    "AuthenticatedUser",
    "ensure_auth_middleware",
    "reset_middleware_state",
]
