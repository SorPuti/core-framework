# Exceptions

Custom exception classes and error handling.

## Exception Hierarchy

```
CoreException
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
│   ├── InvalidCredentials
│   ├── InvalidToken
│   ├── TokenExpired
│   ├── PermissionDenied
│   ├── UserInactive
│   └── UserNotFound
└── BusinessException
    ├── ResourceLocked
    ├── PreconditionFailed
    ├── OperationNotAllowed
    └── QuotaExceeded

HTTPException
├── BadRequest (400)
├── Unauthorized (401)
├── Forbidden (403)
├── NotFound (404)
├── MethodNotAllowed (405)
├── Conflict (409)
├── UnprocessableEntity (422)
├── TooManyRequests (429)
├── InternalServerError (500)
└── ServiceUnavailable (503)
```

## Usage

### Validation Errors

```python
from core.exceptions import ValidationException, FieldValidationError

# Single field error
raise FieldValidationError(
    message="Invalid email format",
    field="email",
    code="invalid_email"
)

# Multiple errors
from core.exceptions import MultipleValidationErrors

errors = [
    FieldValidationError("Email required", field="email"),
    FieldValidationError("Password too short", field="password"),
]
raise MultipleValidationErrors(errors)

# Unique constraint
from core.exceptions import UniqueConstraintError

raise UniqueConstraintError(
    message="Email already exists",
    field="email"
)
```

### Database Errors

```python
from core.exceptions import DoesNotExist, MultipleObjectsReturned

# Not found
raise DoesNotExist(
    message="User not found",
    model="User",
    lookup={"id": 1}
)

# Multiple results
raise MultipleObjectsReturned(
    message="Multiple users found",
    model="User",
    count=3
)
```

### Auth Errors

```python
from core.exceptions import (
    AuthenticationFailed,
    InvalidCredentials,
    InvalidToken,
    TokenExpired,
    PermissionDenied,
)

raise AuthenticationFailed("Authentication required")
raise InvalidCredentials("Wrong email or password")
raise InvalidToken("Token is invalid")
raise TokenExpired("Token has expired")
raise PermissionDenied(
    message="Cannot edit this resource",
    permission="posts.edit",
    resource="Post"
)
```

### HTTP Errors

```python
from core.exceptions import (
    BadRequest,
    Unauthorized,
    Forbidden,
    NotFound,
    Conflict,
    TooManyRequests,
)

# 400 Bad Request
raise BadRequest("Invalid request")
raise BadRequest.with_field("email", "Invalid format")

# 401 Unauthorized
raise Unauthorized("Login required")

# 403 Forbidden
raise Forbidden("Access denied")
raise Forbidden.for_resource("Post", "delete")

# 404 Not Found
raise NotFound("Resource not found")
raise NotFound.for_model("User", id=1)

# 409 Conflict
raise Conflict("Resource already exists")
raise Conflict.duplicate("email", "user@example.com")

# 429 Too Many Requests
raise TooManyRequests(
    message="Rate limit exceeded",
    retry_after=60
)
```

### Business Errors

```python
from core.exceptions import (
    ResourceLocked,
    PreconditionFailed,
    OperationNotAllowed,
    QuotaExceeded,
)

raise ResourceLocked("Document is being edited")
raise PreconditionFailed("Version mismatch")
raise OperationNotAllowed("Cannot delete active subscription")
raise QuotaExceeded("Storage limit reached")
```

## Error Response Format

All exceptions return consistent JSON:

```json
{
  "detail": "Error message",
  "code": "error_code"
}
```

### Validation Errors

```json
{
  "detail": "Validation error",
  "code": "validation_error",
  "errors": [
    {
      "message": "Invalid email format",
      "code": "invalid_email",
      "field": "email"
    }
  ]
}
```

### Unique Constraint

```json
{
  "detail": "Email already exists",
  "code": "unique_constraint",
  "field": "email",
  "value": "user@example.com"
}
```

### Not Found

```json
{
  "detail": "User not found",
  "code": "does_not_exist"
}
```

## Exception Handlers

CoreApp auto-registers handlers for:

- Pydantic `ValidationError` → 422
- Core `ValidationError` → 422
- `MultipleValidationErrors` → 422
- `UniqueValidationError` → 409
- SQLAlchemy `IntegrityError` → 409/400/422
- SQLAlchemy `DataError` → 422
- SQLAlchemy `OperationalError` → 503
- Generic `Exception` → 500

## Custom Exception

```python
from core.exceptions import CoreException

class PaymentFailedException(CoreException):
    """Payment processing failed."""
    
    def __init__(
        self,
        message: str = "Payment failed",
        code: str = "payment_failed",
        transaction_id: str | None = None,
    ):
        super().__init__(message=message, code=code)
        self.transaction_id = transaction_id
    
    def to_dict(self) -> dict:
        data = super().to_dict()
        if self.transaction_id:
            data["transaction_id"] = self.transaction_id
        return data
```

## Custom Handler

```python
from fastapi import Request
from fastapi.responses import JSONResponse
from core import CoreApp

app = CoreApp()

@app.app.exception_handler(PaymentFailedException)
async def payment_failed_handler(request: Request, exc: PaymentFailedException):
    return JSONResponse(
        status_code=402,
        content=exc.to_dict()
    )
```

## In ViewSets

```python
from core import ModelViewSet
from core.exceptions import NotFound, Forbidden

class PostViewSet(ModelViewSet):
    model = Post
    
    async def retrieve(self, request, db, **kwargs):
        post = await self.get_object(db, **kwargs)
        
        if post.is_private and post.author_id != request.user.id:
            raise Forbidden("Cannot view private post")
        
        return await self.serialize(post)
```

## Status Codes

| Exception | Status |
|-----------|--------|
| `BadRequest` | 400 |
| `Unauthorized` | 401 |
| `Forbidden` | 403 |
| `NotFound` | 404 |
| `MethodNotAllowed` | 405 |
| `Conflict` | 409 |
| `UnprocessableEntity` | 422 |
| `ResourceLocked` | 423 |
| `TooManyRequests` | 429 |
| `InternalServerError` | 500 |
| `ServiceUnavailable` | 503 |

## Next

- [Validators](14-validators.md) — Data validation
- [ViewSets](04-viewsets.md) — CRUD endpoints
