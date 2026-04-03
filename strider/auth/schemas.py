"""
Base authentication schemas for common auth operations.

These schemas can be used directly or extended for custom fields.

Example:
    # Use directly
    from strider.auth.schemas import LoginInput, TokenResponse
    
    # Or extend
    from strider.auth.schemas import BaseRegisterInput
    
    class RegisterInput(BaseRegisterInput):
        phone: str | None = None
        company: str | None = None
"""

from __future__ import annotations

from pydantic import ConfigDict, EmailStr, field_validator

from strider.serializers import InputSchema, OrmPrimaryKey, OutputSchema

# Chaves que o AuthViewSet nunca inclui no JSON de `/auth/me` (defesa em profundidade).
AUTH_USER_API_RESPONSE_BLOCKLIST: frozenset[str] = frozenset({
    "password",
    "password_hash",
    "hashed_password",
})


# =============================================================================
# Input Schemas
# =============================================================================

class BaseRegisterInput(InputSchema):
    """
    Base schema for user registration.
    
    Chaves JSON extra são **aceites** (``extra="allow"``): não provocam 422.
    O ``AuthViewSet`` repassa ao ``create_user`` apenas valores cujo nome corresponde
    a **colunas** do modelo de utilizador (e não são PK, ``email``, ``password`` ou
    ``password_hash``). ``is_superuser`` / ``is_staff`` enviados só como extra,
    sem estarem declarados no schema de registo, são **omitidos** por defeito
    (ver ``register_block_privilege_extras`` no ViewSet).
    
    Para **rejeitar** chaves não declaradas (422), usa uma subclasse com
    ``model_config = ConfigDict(extra="forbid")``.
    
    Extend this to add custom fields:
        class RegisterInput(BaseRegisterInput):
            phone: str | None = None
    """
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_default=True,
        extra="allow",
        from_attributes=True,
    )

    email: EmailStr
    password: str
    
    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """
        Basic password validation.
        
        Override this method for custom validation rules.
        """
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class BaseLoginInput(InputSchema):
    """
    Base schema for user login.
    
    Uses email as identifier by default.
    """
    email: EmailStr
    password: str


class RefreshTokenInput(InputSchema):
    """Schema for token refresh."""
    refresh_token: str


class ChangePasswordInput(InputSchema):
    """Schema for password change."""
    current_password: str
    new_password: str
    
    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


# =============================================================================
# Output Schemas
# =============================================================================

class TokenResponse(OutputSchema):
    """
    Standard token response for login/refresh.
    
    Compatible with OAuth2 token response format.
    """
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 1800  # 30 minutes default


class BaseUserOutput(OutputSchema):
    """
    Base user output schema.
    
    Bug #4 Fix: Now supports both int and UUID ids.
    
    Extend to add custom fields:
        class UserOutput(BaseUserOutput):
            phone: str | None = None
            avatar_url: str | None = None
    
    For UUID users, the id will be automatically serialized to string.
    """

    id: OrmPrimaryKey
    email: str
    is_active: bool = True
    is_staff: bool = False
    is_superuser: bool = False


class MessageResponse(OutputSchema):
    """Simple message response."""
    message: str
    success: bool = True


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "AUTH_USER_API_RESPONSE_BLOCKLIST",
    # Input
    "BaseRegisterInput",
    "BaseLoginInput",
    "RefreshTokenInput",
    "ChangePasswordInput",
    # Output
    "TokenResponse",
    "BaseUserOutput",
    "MessageResponse",
]
