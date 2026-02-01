"""
Core Framework - Django-inspired, FastAPI-powered.

A minimalist high-performance framework that combines:
- Django's productivity
- FastAPI's performance
- Full developer control

Principles:
- Zero unnecessary abstractions
- Async by default
- Strong typing (mypy friendly)
- Performance first

Enterprise Features (v0.3.0+):
- Messaging: Kafka, Redis Streams, RabbitMQ
- Background Tasks: @task, @periodic_task
- Deployment: Docker, PM2, Kubernetes generators
"""

from core.models import Model, Field
from core.serializers import InputSchema, OutputSchema, Serializer
from core.views import APIView, ViewSet, ModelViewSet, action
from core.routing import Router, AutoRouter
from core.permissions import Permission, IsAuthenticated, AllowAny, IsAdmin, IsOwner, HasRole
from core.dependencies import Depends, get_db, get_current_user
from core.config import Settings, get_settings
from core.app import CoreApp

# DateTime - SEMPRE use timezone.now() em vez de datetime.now()
from core.datetime import (
    # Classe principal - USE ESTA
    timezone,
    # Classes de tipo
    DateTime,
    Date,
    Time,
    TimeDelta,
    UTC,
    # Configuração
    configure_datetime,
    get_datetime_config,
    get_timezone,
)

# Auth - Sistema plugável de autenticação
from core.auth import (
    # Config
    AuthConfig,
    configure_auth,
    get_auth_config,
    # Interfaces (para criar backends customizados)
    AuthBackend,
    PasswordHasher,
    TokenBackend,
    PermissionBackend,
    # Registry
    register_auth_backend,
    register_password_hasher,
    register_token_backend,
    register_permission_backend,
    get_auth_backend,
    get_password_hasher,
    get_token_backend,
    get_permission_backend,
    # Hashers
    PBKDF2Hasher,
    Argon2Hasher,
    BCryptHasher,
    ScryptHasher,
    # Tokens
    JWTBackend,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_token,
    # Backends
    ModelBackend,
    TokenAuthBackend,
    # Permission Backends
    DefaultPermissionBackend,
    ObjectPermissionBackend,
    # Models
    AbstractUser,
    User,
    Group,
    Permission as AuthPermission,
    PermissionsMixin,
    # Decorators
    HasPermission,
    IsInGroup,
    require_permission,
    require_group,
    require_superuser,
    require_staff,
    require_active,
    login_required,
)

# Migrations
from core.migrations import (
    makemigrations,
    migrate,
    showmigrations,
    rollback,
    MigrationEngine,
    Migration,
)

# Validators
from core.validators import (
    ValidationError,
    UniqueValidationError,
    MultipleValidationErrors,
    UniqueValidator,
    UniqueTogetherValidator,
    ExistsValidator,
    RegexValidator,
    EmailValidator,
    URLValidator,
    SlugValidator,
    PhoneValidator,
    CPFValidator,
    CNPJValidator,
    MinLengthValidator,
    MaxLengthValidator,
    MinValueValidator,
    MaxValueValidator,
    RangeValidator,
    PasswordValidator,
    ChoiceValidator,
    FileExtensionValidator,
    FileSizeValidator,
)

__version__ = "0.3.9"
__all__ = [
    # Models
    "Model",
    "Field",
    # Serializers
    "InputSchema",
    "OutputSchema",
    "Serializer",
    # Views
    "APIView",
    "ViewSet",
    "ModelViewSet",
    "action",
    # Routing
    "Router",
    "AutoRouter",
    # Permissions
    "Permission",
    "IsAuthenticated",
    "AllowAny",
    "IsAdmin",
    "IsOwner",
    "HasRole",
    # Dependencies
    "Depends",
    "get_db",
    "get_current_user",
    # Config
    "Settings",
    "get_settings",
    # App
    "CoreApp",
    # DateTime
    "timezone",
    "DateTime",
    "Date",
    "Time",
    "TimeDelta",
    "UTC",
    "configure_datetime",
    "get_datetime_config",
    "get_timezone",
    # Auth - Config
    "AuthConfig",
    "configure_auth",
    "get_auth_config",
    # Auth - Interfaces
    "AuthBackend",
    "PasswordHasher",
    "TokenBackend",
    "PermissionBackend",
    # Auth - Registry
    "register_auth_backend",
    "register_password_hasher",
    "register_token_backend",
    "register_permission_backend",
    "get_auth_backend",
    "get_password_hasher",
    "get_token_backend",
    "get_permission_backend",
    # Auth - Hashers
    "PBKDF2Hasher",
    "Argon2Hasher",
    "BCryptHasher",
    "ScryptHasher",
    # Auth - Tokens
    "JWTBackend",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "verify_token",
    # Auth - Backends
    "ModelBackend",
    "TokenAuthBackend",
    "DefaultPermissionBackend",
    "ObjectPermissionBackend",
    # Auth - Models
    "AbstractUser",
    "User",
    "Group",
    "AuthPermission",
    "PermissionsMixin",
    # Auth - Decorators
    "HasPermission",
    "IsInGroup",
    "require_permission",
    "require_group",
    "require_superuser",
    "require_staff",
    "require_active",
    "login_required",
    # Migrations
    "makemigrations",
    "migrate",
    "showmigrations",
    "rollback",
    "MigrationEngine",
    "Migration",
    # Validators
    "ValidationError",
    "UniqueValidationError",
    "MultipleValidationErrors",
    "UniqueValidator",
    "UniqueTogetherValidator",
    "ExistsValidator",
    "RegexValidator",
    "EmailValidator",
    "URLValidator",
    "SlugValidator",
    "PhoneValidator",
    "CPFValidator",
    "CNPJValidator",
    "MinLengthValidator",
    "MaxLengthValidator",
    "MinValueValidator",
    "MaxValueValidator",
    "RangeValidator",
    "PasswordValidator",
    "ChoiceValidator",
    "FileExtensionValidator",
    "FileSizeValidator",
    # Messaging (Enterprise)
    "event",
    "consumer",
    "on_event",
    "publish_event",
    # Tasks (Enterprise)
    "task",
    "periodic_task",
]


# =============================================================================
# Enterprise Features (Lazy imports to avoid requiring optional dependencies)
# =============================================================================

def __getattr__(name: str):
    """Lazy import for enterprise features."""
    # Messaging decorators
    if name in ("event", "consumer", "on_event", "publish_event"):
        from core.messaging.decorators import event, consumer, on_event, publish_event
        return locals()[name]
    
    # Task decorators
    if name in ("task", "periodic_task"):
        from core.tasks.decorators import task, periodic_task
        return locals()[name]
    
    raise AttributeError(f"module 'core' has no attribute '{name}'")
