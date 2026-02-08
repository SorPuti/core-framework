# Authentication

JWT-based authentication with login, register, and token refresh.

## Setup

### 1. Configure Settings

```python
# src/settings.py
from core.config import Settings, configure

class AppSettings(Settings):
    # Required
    user_model: str = "src.apps.users.models.User"
    
    # Optional (defaults shown)
    auth_secret_key: str = ""  # Falls back to secret_key
    auth_algorithm: str = "HS256"
    auth_access_token_expire_minutes: int = 30
    auth_refresh_token_expire_days: int = 7

settings = configure(settings_class=AppSettings)
```

### 2. Create User Model

```python
# src/apps/users/models.py
from core.auth import AbstractUser, PermissionsMixin
from core import Field
from sqlalchemy.orm import Mapped

class User(AbstractUser, PermissionsMixin):
    __tablename__ = "users"
    
    # AbstractUser provides:
    # - id, email, password (hashed), is_active, is_staff, is_superuser
    
    # PermissionsMixin provides:
    # - groups, user_permissions (M2M relationships)
    
    # Add custom fields
    first_name: Mapped[str | None] = Field.string(max_length=100, nullable=True)
    last_name: Mapped[str | None] = Field.string(max_length=100, nullable=True)
```

### 3. Add Auth Routes

```python
# src/apps/users/views.py
from core.auth import AuthViewSet

class AuthViewSet(AuthViewSet):
    pass  # Uses defaults
```

```python
# src/apps/users/routes.py
from core import AutoRouter
from .views import AuthViewSet

auth_router = AutoRouter(prefix="/auth", tags=["Auth"])
auth_router.register("", AuthViewSet)
```

```python
# src/main.py
from core import CoreApp, AutoRouter
from src.apps.users.routes import auth_router

api = AutoRouter(prefix="/api/v1")
api.include_router(auth_router)

app = CoreApp(
    routers=[api],
    middleware=["auth"],  # Enable auth middleware
)
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /auth/login | Login, get tokens |
| POST | /auth/register | Create account |
| POST | /auth/refresh | Refresh access token |
| GET | /auth/me | Get current user |
| POST | /auth/logout | Invalidate tokens |

### Login

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "secret123"}'
```

Response:

```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "email": "user@example.com"
  }
}
```

### Register

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "new@example.com", "password": "secret123"}'
```

### Authenticated Request

```bash
curl http://localhost:8000/api/v1/posts/ \
  -H "Authorization: Bearer eyJ..."
```

## Protect Endpoints

```python
from core import ModelViewSet
from core.permissions import IsAuthenticated, AllowAny

class PostViewSet(ModelViewSet):
    model = Post
    permission_classes = [IsAuthenticated]  # Require auth
    
    permission_classes_by_action = {
        "list": [AllowAny],  # Public list
        "retrieve": [AllowAny],  # Public detail
    }
```

## Access Current User

```python
from core import ModelViewSet

class PostViewSet(ModelViewSet):
    model = Post
    
    async def perform_create(self, instance, validated_data):
        instance.author_id = self.request.user.id
        await instance.save()
```

Or in any route:

```python
from fastapi import Depends
from core.auth import get_current_user

@router.get("/me")
async def me(user = Depends(get_current_user)):
    return {"id": user.id, "email": user.email}
```

## Create Superuser

```bash
core createsuperuser
# Enter email and password
```

## Password Hashers

Default: PBKDF2-SHA256

Available:

```python
class AppSettings(Settings):
    auth_password_hasher: str = "pbkdf2_sha256"  # Default
    # auth_password_hasher: str = "argon2"
    # auth_password_hasher: str = "bcrypt"
```

## Custom Auth ViewSet

```python
from core.auth import AuthViewSet
from core import action

class CustomAuthViewSet(AuthViewSet):
    
    @action(detail=False, methods=["POST"])
    async def change_password(self, request) -> dict:
        user = request.user
        data = await request.json()
        
        if not user.check_password(data["old_password"]):
            raise HTTPException(400, "Wrong password")
        
        user.set_password(data["new_password"])
        await user.save()
        return {"status": "ok"}
```

## Next

- [Admin](06-admin.md) — Admin panel
- [Permissions](11-permissions.md) — Custom permissions
