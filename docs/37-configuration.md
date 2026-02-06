# Configuration System

## Overview

The Core Framework uses a **single source of truth** for all configuration: `core.config.Settings`.

All settings — application, database, auth, messaging, tasks, CLI — live in one centralized class. There are no separate config files per module.

## Configuration Precedence

From highest to lowest priority:

1. **OS Environment Variables** — always win
2. **`.env.{ENVIRONMENT}`** — environment-specific overrides (e.g., `.env.production`)
3. **`.env`** — base configuration
4. **`Settings` class defaults** — built-in framework defaults

## Quick Start

### 1. Create a settings file

```python
# myapp/settings.py
from core.config import Settings, PydanticField

class AppSettings(Settings):
    """All your app configuration in ONE place."""
    
    # Custom fields
    stripe_api_key: str = PydanticField(default="", description="Stripe API key")
    sendgrid_api_key: str = PydanticField(default="", description="SendGrid API key")
    
    # Override framework defaults
    # (or set via .env — env vars always win)

settings = AppSettings()
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
# myapp/app.py
from core.app import CoreApp
from myapp.settings import settings

app = CoreApp(
    title="My API",
    settings=settings,
)
```

### 4. Access settings anywhere

```python
from core.config import get_settings

settings = get_settings()
print(settings.database_url)
print(settings.kafka_backend)
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

## Programmatic Configuration

For cases where `.env` files are not enough:

```python
from core.config import configure, Settings

# Option 1: Override values
configure(
    kafka_backend="confluent",
    database_url="postgresql+asyncpg://localhost/myapp",
)

# Option 2: Custom settings class
class MySettings(Settings):
    stripe_api_key: str = ""

configure(settings_class=MySettings)

# Option 3: Both
configure(settings_class=MySettings, kafka_backend="confluent")
```

**Important:** Call `configure()` BEFORE creating `CoreApp` or importing components that use `get_settings()`.

## Post-Load Hooks

Register callbacks executed after Settings is loaded:

```python
from core.config import on_settings_loaded

@on_settings_loaded
def setup_logging(settings):
    import logging
    logging.basicConfig(level=settings.log_level)

@on_settings_loaded
def validate_config(settings):
    if settings.kafka_enabled and not settings.kafka_bootstrap_servers:
        raise ValueError("KAFKA_BOOTSTRAP_SERVERS required when KAFKA_ENABLED=true")
```

## CLI Integration

The CLI reads configuration from the same Settings. No more separate `core.toml` configuration needed (though it's still supported as a fallback).

```bash
# These are all equivalent:
DATABASE_URL=... core migrate
# or set in .env
core migrate
```
