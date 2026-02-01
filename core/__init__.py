"""
Core Framework - Django-inspired, FastAPI-powered.

Um framework minimalista de alta performance que combina:
- Produtividade do Django
- Performance do FastAPI
- Controle total do desenvolvedor

Princípios:
- Zero abstrações desnecessárias
- Async por padrão
- Tipagem forte (mypy friendly)
- Performance first
"""

from core.models import Model, Field
from core.serializers import InputSchema, OutputSchema, Serializer
from core.views import APIView, ViewSet, ModelViewSet
from core.routing import Router, AutoRouter
from core.permissions import Permission, IsAuthenticated, AllowAny, IsAdmin, IsOwner, HasRole
from core.dependencies import Depends, get_db, get_current_user, configure_auth
from core.config import Settings, get_settings
from core.app import CoreApp

# Auth
from core.auth import (
    AbstractUser,
    User,
    Group,
    Permission as AuthPermission,
    PermissionsMixin,
    HasPermission,
    IsInGroup,
    require_permission,
    require_group,
    require_superuser,
    require_staff,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_token,
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

__version__ = "0.2.12"
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
    "configure_auth",
    # Config
    "Settings",
    "get_settings",
    # App
    "CoreApp",
    # Auth
    "AbstractUser",
    "User",
    "Group",
    "AuthPermission",
    "PermissionsMixin",
    "HasPermission",
    "IsInGroup",
    "require_permission",
    "require_group",
    "require_superuser",
    "require_staff",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "verify_token",
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
]
