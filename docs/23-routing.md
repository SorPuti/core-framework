# Routing

URL routing and ViewSet registration.

## Auto-Discovery (Plug-and-Play)

The framework automatically discovers and loads URLs from `urls.py` files in each app listed in `settings.installed_apps`.

### Simple Usage

```python
# src/main.py
from strider import StrideApp

app = StrideApp()  # Everything loaded automatically
```

### Defining URLs

Create a `urls.py` file in each app:

```python
# src/apps/users/urls.py
from strider import path
from .views import UserViewSet, AuthViewSet

urlpatterns = [
    path("users", UserViewSet),
    path("auth", AuthViewSet),
]
```

### URL Configuration

Configure the prefix in `settings.py`:

```python
# src/settings.py
from strider import Settings

class AppSettings(Settings):
    url_prefix: str = "/api/v1"  # Default
    installed_apps: list[str] = [
        "src.apps.users",
        "src.apps.items",
    ]
```

## path()

Define URL patterns similar to Django.

```python
from strider import path

urlpatterns = [
    path("users", UserViewSet),                    # ViewSet
    path("profile", ProfileView),                  # APIView
    path("health", health_check),                # Function
]
```

### URLPattern Options

```python
path(
    route="users",
    view=UserViewSet,
    name="user-list",              # Optional route name
    basename="user",               # Optional base name
    tags=["Users"],                # OpenAPI tags
)
```

## include()

Include URLs from other modules.

```python
from strider import path, include

urlpatterns = [
    path("api/v1/", include("src.apps.users.urls")),
    path("api/v1/", include("src.apps.items.urls")),
]
```

### Nested Includes

```python
# src/apps/api/urls.py
from strider import path, include

urlpatterns = [
    path("v1/", include("src.apps.users.urls")),
    path("v1/", include("src.apps.posts.urls")),
    path("v2/", include("src.apps.v2.urls")),
]
```

## AutoRouter

Main router for registering ViewSets (used internally by auto-discovery).

```python
from strider import AutoRouter

api = AutoRouter(prefix="/api/v1", tags=["API"])
```

### Register ViewSet Manually

```python
from strider import AutoRouter
from .views import UserViewSet, PostViewSet

api = AutoRouter(prefix="/api/v1")
api.register("/users", UserViewSet, basename="user")
api.register("/posts", PostViewSet, basename="post", tags=["Posts"])
```

## Generated Routes

For a `ModelViewSet`:

| Method | Path | Action | Name |
|--------|------|--------|------|
| GET | `/users/` | list | `user-list` |
| POST | `/users/` | create | `user-create` |
| GET | `/users/{id}` | retrieve | `user-detail` |
| PUT | `/users/{id}` | update | `user-update` |
| PATCH | `/users/{id}` | partial_update | `user-partial-update` |
| DELETE | `/users/{id}` | destroy | `user-delete` |

## Custom Actions

```python
from strider import ModelViewSet, action

class UserViewSet(ModelViewSet):
    model = User

    @action(detail=False, methods=["GET"])
    async def me(self, request, db):
        """GET /users/me"""
        return await self.serialize(request.user)

    @action(detail=True, methods=["POST"])
    async def activate(self, request, db, id: int):
        """POST /users/{id}/activate"""
        user = await self.get_object(db, id=id)
        user.is_active = True
        await user.save(db)
        return await self.serialize(user)
```

## Router Class

Lower-level router (extends FastAPI's `APIRouter`).

```python
from strider.routing import Router

router = Router(prefix="/api/v1")
router.register_viewset("/users", UserViewSet, basename="user")
```

### Register View

```python
from strider import APIView

class HealthView(APIView):
    async def get(self, request):
        return {"status": "ok"}

router.register_view("/health", HealthView)
```

## Project Structure

Recommended structure with auto-discovery:

```
src/
├── main.py              # Just: app = StrideApp()
├── settings.py          # Settings with installed_apps
├── urls.py              # (Optional) Global URL config
└── apps/
    ├── users/
    │   ├── __init__.py
    │   ├── models.py
    │   ├── views.py
    │   └── urls.py      # urlpatterns = [...]
    └── items/
        ├── __init__.py
        ├── models.py
        ├── views.py
        └── urls.py      # urlpatterns = [...]
```

### main.py

```python
"""Application entry point."""
from strider import StrideApp

app = StrideApp()
```

### settings.py

```python
"""Application settings."""
from strider import Settings

class AppSettings(Settings):
    app_name: str = "My API"
    url_prefix: str = "/api/v1"
    installed_apps: list[str] = [
        "src.apps.users",
        "src.apps.items",
    ]
```

## Legacy Mode

While auto-discovery is the recommended approach, you can still manually register routers if needed (not recommended for new projects):

```python
from strider import StrideApp, AutoRouter
from src.apps.users.views import UserViewSet

# Manual router (legacy)
router = AutoRouter(prefix="/api/v1")
router.register("/users", UserViewSet)

# Note: This is kept for compatibility only
# Auto-discovery is always active and preferred
```
