# Multi-Tenancy

Isolate data by tenant (workspace, organization, etc.).

## Setup

```python
# src/settings.py
class AppSettings(Settings):
    tenancy_enabled: bool = True
    tenancy_header: str = "X-Tenant-ID"  # Or from subdomain, path, etc.
```

## Tenant Model

```python
# src/apps/tenants/models.py
from core import Model, Field
from sqlalchemy.orm import Mapped

class Tenant(Model):
    __tablename__ = "tenants"
    
    id: Mapped[int] = Field.pk()
    name: Mapped[str] = Field.string(200)
    slug: Mapped[str] = Field.string(100, unique=True)
    is_active: Mapped[bool] = Field.boolean(default=True)
```

## Tenant Mixin

```python
# src/apps/posts/models.py
from core import Model, Field
from core.tenancy import TenantMixin
from sqlalchemy.orm import Mapped

class Post(TenantMixin, Model):
    __tablename__ = "posts"
    
    id: Mapped[int] = Field.pk()
    title: Mapped[str] = Field.string(200)
    # tenant_id is added automatically by TenantMixin
```

## Automatic Filtering

With `TenantMixin`, queries are automatically filtered:

```python
# Only returns posts for current tenant
posts = await Post.objects.all()

# Equivalent to:
posts = await Post.objects.filter(tenant_id=current_tenant_id).all()
```

## Set Tenant Context

```python
from core.tenancy import set_tenant, get_tenant

# In middleware or view
async def my_view(request):
    tenant_id = request.headers.get("X-Tenant-ID")
    set_tenant(tenant_id)
    
    # All queries now filtered by tenant
    posts = await Post.objects.all()
```

## Tenant Middleware

```python
# src/middleware.py
from core.tenancy import TenantMiddleware

# Auto-configured if tenancy_enabled=True
# Reads tenant from header, subdomain, or path
```

## Cross-Tenant Queries

```python
from core.tenancy import tenant_context

# Temporarily switch tenant
async with tenant_context(other_tenant_id):
    posts = await Post.objects.all()  # Other tenant's posts

# Or bypass tenant filter
posts = await Post.objects.unscoped().all()  # All posts
```

## Subdomain-Based Tenancy

```python
# src/settings.py
class AppSettings(Settings):
    tenancy_enabled: bool = True
    tenancy_mode: str = "subdomain"  # header, subdomain, path
```

Request to `acme.myapp.com` → tenant = "acme"

## Path-Based Tenancy

```python
tenancy_mode: str = "path"
```

Request to `/tenants/acme/posts` → tenant = "acme"

## Flexible Tenant Mixin

For models that can be tenant-scoped OR global:

```python
from core.tenancy import FlexibleTenantMixin

class Setting(FlexibleTenantMixin, Model):
    __tablename__ = "settings"
    
    id: Mapped[int] = Field.pk()
    key: Mapped[str] = Field.string(100)
    value: Mapped[str] = Field.text()
    # tenant_id is nullable - NULL means global
```

## Next

- [Replicas](23-replicas.md) — Read/write split
- [Settings](02-settings.md) — Tenancy settings
