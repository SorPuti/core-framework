# Migration Guide — v0.12.x to v0.13.0

## Breaking Changes

### 1. `secret_key` is now required in production/staging

**Before:** Default `"change-me-in-production"` allowed apps to run without configuring a secret key.

**After:** In `production` and `staging` environments, the app will **fail to start** if `SECRET_KEY` is not set. In `development` and `testing`, a random key is auto-generated with a warning.

**Fix:**

```bash
# .env or .env.production
SECRET_KEY=your-secure-random-key-here
```

Generate a secure key:

```python
import secrets
print(secrets.token_urlsafe(64))
```

### 2. CORS defaults are now restrictive

**Before:** `cors_origins=["*"]`, `cors_allow_credentials=True`

**After:** `cors_origins=[]`, `cors_allow_credentials=False`

**Fix:**

```bash
# .env.development
CORS_ORIGINS='["http://localhost:3000"]'
CORS_ALLOW_CREDENTIALS=true
```

### 3. `auto_create_tables` default is now `False`

**Before:** `CoreApp(auto_create_tables=True)` was the default.

**After:** Tables are NOT created automatically. Use migrations or set explicitly.

**Fix (option A — explicit):**

```python
app = CoreApp(auto_create_tables=True)
```

**Fix (option B — via settings):**

```bash
# .env.development
AUTO_CREATE_TABLES=true
```

### 4. Docs/OpenAPI disabled by default

**Before:** `/docs`, `/redoc`, `/openapi.json` always available.

**After:** Disabled by default. Auto-enabled in `development` environment.

**Fix:**

```bash
# .env.production (if you want docs in prod)
DOCS_URL=/docs
REDOC_URL=/redoc
OPENAPI_URL=/openapi.json
```

### 5. `get_messaging_settings()` and `get_task_settings()` deprecated

**Before:**

```python
from core.messaging.config import get_messaging_settings
settings = get_messaging_settings()
```

**After:**

```python
from core.config import get_settings
settings = get_settings()
```

The old functions still work but emit `DeprecationWarning`.

### 6. `load_config()` in CLI now uses Settings

The CLI `load_config()` function now delegates to `get_settings()` internally. New CLI-related settings fields are available:

```bash
# .env
MIGRATIONS_DIR=./migrations
APP_LABEL=main
MODELS_MODULE=app.models
APP_MODULE=app.main
```

### 7. Middleware: `ASGIMiddleware` replaces `BaseMiddleware`

**Before:**

```python
from core.middleware import BaseMiddleware

class MyMiddleware(BaseMiddleware):
    async def before_request(self, request):
        ...
    async def after_request(self, request, response):
        return response
```

**After (recommended):**

```python
from core.middleware import ASGIMiddleware

class MyMiddleware(ASGIMiddleware):
    async def before_request(self, scope, request):
        ...
    async def after_response(self, scope, request, status_code, response_headers):
        response_headers.append((b"x-custom", b"value"))
```

`BaseMiddleware` still works but is deprecated. `ASGIMiddleware` has zero overhead and supports streaming responses.

### 8. Auth error messages are now generic

**Before:** `"Invalid token: Signature has expired"` (leaked implementation details)

**After:** `"Invalid or expired token"` (generic, secure)

## New Features

- **`.env.{environment}` support**: Place `.env.development`, `.env.production`, etc. alongside `.env` for environment-specific overrides.
- **Health check endpoints**: `/healthz` (liveness) and `/readyz` (readiness) are auto-registered.
- **Session factory**: Use `set_session_factory()` to customize database session creation without forking the core.
- **`on_settings_loaded()` hook**: Register callbacks executed after Settings is loaded.
- **Production warnings**: Automatic warnings for insecure configurations in production.
