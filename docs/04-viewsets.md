# ViewSets

Auto-generate CRUD endpoints from models.

## Basic ViewSet

```python
from core import ModelViewSet
from .models import Post

class PostViewSet(ModelViewSet):
    model = Post
```

Generated endpoints:

| Method | Path | Action |
|--------|------|--------|
| GET | /posts/ | `list` |
| POST | /posts/ | `create` |
| GET | /posts/{id} | `retrieve` |
| PUT | /posts/{id} | `update` |
| PATCH | /posts/{id} | `partial_update` |
| DELETE | /posts/{id} | `destroy` |

## Schemas

Control input/output data:

```python
from core import ModelViewSet, InputSchema, OutputSchema
from .models import Post

class PostInput(InputSchema):
    title: str
    content: str
    published: bool = False

class PostOutput(OutputSchema):
    id: int
    title: str
    content: str
    published: bool
    created_at: datetime

class PostViewSet(ModelViewSet):
    model = Post
    input_schema = PostInput
    output_schema = PostOutput
```

## Permissions

```python
from core import ModelViewSet
from core.permissions import AllowAny, IsAuthenticated, IsAdminUser

class PostViewSet(ModelViewSet):
    model = Post
    
    # Default for all actions
    permission_classes = [IsAuthenticated]
    
    # Override per action
    permission_classes_by_action = {
        "list": [AllowAny],
        "retrieve": [AllowAny],
        "create": [IsAuthenticated],
        "update": [IsAuthenticated],
        "destroy": [IsAdminUser],
    }
```

## Custom Actions

```python
from core import ModelViewSet, action
from fastapi import Response

class PostViewSet(ModelViewSet):
    model = Post
    
    @action(detail=True, methods=["POST"])
    async def publish(self, request, pk: int) -> dict:
        """POST /posts/{pk}/publish/"""
        post = await self.get_object(pk)
        post.published = True
        await post.save()
        return {"status": "published"}
    
    @action(detail=False, methods=["GET"])
    async def recent(self, request) -> list[dict]:
        """GET /posts/recent/"""
        posts = await Post.objects.filter(published=True).order_by("-created_at").limit(5).all()
        return [self.serialize(p) for p in posts]
```

### Action Options

```python
@action(
    detail=True,           # True: /posts/{pk}/action/, False: /posts/action/
    methods=["POST"],      # HTTP methods
    url_path="custom-path", # Override URL path
    permission_classes=[IsAdminUser],  # Override permissions
)
```

## Hooks

Override lifecycle methods:

```python
class PostViewSet(ModelViewSet):
    model = Post
    
    async def perform_create(self, instance, validated_data: dict) -> None:
        """Called after create, before save."""
        instance.author_id = self.request.user.id
        await instance.save()
    
    async def perform_update(self, instance, validated_data: dict) -> None:
        """Called after update, before save."""
        instance.updated_by = self.request.user.id
        await instance.save()
    
    async def perform_destroy(self, instance) -> None:
        """Called before delete."""
        # Soft delete instead
        instance.deleted = True
        await instance.save()
```

## QuerySet Filtering

```python
class PostViewSet(ModelViewSet):
    model = Post
    
    def get_queryset(self, db):
        """Filter queryset based on request."""
        qs = super().get_queryset(db)
        
        # Only show user's own posts
        if not self.request.user.is_staff:
            qs = qs.filter(author_id=self.request.user.id)
        
        return qs
```

## Pagination

```python
class PostViewSet(ModelViewSet):
    model = Post
    page_size = 20  # Default: 25
```

Query params: `?page=1&per_page=20`

Response:

```json
{
  "items": [...],
  "total": 100,
  "page": 1,
  "per_page": 20,
  "pages": 5
}
```

## Read-Only ViewSet

```python
from core import ReadOnlyModelViewSet

class PostViewSet(ReadOnlyModelViewSet):
    model = Post
    # Only list and retrieve, no create/update/delete
```

## Routes

```python
# src/apps/posts/routes.py
from core import AutoRouter
from .views import PostViewSet

router = AutoRouter(prefix="/posts", tags=["Posts"])
router.register("", PostViewSet)
```

```python
# src/main.py
from core import CoreApp, AutoRouter
from src.apps.posts.routes import router as posts_router

api = AutoRouter(prefix="/api/v1")
api.include_router(posts_router)

app = CoreApp(routers=[api])
```

## Next

- [Auth](05-auth.md) — Authentication
- [Permissions](08-permissions.md) — Access control
