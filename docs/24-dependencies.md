# Dependencies

Dependency injection system.

## Built-in Dependencies

### get_db

Database session.

```python
from core.dependencies import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

async def my_view(db: AsyncSession = Depends(get_db)):
    users = await User.objects.using(db).all()
```

### get_current_user

Authenticated user (required).

```python
from core.dependencies import get_current_user

async def my_view(user = Depends(get_current_user)):
    # Raises 401 if not authenticated
    return {"user_id": user.id}
```

### get_optional_user

Authenticated user (optional).

```python
from core.dependencies import get_optional_user

async def my_view(user = Depends(get_optional_user)):
    if user:
        return {"user_id": user.id}
    return {"user_id": None}
```

### get_settings_dep

Application settings.

```python
from core.dependencies import get_settings_dep
from core.config import Settings

async def my_view(settings: Settings = Depends(get_settings_dep)):
    return {"app_name": settings.app_name}
```

## Type Aliases

```python
from core.dependencies import DatabaseSession, CurrentUser, OptionalUser, AppSettings

async def my_view(
    db: DatabaseSession,
    user: CurrentUser,
    settings: AppSettings,
):
    pass
```

## Configuration

### configure_auth

Set up user loading.

```python
from core.dependencies import configure_auth
from src.apps.users.models import User

async def load_user(user_id: int, db):
    return await User.objects.using(db).get_or_none(id=user_id)

configure_auth(user_loader=load_user)
```

With token decoder:

```python
from core.auth import decode_token

configure_auth(
    user_loader=load_user,
    token_decoder=decode_token,
)
```

### set_session_factory

Custom session factory.

```python
from core.dependencies import set_session_factory
from core.database import get_db_replicas

# Use replicas globally
set_session_factory(get_db_replicas)
```

## Pagination

```python
from core.dependencies import PaginationParams
from fastapi import Depends

async def list_items(
    db: DatabaseSession,
    pagination: PaginationParams = Depends(),
):
    items = await Item.objects.using(db).offset(pagination.offset).limit(pagination.limit).all()
    return {"items": items, "page": pagination.page}
```

PaginationParams attributes:
- `page`: Current page (default: 1)
- `page_size`: Items per page (default: 20)
- `max_page_size`: Maximum allowed (default: 100)
- `offset`: Calculated offset
- `limit`: Same as page_size

## Sorting

```python
from core.dependencies import SortingParams
from fastapi import Depends

async def list_items(
    db: DatabaseSession,
    sorting: SortingParams = Depends(),
):
    order = sorting.order_by  # Returns list for SQLAlchemy
    items = await Item.objects.using(db).order_by(*order).all()
    return items
```

SortingParams attributes:
- `sort_by`: Field name
- `sort_order`: `"asc"` or `"desc"`
- `allowed_fields`: List of allowed sort fields
- `order_by`: Property returning SQLAlchemy-compatible list

## Request Context

```python
from core.dependencies import get_request_context, RequestContext
from fastapi import Depends

async def my_view(context: RequestContext = Depends(get_request_context)):
    return {
        "method": context["method"],
        "url": context["url"],
        "client_ip": context["client_ip"],
        "user_agent": context["user_agent"],
        "user": context["user"],
    }
```

## Custom Dependencies

### Simple Dependency

```python
from fastapi import Depends

def get_api_key(api_key: str = Header(...)):
    if api_key != "secret":
        raise HTTPException(401, "Invalid API key")
    return api_key

async def my_view(api_key: str = Depends(get_api_key)):
    return {"authenticated": True}
```

### Class Dependency

```python
class RateLimiter:
    def __init__(self, requests_per_minute: int = 60):
        self.limit = requests_per_minute
    
    async def __call__(self, request: Request):
        # Check rate limit
        if await self.is_limited(request.client.host):
            raise HTTPException(429, "Rate limit exceeded")
        return True

rate_limiter = RateLimiter(requests_per_minute=100)

async def my_view(_: bool = Depends(rate_limiter)):
    return {"ok": True}
```

### Service Dependency

```python
from core.dependencies import DependencyFactory

class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_active_users(self):
        return await User.objects.using(self.db).filter(is_active=True).all()

# Auto-injects db
user_service_dep = DependencyFactory(UserService)

async def my_view(service: UserService = Depends(user_service_dep)):
    users = await service.get_active_users()
    return users
```

## ViewSet Dependencies

ViewSets auto-inject:
- `db`: Database session
- `_user`: Optional user (via `get_optional_user`)

```python
class ItemViewSet(ModelViewSet):
    model = Item
    
    async def list(self, request, db, **kwargs):
        # db is auto-injected
        return await super().list(request, db, **kwargs)
```

## Dependency Override

For testing:

```python
from fastapi.testclient import TestClient

async def mock_get_db():
    yield test_session

app.dependency_overrides[get_db] = mock_get_db

client = TestClient(app)
response = client.get("/items")
```

## Common Patterns

### Require Admin

```python
from core.dependencies import get_current_user

async def require_admin(user = Depends(get_current_user)):
    if not user.is_admin:
        raise HTTPException(403, "Admin required")
    return user

async def admin_view(user = Depends(require_admin)):
    return {"admin": True}
```

### Tenant Context

```python
async def get_tenant(
    request: Request,
    db: DatabaseSession,
    user: CurrentUser,
):
    tenant_id = request.headers.get("X-Tenant-ID") or user.default_tenant_id
    return await Tenant.objects.using(db).get(id=tenant_id)

async def my_view(tenant = Depends(get_tenant)):
    return {"tenant": tenant.name}
```

### Combined Dependencies

```python
async def get_post_with_permission(
    post_id: int,
    db: DatabaseSession,
    user: CurrentUser,
):
    post = await Post.objects.using(db).get_or_none(id=post_id)
    if not post:
        raise HTTPException(404, "Post not found")
    if post.author_id != user.id and not user.is_admin:
        raise HTTPException(403, "Not allowed")
    return post

async def update_post(post = Depends(get_post_with_permission)):
    # post is loaded and permission checked
    pass
```

## Next

- [Routing](23-routing.md) — URL routing
- [ViewSets](04-viewsets.md) — CRUD endpoints
