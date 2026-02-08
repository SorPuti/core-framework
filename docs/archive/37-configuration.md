# Configuration System

## Overview

The Core Framework uses a **single source of truth** for all configuration: `src/settings.py`.

All settings — application, database, auth, messaging, tasks, CLI — are defined in one centralized file. There are no separate config files, no auto-discovery, no fallbacks.

## Architecture

### Single Source of Truth

```
{project_root}/src/settings.py  ← ÚNICA fonte de configuração
```

This file is loaded **once** during bootstrap. All runtime configuration flows from here.

### Configuration Precedence

From highest to lowest priority:

1. **OS Environment Variables** — always win
2. **`.env.{ENVIRONMENT}`** — environment-specific overrides (e.g., `.env.production`)
3. **`.env`** — base configuration
4. **`Settings` class defaults** — built-in framework defaults

**Important:** `.env` files are read **once** during bootstrap via Pydantic Settings, not in runtime.

## Quick Start

### 1. Create src/settings.py

```python
# src/settings.py (REQUIRED)
from core.config import Settings, PydanticField, configure

class AppSettings(Settings):
    """All your app configuration in ONE place."""
    
    # Auth configuration (required if using auth)
    user_model: str = "app.models.User"
    
    # Custom fields
    stripe_api_key: str = PydanticField(default="", description="Stripe API key")
    sendgrid_api_key: str = PydanticField(default="", description="SendGrid API key")
    
    # Override framework defaults
    # (or set via .env — env vars always win)

# Register settings globally (REQUIRED)
settings = configure(settings_class=AppSettings)
```

### 2. Create `.env` files

```bash
# .env (base — always loaded)
DATABASE_URL=postgresql+asyncpg://localhost/myapp
SECRET_KEY=your-secret-key
APP_NAME=My Application

# .env.development (loaded in development)
DEBUG=true
CORS_ORIGINS='["http://localhost:3000"]'
CORS_ALLOW_CREDENTIALS=true
AUTO_CREATE_TABLES=true

# .env.production (loaded in production)
ENVIRONMENT=production
DATABASE_URL=postgresql+asyncpg://prod-db:5432/myapp
DATABASE_POOL_SIZE=20
KAFKA_ENABLED=true
KAFKA_BACKEND=confluent
KAFKA_BOOTSTRAP_SERVERS=kafka-1:9092,kafka-2:9092
WORKERS=4
RELOAD=false
```

### 3. Use in your app

```python
# app/main.py
from core.app import CoreApp
from core.config import get_settings

# Settings are loaded automatically from src.settings
app = CoreApp(title="My API")
```

### 4. Access settings anywhere

```python
from core.config import get_settings

settings = get_settings()  # Returns singleton from src/settings.py
print(settings.database_url)
print(settings.kafka_backend)
print(settings.user_model)
```

## Environment-Specific Files

| File | When loaded | Purpose |
|------|-------------|---------|
| `.env` | Always | Base configuration |
| `.env.development` | `ENVIRONMENT=development` | Dev-friendly defaults |
| `.env.staging` | `ENVIRONMENT=staging` | Staging overrides |
| `.env.production` | `ENVIRONMENT=production` | Production hardening |
| `.env.testing` | `ENVIRONMENT=testing` | Test isolation |

The `ENVIRONMENT` variable is read from the OS environment first, defaulting to `"development"`.

## Available Settings

### Application

| Setting | Default | Description |
|---------|---------|-------------|
| `APP_NAME` | `"Core Framework App"` | Application name |
| `APP_VERSION` | `"0.1.0"` | Application version |
| `ENVIRONMENT` | `"development"` | `development`, `staging`, `production`, `testing` |
| `DEBUG` | `false` | Debug mode (never in production) |
| `SECRET_KEY` | auto-generated | **Required** in production/staging |
| `AUTO_CREATE_TABLES` | `false` | Auto-create DB tables on startup |

### Database

| Setting | Default | Description |
|---------|---------|-------------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./app.db` | Async database URL |
| `DATABASE_ECHO` | `false` | Log SQL queries |
| `DATABASE_POOL_SIZE` | `5` | Connection pool size |
| `DATABASE_MAX_OVERFLOW` | `10` | Extra connections beyond pool |
| `DATABASE_READ_URL` | `None` | Read replica URL |

### API

| Setting | Default | Description |
|---------|---------|-------------|
| `API_PREFIX` | `/api/v1` | API route prefix |
| `DOCS_URL` | `None` (auto in dev) | Swagger docs URL |
| `REDOC_URL` | `None` (auto in dev) | ReDoc URL |
| `OPENAPI_URL` | `None` (auto in dev) | OpenAPI schema URL |

### CORS

| Setting | Default | Description |
|---------|---------|-------------|
| `CORS_ORIGINS` | `[]` | Allowed origins |
| `CORS_ALLOW_CREDENTIALS` | `false` | Allow credentials |
| `CORS_ALLOW_METHODS` | `["*"]` | Allowed methods |
| `CORS_ALLOW_HEADERS` | `["*"]` | Allowed headers |

### Authentication

| Setting | Default | Description |
|---------|---------|-------------|
| `AUTH_SECRET_KEY` | `None` (uses SECRET_KEY) | JWT signing key |
| `AUTH_ALGORITHM` | `HS256` | JWT algorithm |
| `AUTH_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access token TTL |
| `AUTH_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token TTL |
| `AUTH_PASSWORD_HASHER` | `pbkdf2_sha256` | Password hash algorithm |

### Kafka / Messaging

| Setting | Default | Description |
|---------|---------|-------------|
| `KAFKA_ENABLED` | `false` | Enable messaging |
| `KAFKA_BACKEND` | `aiokafka` | `aiokafka` or `confluent` |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka servers |
| `KAFKA_FIRE_AND_FORGET` | `false` | Skip delivery confirmation |

### Tasks

| Setting | Default | Description |
|---------|---------|-------------|
| `TASK_ENABLED` | `false` | Enable task system |
| `TASK_DEFAULT_QUEUE` | `default` | Default task queue |
| `TASK_WORKER_CONCURRENCY` | `4` | Concurrent tasks per worker |

### CLI / Project

| Setting | Default | Description |
|---------|---------|-------------|
| `MIGRATIONS_DIR` | `./migrations` | Migrations directory |
| `APP_LABEL` | `main` | Application label |
| `MODELS_MODULE` | `app.models` | Models module path |
| `APP_MODULE` | `app.main` | Application module path |

### Server

| Setting | Default | Description |
|---------|---------|-------------|
| `HOST` | `0.0.0.0` | Server host |
| `PORT` | `8000` | Server port |
| `WORKERS` | `1` | Number of workers |
| `RELOAD` | `true` | Auto-reload in dev |

### Health Check

| Setting | Default | Description |
|---------|---------|-------------|
| `HEALTH_CHECK_ENABLED` | `true` | Enable /healthz and /readyz |

## Bootstrap Process

The framework loads settings in this order:

1. Reads `ENVIRONMENT` from OS env vars (default: `"development"`)
2. Determines which `.env` files to load (`.env` + `.env.{ENVIRONMENT}`)
3. Imports `src.settings` module
4. `src/settings.py` calls `configure(settings_class=AppSettings)`
5. Pydantic reads `.env` files **once** and creates Settings instance
6. Settings singleton is registered globally

**Fail-fast behavior:**
- Missing `src/settings.py` → **RuntimeError** with clear instructions
- Invalid `user_model` path → **ImportError** with exact module/class issue
- Missing required fields → **ValidationError** from Pydantic

## Configuration Overrides

If you need programmatic overrides (rare), use the `configure()` overrides parameter:

```python
# src/settings.py
from core.config import Settings, configure

class AppSettings(Settings):
    user_model: str = "app.models.User"

# Override specific values (rarely needed)
settings = configure(
    settings_class=AppSettings,
    kafka_backend="confluent",  # Override just this field
)
```

**Warning:** Overrides should be avoided. Use `.env` files or OS env vars instead.

## CLI Integration

The CLI reads configuration from `src/settings.py` automatically.

```bash
# Set via .env or OS env vars
DATABASE_URL=postgresql://... core migrate

# Or just use .env file
core migrate
```

## Authentication Configuration

The `user_model` field in settings is used to configure auth:

```python
# src/settings.py
class AppSettings(Settings):
    user_model: str = "app.models.User"  # Path to your User model
    
settings = configure(settings_class=AppSettings)
```

The framework calls `configure_auth(user_model=User)` automatically during bootstrap based on this setting.

**No fallbacks:** There are no TOML files, no environment variable alternatives. Define `user_model` in `src/settings.py` or don't use auth.

## Removed Features

The following features were removed in this refactoring for simplicity:

- ❌ `on_settings_loaded()` callbacks
- ❌ `core.toml` / `pyproject.toml` fallback configuration
- ❌ `USER_MODEL` environment variable auto-detection
- ❌ Auto-discovery of settings modules
- ❌ Entry points for settings
- ❌ Multiple bootstrap paths

**One way to do it:** `src/settings.py` with `configure()`. That's it.
