# Auth Backends

Customizable authentication backends.

## Available Backends

| Name | Class | Description |
|------|-------|-------------|
| `"model"` | `ModelBackend` | Email/password auth (default) |
| `"token"` | `TokenAuthBackend` | Bearer token auth |
| `"multi"` | `MultiBackend` | Try multiple backends |

## Custom Auth Backend

```python
# src/apps/auth/backends.py
from core.auth import AuthBackend, register_auth_backend

class OAuthBackend(AuthBackend):
    """OAuth2 authentication backend."""
    
    async def authenticate(self, request=None, **credentials):
        token = credentials.get("oauth_token")
        if not token:
            return None
        
        # Validate with OAuth provider
        user_data = await self.validate_oauth(token)
        if not user_data:
            return None
        
        # Get or create user
        return await self.get_or_create_user(user_data)
    
    async def get_user(self, user_id, db):
        from src.apps.users.models import User
        return await User.objects.using(db).get_or_none(id=user_id)

# Register backend
register_auth_backend("oauth", OAuthBackend())
```

## Use Custom Backend

```python
# src/settings.py
class AppSettings(Settings):
    auth_backend: str = "oauth"  # Use your backend
```

Or use MultiBackend:

```python
from core.auth import MultiBackend, register_auth_backend

multi = MultiBackend(backends=["oauth", "token", "model"])
register_auth_backend("multi", multi)

# In settings
class AppSettings(Settings):
    auth_backend: str = "multi"
```

## Password Hashers

| Name | Algorithm | Dependencies |
|------|-----------|--------------|
| `"pbkdf2_sha256"` | PBKDF2-SHA256 | None (default) |
| `"argon2"` | Argon2id | `pip install argon2-cffi` |
| `"bcrypt"` | BCrypt | `pip install bcrypt` |
| `"scrypt"` | Scrypt | None |

### Custom Hasher

```python
from core.auth import PasswordHasher, register_password_hasher

class MyHasher(PasswordHasher):
    algorithm = "my_algo"
    
    def hash(self, password: str) -> str:
        return my_hash_function(password)
    
    def verify(self, password: str, hashed: str) -> bool:
        return my_verify_function(password, hashed)

register_password_hasher("my_algo", MyHasher())
```

## Token Backends

Default: JWT (`"jwt"`)

### Custom Token Backend

```python
from core.auth import TokenBackend, register_token_backend

class MyTokenBackend(TokenBackend):
    def create_token(self, payload, token_type="access", expires_delta=None):
        return my_encode(payload, expires_delta)
    
    def decode_token(self, token):
        return my_decode(token)
    
    def verify_token(self, token, token_type="access"):
        try:
            payload = self.decode_token(token)
            if payload.get("type") != token_type:
                return None
            return payload
        except Exception:
            return None

register_token_backend("my_tokens", MyTokenBackend())
```

## Permission Backends

| Name | Class | Description |
|------|-------|-------------|
| `"default"` | `DefaultPermissionBackend` | User + group permissions |
| `"object"` | `ObjectPermissionBackend` | Object-level permissions |
| `"rbac"` | `RoleBasedPermissionBackend` | Role-based access |

### RBAC Example

```python
from core.auth import RoleBasedPermissionBackend, register_permission_backend

rbac = RoleBasedPermissionBackend(
    role_permissions={
        "admin": ["*"],  # All permissions
        "editor": ["posts.*", "comments.*"],
        "viewer": ["posts.view", "comments.view"],
    }
)
register_permission_backend("rbac", rbac)
```

## User ID Customization

### Integer ID (Default)

```python
from core.auth import AbstractUser

class User(AbstractUser):
    __tablename__ = "users"
    # id: Mapped[int] = Field.pk()  # Inherited
```

### UUID ID

```python
from core.auth import AbstractUUIDUser

class User(AbstractUUIDUser):
    __tablename__ = "users"
    # id: Mapped[UUID] = AdvancedField.uuid_pk()  # Inherited
```

### Custom ID

```python
from core.auth import AbstractUser
from core.fields import AdvancedField
from uuid import UUID

class User(AbstractUser):
    __tablename__ = "users"
    
    # Override with BigInteger
    id: Mapped[int] = AdvancedField.bigint_pk()
    
    # Or with String
    # id: Mapped[str] = Field.string(primary_key=True, max_length=36)
```

## AuthConfig

Full configuration:

```python
from core.auth import configure_auth, AuthConfig

configure_auth(
    secret_key="your-secret-key",
    user_model=User,
    password_hasher="argon2",
    token_backend="jwt",
    auth_backend="model",
    permission_backend="default",
    access_token_expire_minutes=30,
    refresh_token_expire_days=7,
    username_field="email",
    jwt_algorithm="HS256",
)
```

## Next

- [Permissions](07-permissions.md) — Access control
- [Auth](05-auth.md) — Basic authentication
