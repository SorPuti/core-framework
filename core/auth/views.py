"""
ViewSets de autenticação prontos para uso.

Endpoints fornecidos:
- POST /auth/register - Registro de usuário
- POST /auth/login - Login
- POST /auth/refresh - Renovar token
- GET /auth/me - Usuário atual
- POST /auth/change-password - Alterar senha

Exemplo:
    from core.auth.views import AuthViewSet
    from myapp.models import User
    
    class MyAuthViewSet(AuthViewSet):
        user_model = User
    
    router.register_viewset("/auth", MyAuthViewSet, basename="auth")
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, TYPE_CHECKING
from uuid import UUID

from fastapi import Request, HTTPException
from pydantic import create_model

from core.views import ViewSet, action
from core.permissions import AllowAny, IsAuthenticated
from core.auth.tokens import create_access_token, create_refresh_token, verify_token
from core.auth.schemas import (
    BaseRegisterInput,
    BaseLoginInput,
    RefreshTokenInput,
    ChangePasswordInput,
    TokenResponse,
    BaseUserOutput,
    MessageResponse,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class AuthViewSet(ViewSet):
    """
    ViewSet de autenticação pronto para uso.
    
    Atributos configuráveis:
        user_model: Classe do modelo User (obrigatório)
        register_schema: Schema de registro customizado
        login_schema: Schema de login customizado  
        user_output_schema: Schema de output do usuário
        extra_register_fields: Campos extras aceitos no registro
        access_token_expire_minutes: Expiração do access token (default: 30)
        refresh_token_expire_days: Expiração do refresh token (default: 7)
    
    Exemplo:
        from core.auth.views import AuthViewSet
        
        class MyAuthViewSet(AuthViewSet):
            user_model = User
            extra_register_fields = ["name", "phone"]
        
        router.register_viewset("/auth", MyAuthViewSet)
    
    Endpoints:
        POST /auth/register
        POST /auth/login
        POST /auth/refresh
        GET /auth/me
        POST /auth/change-password
    """
    
    # Configuration - override in subclass or use get_user_model()
    user_model: type | None = None
    register_schema: type = BaseRegisterInput
    login_schema: type = BaseLoginInput
    user_output_schema: type = BaseUserOutput
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    
    # Bug #5 Fix: Extra fields to accept on registration
    extra_register_fields: list[str] = []
    
    # ViewSet config
    tags: list[str] = ["auth"]
    
    # Cache for dynamic schema
    _dynamic_register_schema: type | None = None
    
    def _get_user_model(self):
        """
        Get user model from class attribute or global config.
        
        Priority:
        1. self.user_model (if set on subclass)
        2. get_user_model() (from configure_auth or settings)
        """
        if self.user_model is not None:
            return self.user_model
        
        # Try to get from global config
        from core.auth.models import get_user_model
        return get_user_model()
    
    def _get_register_schema(self) -> type:
        """
        Get registration schema with STRICT extra fields support.
        
        This method validates against the model to determine if fields are
        required (NOT NULL) or optional (nullable).
        
        Rules:
            - If model column is NOT NULL and has no default -> REQUIRED in schema
            - If model column is nullable or has default -> OPTIONAL in schema
        
        Returns:
            Pydantic schema class for registration
        """
        import logging
        import warnings
        logger = logging.getLogger("core.auth")
        
        # If register_schema was explicitly overridden, use it
        if self.register_schema != BaseRegisterInput:
            return self.register_schema
        
        # If no extra fields, use base schema
        if not self.extra_register_fields:
            return BaseRegisterInput
        
        # Return cached schema if available
        if self._dynamic_register_schema is not None:
            return self._dynamic_register_schema
        
        User = self._get_user_model()
        
        # Get model column info for nullable/required check
        model_columns = {}
        try:
            from sqlalchemy import inspect
            mapper = inspect(User)
            model_columns = {col.name: col for col in mapper.columns}
        except Exception as e:
            logger.debug(f"Could not inspect User model: {e}")
        
        extra_fields = {}
        
        for field_name in self.extra_register_fields:
            col = model_columns.get(field_name)
            
            if col is not None:
                # Determine type from model
                python_type = self._get_python_type_from_column(col.type)
                
                # Check if field is required
                is_nullable = col.nullable
                has_default = col.default is not None or col.server_default is not None
                
                if not is_nullable and not has_default:
                    # REQUIRED field - use ... (Ellipsis) as default
                    extra_fields[field_name] = (python_type, ...)
                    logger.info(
                        f"Field '{field_name}' is NOT NULL in model, "
                        f"adding as REQUIRED to register schema"
                    )
                else:
                    # Optional field
                    extra_fields[field_name] = (python_type | None, None)
            else:
                # Field not in model columns, warn and make optional
                warnings.warn(
                    f"Field '{field_name}' in extra_register_fields "
                    f"not found in {User.__name__} model columns. "
                    f"Adding as optional str.",
                    UserWarning,
                    stacklevel=2,
                )
                extra_fields[field_name] = (str | None, None)
        
        # Create dynamic model
        self._dynamic_register_schema = create_model(
            "DynamicRegisterInput",
            __base__=BaseRegisterInput,
            __module__=__name__,
            **extra_fields,
        )
        
        # Allow extra fields (ignore unknown)
        self._dynamic_register_schema.model_config = {
            **BaseRegisterInput.model_config,
            "extra": "ignore",
        }
        
        return self._dynamic_register_schema
    
    def _get_python_type_from_column(self, sa_type) -> type:
        """
        Convert SQLAlchemy column type to Python type.
        
        Args:
            sa_type: SQLAlchemy type instance
        
        Returns:
            Corresponding Python type
        """
        from sqlalchemy import String, Integer, Boolean, Float, Text, DateTime, Date
        
        type_map = {
            String: str,
            Text: str,
            Integer: int,
            Boolean: bool,
            Float: float,
        }
        
        for sa_cls, py_type in type_map.items():
            if isinstance(sa_type, sa_cls):
                return py_type
        
        # Check type name for dialect-specific types
        type_name = type(sa_type).__name__
        if "String" in type_name or "Text" in type_name or "VARCHAR" in type_name:
            return str
        if "Integer" in type_name or "INT" in type_name:
            return int
        if "Boolean" in type_name or "BOOL" in type_name:
            return bool
        if "Float" in type_name or "Numeric" in type_name or "Decimal" in type_name:
            return float
        if "DateTime" in type_name or "Timestamp" in type_name:
            from datetime import datetime
            return datetime
        if "Date" in type_name:
            from datetime import date
            return date
        if "UUID" in type_name:
            from uuid import UUID
            return UUID
        
        # Default to str
        return str
    
    def _get_extra_field_names(self) -> list[str]:
        """
        Auto-detect extra fields from register_schema.
        
        Compares register_schema fields with BaseRegisterInput to find
        additional fields that need to be passed to create_user().
        
        This allows users to define a custom register_schema without
        also having to define extra_register_fields (DRY principle).
        
        Returns:
            List of field names that are in register_schema but not in BaseRegisterInput
        
        Example:
            class CustomRegisterInput(BaseRegisterInput):
                name: str
                phone: str | None = None
            
            class MyAuthViewSet(AuthViewSet):
                register_schema = CustomRegisterInput
                # extra_register_fields not needed!
            
            # _get_extra_field_names() returns ["name", "phone"]
        """
        schema = self._get_register_schema()
        
        # Get base fields (email, password)
        base_fields = set(BaseRegisterInput.model_fields.keys())
        
        # Get schema fields
        schema_fields = set(schema.model_fields.keys())
        
        # Return extra fields (fields in schema but not in base)
        extra = schema_fields - base_fields
        
        return list(extra)
    
    def _create_tokens(self, user) -> dict:
        """
        Bug #6 Fix: Create access and refresh tokens using current API.
        
        Uses the correct function signature with user_id and extra_claims.
        """
        access_token = create_access_token(
            user_id=str(user.id),
            extra_claims={"email": getattr(user, "email", None)},
            expires_delta=timedelta(minutes=self.access_token_expire_minutes),
        )
        refresh_token = create_refresh_token(
            user_id=str(user.id),
            expires_delta=timedelta(days=self.refresh_token_expire_days),
        )
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": self.access_token_expire_minutes * 60,
        }
    
    def _convert_user_id(self, user_id: str, User: type) -> Any:
        """
        Bug #7 Fix: Convert user_id string to the correct type.
        
        Intelligently converts based on the User model's PK type.
        
        Args:
            user_id: String representation of user ID
            User: User model class
            
        Returns:
            Converted user ID in the correct type
        """
        # Try to detect PK type from model
        from core.auth.models import _get_pk_column_type
        from sqlalchemy.dialects.postgresql import UUID as PG_UUID
        from sqlalchemy import Integer, BigInteger, String
        
        pk_type = _get_pk_column_type(User)
        
        if pk_type == PG_UUID:
            try:
                return UUID(user_id)
            except (ValueError, TypeError):
                return user_id
        elif pk_type in (Integer, BigInteger):
            try:
                return int(user_id)
            except (ValueError, TypeError):
                return user_id
        else:
            return user_id
    
    @action(methods=["POST"], detail=False, permission_classes=[AllowAny])
    async def register(
        self,
        request: Request,
        db: "AsyncSession",
        data: dict[str, Any] | None = None,
        **kwargs,
    ) -> dict:
        """
        Register a new user.
        
        Bug #5 Fix: Now supports extra_register_fields.
        
        Returns tokens on successful registration.
        """
        User = self._get_user_model()
        
        # Bug #5 Fix: Use dynamic schema that includes extra fields
        schema = self._get_register_schema()
        validated = schema.model_validate(data)
        
        # Check if user exists
        existing = await User.get_by_email(validated.email, db)
        if existing:
            raise HTTPException(
                status_code=400,
                detail="User with this email already exists"
            )
        
        # Extract extra fields for user creation
        # Auto-detect from schema if extra_register_fields not explicitly defined
        extra_field_names = self.extra_register_fields or self._get_extra_field_names()
        
        extra_fields = {}
        for field_name in extra_field_names:
            value = getattr(validated, field_name, None)
            if value is not None:
                extra_fields[field_name] = value
        
        # Create user with extra fields
        user = await User.create_user(
            email=validated.email,
            password=validated.password,
            db=db,
            **extra_fields,
        )
        
        # Commit the transaction
        await db.commit()
        
        # Return tokens
        return self._create_tokens(user)
    
    @action(methods=["POST"], detail=False, permission_classes=[AllowAny])
    async def login(
        self,
        request: Request,
        db: "AsyncSession",
        data: dict[str, Any] | None = None,
        **kwargs,
    ) -> dict:
        """
        Login with email and password.
        
        Returns access and refresh tokens.
        """
        User = self._get_user_model()
        
        # Validate input
        validated = self.login_schema.model_validate(data)
        
        # Authenticate
        user = await User.authenticate(
            email=validated.email,
            password=validated.password,
            db=db,
        )
        
        if user is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid email or password"
            )
        
        # Commit any changes (last_login update)
        await db.commit()
        
        # Return tokens
        return self._create_tokens(user)
    
    @action(methods=["POST"], detail=False, permission_classes=[AllowAny])
    async def refresh(
        self,
        request: Request,
        db: "AsyncSession",
        data: dict[str, Any] | None = None,
        **kwargs,
    ) -> dict:
        """
        Refresh access token using refresh token.
        
        Bug #7 Fix: Now correctly handles UUID user IDs.
        """
        User = self._get_user_model()
        
        # Validate input
        validated = RefreshTokenInput.model_validate(data)
        
        # Verify refresh token
        payload = verify_token(validated.refresh_token, token_type="refresh")
        if payload is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired refresh token"
            )
        
        # Bug #7 Fix: Convert user_id to correct type
        user_id_str = payload.get("sub")
        user_id = self._convert_user_id(user_id_str, User)
        
        user = await User.objects.using(db).filter(id=user_id).first()
        
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=401,
                detail="User not found or inactive"
            )
        
        # Return new tokens
        return self._create_tokens(user)
    
    @action(methods=["GET"], detail=False, permission_classes=[IsAuthenticated])
    async def me(
        self,
        request: Request,
        db: "AsyncSession",
        **kwargs,
    ) -> dict:
        """
        Get current authenticated user.
        
        Uses request.user (Starlette pattern) with fallback to request.state.user
        for backward compatibility.
        """
        # Try request.user first (Starlette AuthenticationMiddleware pattern)
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            # user is an AuthenticatedUser wrapper - get underlying model
            if hasattr(user, "_user"):
                user = user._user
            return self.user_output_schema.model_validate(user).model_dump()
        
        # Fallback to request.state.user (legacy pattern)
        user = getattr(request.state, "user", None)
        if user is not None:
            return self.user_output_schema.model_validate(user).model_dump()
        
        raise HTTPException(
            status_code=401,
            detail="Not authenticated"
        )
    
    @action(methods=["POST"], detail=False, permission_classes=[IsAuthenticated])
    async def change_password(
        self,
        request: Request,
        db: "AsyncSession",
        data: dict[str, Any] | None = None,
        **kwargs,
    ) -> dict:
        """
        Change password for current user.
        """
        # Try request.user first (Starlette pattern)
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            if hasattr(user, "_user"):
                user = user._user
        else:
            # Fallback to request.state.user
            user = getattr(request.state, "user", None)
        
        if user is None:
            raise HTTPException(
                status_code=401,
                detail="Not authenticated"
            )
        
        # Validate input
        validated = ChangePasswordInput.model_validate(data)
        
        # Verify current password
        if not user.check_password(validated.current_password):
            raise HTTPException(
                status_code=400,
                detail="Current password is incorrect"
            )
        
        # Set new password
        user.set_password(validated.new_password)
        await user.save(db)
        await db.commit()
        
        return {"message": "Password changed successfully", "success": True}


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "AuthViewSet",
]
