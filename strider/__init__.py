"""
Stride - Django-style framework for FastAPI.

Docs: https://github.com/SorPuti/stride

Quick start (Plug-and-Play):
    from strider import StrideApp
    
    app = StrideApp()  # Auto-discovery carrega tudo automaticamente

With explicit model and view:
    from strider import StrideApp, Model, ModelViewSet, Field, path
    
    class Item(Model):
        __tablename__ = "items"
        id: Mapped[int] = Field.pk()
        name: Mapped[str] = Field.string(200)
    
    class ItemViewSet(ModelViewSet):
        model = Item
    
    # Create src/apps/items/urls.py:
    # urlpatterns = [path("items", ItemViewSet)]
"""

from strider.app import StrideApp, get_application
# Auth - Sistema plugável de autenticação
from strider.auth import (
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
# Auth - ViewSet
from strider.auth.views import AuthViewSet
# Choices - Django-style enums with value and label
from strider.choices import (
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
from strider.config import (
    Settings,
    get_settings,
    configure,
    apply_settings,
    is_configured,
    reset_settings,
    auto_configure_auth,
    is_auth_configured,
)
# Database Replicas
from strider.database import (
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
from strider.citus import (
    CitusStatus,
    CITUS_OVERVIEW_URL,
    probe_citus_on_engine,
    asyncpg_connect_args_from_settings,
    merge_asyncpg_connect_args,
    is_postgres_async_url,
)
# DateTime - SEMPRE use timezone.now() em vez de datetime.now()
from strider.datetime import (
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
from strider.dependencies import Depends, get_db, get_current_user, set_session_factory
# Exceptions - Centralized exception classes
from strider.exceptions import (
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
    StridePathParamBindingError,
)
# Advanced Fields (UUID7, JSON, FileField, etc.)
from strider.fields import (
    uuid7,
    uuid7_str,
    AdaptiveJSON,
    AdvancedField,
    FileField,
    FieldFile,
)
from strider.logger import logger, get_logger, configure_logging
# Middleware - Sistema Django-style
from strider.middleware import (
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
# Migrations
from strider.migrations import (
    makemigrations,
    migrate,
    showmigrations,
    rollback,
    MigrationEngine,
    Migration,
)
from strider.models import (
    Model,
    UUIDModel,
    Field,
    SoftDeleteMixin,
    SoftDeleteManager,
    TenantSoftDeleteManager,
)
from strider.permissions import Permission, IsAuthenticated, AllowAny, IsAdmin, IsOwner, HasRole
# Advanced QuerySets
from strider.querysets import (
    SoftDeleteQuerySet,
    TenantQuerySet,
    TenantSoftDeleteQuerySet,
)
from strider.realtime import WebSocketView, SSEView, Channel, sse_response
from strider.pushpin import (
    grip_stream_headers,
    grip_stream_response,
    grip_response_hold_headers,
    merge_grip_into_response_headers,
    qualify_channel,
    qualify_channel_from_settings,
    PushpinPublishError,
    build_http_stream_item,
    publish_pushpin_items,
    publish_http_stream,
)
# Relations - Django-like relationship helpers
from strider.relations import (
    Rel,
    AssociationTable,
)
from strider.routing import Router, AutoRouter
from strider.serializers import (
    InputSchema,
    OutputSchema,
    OrmPrimaryKey,
    Serializer,
    ModelSerializer,
    UnifiedModelSerializer,
    build_schemas_from_model,
    PaginatedResponse,
    ErrorResponse,
    SuccessResponse,
    DeleteResponse,
    ValidationErrorResponse,
    NotFoundResponse,
    ConflictResponse,
    DatabaseIntegrityResponse,
    computed_orm_field,
)
# Storage - File storage (local or GCS with signed URLs)
from strider.storage import (
    save_file,
    delete_file,
    get_file_url,
    file_exists,
    get_storage_file_fields,
    collect_file_paths,
    StorageFile,
    storage_file_property,
)
# Multi-Tenancy
from strider.tenancy import (
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
from strider.urls import path, include, URLPattern, URLInclude
# Validation
from strider.validation import (
    SchemaModelValidator,
    SchemaModelMismatchError,
    ValidationWarning,
    validate_schema,
    validate_all_viewsets,
)
# Validators
from strider.validators import (
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
from strider.views import (
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

__version__ = "0.18.77"
__all__ = [
    # Logger - use diretamente: from strider import logger
    "logger",
    "get_logger",
    "configure_logging",
    # Models
    "Model",
    "UUIDModel",
    "Field",
    "SoftDeleteMixin",
    "SoftDeleteManager",
    "TenantSoftDeleteManager",
    # Serializers
    "InputSchema",
    "OutputSchema",
    "OrmPrimaryKey",
    "Serializer",
    "ModelSerializer",
    "UnifiedModelSerializer",
    "build_schemas_from_model",
    "PaginatedResponse",
    "ErrorResponse",
    "SuccessResponse",
    "DeleteResponse",
    "ValidationErrorResponse",
    "NotFoundResponse",
    "ConflictResponse",
    "DatabaseIntegrityResponse",
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
    # Real-time
    "WebSocketView",
    "SSEView",
    "Channel",
    "sse_response",
    # Pushpin (GRIP edge proxy)
    "grip_stream_headers",
    "grip_stream_response",
    "grip_response_hold_headers",
    "merge_grip_into_response_headers",
    "qualify_channel",
    "qualify_channel_from_settings",
    "PushpinPublishError",
    "build_http_stream_item",
    "publish_pushpin_items",
    "publish_http_stream",
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
    "CitusStatus",
    "CITUS_OVERVIEW_URL",
    "probe_citus_on_engine",
    "asyncpg_connect_args_from_settings",
    "merge_asyncpg_connect_args",
    "is_postgres_async_url",
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
    # Exceptions - Routing
    "StridePathParamBindingError",
]


# =============================================================================
# Enterprise Features (Lazy imports to avoid requiring optional dependencies)
# =============================================================================

def __getattr__(name: str):
    """Lazy import for enterprise features."""
    # Messaging decorators
    if name in ("event", "consumer", "on_event", "publish_event"):
        from strider.messaging.decorators import event, consumer, on_event, publish_event
        return locals()[name]
    
    # Task decorators
    if name in ("task", "periodic_task"):
        from strider.tasks.decorators import task, periodic_task
        return locals()[name]
    
    raise AttributeError(f"module 'core' has no attribute '{name}'")
