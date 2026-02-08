# Middleware

Request/response processing hooks.

## Configuration

**Important:** Register middleware via settings, not directly on FastAPI.

```python
# src/settings.py
class AppSettings(Settings):
    middleware: list[str] = [
        "timing",
        "request_id",
        "auth",
        "myapp.middleware.CustomMiddleware",
    ]
```

Or via CoreApp:

```python
app = CoreApp(
    middleware=[
        "timing",
        "auth",
        ("logging", {"log_body": True}),  # With kwargs
    ]
)
```

## Built-in Middleware

| Shortcut | Class | Description |
|----------|-------|-------------|
| `"timing"` | `TimingMiddleware` | Adds `X-Response-Time` header |
| `"request_id"` | `RequestIDMiddleware` | Adds unique request ID |
| `"logging"` | `LoggingMiddleware` | Logs requests/responses |
| `"auth"` | `AuthenticationMiddleware` | JWT authentication |
| `"optional_auth"` | `OptionalAuthenticationMiddleware` | Optional JWT auth |
| `"tenant"` | `TenantMiddleware` | Multi-tenant context |
| `"security_headers"` | `SecurityHeadersMiddleware` | Security headers |
| `"maintenance"` | `MaintenanceModeMiddleware` | Maintenance mode |
| `"cors"` | `CORSMiddleware` | CORS handling |
| `"gzip"` | `GZipMiddleware` | Response compression |

## Execution Order

Middleware executes in list order:

```
Request:
  timing.before_request()      # First (outermost)
    → auth.before_request()
      → logging.before_request()  # Last (innermost)
        → [VIEW]
      ← logging.after_response()
    ← auth.after_response()
  ← timing.after_response()
Response
```

## Custom Middleware

### ASGIMiddleware (Recommended)

```python
# src/middleware.py
from core.middleware import ASGIMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import Scope

class RateLimitMiddleware(ASGIMiddleware):
    name = "RateLimitMiddleware"
    order = 5  # Lower = executes first
    
    # Optional: path filtering
    exclude_paths = ["/health", "/docs"]
    include_paths = []  # Empty = all paths
    
    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.limit = requests_per_minute
    
    async def before_request(
        self, scope: Scope, request: Request
    ) -> Response | None:
        """Called before request. Return Response to short-circuit."""
        client_ip = request.client.host
        
        if await self.is_rate_limited(client_ip):
            return Response(
                content='{"detail": "Too many requests"}',
                status_code=429,
                media_type="application/json"
            )
        
        # Continue to next middleware
        return None
    
    async def after_response(
        self,
        scope: Scope,
        request: Request,
        status_code: int,
        response_headers: list[tuple[bytes, bytes]],
    ) -> None:
        """Called after response. Can modify headers in-place."""
        response_headers.append((b"x-rate-limit", b"60"))
    
    async def on_error(
        self, scope: Scope, request: Request, exc: Exception
    ) -> Response | None:
        """Called on exception. Return Response or None to re-raise."""
        return None
```

### Register Custom Middleware

```python
# src/settings.py
class AppSettings(Settings):
    middleware: list[str] = [
        "timing",
        ("src.middleware.RateLimitMiddleware", {"requests_per_minute": 100}),
        "auth",
    ]
```

Or programmatically:

```python
from core.middleware import register_middleware

register_middleware(
    "src.middleware.RateLimitMiddleware",
    kwargs={"requests_per_minute": 100}
)
```

## Middleware Options

### TimingMiddleware

```python
middleware = [
    "timing",  # Adds X-Response-Time header
]
```

### RequestIDMiddleware

```python
middleware = [
    ("request_id", {"header_name": "X-Request-ID"}),
]
```

### LoggingMiddleware

```python
middleware = [
    ("logging", {
        "log_body": False,
        "log_headers": False,
        "logger_name": "core.requests",
    }),
]
```

### SecurityHeadersMiddleware

```python
middleware = [
    ("security_headers", {
        "headers": {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
        },
        "enable_hsts": True,
        "hsts_max_age": 31536000,
    }),
]
```

### MaintenanceModeMiddleware

```python
middleware = [
    ("maintenance", {
        "maintenance_enabled": False,
        "message": "System under maintenance",
        "allowed_ips": ["127.0.0.1"],
        "allowed_paths": ["/health"],
    }),
]
```

## Request State

Access data set by middleware:

```python
# In view
async def my_view(request: Request):
    request_id = request.state.request_id
    user = request.state.user
    tenant_id = request.state.tenant_id
```

## Exception Handling

```python
class ErrorHandlerMiddleware(ASGIMiddleware):
    name = "ErrorHandlerMiddleware"
    order = 1  # Run first
    
    async def on_error(
        self, scope: Scope, request: Request, exc: Exception
    ) -> Response | None:
        if isinstance(exc, MyCustomError):
            return JSONResponse(
                {"detail": str(exc)},
                status_code=400
            )
        # Re-raise other exceptions
        return None
```

## Middleware Registry

```python
from core.middleware import (
    register_middleware,
    unregister_middleware,
    get_registered_middlewares,
    clear_middleware_registry,
    configure_middleware,
)

# Register
register_middleware("myapp.middleware.Custom")

# Unregister
unregister_middleware("myapp.middleware.Custom")

# Get all
middlewares = get_registered_middlewares()

# Clear all
clear_middleware_registry()

# Configure entire list
configure_middleware([
    "timing",
    "auth",
    "logging",
], clear_existing=True)
```

## Order Attribute

Control execution order via `order` attribute:

```python
class EarlyMiddleware(ASGIMiddleware):
    order = 1  # Runs first

class LateMiddleware(ASGIMiddleware):
    order = 100  # Runs later
```

Default orders:
- `MaintenanceModeMiddleware`: 1
- `RequestIDMiddleware`: 5
- `TimingMiddleware`: 10
- `SecurityHeadersMiddleware`: 15
- `LoggingMiddleware`: 20
- Default: 100

## Next

- [Security](36-security.md) — Security best practices
- [Auth](05-auth.md) — Authentication
