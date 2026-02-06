# Security Defaults

## Philosophy

The Core Framework follows **Secure by Default** — production deployments are safe out of the box. Developer-friendly features (docs, auto-create tables, verbose errors) are only enabled explicitly or in development environments.

## What Changed in v0.13.0

| Setting | Old Default | New Default | Rationale |
|---------|-------------|-------------|-----------|
| `SECRET_KEY` | `"change-me-in-production"` | **Required** (fails in prod/staging) | Prevents running with predictable secret |
| `CORS_ORIGINS` | `["*"]` | `[]` | No origins allowed unless configured |
| `CORS_ALLOW_CREDENTIALS` | `true` | `false` | Credentials require explicit opt-in |
| `AUTO_CREATE_TABLES` | `true` | `false` | Prod should use migrations |
| `DOCS_URL` | `"/docs"` | `None` (auto in dev) | No API docs exposed in prod |
| `REDOC_URL` | `"/redoc"` | `None` (auto in dev) | Same as above |
| `OPENAPI_URL` | `"/openapi.json"` | `None` (auto in dev) | No schema leakage in prod |

## Secret Key Behavior

### Development / Testing
- If `SECRET_KEY` is not set, a random key is auto-generated
- A warning is logged: `"SECRET_KEY not configured — auto-generated random key"`
- The key changes on every restart (tokens from previous sessions become invalid)

### Production / Staging
- `SECRET_KEY` **must** be set explicitly
- The app **fails to start** if not configured
- Error: `"SECRET_KEY is required in production/staging environments"`

### How to Set

```bash
# Generate a secure key
python -c "import secrets; print(secrets.token_urlsafe(64))"

# Add to .env.production
SECRET_KEY=your-generated-key-here
```

## CORS Configuration

### Development

```bash
# .env.development
CORS_ORIGINS='["http://localhost:3000", "http://localhost:5173"]'
CORS_ALLOW_CREDENTIALS=true
```

### Production

```bash
# .env.production
CORS_ORIGINS='["https://app.example.com", "https://admin.example.com"]'
CORS_ALLOW_CREDENTIALS=true
```

### Warning

If `CORS_ORIGINS` contains `"*"` in production, a warning is logged:
```
CORS_ORIGINS contains '*' in production. This allows any origin. Restrict to specific domains.
```

## API Documentation

In development (`ENVIRONMENT=development`), docs are auto-enabled:
- `/docs` — Swagger UI
- `/redoc` — ReDoc
- `/openapi.json` — OpenAPI schema

In production, all three are `None` (disabled). To enable in prod:

```bash
# .env.production (not recommended)
DOCS_URL=/docs
OPENAPI_URL=/openapi.json
```

## Error Handling

### Auth Errors
- Error messages are generic: `"Invalid or expired token"`
- Internal exceptions are logged at DEBUG level server-side
- No implementation details leak to clients

### Generic Exception Handler
- In production, even if `DEBUG=True` accidentally, tracebacks are **never** exposed
- Condition: `debug AND NOT production` must both be true for verbose errors
- All unhandled exceptions are logged server-side via `app_logger.exception()`

## Production Warnings

The framework automatically warns about risky configurations in production:

| Condition | Warning |
|-----------|---------|
| `DEBUG=true` in production | `"DEBUG=True in production environment"` |
| `CORS_ORIGINS=["*"]` in production | `"CORS_ORIGINS contains '*' in production"` |
| `AUTO_CREATE_TABLES=true` in production | `"Use migrations instead"` |

## Security Checklist for Production

- [ ] `SECRET_KEY` set to a random, unique value
- [ ] `ENVIRONMENT=production`
- [ ] `DEBUG=false`
- [ ] `CORS_ORIGINS` restricted to specific domains
- [ ] `AUTO_CREATE_TABLES=false`
- [ ] `DOCS_URL`, `REDOC_URL`, `OPENAPI_URL` not set (or intentionally enabled)
- [ ] Database credentials in environment variables (not in code)
- [ ] Kafka SASL/SSL configured if using Kafka
- [ ] `AUTH_PASSWORD_HASHER` set to `argon2` or `bcrypt` (not `pbkdf2_sha256`)
- [ ] Rate limiting configured (middleware or reverse proxy)
- [ ] HTTPS enforced (via reverse proxy)
