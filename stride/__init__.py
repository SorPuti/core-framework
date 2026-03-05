"""
Stride - Django-style framework for FastAPI.

Docs: https://github.com/SorPuti/stride

Quick start (Plug-and-Play):
    from stride import StrideApp
    
    app = StrideApp()  # Auto-discovery carrega tudo automaticamente

With explicit model and view:
    from stride import StrideApp, Model, ModelViewSet, Field, path
    
    class Item(Model):
        __tablename__ = "items"
        id: Mapped[int] = Field.pk()
        name: Mapped[str] = Field.string(200)
    
    class ItemViewSet(ModelViewSet):
        model = Item
    
    # Create src/apps/items/urls.py:
    # urlpatterns = [path("items", ItemViewSet)]
"""

from stride.models import Model, Field, SoftDeleteMixin, SoftDeleteManager, TenantSoftDeleteManager
from stride.serializers import (
    InputSchema,
    OutputSchema,
    Serializer,
    PaginatedResponse,
    ErrorResponse,
    SuccessResponse,
    DeleteResponse,
    ValidationErrorResponse,
    NotFoundResponse,
    ConflictResponse,
)
from stride.views import (
    APIView,
    ViewSet,
    ModelViewSet,
    ReadOnlyModelViewSet,
    CreateModelViewSet,
    ListModelViewSet,
    ListCreateModelViewSet,
    RetrieveUpdateModelViewSet,
    RetrieveDestroyModelViewSet,
    RetrieveUpdateDestroyModelViewSet,
    SearchModelViewSet,
    BulkModelViewSet,
    action,
)
from stride.routing import Router, AutoRouter
from stride.urls import path, include, URLPattern, URLInclude
from stride.realtime import WebSocketView, SSEView, Channel, sse_response
from stride.permissions import Permission, IsAuthenticated, AllowAny, IsAdmin, IsOwner, HasRole
from stride.dependencies import Depends, get_db, get_current_user, set_session_factory
from stride.config import (
    Settings, 
    get_settings, 
    configure, 
    apply_settings,
    is_configured, 
    reset_settings,
    auto_configure_auth,
    is_auth_configured,
)
from stride.app import StrideApp, get_application

# Validation
from stride.validation import (
    SchemaModelValidator,
    SchemaModelMismatchError,
    ValidationWarning,
    validate_schema,
    validate_all_viewsets,
)

# Advanced Fields (UUID7, JSON, FileField, etc.)
from stride.fields import (
    uuid7,
    uuid7_str,
    AdaptiveJSON,
    AdvancedField,
    FileField,
    FieldFile,
)

# Multi-Tenancy
from stride.tenancy import (
    set_tenant,
    get_tenant,
    require_tenant,
    clear_tenant,
    TenantMixin,
    FlexibleTenantMixin,
    TenantMiddleware,
    tenant_context,
    get_tenant_dependency,
)

# Database Replicas
from stride.database import (
    DatabaseSession,
    init_db,
    init_replicas,
    close_replicas,
    get_db_replicas,
    get_write_db,
    get_read_db,
    DBSession,
    WriteSession,
    ReadSession,
)

# Advanced QuerySets
from stride.querysets import (
    SoftDeleteQuerySet,
    TenantQuerySet,
    TenantSoftDeleteQuerySet,
)

# DateTime - SEMPRE use timezone.now() em vez de datetime.now()
from stride.datetime import (
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

# Middleware - Sistema Django-style
from stride.middleware import (
    ASGIMiddleware,
    BaseMiddleware,
    configure_middleware,
    register_middleware,
    apply_middlewares,
    get_middleware_stack_info,
    print_middleware_stack,
    # Pre-built middlewares (Pure ASGI)
    TimingMiddleware,
    RequestIDMiddleware,
    LoggingMiddleware,
    MaintenanceModeMiddleware,
    SecurityHeadersMiddleware,
)

# Auth - ViewSet
from stride.auth.views import AuthViewSet

# Auth - Sistema plugável de autenticação
from stride.auth import (
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
    AbstractUUIDUser,
    Group,
    Permission as AuthPermission,
    PermissionsMixin,
    get_user_model,
    # Decorators
    HasPermission,
    IsInGroup,
    require_permission,
    require_group,
    require_superuser,
    require_staff,
    require_active,
    login_required,
    # Middleware
    AuthenticationMiddleware,
    OptionalAuthenticationMiddleware,
)

# Migrations
from stride.migrations import (
    makemigrations,
    migrate,
    showmigrations,
    rollback,
    MigrationEngine,
    Migration,
)

# Validators
from stride.validators import (
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

# Relations - Django-like relationship helpers
from stride.relations import (
    Rel,
    AssociationTable,
)

# Choices - Django-style enums with value and label
from stride.choices import (
    Choices,
    TextChoices,
    IntegerChoices,
    # Common choices
    ThemeOptions,
    CommonStatus,
    PublishStatus,
    OrderStatus,
    PaymentStatus,
    TaskPriority,
    Weekday,
    Month,
    Gender,
    Visibility,
)

# Storage - File storage (local or GCS with signed URLs)
from stride.storage import (
    save_file,
    delete_file,
    get_file_url,
    file_exists,
    get_storage_file_fields,
    collect_file_paths,
    StorageFile,
    storage_file_property,
)

# Exceptions - Centralized exception classes
from stride.exceptions import (
    # Base
    StrideException,
    CoreException,
    # Validation
    ValidationException,
    FieldValidationError,
    UniqueConstraintError,
    # Database
    DatabaseException,
    DoesNotExist,
    MultipleObjectsReturned,
    IntegrityError,
    # Auth
    AuthException,
    AuthenticationFailed,
    InvalidCredentials,
    InvalidToken,
    TokenExpired,
    PermissionDenied,
    UserInactive,
    UserNotFound,
    # HTTP
    BadRequest,
    Unauthorized,
    Forbidden,
    NotFound,
    MethodNotAllowed,
    Conflict,
    UnprocessableEntity,
    TooManyRequests,
    InternalServerError,
    ServiceUnavailable,
    # Business
    BusinessException,
    ResourceLocked,
    PreconditionFailed,
    OperationNotAllowed,
    QuotaExceeded,
    # Configuration
    ConfigurationError,
    MissingDependency,
)

__version__ = "0.17.60"
__all__ = [
    # Models
    "Model",
    "Field",
    "SoftDeleteMixin",
    "SoftDeleteManager",
    "TenantSoftDeleteManager",
    # Serializers
    "InputSchema",
    "OutputSchema",
    "Serializer",
    "PaginatedResponse",
    "ErrorResponse",
    "SuccessResponse",
    "DeleteResponse",
    "ValidationErrorResponse",
    "NotFoundResponse",
    "ConflictResponse",
    # Views
    "APIView",
    "ViewSet",
    "ModelViewSet",
    "ReadOnlyModelViewSet",
    "CreateModelViewSet",
    "ListModelViewSet",
    "ListCreateModelViewSet",
    "RetrieveUpdateModelViewSet",
    "RetrieveDestroyModelViewSet",
    "RetrieveUpdateDestroyModelViewSet",
    "SearchModelViewSet",
    "BulkModelViewSet",
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
    "set_session_factory",
    # Config
    "Settings",
    "get_settings",
    "configure",
    "apply_settings",
    "is_configured",
    "reset_settings",
    "auto_configure_auth",
    "is_auth_configured",
    # App
    "StrideApp",
    "get_application",
    # Middleware
    "ASGIMiddleware",
    "BaseMiddleware",
    "configure_middleware",
    "register_middleware",
    "apply_middlewares",
    "get_middleware_stack_info",
    "print_middleware_stack",
    "TimingMiddleware",
    "RequestIDMiddleware",
    "LoggingMiddleware",
    "MaintenanceModeMiddleware",
    "SecurityHeadersMiddleware",
    # Advanced Fields
    "uuid7",
    "uuid7_str",
    "AdaptiveJSON",
    "AdvancedField",
    "FileField",
    "FieldFile",
    # Multi-Tenancy
    "set_tenant",
    "get_tenant",
    "require_tenant",
    "clear_tenant",
    "TenantMixin",
    "FlexibleTenantMixin",
    "TenantMiddleware",
    "tenant_context",
    "get_tenant_dependency",
    # Database Replicas
    "DatabaseSession",
    "init_db",
    "init_replicas",
    "close_replicas",
    "get_db_replicas",
    "get_write_db",
    "get_read_db",
    "DBSession",
    "WriteSession",
    "ReadSession",
    # Advanced QuerySets
    "SoftDeleteQuerySet",
    "TenantQuerySet",
    "TenantSoftDeleteQuerySet",
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
    # Auth - ViewSet
    "AuthViewSet",
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
    "AbstractUUIDUser",
    "Group",
    "AuthPermission",
    "PermissionsMixin",
    "get_user_model",
    # Auth - Middleware
    "AuthenticationMiddleware",
    "OptionalAuthenticationMiddleware",
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
    # Relations
    "Rel",
    "AssociationTable",
    # Choices
    "Choices",
    "TextChoices",
    "IntegerChoices",
    "ThemeOptions",
    "CommonStatus",
    "PublishStatus",
    "OrderStatus",
    "PaymentStatus",
    "TaskPriority",
    "Weekday",
    "Month",
    "Gender",
    "Visibility",
    # Storage
    "save_file",
    "delete_file",
    "get_file_url",
    "file_exists",
    "get_storage_file_fields",
    "collect_file_paths",
    "StorageFile",
    "storage_file_property",
    # Exceptions - Base
    "StrideException",
    "CoreException",
    # Exceptions - Validation
    "ValidationException",
    "FieldValidationError",
    "UniqueConstraintError",
    # Exceptions - Database
    "DatabaseException",
    "DoesNotExist",
    "MultipleObjectsReturned",
    "IntegrityError",
    # Exceptions - Auth
    "AuthException",
    "AuthenticationFailed",
    "InvalidCredentials",
    "InvalidToken",
    "TokenExpired",
    "PermissionDenied",
    "UserInactive",
    "UserNotFound",
    # Exceptions - HTTP
    "BadRequest",
    "Unauthorized",
    "Forbidden",
    "NotFound",
    "MethodNotAllowed",
    "Conflict",
    "UnprocessableEntity",
    "TooManyRequests",
    "InternalServerError",
    "ServiceUnavailable",
    # Exceptions - Business
    "BusinessException",
    "ResourceLocked",
    "PreconditionFailed",
    "OperationNotAllowed",
    "QuotaExceeded",
    # Exceptions - Configuration
    "ConfigurationError",
    "MissingDependency",
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
        from stride.messaging.decorators import event, consumer, on_event, publish_event
        return locals()[name]
    
    # Task decorators
    if name in ("task", "periodic_task"):
        from stride.tasks.decorators import task, periodic_task
        return locals()[name]
    
    raise AttributeError(f"module 'core' has no attribute '{name}'")
