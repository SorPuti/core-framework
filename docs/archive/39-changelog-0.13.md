# Changelog — v0.13.0

## Configuration Centralization (Phase 0)

### `core/config.py` — Single Source of Truth

- **NEW**: Environment-specific `.env` file support (`.env.development`, `.env.production`, `.env.staging`, `.env.testing`)
- **NEW**: `_resolve_env_files()` helper resolves which `.env` files to load based on `ENVIRONMENT`
- **NEW**: `on_settings_loaded()` hook for post-load callbacks
- **NEW**: `auto_create_tables` setting field (default: `False`)
- **NEW**: CLI/project fields: `migrations_dir`, `app_label`, `models_module`, `workers_module`, `tasks_module`, `app_module`
- **NEW**: `health_check_enabled` setting field
- **CHANGED**: `secret_key` default changed from `"change-me-in-production"` to `"__auto_generate__"` — required in production/staging, auto-generated in development/testing
- **CHANGED**: `cors_origins` default changed from `["*"]` to `[]`
- **CHANGED**: `cors_allow_credentials` default changed from `True` to `False`
- **CHANGED**: `docs_url` default changed from `"/docs"` to `None` (auto-enabled in development)
- **CHANGED**: `redoc_url` default changed from `"/redoc"` to `None` (auto-enabled in development)
- **CHANGED**: `openapi_url` default changed from `"/openapi.json"` to `None` (auto-enabled in development)
- **FIXED**: `configure()` dead code removed — `ConfiguredSettings` class was created but never used, loop was a no-op
- **FIXED**: `configure()` now validates unknown override keys and warns
- **FIXED**: `get_settings()` now loads `.env.{ENVIRONMENT}` files automatically
- **FIXED**: `reset_settings()` is now protected in production
- **DEPRECATED**: `get_settings_class_instance()` — use `configure(settings_class=...)` instead

### CLI — Unified with Settings

- **CHANGED**: `load_config()` now delegates to `get_settings()` as single source of truth
- **REMOVED**: `DEFAULT_CONFIG` dict — all defaults are in `Settings` class
- **KEPT**: `core.toml` / `pyproject.toml` support as fallback (Settings always wins)

### Satellite Configs — Deprecated

- **DEPRECATED**: `core.messaging.config.get_messaging_settings()` — use `get_settings()` directly
- **DEPRECATED**: `core.messaging.config.configure_messaging()` — use `configure()` directly
- **DEPRECATED**: `core.tasks.config.get_task_settings()` — use `get_settings()` directly
- **DEPRECATED**: `core.tasks.config.configure_tasks()` — use `configure()` directly
- **UPDATED**: All internal call sites (~25 files) updated to use `get_settings()` directly

### Boot Sequence — Validated

- **NEW**: Explicit boot sequence in `CoreApp.__init__()` with numbered steps
- **NEW**: Settings stored on `app.state.settings` for request-level access
- **NEW**: `openapi_url` now passed to FastAPI constructor
- **CHANGED**: `auto_create_tables` now reads from Settings if not explicitly passed
- **NEW**: Startup log with app name, environment, and debug status

### Example Application

- **NEW**: `example/settings.py` — dedicated settings file
- **CHANGED**: `example/app.py` imports settings from `example/settings.py`
- **CHANGED**: `main.py` reads `host`, `port`, `reload` from settings

## Security Hardening (Phase 1)

- **CHANGED**: `secret_key` required in production/staging, auto-generated in dev/test
- **CHANGED**: CORS defaults restrictive (no origins, no credentials)
- **CHANGED**: API docs disabled by default (auto-enabled in development only)
- **FIXED**: `core/dependencies.py` auth error now returns generic `"Invalid or expired token"` instead of leaking exception details
- **FIXED**: `generic_exception_handler` never exposes tracebacks in production, even if `debug=True`
- **NEW**: Production warnings for `DEBUG=true`, wildcard CORS, auto-create tables

## Performance & Architecture (Phase 2)

### Pure ASGI Middleware

- **NEW**: `ASGIMiddleware` base class — zero overhead, streaming-compatible
- **MIGRATED**: `TimingMiddleware` to Pure ASGI
- **MIGRATED**: `RequestIDMiddleware` to Pure ASGI
- **MIGRATED**: `LoggingMiddleware` to Pure ASGI
- **MIGRATED**: `MaintenanceModeMiddleware` to Pure ASGI
- **MIGRATED**: `SecurityHeadersMiddleware` to Pure ASGI
- **DEPRECATED**: `BaseMiddleware` (BaseHTTPMiddleware wrapper) — still works, emits no warning (soft deprecation)

### TaskWorker

- **FIXED**: `TaskWorker.start()` now uses `create_consumer()` from messaging registry instead of hardcoding `KafkaConsumer` — respects `kafka_backend` setting

### Hot Path Optimization

- **FIXED**: `get_db()` no longer calls `try/except ImportError` on every request
- **NEW**: `_resolve_has_replicas()` caches replica configuration after first call
- **NEW**: `set_session_factory()` allows plugging custom session logic without forking core

## Extensibility (Phase 3)

### Session Factory

- **NEW**: `set_session_factory()` in `core/dependencies.py` — register custom session factory
- **NEW**: `get_db()` uses custom factory if registered, falls back to default

### Health Checks

- **NEW**: `/healthz` endpoint — liveness probe (always returns 200 if app is running)
- **NEW**: `/readyz` endpoint — readiness probe (checks database, Kafka if enabled)
- **NEW**: `HEALTH_CHECK_ENABLED` setting (default: `true`)
- Endpoints excluded from OpenAPI schema (`include_in_schema=False`)

## Serializer Fixes (Schemas)

### Response Presets — Correct Inheritance

- **FIXED**: `PaginatedResponse` now inherits from `OutputSchema` (was `BaseModel`)
- **FIXED**: `ErrorResponse` now inherits from `OutputSchema` (was `BaseModel`)
- **FIXED**: `SuccessResponse` now inherits from `OutputSchema` (was `BaseModel`)
- **FIXED**: `DeleteResponse` now inherits from `OutputSchema` (was `BaseModel`)
- **FIXED**: `ValidationErrorResponse` now inherits from `OutputSchema` (was `BaseModel`)
- **FIXED**: `NotFoundResponse` now inherits from `OutputSchema` (was `BaseModel`)
- **FIXED**: `ConflictResponse` now inherits from `OutputSchema` (was `BaseModel`)
- **FIXED**: `ValidationErrorDetail` now inherits from `OutputSchema` (was `BaseModel`)
- All presets now have `from_attributes=True` via `OutputSchema.model_config`
- Compatible with `issubclass(schema, OutputSchema)` checks in ViewSet validation

### Partial Models — Preserve Inheritance

- **FIXED**: `_make_partial_model()` in routing now creates partial models inheriting from the original schema (was `BaseModel`)
- Partial models preserve `extra="forbid"`, `str_strip_whitespace=True`, custom validators

## Files Changed

| File | Type |
|------|------|
| `core/config.py` | **Rewritten** |
| `core/app.py` | Modified |
| `core/serializers.py` | Modified (preset inheritance fix) |
| `core/routing.py` | Modified (partial model inheritance fix) |
| `core/middleware.py` | **Rewritten** |
| `core/dependencies.py` | Modified |
| `core/cli/main.py` | Modified |
| `core/tasks/worker.py` | Modified |
| `core/tasks/scheduler.py` | Modified |
| `core/tasks/config.py` | **Rewritten** (deprecated wrapper) |
| `core/messaging/config.py` | **Rewritten** (deprecated wrapper) |
| `core/messaging/registry.py` | Modified |
| `core/messaging/decorators.py` | Modified |
| `core/messaging/confluent/broker.py` | Modified |
| `core/messaging/confluent/admin.py` | Modified |
| `core/messaging/confluent/producer.py` | Modified |
| `core/messaging/confluent/consumer.py` | Modified |
| `core/messaging/kafka/broker.py` | Modified |
| `core/messaging/kafka/producer.py` | Modified |
| `core/messaging/kafka/consumer.py` | Modified |
| `core/messaging/kafka/admin.py` | Modified |
| `core/messaging/rabbitmq/broker.py` | Modified |
| `core/messaging/rabbitmq/producer.py` | Modified |
| `core/messaging/rabbitmq/consumer.py` | Modified |
| `core/messaging/redis/broker.py` | Modified |
| `core/messaging/redis/producer.py` | Modified |
| `core/messaging/redis/consumer.py` | Modified |
| `example/settings.py` | **New** |
| `example/app.py` | Modified |
| `main.py` | **Rewritten** |
| `docs/36-migration-guide-0.13.md` | **New** |
| `docs/37-configuration.md` | **New** |
| `docs/38-security-defaults.md` | **New** |
| `docs/39-changelog-0.13.md` | **New** |
