# Multi-Tenancy

Data isolation for multi-tenant applications.

## Setup

```python
# src/settings.py
class AppSettings(Settings):
    tenancy_enabled: bool = True
    tenancy_field: str = "workspace_id"  # Default FK field
```

## Tenant Model

```python
from core import Model, Field
from sqlalchemy.orm import Mapped

class Workspace(Model):
    __tablename__ = "workspaces"
    
    id: Mapped[int] = Field.pk()
    name: Mapped[str] = Field.string(max_length=100)
    slug: Mapped[str] = Field.string(max_length=50, unique=True)
```

## TenantMixin

Add to models that belong to a tenant:

```python
from core import Model, Field
from core.tenancy import TenantMixin, TenantManager
from sqlalchemy.orm import Mapped

class Project(Model, TenantMixin):
    __tablename__ = "projects"
    objects = TenantManager["Project"]()
    
    id: Mapped[int] = Field.pk()
    name: Mapped[str] = Field.string(max_length=200)
    # workspace_id is added by TenantMixin
```

## Querying

### Filter by Tenant

```python
# Explicit tenant
projects = await Project.objects.using(db).for_tenant(workspace_id).all()

# From context (set by middleware)
projects = await Project.objects.using(db).for_tenant().all()
```

### Cross-Tenant Query

```python
# All projects (admin use)
all_projects = await Project.objects.using(db).all()
```

## TenantMiddleware

Auto-sets tenant context from request:

```python
# src/settings.py
class AppSettings(Settings):
    middleware: list[str] = [
        "tenant",  # or "tenancy"
        "auth",
    ]
```

The middleware extracts tenant from:
1. `X-Tenant-ID` header
2. User's default tenant
3. Query parameter `?tenant_id=`

## Set Tenant Context

### In Middleware

```python
from core.tenancy import set_tenant_context

class CustomTenantMiddleware(ASGIMiddleware):
    async def before_request(self, scope, request):
        tenant_id = extract_tenant(request)
        set_tenant_context(tenant_id)
        return None
```

### In View

```python
from core.tenancy import set_tenant_context

async def my_view(request, db):
    set_tenant_context(request.user.workspace_id)
    
    # Now for_tenant() uses this context
    projects = await Project.objects.using(db).for_tenant().all()
```

## ViewSet Integration

```python
from core import ModelViewSet
from core.tenancy import TenantMixin

class ProjectViewSet(ModelViewSet):
    model = Project
    
    async def get_queryset(self, db):
        # Auto-filter by tenant
        return Project.objects.using(db).for_tenant(
            self.request.state.tenant_id
        )
    
    async def perform_create(self, instance, validated_data, db):
        instance.workspace_id = self.request.state.tenant_id
        await instance.save(db)
```

## Subdomain Tenancy

```python
class SubdomainTenantMiddleware(ASGIMiddleware):
    async def before_request(self, scope, request):
        host = request.headers.get("host", "")
        subdomain = host.split(".")[0]
        
        workspace = await Workspace.objects.using(db).get_or_none(
            slug=subdomain
        )
        
        if workspace:
            set_tenant_context(workspace.id)
            request.state.workspace = workspace
        
        return None
```

## Path-Based Tenancy

```python
# Routes: /workspaces/{workspace_id}/projects/

class ProjectViewSet(ModelViewSet):
    model = Project
    
    async def get_queryset(self, db, workspace_id: int):
        return Project.objects.using(db).for_tenant(workspace_id)
```

## FlexibleTenantMixin

For models that can be tenant-scoped or global:

```python
from core.tenancy import FlexibleTenantMixin

class Template(Model, FlexibleTenantMixin):
    __tablename__ = "templates"
    
    id: Mapped[int] = Field.pk()
    name: Mapped[str] = Field.string(max_length=100)
    # workspace_id is nullable
```

```python
# Global templates (workspace_id = NULL)
global_templates = await Template.objects.using(db).filter(
    workspace_id__isnull=True
).all()

# Tenant templates
tenant_templates = await Template.objects.using(db).for_tenant(workspace_id).all()

# Both
all_templates = await Template.objects.using(db).filter(
    Q(workspace_id__isnull=True) | Q(workspace_id=workspace_id)
).all()
```

## With Soft Delete

```python
from core.models import TenantSoftDeleteManager

class Project(Model, TenantMixin, SoftDeleteMixin):
    __tablename__ = "projects"
    objects = TenantSoftDeleteManager["Project"]()
```

```python
# Filter by tenant + exclude deleted
projects = await Project.objects.using(db).for_tenant(workspace_id).all()

# Include deleted
projects = await Project.objects.using(db).for_tenant(workspace_id).with_deleted().all()
```

## Custom Tenant Field

```python
class Project(Model, TenantMixin):
    __tablename__ = "projects"
    
    # Override default field name
    tenant_field = "organization_id"
    
    organization_id: Mapped[int] = Field.foreign_key("organizations.id")
```

## Complete Example

```python
# src/apps/workspaces/models.py
from core import Model, Field
from sqlalchemy.orm import Mapped

class Workspace(Model):
    __tablename__ = "workspaces"
    
    id: Mapped[int] = Field.pk()
    name: Mapped[str] = Field.string(max_length=100)
    slug: Mapped[str] = Field.string(max_length=50, unique=True)

# src/apps/projects/models.py
from core import Model, Field
from core.tenancy import TenantMixin, TenantManager
from sqlalchemy.orm import Mapped

class Project(Model, TenantMixin):
    __tablename__ = "projects"
    objects = TenantManager["Project"]()
    
    id: Mapped[int] = Field.pk()
    name: Mapped[str] = Field.string(max_length=200)

# src/apps/projects/views.py
from core import ModelViewSet

class ProjectViewSet(ModelViewSet):
    model = Project
    
    async def get_queryset(self, db):
        return Project.objects.using(db).for_tenant(
            self.request.state.tenant_id
        )
    
    async def perform_create(self, instance, validated_data, db):
        instance.workspace_id = self.request.state.tenant_id
        await instance.save(db)
```

## Next

- [Soft Delete](22-soft-delete.md) — Logical deletion
- [QuerySets](12-querysets.md) — Querying data
