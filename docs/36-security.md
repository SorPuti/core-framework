# Security

Security best practices and configuration.

## Security Layers

```mermaid
flowchart TB
    subgraph "Request"
        REQ[HTTP Request]
    end
    
    subgraph "Security Stack"
        CORS[CORS Check]
        HEADERS[Security Headers]
        AUTH[Authentication]
        PERM[Permissions]
        VALID[Input Validation]
    end
    
    subgraph "Protection"
        XSS[XSS Prevention]
        SQLI[SQL Injection Prevention]
        CSRF[CSRF Protection]
    end
    
    REQ --> CORS --> HEADERS --> AUTH --> PERM --> VALID
    VALID --> XSS
    VALID --> SQLI
    VALID --> CSRF
    
    style CORS fill:#ffcdd2
    style AUTH fill:#fff3e0
    style PERM fill:#e3f2fd
    style VALID fill:#c8e6c9
```

## Security Checklist

```mermaid
flowchart LR
    subgraph "Must Have"
        A[✓ HTTPS]
        B[✓ JWT Auth]
        C[✓ Input Validation]
        D[✓ SQL Parameterization]
    end
    
    subgraph "Recommended"
        E[✓ Security Headers]
        F[✓ Rate Limiting]
        G[✓ CORS Config]
        H[✓ HSTS]
    end
    
    subgraph "Advanced"
        I[✓ CSP]
        J[✓ Audit Logs]
        K[✓ IP Allowlist]
    end
    
    style A fill:#c8e6c9
    style B fill:#c8e6c9
    style C fill:#c8e6c9
    style D fill:#c8e6c9
```

## Security Headers

Enable via middleware:

```python
# src/settings.py
class AppSettings(Settings):
    middleware: list[str] = [
        "security_headers",
        # ...
    ]
```

Default headers:

| Header | Value | Purpose |
|--------|-------|---------|
| `X-Content-Type-Options` | `nosniff` | Prevent MIME sniffing |
| `X-Frame-Options` | `DENY` | Prevent clickjacking |
| `X-XSS-Protection` | `1; mode=block` | XSS filter |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Control referrer |

### Custom Headers

```python
middleware = [
    ("security_headers", {
        "headers": {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "SAMEORIGIN",
            "Content-Security-Policy": "default-src 'self'",
        },
        "enable_hsts": True,
        "hsts_max_age": 31536000,
    }),
]
```

### HSTS

Enable for HTTPS:

```python
middleware = [
    ("security_headers", {
        "enable_hsts": True,
        "hsts_max_age": 31536000,  # 1 year
    }),
]
```

## CORS

```python
# src/settings.py
class AppSettings(Settings):
    # Allowed origins (empty = none)
    cors_origins: list[str] = ["https://app.example.com"]
    
    # Allow credentials (cookies, auth headers)
    cors_allow_credentials: bool = True
    
    # Allowed methods
    cors_allow_methods: list[str] = ["GET", "POST", "PUT", "PATCH", "DELETE"]
    
    # Allowed headers
    cors_allow_headers: list[str] = ["Authorization", "Content-Type"]
```

### Production Warning

**Never use `"*"` in production:**

```python
# BAD - allows any origin
cors_origins: list[str] = ["*"]

# GOOD - explicit origins
cors_origins: list[str] = [
    "https://app.example.com",
    "https://admin.example.com",
]
```

## Authentication

### JWT Configuration

```python
class AppSettings(Settings):
    secret_key: str = "your-256-bit-secret-key"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    jwt_algorithm: str = "HS256"
```

### Password Requirements

```python
from core.validators import PasswordValidator

validator = PasswordValidator(
    min_length=8,
    max_length=128,
    require_uppercase=True,
    require_lowercase=True,
    require_digit=True,
    require_special=True,
)
```

### Password Hashing

Use strong hashers:

```python
class AppSettings(Settings):
    # Recommended: Argon2
    password_hasher: str = "argon2"  # pip install argon2-cffi
    
    # Alternative: BCrypt
    # password_hasher: str = "bcrypt"  # pip install bcrypt
```

## SQL Injection Prevention

The framework uses SQLAlchemy ORM with parameterized queries:

```python
# SAFE - parameterized query
users = await User.objects.using(db).filter(email=user_input).all()

# SAFE - QuerySet API
users = await User.objects.using(db).filter(
    name__contains=search_term
).all()
```

**Never use raw SQL with user input:**

```python
# DANGEROUS - never do this
query = f"SELECT * FROM users WHERE email = '{user_input}'"

# SAFE - use parameters
from sqlalchemy import text
result = await db.execute(
    text("SELECT * FROM users WHERE email = :email"),
    {"email": user_input}
)
```

## Input Validation

### Use InputSchema

```python
from core.serializers import InputSchema

class UserInput(InputSchema):
    email: str
    name: str
    # extra="forbid" rejects unknown fields
    # str_strip_whitespace=True cleans strings
```

### Validate All Input

```python
from core.validators import (
    EmailValidator,
    MinLengthValidator,
    MaxLengthValidator,
)

class UserViewSet(ModelViewSet):
    model = User
    
    field_validators = {
        "email": [EmailValidator()],
        "name": [MinLengthValidator(2), MaxLengthValidator(100)],
    }
```

## Rate Limiting

**Not built-in.** Implement with middleware:

```python
from core.middleware import ASGIMiddleware
from core.exceptions import TooManyRequests

class RateLimitMiddleware(ASGIMiddleware):
    name = "RateLimitMiddleware"
    
    async def before_request(self, scope, request):
        client_ip = request.client.host
        
        if await self.is_rate_limited(client_ip):
            raise TooManyRequests(
                message="Too many requests",
                retry_after=60
            )
        
        await self.increment_counter(client_ip)
        return None
```

## CSRF Protection

Admin panel uses `SameSite=Lax` cookies:

```python
response.set_cookie(
    key="admin_session",
    value=session_key,
    httponly=True,
    samesite="lax",
    secure=True,  # HTTPS only
)
```

For API endpoints, use JWT tokens instead of cookies.

## Secrets Management

### Environment Variables

```bash
# .env (never commit)
SECRET_KEY=your-256-bit-secret-key
DATABASE_URL=postgresql+asyncpg://user:pass@host/db
```

### Never Commit Secrets

```gitignore
# .gitignore
.env
.env.local
.env.production
credentials.json
*.pem
*.key
```

### Validate in Production

```python
from core.auth import validate_auth_configuration

issues = validate_auth_configuration()
if issues:
    for issue in issues:
        print(f"WARNING: {issue}")
```

## Sensitive Data

### Exclude from Responses

```python
class UserOutput(OutputSchema):
    id: int
    email: str
    name: str
    # password NOT included
```

### Exclude from Logs

```python
middleware = [
    ("logging", {
        "log_body": False,  # Don't log request bodies
        "log_headers": False,  # Don't log headers
    }),
]
```

## Production Checklist

- [ ] `SECRET_KEY` is unique and secure (256+ bits)
- [ ] `DEBUG` is `False`
- [ ] `CORS_ORIGINS` is explicit (no `"*"`)
- [ ] HTTPS is enforced
- [ ] HSTS is enabled
- [ ] Password hasher is Argon2 or BCrypt
- [ ] Rate limiting is implemented
- [ ] Sensitive data excluded from logs
- [ ] `.env` files not committed
- [ ] Database credentials are secure
- [ ] Admin panel has strong authentication

## Security Headers Reference

```python
# Recommended production headers
headers = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": "default-src 'self'",
    "Permissions-Policy": "geolocation=(), microphone=()",
}
```

## Next

- [Middleware](20-middleware.md) — Request/response hooks
- [Auth](05-auth.md) — Authentication
