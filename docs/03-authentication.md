# Authentication

## Setup

```python
# src/main.py
from core.auth import configure_auth
from src.apps.users.models import User

configure_auth(
    secret_key="your-secret-key",
    access_token_expire_minutes=30,
    refresh_token_expire_days=7,
    user_model=User,
)
```

## User Model

Extend `AbstractUser` for built-in auth.

```python
# src/apps/users/models.py
from core.auth import AbstractUser
from sqlalchemy.orm import Mapped, mapped_column

class User(AbstractUser):
    __tablename__ = "users"
    
    # Additional fields
    phone: Mapped[str | None] = mapped_column(default=None)
    avatar_url: Mapped[str | None] = mapped_column(default=None)
```

Inherited from AbstractUser:
- id, email, password_hash
- is_active, is_staff, is_superuser
- date_joined, last_login
- set_password(), check_password()
- authenticate(), create_user(), create_superuser()

## Token Functions

```python
from core.auth import (
    create_access_token,
    create_refresh_token,
    verify_token,
)

# Create tokens
access = create_access_token(user_id=user.id, extra_claims={"email": user.email})
refresh = create_refresh_token(user_id=user.id)

# Verify token
payload = verify_token(token, token_type="access")  # or "refresh"
if payload:
    user_id = payload["sub"]
```

## Auth ViewSet

```python
from core import ModelViewSet, action
from core.auth import create_access_token, create_refresh_token, verify_token
from core.permissions import AllowAny, IsAuthenticated

class AuthViewSet(ModelViewSet):
    model = User
    permission_classes = [AllowAny]
    tags = ["Auth"]
    
    @action(methods=["POST"], detail=False)
    async def login(self, request, db, **kwargs):
        body = await request.json()
        user = await User.authenticate(body["email"], body["password"], db)
        if not user:
            raise HTTPException(401, "Invalid credentials")
        
        return {
            "access_token": create_access_token(user.id),
            "refresh_token": create_refresh_token(user.id),
        }
    
    @action(methods=["POST"], detail=False)
    async def register(self, request, db, **kwargs):
        body = await request.json()
        user = await User.create_user(
            email=body["email"],
            password=body["password"],
            db=db,
        )
        return {"id": user.id, "email": user.email}
    
    @action(methods=["GET"], detail=False, permission_classes=[IsAuthenticated])
    async def me(self, request, db, **kwargs):
        user = request.state.user
        return {"id": user.id, "email": user.email}
```

## Permissions

```python
from core.permissions import (
    AllowAny,           # No auth required
    IsAuthenticated,    # Must be logged in
    IsAdmin,            # is_admin or is_superuser
    IsOwner,            # Object owner only
    HasRole,            # Specific roles
)

class PostViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    
    permission_classes_by_action = {
        "list": [AllowAny],
        "retrieve": [AllowAny],
        "create": [IsAuthenticated],
        "update": [IsOwner],
        "destroy": [IsAdmin],
    }
```

## Custom Permission

```python
from core.permissions import Permission

class IsPremiumUser(Permission):
    message = "Premium subscription required"
    
    async def has_permission(self, request, view=None) -> bool:
        user = getattr(request.state, "user", None)
        return user and user.is_premium
    
    async def has_object_permission(self, request, view, obj) -> bool:
        return await self.has_permission(request, view)
```

## Custom Auth Backend

```python
from core.auth.backends import AuthBackend

class APIKeyBackend(AuthBackend):
    async def authenticate(self, request, db, **kwargs):
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            return None
        
        return await APIKey.objects.using(db).filter(
            key=api_key,
            is_active=True,
        ).first()
```

Register:

```python
from core.auth.backends import register_auth_backend

register_auth_backend("api_key", APIKeyBackend)
```

## Password Hashers

Available: `pbkdf2_sha256`, `bcrypt`, `argon2`

```python
configure_auth(
    password_hasher="argon2",  # Recommended for new projects
)
```

Custom hasher:

```python
from core.auth.hashers import PasswordHasher

class CustomHasher(PasswordHasher):
    algorithm = "custom"
    
    def hash(self, password: str) -> str:
        # Return hashed password
        pass
    
    def verify(self, password: str, hashed: str) -> bool:
        # Return True if matches
        pass
```

Next: [Messaging](04-messaging.md)
