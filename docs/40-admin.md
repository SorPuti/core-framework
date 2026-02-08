# Admin Panel

Django-style admin panel for managing data.

## Enable

Admin is enabled by default. Access at `/admin/`.

```python
# src/settings.py
class AppSettings(Settings):
    admin_enabled: bool = True  # Default
    admin_url_prefix: str = "/admin"
```

## Register Models

```python
# src/apps/posts/admin.py
from core.admin import admin, ModelAdmin
from .models import Post

@admin.register(Post)
class PostAdmin(ModelAdmin):
    list_display = ["id", "title", "published", "created_at"]
    list_filter = ["published"]
    search_fields = ["title", "content"]
    ordering = ["-created_at"]
```

## Options

```python
@admin.register(Post)
class PostAdmin(ModelAdmin):
    # List view
    list_display = ["id", "title", "author", "published"]
    list_filter = ["published", "author"]
    search_fields = ["title", "content"]
    ordering = ["-created_at"]
    list_per_page = 25
    
    # Detail view
    fields = ["title", "content", "published"]
    readonly_fields = ["created_at", "updated_at"]
    
    # Fieldsets (group fields)
    fieldsets = [
        ("Content", {"fields": ["title", "content"]}),
        ("Status", {"fields": ["published"]}),
        ("Metadata", {"fields": ["created_at", "updated_at"]}),
    ]
```

## Relationships

```python
@admin.register(Post)
class PostAdmin(ModelAdmin):
    list_display = ["id", "title", "author"]
    
    # Show related field in list
    def author(self, obj):
        return obj.author.email if obj.author else "-"
```

## Actions

```python
@admin.register(Post)
class PostAdmin(ModelAdmin):
    list_display = ["id", "title", "published"]
    actions = ["publish", "unpublish"]
    
    @admin.action(description="Publish selected")
    async def publish(self, request, queryset):
        for post in queryset:
            post.published = True
            await post.save()
    
    @admin.action(description="Unpublish selected")
    async def unpublish(self, request, queryset):
        for post in queryset:
            post.published = False
            await post.save()
```

## Permissions

Admin access requires `is_staff=True`.

```python
@admin.register(Post)
class PostAdmin(ModelAdmin):
    # Disable specific actions
    can_add = True
    can_edit = True
    can_delete = False  # Disable delete
    can_view = True
```

## User Admin

Built-in User admin with password handling:

```python
# src/apps/users/admin.py
from core.admin import admin
from core.auth.admin import UserAdmin
from .models import User

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ["id", "email", "is_active", "is_staff"]
    list_filter = ["is_active", "is_staff", "is_superuser"]
    search_fields = ["email", "first_name", "last_name"]
    
    fieldsets = [
        ("Account", {"fields": ["email", "password"]}),
        ("Profile", {"fields": ["first_name", "last_name"]}),
        ("Permissions", {"fields": ["is_active", "is_staff", "is_superuser", "groups"]}),
    ]
```

## Theme

```python
class AppSettings(Settings):
    admin_site_title: str = "My Admin"
    admin_site_header: str = "My App Administration"
    admin_primary_color: str = "#3B82F6"  # Blue
```

Users can toggle dark/light mode in the admin panel.

## Login

Admin uses session-based auth (separate from API JWT).

Default login: `/admin/login`

Create admin user:

```bash
core createsuperuser
```

## Auto-Discovery

Admin modules are auto-discovered from `admin.py` files in your apps.

Structure:

```
src/apps/
├── posts/
│   ├── models.py
│   └── admin.py  # Auto-discovered
└── users/
    ├── models.py
    └── admin.py  # Auto-discovered
```

## Next

- [CLI](07-cli.md) — Command reference
- [Permissions](08-permissions.md) — Access control
