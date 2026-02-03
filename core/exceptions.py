"""
Centralized exception classes for the Core Framework.

This module provides a comprehensive set of exceptions for handling errors
in a consistent and informative way across the application.

Exception Hierarchy:
    CoreException (base)
    ├── ValidationException
    │   ├── FieldValidationError
    │   ├── UniqueConstraintError
    │   └── MultipleValidationErrors
    ├── DatabaseException
    │   ├── DoesNotExist
    │   ├── MultipleObjectsReturned
    │   ├── IntegrityError
    │   └── ConnectionError
    ├── AuthException
    │   ├── AuthenticationFailed
    │   ├── InvalidToken
    │   ├── TokenExpired
    │   ├── PermissionDenied
    │   └── UserInactive
    └── HTTPException (convenience wrappers)
        ├── BadRequest (400)
        ├── Unauthorized (401)
        ├── Forbidden (403)
        ├── NotFound (404)
        ├── MethodNotAllowed (405)
        ├── Conflict (409)
        ├── UnprocessableEntity (422)
        └── InternalServerError (500)

Example:
    from core.exceptions import NotFound, ValidationException, PermissionDenied
    
    # Raise HTTP exceptions
    raise NotFound("User not found")
    raise NotFound.with_detail(resource="User", id=123)
    
    # Raise validation errors
    raise ValidationException("Invalid email format", field="email")
    
    # Raise auth errors
    raise PermissionDenied("You cannot delete this resource")
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException as FastAPIHTTPException
from fastapi import status


# =============================================================================
# Base Exception
# =============================================================================

class CoreException(Exception):
    """
    Base exception for all Core Framework exceptions.
    
    Attributes:
        message: Human-readable error message
        code: Machine-readable error code
        details: Additional error details
    """
    
    message: str = "An error occurred"
    code: str = "error"
    
    def __init__(
        self,
        message: str | None = None,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.details = details or {}
        super().__init__(self.message)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for JSON response."""
        result = {
            "message": self.message,
            "code": self.code,
        }
        if self.details:
            result["details"] = self.details
        return result
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(message={self.message!r}, code={self.code!r})"


# =============================================================================
# Validation Exceptions
# =============================================================================

class ValidationException(CoreException):
    """
    Base exception for validation errors.
    
    Use for field-level validation failures.
    
    Example:
        raise ValidationException(
            "Email format is invalid",
            field="email",
            code="invalid_email",
        )
    """
    
    message = "Validation error"
    code = "validation_error"
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def __init__(
        self,
        message: str | None = None,
        field: str | None = None,
        code: str | None = None,
        value: Any = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code, details)
        self.field = field
        self.value = value
    
    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        if self.field:
            result["field"] = self.field
        if self.value is not None:
            result["value"] = self.value
        return result


class FieldValidationError(ValidationException):
    """Validation error for a specific field."""
    
    code = "field_validation_error"
    
    def __init__(
        self,
        field: str,
        message: str,
        code: str | None = None,
        value: Any = None,
    ) -> None:
        super().__init__(message=message, field=field, code=code, value=value)


class UniqueConstraintError(ValidationException):
    """
    Raised when a unique constraint is violated.
    
    Example:
        raise UniqueConstraintError(
            field="email",
            value="user@example.com",
        )
    """
    
    message = "Value already exists"
    code = "unique_constraint"
    status_code = status.HTTP_409_CONFLICT
    
    def __init__(
        self,
        field: str,
        value: Any = None,
        message: str | None = None,
    ) -> None:
        msg = message or f"A record with this {field} already exists"
        super().__init__(message=msg, field=field, value=value)


class MultipleValidationErrors(ValidationException):
    """
    Container for multiple validation errors.
    
    Example:
        errors = [
            FieldValidationError("email", "Invalid format"),
            FieldValidationError("password", "Too short"),
        ]
        raise MultipleValidationErrors(errors)
    """
    
    message = "Multiple validation errors"
    code = "multiple_validation_errors"
    
    def __init__(self, errors: list[ValidationException]) -> None:
        super().__init__()
        self.errors = errors
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "code": self.code,
            "errors": [e.to_dict() for e in self.errors],
        }


# =============================================================================
# Database Exceptions
# =============================================================================

class DatabaseException(CoreException):
    """Base exception for database-related errors."""
    
    message = "Database error"
    code = "database_error"


class DoesNotExist(DatabaseException):
    """
    Raised when a requested record does not exist.
    
    Example:
        user = await User.objects.get(id=999)
        # Raises: DoesNotExist("User with id=999 does not exist")
    """
    
    message = "Record does not exist"
    code = "does_not_exist"
    status_code = status.HTTP_404_NOT_FOUND
    
    def __init__(
        self,
        model: str | None = None,
        lookup: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> None:
        if message is None and model:
            if lookup:
                lookup_str = ", ".join(f"{k}={v}" for k, v in lookup.items())
                message = f"{model} with {lookup_str} does not exist"
            else:
                message = f"{model} does not exist"
        super().__init__(message=message, details={"model": model, "lookup": lookup})
        self.model = model
        self.lookup = lookup


class MultipleObjectsReturned(DatabaseException):
    """
    Raised when get() returns multiple objects.
    
    Example:
        user = await User.objects.get(is_active=True)
        # Raises: MultipleObjectsReturned if multiple active users exist
    """
    
    message = "Multiple objects returned"
    code = "multiple_objects_returned"
    
    def __init__(
        self,
        model: str | None = None,
        count: int | None = None,
        message: str | None = None,
    ) -> None:
        if message is None and model:
            message = f"get() returned multiple {model} objects"
            if count:
                message += f" ({count} found)"
        super().__init__(message=message)
        self.model = model
        self.count = count


class IntegrityError(DatabaseException):
    """
    Raised when a database integrity constraint is violated.
    
    Wraps SQLAlchemy IntegrityError with more context.
    """
    
    message = "Database integrity error"
    code = "integrity_error"
    status_code = status.HTTP_409_CONFLICT
    
    def __init__(
        self,
        message: str | None = None,
        constraint: str | None = None,
        table: str | None = None,
    ) -> None:
        super().__init__(message=message, details={"constraint": constraint, "table": table})
        self.constraint = constraint
        self.table = table


class ConnectionError(DatabaseException):
    """Raised when database connection fails."""
    
    message = "Database connection failed"
    code = "connection_error"
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE


# =============================================================================
# Authentication Exceptions
# =============================================================================

class AuthException(CoreException):
    """Base exception for authentication/authorization errors."""
    
    message = "Authentication error"
    code = "auth_error"
    status_code = status.HTTP_401_UNAUTHORIZED


class AuthenticationFailed(AuthException):
    """
    Raised when authentication fails.
    
    Example:
        raise AuthenticationFailed("Invalid email or password")
    """
    
    message = "Authentication failed"
    code = "authentication_failed"


class InvalidCredentials(AuthException):
    """Raised when provided credentials are invalid."""
    
    message = "Invalid credentials"
    code = "invalid_credentials"


class InvalidToken(AuthException):
    """
    Raised when a token is invalid or malformed.
    
    Example:
        raise InvalidToken("Token signature is invalid")
    """
    
    message = "Invalid token"
    code = "invalid_token"


class TokenExpired(AuthException):
    """
    Raised when a token has expired.
    
    Example:
        raise TokenExpired("Access token has expired")
    """
    
    message = "Token has expired"
    code = "token_expired"


class PermissionDenied(AuthException):
    """
    Raised when user lacks required permissions.
    
    Example:
        raise PermissionDenied("You do not have permission to delete this resource")
    """
    
    message = "Permission denied"
    code = "permission_denied"
    status_code = status.HTTP_403_FORBIDDEN
    
    def __init__(
        self,
        message: str | None = None,
        permission: str | None = None,
        resource: str | None = None,
    ) -> None:
        super().__init__(message=message, details={"permission": permission, "resource": resource})
        self.permission = permission
        self.resource = resource


class UserInactive(AuthException):
    """Raised when an inactive user attempts to authenticate."""
    
    message = "User account is inactive"
    code = "user_inactive"


class UserNotFound(AuthException):
    """Raised when user is not found during authentication."""
    
    message = "User not found"
    code = "user_not_found"


# =============================================================================
# HTTP Exception Wrappers
# =============================================================================

class HTTPException(FastAPIHTTPException):
    """
    Enhanced HTTP exception with additional features.
    
    Provides convenience class methods for common HTTP errors.
    
    Example:
        raise HTTPException(404, "User not found")
        raise HTTPException.not_found("User", id=123)
    """
    
    def __init__(
        self,
        status_code: int,
        detail: str | None = None,
        headers: dict[str, str] | None = None,
        code: str | None = None,
    ) -> None:
        # Build detail dict if code is provided
        if code and detail:
            detail_dict = {"message": detail, "code": code}
            super().__init__(status_code=status_code, detail=detail_dict, headers=headers)
        else:
            super().__init__(status_code=status_code, detail=detail, headers=headers)


class BadRequest(HTTPException):
    """
    400 Bad Request exception.
    
    Use when the request is malformed or contains invalid data.
    
    Example:
        raise BadRequest("Invalid JSON payload")
        raise BadRequest.with_field("email", "Invalid format")
    """
    
    def __init__(self, detail: str = "Bad request", code: str = "bad_request") -> None:
        super().__init__(status.HTTP_400_BAD_REQUEST, detail, code=code)
    
    @classmethod
    def with_field(cls, field: str, message: str) -> "BadRequest":
        """Create BadRequest with field context."""
        return cls(f"{field}: {message}", code=f"invalid_{field}")


class Unauthorized(HTTPException):
    """
    401 Unauthorized exception.
    
    Use when authentication is required but not provided or invalid.
    
    Example:
        raise Unauthorized("Invalid or expired token")
    """
    
    def __init__(
        self,
        detail: str = "Authentication required",
        code: str = "unauthorized",
        headers: dict[str, str] | None = None,
    ) -> None:
        # Add WWW-Authenticate header for proper 401 response
        if headers is None:
            headers = {"WWW-Authenticate": "Bearer"}
        super().__init__(status.HTTP_401_UNAUTHORIZED, detail, headers=headers, code=code)


class Forbidden(HTTPException):
    """
    403 Forbidden exception.
    
    Use when user is authenticated but lacks permission.
    
    Example:
        raise Forbidden("You cannot access this resource")
        raise Forbidden.for_resource("Post", action="delete")
    """
    
    def __init__(self, detail: str = "Access forbidden", code: str = "forbidden") -> None:
        super().__init__(status.HTTP_403_FORBIDDEN, detail, code=code)
    
    @classmethod
    def for_resource(cls, resource: str, action: str = "access") -> "Forbidden":
        """Create Forbidden for a specific resource action."""
        return cls(f"You do not have permission to {action} this {resource}", code="permission_denied")


class NotFound(HTTPException):
    """
    404 Not Found exception.
    
    Use when a requested resource does not exist.
    
    Example:
        raise NotFound("User not found")
        raise NotFound.for_model("User", id=123)
    """
    
    def __init__(self, detail: str = "Resource not found", code: str = "not_found") -> None:
        super().__init__(status.HTTP_404_NOT_FOUND, detail, code=code)
    
    @classmethod
    def for_model(cls, model: str, **lookup: Any) -> "NotFound":
        """Create NotFound for a model lookup."""
        if lookup:
            lookup_str = ", ".join(f"{k}={v}" for k, v in lookup.items())
            return cls(f"{model} with {lookup_str} not found", code=f"{model.lower()}_not_found")
        return cls(f"{model} not found", code=f"{model.lower()}_not_found")


class MethodNotAllowed(HTTPException):
    """
    405 Method Not Allowed exception.
    
    Use when HTTP method is not supported for the endpoint.
    
    Example:
        raise MethodNotAllowed("GET", allowed=["POST", "PUT"])
    """
    
    def __init__(
        self,
        method: str,
        allowed: list[str] | None = None,
        detail: str | None = None,
    ) -> None:
        msg = detail or f"Method {method} not allowed"
        headers = {}
        if allowed:
            headers["Allow"] = ", ".join(allowed)
            msg += f". Allowed: {', '.join(allowed)}"
        super().__init__(status.HTTP_405_METHOD_NOT_ALLOWED, msg, headers=headers or None, code="method_not_allowed")


class Conflict(HTTPException):
    """
    409 Conflict exception.
    
    Use when request conflicts with current state (e.g., duplicate).
    
    Example:
        raise Conflict("User with this email already exists")
        raise Conflict.duplicate("email", "user@example.com")
    """
    
    def __init__(self, detail: str = "Resource conflict", code: str = "conflict") -> None:
        super().__init__(status.HTTP_409_CONFLICT, detail, code=code)
    
    @classmethod
    def duplicate(cls, field: str, value: Any = None) -> "Conflict":
        """Create Conflict for duplicate value."""
        if value:
            return cls(f"A record with {field}={value!r} already exists", code="duplicate")
        return cls(f"A record with this {field} already exists", code="duplicate")


class UnprocessableEntity(HTTPException):
    """
    422 Unprocessable Entity exception.
    
    Use for validation errors that prevent processing.
    
    Example:
        raise UnprocessableEntity("Invalid data format")
        raise UnprocessableEntity.validation_error("email", "Invalid format")
    """
    
    def __init__(self, detail: str = "Validation error", code: str = "validation_error") -> None:
        super().__init__(status.HTTP_422_UNPROCESSABLE_ENTITY, detail, code=code)
    
    @classmethod
    def validation_error(cls, field: str, message: str) -> "UnprocessableEntity":
        """Create UnprocessableEntity for field validation."""
        return cls(f"{field}: {message}", code=f"invalid_{field}")


class TooManyRequests(HTTPException):
    """
    429 Too Many Requests exception.
    
    Use for rate limiting.
    
    Example:
        raise TooManyRequests(retry_after=60)
    """
    
    def __init__(
        self,
        detail: str = "Too many requests",
        retry_after: int | None = None,
    ) -> None:
        headers = {}
        if retry_after:
            headers["Retry-After"] = str(retry_after)
            detail += f". Retry after {retry_after} seconds"
        super().__init__(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail,
            headers=headers or None,
            code="rate_limited",
        )


class InternalServerError(HTTPException):
    """
    500 Internal Server Error exception.
    
    Use for unexpected server errors.
    
    Example:
        raise InternalServerError("An unexpected error occurred")
    """
    
    def __init__(self, detail: str = "Internal server error", code: str = "internal_error") -> None:
        super().__init__(status.HTTP_500_INTERNAL_SERVER_ERROR, detail, code=code)


class ServiceUnavailable(HTTPException):
    """
    503 Service Unavailable exception.
    
    Use when service is temporarily unavailable.
    
    Example:
        raise ServiceUnavailable("Database is temporarily unavailable")
    """
    
    def __init__(
        self,
        detail: str = "Service temporarily unavailable",
        retry_after: int | None = None,
    ) -> None:
        headers = {}
        if retry_after:
            headers["Retry-After"] = str(retry_after)
        super().__init__(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail,
            headers=headers or None,
            code="service_unavailable",
        )


# =============================================================================
# Business Logic Exceptions
# =============================================================================

class BusinessException(CoreException):
    """
    Base exception for business logic errors.
    
    Use for domain-specific errors that don't fit other categories.
    
    Example:
        class InsufficientFunds(BusinessException):
            message = "Insufficient funds for this transaction"
            code = "insufficient_funds"
    """
    
    message = "Business logic error"
    code = "business_error"
    status_code = status.HTTP_400_BAD_REQUEST


class ResourceLocked(BusinessException):
    """Raised when a resource is locked and cannot be modified."""
    
    message = "Resource is locked"
    code = "resource_locked"
    status_code = status.HTTP_423_LOCKED


class PreconditionFailed(BusinessException):
    """Raised when a precondition for an operation is not met."""
    
    message = "Precondition failed"
    code = "precondition_failed"
    status_code = status.HTTP_412_PRECONDITION_FAILED


class OperationNotAllowed(BusinessException):
    """Raised when an operation is not allowed in current state."""
    
    message = "Operation not allowed"
    code = "operation_not_allowed"
    status_code = status.HTTP_400_BAD_REQUEST


class QuotaExceeded(BusinessException):
    """Raised when a quota or limit is exceeded."""
    
    message = "Quota exceeded"
    code = "quota_exceeded"
    status_code = status.HTTP_429_TOO_MANY_REQUESTS


# =============================================================================
# Configuration Exceptions
# =============================================================================

class ConfigurationError(CoreException):
    """
    Raised when there's a configuration error.
    
    Example:
        raise ConfigurationError("DATABASE_URL is not set")
    """
    
    message = "Configuration error"
    code = "configuration_error"


class MissingDependency(ConfigurationError):
    """
    Raised when a required dependency is not installed.
    
    Example:
        raise MissingDependency("bcrypt", "pip install bcrypt")
    """
    
    message = "Missing dependency"
    code = "missing_dependency"
    
    def __init__(self, package: str, install_cmd: str | None = None) -> None:
        msg = f"Required package '{package}' is not installed"
        if install_cmd:
            msg += f". Install with: {install_cmd}"
        super().__init__(message=msg, details={"package": package, "install_cmd": install_cmd})


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Base
    "CoreException",
    
    # Validation
    "ValidationException",
    "FieldValidationError",
    "UniqueConstraintError",
    "MultipleValidationErrors",
    
    # Database
    "DatabaseException",
    "DoesNotExist",
    "MultipleObjectsReturned",
    "IntegrityError",
    "ConnectionError",
    
    # Auth
    "AuthException",
    "AuthenticationFailed",
    "InvalidCredentials",
    "InvalidToken",
    "TokenExpired",
    "PermissionDenied",
    "UserInactive",
    "UserNotFound",
    
    # HTTP
    "HTTPException",
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
    
    # Business
    "BusinessException",
    "ResourceLocked",
    "PreconditionFailed",
    "OperationNotAllowed",
    "QuotaExceeded",
    
    # Configuration
    "ConfigurationError",
    "MissingDependency",
]
