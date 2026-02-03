"""
Sistema de Autenticação e Autorização Plugável.

Arquitetura modular que permite:
- Usar implementação padrão (JWT + AbstractUser)
- Substituir por backends customizados
- Criar validadores e hashers próprios
- Integrar com sistemas externos (OAuth, LDAP, etc.)

Exemplo de uso padrão:
    from core.auth import AbstractUser, PermissionsMixin
    
    class User(AbstractUser, PermissionsMixin):
        __tablename__ = "users"

Exemplo de backend customizado:
    from core.auth import AuthBackend, register_backend
    
    class MyOAuthBackend(AuthBackend):
        async def authenticate(self, request, **credentials):
            # Sua lógica OAuth
            ...
    
    register_backend("oauth", MyOAuthBackend())
"""

# Base abstractions
from core.auth.base import (
    # Interfaces
    AuthBackend,
    PasswordHasher,
    TokenBackend,
    PermissionBackend,
    # Registry
    get_auth_backend,
    get_password_hasher,
    get_token_backend,
    get_permission_backend,
    register_auth_backend,
    register_password_hasher,
    register_token_backend,
    register_permission_backend,
    # Config
    AuthConfig,
    AuthConfigurationError,
    ConfigurationWarning,
    configure_auth,
    get_auth_config,
    # Validation helpers (preventive)
    validate_auth_configuration,
    check_middleware_configured,
    get_auth_setup_checklist,
)

# Default implementations
from core.auth.hashers import (
    PBKDF2Hasher,
    Argon2Hasher,
    BCryptHasher,
    ScryptHasher,
)

from core.auth.tokens import (
    JWTBackend,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_token,
)

from core.auth.backends import (
    ModelBackend,
    TokenAuthBackend,
)

from core.auth.permissions import (
    DefaultPermissionBackend,
    ObjectPermissionBackend,
)

# Models
from core.auth.models import (
    AbstractUser,
    AbstractUUIDUser,
    PermissionsMixin,
    Group,
    Permission,
    get_user_model,
    clear_association_table_cache,
)

# Decorators and dependencies
from core.auth.decorators import (
    HasPermission,
    IsInGroup,
    require_permission,
    require_group,
    require_superuser,
    require_staff,
    require_active,
    login_required,
)

# Schemas
from core.auth.schemas import (
    BaseRegisterInput,
    BaseLoginInput,
    RefreshTokenInput,
    ChangePasswordInput,
    TokenResponse,
    BaseUserOutput,
    MessageResponse,
)

# Views
from core.auth.views import (
    AuthViewSet,
)

# Middleware (Bug #8 Fix)
from core.auth.middleware import (
    AuthenticationMiddleware,
    OptionalAuthenticationMiddleware,
    ensure_auth_middleware,
)

__all__ = [
    # Base
    "AuthBackend",
    "PasswordHasher",
    "TokenBackend",
    "PermissionBackend",
    # Registry
    "get_auth_backend",
    "get_password_hasher",
    "get_token_backend",
    "get_permission_backend",
    "register_auth_backend",
    "register_password_hasher",
    "register_token_backend",
    "register_permission_backend",
    # Config
    "AuthConfig",
    "AuthConfigurationError",
    "ConfigurationWarning",
    "configure_auth",
    "get_auth_config",
    # Validation helpers
    "validate_auth_configuration",
    "check_middleware_configured",
    "get_auth_setup_checklist",
    # Hashers
    "PBKDF2Hasher",
    "Argon2Hasher",
    "BCryptHasher",
    "ScryptHasher",
    # Tokens
    "JWTBackend",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "verify_token",
    # Backends
    "ModelBackend",
    "TokenAuthBackend",
    # Permissions
    "DefaultPermissionBackend",
    "ObjectPermissionBackend",
    # Models
    "AbstractUser",
    "AbstractUUIDUser",
    "PermissionsMixin",
    "Group",
    "Permission",
    "get_user_model",
    "clear_association_table_cache",
    # Decorators
    "HasPermission",
    "IsInGroup",
    "require_permission",
    "require_group",
    "require_superuser",
    "require_staff",
    "require_active",
    "login_required",
    # Schemas
    "BaseRegisterInput",
    "BaseLoginInput",
    "RefreshTokenInput",
    "ChangePasswordInput",
    "TokenResponse",
    "BaseUserOutput",
    "MessageResponse",
    # Views
    "AuthViewSet",
    # Middleware
    "AuthenticationMiddleware",
    "OptionalAuthenticationMiddleware",
    "ensure_auth_middleware",
]
