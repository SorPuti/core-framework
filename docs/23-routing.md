# Routing

URL routing and ViewSet registration.

## AutoRouter

Main router for registering ViewSets.

```python
from core import AutoRouter

api = AutoRouter(prefix="/api/v1", tags=["API"])
```

### Register ViewSet

```python
from core import AutoRouter
from .views import UserViewSet, PostViewSet

api = AutoRouter(prefix="/api/v1")
api.register("/users", UserViewSet, basename="user")
api.register("/posts", PostViewSet, basename="post", tags=["Posts"])
```

### Include in App

```python
from core import CoreApp

app = CoreApp(routers=[api])
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
from core import ModelViewSet, action

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
from core.routing import Router

router = Router(prefix="/api/v1")
router.register_viewset("/users", UserViewSet, basename="user")
```

### Register View

```python
from core import APIView

class HealthView(APIView):
    async def get(self, request):
        return {"status": "ok"}

router.register_view("/health", HealthView)
```

## Include Routers

```python
# users/routes.py
from core import AutoRouter
from .views import UserViewSet

router = AutoRouter()
router.register("/users", UserViewSet)

# main.py
from core import AutoRouter
from users.routes import router as users_router
from posts.routes import router as posts_router

api = AutoRouter(prefix="/api/v1")
api.include_router(users_router)
api.include_router(posts_router, prefix="/blog", tags=["Blog"])
```

## Lookup Field

Default: `id`

```python
class UserViewSet(ModelViewSet):
    model = User
    lookup_field = "id"  # Default
    lookup_url_kwarg = "user_id"  # Custom URL param name
```

Routes become:
- `GET /users/{user_id}`
- `PUT /users/{user_id}`
- etc.

## Tags

For OpenAPI grouping:

```python
# On AutoRouter
api = AutoRouter(prefix="/api/v1", tags=["API"])

# On registration
api.register("/users", UserViewSet, tags=["Users"])

# On ViewSet
class UserViewSet(ModelViewSet):
    tags = ["Users", "Auth"]
```

Priority: registration > AutoRouter default > ViewSet.tags > [basename]

## Exclude CRUD

For ViewSets without model CRUD:

```python
class AuthViewSet(ViewSet):
    _exclude_crud = True
    
    @action(detail=False, methods=["POST"])
    async def login(self, request, db, data: LoginInput):
        ...
```

## API Root

List all registered URLs:

```python
api = AutoRouter(prefix="/api/v1")
api.register("/users", UserViewSet)
api.register("/posts", PostViewSet)

# GET /api/v1/ returns list of all URLs
root_view = api.get_api_root_view()
```

## URL Patterns

```python
# List all URLs
for url in api.urls:
    print(f"{url['path']} - {url['name']} - {url['methods']}")
```

## FastAPI Integration

AutoRouter wraps FastAPI's APIRouter:

```python
# Access underlying FastAPI router
fastapi_router = api.router

# Add raw FastAPI routes
@api.router.get("/custom")
async def custom_route():
    return {"custom": True}
```

## Route Naming

| Action | Name Pattern |
|--------|--------------|
| list | `{basename}-list` |
| create | `{basename}-create` |
| retrieve | `{basename}-detail` |
| update | `{basename}-update` |
| partial_update | `{basename}-partial-update` |
| destroy | `{basename}-delete` |
| custom action | `{basename}-{action_name}` |

## Duplicate Prevention

Router prevents duplicate route registration:

```python
router.register_viewset("/users", UserViewSet)
router.register_viewset("/users", UserViewSet)  # Ignored, no error
```

## Complete Example

```python
# src/apps/users/routes.py
from core import AutoRouter
from .views import UserViewSet, ProfileViewSet

router = AutoRouter()
router.register("/users", UserViewSet, basename="user")
router.register("/profiles", ProfileViewSet, basename="profile")

# src/main.py
from core import CoreApp, AutoRouter
from src.apps.users.routes import router as users_router
from src.apps.posts.routes import router as posts_router

api = AutoRouter(prefix="/api/v1", tags=["API"])
api.include_router(users_router, tags=["Users"])
api.include_router(posts_router, tags=["Posts"])

app = CoreApp(routers=[api])
```

## Next

- [ViewSets](04-viewsets.md) — CRUD endpoints
- [Dependencies](24-dependencies.md) — Dependency injection
