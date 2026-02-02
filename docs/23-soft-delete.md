# Soft Delete

Sistema de exclusão lógica (soft delete) que marca registros como deletados em vez de removê-los fisicamente.

## Conceito

```
Hard Delete (tradicional):
┌──────────┐     DELETE     ┌──────────┐
│ Registro │ ──────────────▶│  (vazio) │
└──────────┘                └──────────┘

Soft Delete:
┌──────────┐     UPDATE     ┌──────────────────┐
│ Registro │ ──────────────▶│ Registro         │
│          │  deleted_at    │ deleted_at=now() │
└──────────┘                └──────────────────┘
```

**Benefícios:**

- Recuperação de dados deletados
- Auditoria e compliance
- Integridade referencial
- Histórico de alterações

## Configuração via Settings (Opcional)

Configure o nome do campo e comportamento via `.env`:

```env
# .env
SOFT_DELETE_FIELD=deleted_at
SOFT_DELETE_CASCADE=false
SOFT_DELETE_AUTO_FILTER=true
```

| Campo | Tipo | Default | Descrição |
|-------|------|---------|-----------|
| `SOFT_DELETE_FIELD` | str | deleted_at | Nome do campo de soft delete |
| `SOFT_DELETE_CASCADE` | bool | false | Soft delete em cascata |
| `SOFT_DELETE_AUTO_FILTER` | bool | true | Filtra deletados automaticamente |

O `SoftDeleteManager` e `SoftDeleteQuerySet` usam essas configurações automaticamente.

## Uso

### 1. Adicionar Mixin ao Model

```python
from core import Model, Field, SoftDeleteMixin, SoftDeleteManager
from core.fields import AdvancedField
from uuid import UUID
from sqlalchemy.orm import Mapped

class User(Model, SoftDeleteMixin):
    __tablename__ = "users"
    
    # Manager especial que filtra deletados
    objects = SoftDeleteManager["User"]()
    
    id: Mapped[UUID] = AdvancedField.uuid_pk()
    email: Mapped[str] = AdvancedField.email()
    name: Mapped[str] = Field.string(max_length=100)
    # deleted_at já vem do SoftDeleteMixin
```

### 2. Usar Normalmente

```python
# Queries ignoram deletados automaticamente
users = await User.objects.using(db).all()  # Só ativos

# Soft delete
user = await User.objects.using(db).get(id=user_id)
await user.soft_delete(db)

# Restaurar
await user.restore(db)
```

## SoftDeleteMixin

Adiciona ao model:

| Atributo/Método | Tipo | Descrição |
|-----------------|------|-----------|
| `deleted_at` | `DateTime \| None` | Timestamp de deleção |
| `is_deleted` | `bool` | True se deletado |
| `is_active` | `bool` | True se ativo |
| `soft_delete(session)` | `async` | Marca como deletado |
| `restore(session)` | `async` | Restaura registro |
| `hard_delete(session)` | `async` | Deleta permanentemente |

### Exemplo

```python
# Verificar status
if user.is_deleted:
    print(f"Deletado em: {user.deleted_at}")

if user.is_active:
    print("Usuário ativo")

# Soft delete
await user.soft_delete(db)
assert user.is_deleted == True
assert user.deleted_at is not None

# Restaurar
await user.restore(db)
assert user.is_deleted == False
assert user.deleted_at is None

# Hard delete (permanente)
await user.hard_delete(db)  # Remove do banco
```

## SoftDeleteManager

Manager que filtra deletados automaticamente.

### Métodos Especiais

| Método | Descrição |
|--------|-----------|
| `with_deleted()` | Inclui registros deletados |
| `only_deleted()` | Apenas registros deletados |
| `active()` | Apenas ativos (padrão) |
| `soft_delete_by(**filters)` | Soft delete em massa |
| `restore_by(**filters)` | Restaura em massa |

### Exemplos

```python
# Padrão: apenas ativos
users = await User.objects.using(db).all()

# Incluir deletados
all_users = await User.objects.using(db).with_deleted().all()

# Apenas deletados
deleted_users = await User.objects.using(db).only_deleted().all()

# Explicitamente ativos
active_users = await User.objects.using(db).active().all()

# Soft delete em massa
count = await User.objects.using(db).soft_delete_by(is_active=False)
print(f"{count} usuários deletados")

# Restaurar em massa
count = await User.objects.using(db).restore_by(workspace_id=ws_id)
print(f"{count} usuários restaurados")
```

## SoftDeleteQuerySet

QuerySet com métodos de soft delete.

```python
from core.querysets import SoftDeleteQuerySet

# Uso direto
qs = SoftDeleteQuerySet(User, session)

# Apenas ativos (padrão)
users = await qs.filter(role="admin").all()

# Com deletados
users = await qs.filter(role="admin").with_deleted().all()

# Apenas deletados
users = await qs.filter(role="admin").only_deleted().all()
```

## ViewSet com Soft Delete

```python
from core import ModelViewSet
from core.database import DBSession

class UserViewSet(ModelViewSet):
    model = User
    
    async def destroy(self, request, db: DBSession, **kwargs):
        """Soft delete em vez de hard delete."""
        obj = await self.get_object(db.read, **kwargs)
        await obj.soft_delete(db.write)
        return {"message": "Deleted", "id": str(obj.id)}
    
    @action(detail=True, methods=["POST"])
    async def restore(self, request, db: DBSession, **kwargs):
        """Restaura registro deletado."""
        # Busca incluindo deletados
        obj = await User.objects.using(db.read).with_deleted().get(**kwargs)
        await obj.restore(db.write)
        return {"message": "Restored", "id": str(obj.id)}
    
    @action(detail=False, methods=["GET"])
    async def deleted(self, request, db: DBSession):
        """Lista registros deletados."""
        return await User.objects.using(db.read).only_deleted().all()
```

## Combinando com Tenant

### TenantSoftDeleteQuerySet

```python
from core.querysets import TenantSoftDeleteQuerySet

# Filtra por tenant E exclui deletados
qs = TenantSoftDeleteQuerySet(Domain, session)
domains = await qs.for_tenant().all()

# Filtra por tenant E inclui deletados
domains = await qs.for_tenant().with_deleted().all()

# Filtra por tenant E apenas deletados
domains = await qs.for_tenant().only_deleted().all()
```

### Model Completo

```python
from core import Model, Field, SoftDeleteMixin, SoftDeleteManager
from core.fields import AdvancedField
from core.tenancy import TenantMixin

class Domain(Model, TenantMixin, SoftDeleteMixin):
    __tablename__ = "domains"
    
    objects = SoftDeleteManager["Domain"]()
    
    id: Mapped[UUID] = AdvancedField.uuid_pk()
    domain: Mapped[str] = Field.string(max_length=255)
    # workspace_id do TenantMixin
    # deleted_at do SoftDeleteMixin
```

## Queries Avançadas

### Filtrar por Data de Deleção

```python
from core.datetime import timezone

# Deletados nos últimos 30 dias
thirty_days_ago = timezone.subtract(timezone.now(), days=30)
recent_deleted = await User.objects.using(db)\
    .only_deleted()\
    .filter(deleted_at__gte=thirty_days_ago)\
    .all()

# Deletados há mais de 90 dias (para limpeza)
ninety_days_ago = timezone.subtract(timezone.now(), days=90)
old_deleted = await User.objects.using(db)\
    .only_deleted()\
    .filter(deleted_at__lt=ninety_days_ago)\
    .all()
```

### Hard Delete de Registros Antigos

```python
async def cleanup_old_deleted(days: int = 90):
    """Remove permanentemente registros deletados há mais de X dias."""
    cutoff = timezone.subtract(timezone.now(), days=days)
    
    # Busca deletados antigos
    old_records = await User.objects.using(db)\
        .only_deleted()\
        .filter(deleted_at__lt=cutoff)\
        .all()
    
    # Hard delete
    for record in old_records:
        await record.hard_delete(db)
    
    return len(old_records)
```

## Índices Recomendados

```sql
-- Índice para queries de ativos (mais comum)
CREATE INDEX ix_users_deleted_at 
ON users (deleted_at) 
WHERE deleted_at IS NULL;

-- Índice para queries de deletados
CREATE INDEX ix_users_deleted_at_not_null 
ON users (deleted_at) 
WHERE deleted_at IS NOT NULL;

-- Índice composto com tenant
CREATE INDEX ix_users_workspace_deleted 
ON users (workspace_id, deleted_at);
```

## Considerações

### Unicidade

Soft delete pode causar conflitos de unicidade:

```python
# Problema: Email único
class User(Model, SoftDeleteMixin):
    email: Mapped[str] = Field.string(unique=True)

# User A: email="test@example.com" (ativo)
# User A deletado
# User B: email="test@example.com" (novo) - ERRO: unique violation
```

**Soluções:**

1. **Índice parcial** (recomendado):

```sql
-- Unicidade apenas para ativos
CREATE UNIQUE INDEX ix_users_email_active 
ON users (email) 
WHERE deleted_at IS NULL;
```

2. **Incluir deleted_at no unique**:

```python
class User(Model, SoftDeleteMixin):
    __table_args__ = (
        UniqueConstraint("email", "deleted_at", name="uq_users_email_deleted"),
    )
```

### Foreign Keys

Registros deletados ainda existem, então FKs continuam válidas:

```python
class Order(Model, SoftDeleteMixin):
    user_id: Mapped[UUID] = Field.foreign_key("users.id")

# User deletado, orders ainda referenciam
# Isso pode ser desejável (histórico) ou não
```

**Opções:**

1. **Cascade soft delete**: Delete orders quando user é deletado
2. **Manter referência**: Orders mantêm histórico
3. **Nullify**: Setar user_id = NULL quando user é deletado

### Performance

Soft delete adiciona condição em todas as queries:

```sql
-- Toda query inclui
WHERE deleted_at IS NULL
```

Para tabelas grandes, garanta índice em `deleted_at`:

```sql
CREATE INDEX ix_users_deleted_at ON users (deleted_at);
```

## Exemplo Completo

```python
from core import Model, Field, SoftDeleteMixin, SoftDeleteManager, ModelViewSet
from core.fields import AdvancedField
from core.tenancy import TenantMixin
from core.database import DBSession

# Model
class Document(Model, TenantMixin, SoftDeleteMixin):
    __tablename__ = "documents"
    
    objects = SoftDeleteManager["Document"]()
    
    id: Mapped[UUID] = AdvancedField.uuid_pk()
    title: Mapped[str] = Field.string(max_length=200)
    content: Mapped[str] = AdvancedField.long_text()
    created_at: Mapped[DateTime] = Field.datetime(auto_now_add=True)

# ViewSet
class DocumentViewSet(ModelViewSet):
    model = Document
    
    def get_queryset(self, db: DBSession):
        # Já filtra deletados automaticamente
        return Document.objects.using(db.read)
    
    async def destroy(self, request, db: DBSession, **kwargs):
        obj = await self.get_object(db.read, **kwargs)
        await obj.soft_delete(db.write)
        return {"status": "deleted"}
    
    @action(detail=True, methods=["POST"])
    async def restore(self, request, db: DBSession, **kwargs):
        obj = await Document.objects.using(db.read)\
            .with_deleted()\
            .get(**kwargs)
        await obj.restore(db.write)
        return {"status": "restored"}
    
    @action(detail=False, methods=["GET"])
    async def trash(self, request, db: DBSession):
        """Lista documentos na lixeira."""
        return await Document.objects.using(db.read)\
            .only_deleted()\
            .order_by("-deleted_at")\
            .all()
    
    @action(detail=True, methods=["DELETE"])
    async def permanent_delete(self, request, db: DBSession, **kwargs):
        """Remove permanentemente."""
        obj = await Document.objects.using(db.read)\
            .with_deleted()\
            .get(**kwargs)
        await obj.hard_delete(db.write)
        return {"status": "permanently deleted"}
```

---

Anterior: [Read/Write Replicas](22-replicas.md)
