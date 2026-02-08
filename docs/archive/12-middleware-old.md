# Middleware

Django-style middleware for request/response processing.

## Enable Middleware

```python
# src/settings.py
class AppSettings(Settings):
    middleware: list[str] = [
        "timing",      # Request timing
        "auth",        # Authentication
        "cors",        # CORS (auto-enabled)
    ]
```

## Built-in Middleware

| Name | Description |
|------|-------------|
| `timing` | Adds `X-Request-Time` header |
| `auth` | JWT authentication |
| `cors` | CORS headers |
| `tenancy` | Multi-tenant context |

## Custom Middleware

```python
# src/middleware.py
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # Before request
        print(f"Request: {request.method} {request.url.path}")
        
        # Process request
        response = await call_next(request)
        
        # After response
        print(f"Response: {response.status_code}")
        
        return response
```

Register:

```python
# src/main.py
from core import CoreApp
from src.middleware import LoggingMiddleware

app = CoreApp(
    routers=[api],
    extra_middleware=[LoggingMiddleware],
)
```

## Middleware Order

Middleware executes in order:

1. First middleware (outermost)
2. Second middleware
3. ... (your code)
4. Second middleware (response)
5. First middleware (response)

```python
middleware = [
    "cors",    # 1. CORS (first in, last out)
    "timing",  # 2. Timing
    "auth",    # 3. Auth (closest to your code)
]
```

## Request State

Pass data between middleware and views:

```python
class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # Set on request state
        request.state.tenant_id = self.get_tenant(request)
        
        response = await call_next(request)
        return response

# Access in view
async def my_view(request: Request):
    tenant_id = request.state.tenant_id
```

## Exception Handling

```python
class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        try:
            return await call_next(request)
        except ValueError as e:
            return JSONResponse(
                status_code=400,
                content={"error": str(e)}
            )
```

## Next

- [Settings](02-settings.md) — Configuration
- [Auth](05-auth.md) — Authentication middleware
