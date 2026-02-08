# Soft Delete

Logical deletion instead of permanent removal.

## Setup

Add `SoftDeleteMixin` to your model:

```python
from core import Model, Field
from core.models import SoftDeleteMixin, SoftDeleteManager
from sqlalchemy.orm import Mapped

class Item(Model, SoftDeleteMixin):
    __tablename__ = "items"
    objects = SoftDeleteManager["Item"]()
    
    id: Mapped[int] = Field.pk()
    name: Mapped[str] = Field.string(max_length=200)
```

This adds:
- `deleted_at: Mapped[DateTime | None]` field
- `is_deleted` and `is_active` properties
- `soft_delete()`, `restore()`, `hard_delete()` methods

## Basic Usage

### Soft Delete

```python
# Soft delete (sets deleted_at)
await item.soft_delete(db)

# Check status
item.is_deleted  # True
item.is_active   # False
```

### Restore

```python
# Restore (sets deleted_at = None)
await item.restore(db)

item.is_deleted  # False
item.is_active   # True
```

### Hard Delete

```python
# Permanent deletion
await item.hard_delete(db)
```

## Querying

### Default Behavior

Soft-deleted records are **excluded by default**:

```python
# Only active records
items = await Item.objects.using(db).all()
```

### Include Deleted

```python
# All records (active + deleted)
items = await Item.objects.using(db).with_deleted().all()
```

### Only Deleted

```python
# Only soft-deleted records
items = await Item.objects.using(db).only_deleted().all()
```

### Explicit Active

```python
# Same as default, but explicit
items = await Item.objects.using(db).active().all()
```

## Bulk Operations

### Bulk Soft Delete

```python
count = await Item.objects.using(db).soft_delete_by(
    status="archived",
    created_at__lt=cutoff_date
)
```

### Bulk Restore

```python
count = await Item.objects.using(db).restore_by(
    workspace_id=workspace_id
)
```

## Configuration

```python
# src/settings.py
class AppSettings(Settings):
    soft_delete_field: str = "deleted_at"  # Field name
    soft_delete_cascade: bool = False      # Cascade to relations
    soft_delete_auto_filter: bool = True   # Auto-filter in queries
```

Or via environment:

```bash
SOFT_DELETE_FIELD=deleted_at
SOFT_DELETE_CASCADE=false
SOFT_DELETE_AUTO_FILTER=true
```

## Custom Field Name

```python
class Item(Model, SoftDeleteMixin):
    __tablename__ = "items"
    objects = SoftDeleteManager["Item"](deleted_field="removed_at")
```

## With Multi-Tenancy

Use `TenantSoftDeleteManager` for both:

```python
from core.models import TenantSoftDeleteManager

class Item(Model, SoftDeleteMixin, TenantMixin):
    __tablename__ = "items"
    objects = TenantSoftDeleteManager["Item"]()
```

```python
# Filter by tenant + exclude deleted
items = await Item.objects.using(db).for_tenant(tenant_id).all()

# Filter by tenant + include deleted
items = await Item.objects.using(db).for_tenant(tenant_id).with_deleted().all()
```

## ViewSet Integration

Soft delete works automatically in ViewSets:

```python
class ItemViewSet(ModelViewSet):
    model = Item  # Uses Item.objects (SoftDeleteManager)
    
    # DELETE endpoint calls soft_delete by default
    # if model has SoftDeleteMixin
```

Override for hard delete:

```python
class ItemViewSet(ModelViewSet):
    model = Item
    
    async def perform_destroy(self, instance, db):
        await instance.hard_delete(db)
```

## Filter Deleted in ViewSet

```python
class ItemViewSet(ModelViewSet):
    model = Item
    
    async def get_queryset(self, db):
        qs = Item.objects.using(db)
        
        # Include deleted for admins
        if self.request.user.is_admin:
            return qs.with_deleted()
        
        return qs  # Default: excludes deleted
```

## Migration

When adding soft delete to existing model:

```python
# 1. Add mixin
class Item(Model, SoftDeleteMixin):
    ...

# 2. Generate migration
core makemigrations

# 3. Apply
core migrate
```

The migration adds `deleted_at` column (nullable).

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `deleted_at` | `DateTime \| None` | Deletion timestamp |
| `is_deleted` | `bool` | `True` if `deleted_at` is set |
| `is_active` | `bool` | `True` if `deleted_at` is `None` |

## Methods

| Method | Description |
|--------|-------------|
| `soft_delete(db)` | Set `deleted_at = now()` |
| `restore(db)` | Set `deleted_at = None` |
| `hard_delete(db)` | Permanent deletion |

## Manager Methods

| Method | Description |
|--------|-------------|
| `with_deleted()` | Include deleted records |
| `only_deleted()` | Only deleted records |
| `active()` | Only active records (default) |
| `soft_delete_by(**filters)` | Bulk soft delete |
| `restore_by(**filters)` | Bulk restore |

## Next

- [QuerySets](12-querysets.md) — Querying data
- [Tenancy](32-tenancy.md) — Multi-tenant
