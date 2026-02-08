# Permissions

Control access to endpoints.

## Built-in Permissions

```python
from core.permissions import AllowAny, IsAuthenticated, IsAdminUser

class PostViewSet(ModelViewSet):
    model = Post
    
    # Default for all actions
    permission_classes = [IsAuthenticated]
```

| Permission | Description |
|------------|-------------|
| `AllowAny` | No auth required |
| `IsAuthenticated` | Must be logged in |
| `IsAdminUser` | Must have `is_staff=True` |
| `IsSuperUser` | Must have `is_superuser=True` |

## Per-Action Permissions

```python
class PostViewSet(ModelViewSet):
    model = Post
    permission_classes = [IsAuthenticated]
    
    permission_classes_by_action = {
        "list": [AllowAny],           # Public
        "retrieve": [AllowAny],       # Public
        "create": [IsAuthenticated],  # Logged in
        "update": [IsAuthenticated],  # Logged in
        "destroy": [IsAdminUser],     # Admin only
    }
```

## Custom Permissions

```python
from core.permissions import Permission

class IsOwner(Permission):
    """Only allow object owner."""
    
    async def has_permission(self, request, view) -> bool:
        return request.user is not None
    
    async def has_object_permission(self, request, view, obj) -> bool:
        return obj.author_id == request.user.id

class PostViewSet(ModelViewSet):
    model = Post
    permission_classes = [IsAuthenticated, IsOwner]
```

## Role-Based Permissions

```python
from core.permissions import HasRole

class PostViewSet(ModelViewSet):
    model = Post
    
    permission_classes_by_action = {
        "create": [HasRole("editor")],
        "destroy": [HasRole("admin")],
    }
```

## Permission with Groups

```python
from core.permissions import Permission

class InGroup(Permission):
    """Check if user is in specific group."""
    
    def __init__(self, group_name: str):
        self.group_name = group_name
    
    async def has_permission(self, request, view) -> bool:
        if not request.user:
            return False
        return await request.user.is_in_group(self.group_name)

class PostViewSet(ModelViewSet):
    model = Post
    permission_classes = [InGroup("editors")]
```

## Combining Permissions

```python
# All must pass (AND)
permission_classes = [IsAuthenticated, IsOwner]

# Any must pass (OR) - use custom permission
class IsOwnerOrAdmin(Permission):
    async def has_object_permission(self, request, view, obj) -> bool:
        if request.user.is_staff:
            return True
        return obj.author_id == request.user.id
```

## Action Decorator

```python
from core import action
from core.permissions import IsAdminUser

class PostViewSet(ModelViewSet):
    model = Post
    
    @action(detail=True, methods=["POST"], permission_classes=[IsAdminUser])
    async def publish(self, request, pk: int):
        """Only admins can publish."""
        post = await self.get_object(pk)
        post.published = True
        await post.save()
        return {"status": "published"}
```

## Model-Level Permissions

```python
# Auto-collected from models
# Format: {app_label}.{action}_{model_name}

# posts.add_post
# posts.change_post
# posts.delete_post
# posts.view_post

# Check in code
if user.has_perm("posts.delete_post"):
    await post.delete()
```

## Collect Permissions

```bash
# Auto-generate permissions from models
core collectpermissions
```

## Next

- [Auth](05-auth.md) — Authentication
- [ViewSets](04-viewsets.md) — CRUD endpoints
