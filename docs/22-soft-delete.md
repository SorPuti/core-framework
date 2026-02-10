# Soft Delete

Deleção lógica ao invés de remoção permanente, com configuração via Settings.

## Setup

Adicione `SoftDeleteMixin` ao seu model:

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

Isso adiciona:
- Campo `deleted_at: Mapped[DateTime | None]`
- Propriedades `is_deleted` e `is_active`
- Métodos `soft_delete()`, `restore()`, `hard_delete()`

## Configuração via Settings

```python
# src/settings.py
class AppSettings(Settings):
    soft_delete_field: str = "deleted_at"      # Nome do campo
    soft_delete_cascade: bool = False          # Cascade para relações
    soft_delete_auto_filter: bool = True       # Auto-filtrar em queries
```

Ou via ambiente:

```bash
SOFT_DELETE_FIELD=deleted_at
SOFT_DELETE_CASCADE=false
SOFT_DELETE_AUTO_FILTER=true
```

## Settings de Soft Delete

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `soft_delete_field` | `str` | `"deleted_at"` | Nome do campo de soft delete |
| `soft_delete_cascade` | `bool` | `False` | Soft delete em cascata para relacionamentos |
| `soft_delete_auto_filter` | `bool` | `True` | Filtrar deletados automaticamente em queries |

## Uso Básico

### Soft Delete

```python
# Soft delete (define deleted_at)
await item.soft_delete(db)

# Verificar status
item.is_deleted  # True
item.is_active   # False
```

### Restaurar

```python
# Restaurar (define deleted_at = None)
await item.restore(db)

item.is_deleted  # False
item.is_active   # True
```

### Hard Delete

```python
# Deleção permanente
await item.hard_delete(db)
```

## Queries

### Comportamento Padrão

Registros soft-deleted são **excluídos por padrão**:

```python
# Apenas registros ativos
items = await Item.objects.using(db).all()
```

### Incluir Deletados

```python
# Todos os registros (ativos + deletados)
items = await Item.objects.using(db).with_deleted().all()
```

### Apenas Deletados

```python
# Apenas registros soft-deleted
items = await Item.objects.using(db).only_deleted().all()
```

### Ativos Explícito

```python
# Mesmo que padrão, mas explícito
items = await Item.objects.using(db).active().all()
```

## Operações em Bulk

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

## Nome de Campo Customizado

```python
class Item(Model, SoftDeleteMixin):
    __tablename__ = "items"
    objects = SoftDeleteManager["Item"](deleted_field="removed_at")
```

## Com Multi-Tenancy

Use `TenantSoftDeleteManager` para ambos:

```python
from core.models import TenantSoftDeleteManager

class Item(Model, SoftDeleteMixin, TenantMixin):
    __tablename__ = "items"
    objects = TenantSoftDeleteManager["Item"]()
```

```python
# Filtra por tenant + exclui deletados
items = await Item.objects.using(db).for_tenant(tenant_id).all()

# Filtra por tenant + inclui deletados
items = await Item.objects.using(db).for_tenant(tenant_id).with_deleted().all()
```

## Integração com ViewSet

Soft delete funciona automaticamente em ViewSets:

```python
class ItemViewSet(ModelViewSet):
    model = Item  # Usa Item.objects (SoftDeleteManager)
    
    # Endpoint DELETE chama soft_delete por padrão
    # se model tem SoftDeleteMixin
```

Sobrescrever para hard delete:

```python
class ItemViewSet(ModelViewSet):
    model = Item
    
    async def perform_destroy(self, instance, db):
        await instance.hard_delete(db)
```

## Filtrar Deletados no ViewSet

```python
class ItemViewSet(ModelViewSet):
    model = Item
    
    async def get_queryset(self, db):
        qs = Item.objects.using(db)
        
        # Incluir deletados para admins
        if self.request.user.is_admin:
            return qs.with_deleted()
        
        return qs  # Padrão: exclui deletados
```

## Migration

Ao adicionar soft delete a model existente:

```python
# 1. Adicionar mixin
class Item(Model, SoftDeleteMixin):
    ...

# 2. Gerar migration
core makemigrations

# 3. Aplicar
core migrate
```

A migration adiciona coluna `deleted_at` (nullable).

## Propriedades

| Propriedade | Tipo | Descrição |
|-------------|------|-----------|
| `deleted_at` | `DateTime \| None` | Timestamp de deleção |
| `is_deleted` | `bool` | `True` se `deleted_at` está definido |
| `is_active` | `bool` | `True` se `deleted_at` é `None` |

## Métodos

| Método | Descrição |
|--------|-----------|
| `soft_delete(db)` | Define `deleted_at = now()` |
| `restore(db)` | Define `deleted_at = None` |
| `hard_delete(db)` | Deleção permanente |

## Métodos do Manager

| Método | Descrição |
|--------|-----------|
| `with_deleted()` | Incluir registros deletados |
| `only_deleted()` | Apenas registros deletados |
| `active()` | Apenas registros ativos (padrão) |
| `soft_delete_by(**filters)` | Bulk soft delete |
| `restore_by(**filters)` | Bulk restore |

## Próximos Passos

- [QuerySets](12-querysets.md) — Consultas de dados
- [Tenancy](32-tenancy.md) — Multi-tenant
- [Settings](02-settings.md) — Todas as configurações
