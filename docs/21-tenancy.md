# Multi-Tenancy

Sistema de multi-tenancy automático para aplicações SaaS. Filtra queries por tenant (workspace/organization) sem precisar passar o ID manualmente.

## Conceito

Multi-tenancy permite que múltiplos clientes (tenants) compartilhem a mesma aplicação e banco de dados, com isolamento de dados.

```
┌─────────────────────────────────────────────────┐
│                   Aplicação                      │
├─────────────────────────────────────────────────┤
│  Workspace A  │  Workspace B  │  Workspace C    │
│  (Tenant A)   │  (Tenant B)   │  (Tenant C)     │
├───────────────┴───────────────┴─────────────────┤
│                 Banco de Dados                   │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐         │
│  │ Dados A │  │ Dados B │  │ Dados C │         │
│  └─────────┘  └─────────┘  └─────────┘         │
└─────────────────────────────────────────────────┘
```

## Configuração via Settings (Recomendado)

A forma mais simples é configurar via `.env`. O CoreApp configura tudo automaticamente.

```env
# .env
TENANCY_ENABLED=true
TENANCY_FIELD=workspace_id
TENANCY_USER_ATTRIBUTE=workspace_id
TENANCY_HEADER=X-Tenant-ID
TENANCY_REQUIRE=false
```

| Campo | Tipo | Default | Descrição |
|-------|------|---------|-----------|
| `TENANCY_ENABLED` | bool | false | Habilita multi-tenancy |
| `TENANCY_FIELD` | str | workspace_id | Nome do campo nos models |
| `TENANCY_USER_ATTRIBUTE` | str | workspace_id | Atributo do usuário com tenant |
| `TENANCY_HEADER` | str | X-Tenant-ID | Header HTTP (fallback) |
| `TENANCY_REQUIRE` | bool | false | Rejeita requests sem tenant |

```python
# main.py - nada a configurar manualmente!
from core import CoreApp
from src.api.config import settings

app = CoreApp(settings=settings)
# TenantMiddleware é adicionado automaticamente quando tenancy_enabled=true
```

## Configuração Manual (Alternativa)

Se preferir configurar manualmente sem usar Settings:

```python
from fastapi import FastAPI
from core.tenancy import TenantMiddleware

app = FastAPI()

# Adiciona middleware manualmente
app.add_middleware(
    TenantMiddleware,
    user_tenant_attr="organization_id",
    tenant_field="organization_id",
)
```

### 2. Usar TenantMixin nos Models

```python
from core import Model, Field
from core.fields import AdvancedField
from core.tenancy import TenantMixin
from uuid import UUID
from sqlalchemy.orm import Mapped

class Domain(Model, TenantMixin):
    __tablename__ = "domains"
    
    id: Mapped[UUID] = AdvancedField.uuid_pk()
    domain: Mapped[str] = Field.string(max_length=255, unique=True)
    is_verified: Mapped[bool] = Field.boolean(default=False)
    # workspace_id já vem do TenantMixin

class Project(Model, TenantMixin):
    __tablename__ = "projects"
    
    id: Mapped[UUID] = AdvancedField.uuid_pk()
    name: Mapped[str] = Field.string(max_length=100)
    # workspace_id já vem do TenantMixin
```

### 3. Filtrar por Tenant

```python
from core.tenancy import for_tenant

# Opção 1: Função utilitária
domains = await for_tenant(Domain.objects.using(db)).all()

# Opção 2: No ViewSet
class DomainViewSet(ModelViewSet):
    model = Domain
    
    def get_queryset(self, db):
        return for_tenant(super().get_queryset(db))
```

## TenantMixin vs FlexibleTenantMixin

### TenantMixin

Cria FK para tabela `workspaces`. Use quando tem tabela de workspaces.

```python
from core.tenancy import TenantMixin

class Domain(Model, TenantMixin):
    __tablename__ = "domains"
    # workspace_id: FK -> workspaces.id (CASCADE)
```

**Requer**: Tabela `workspaces` com coluna `id` UUID.

### FlexibleTenantMixin

Não cria FK. Use quando:
- Tabela de workspaces tem nome diferente
- Tenant é gerenciado em outro serviço
- Quer mais controle

```python
from core.tenancy import FlexibleTenantMixin

class Domain(Model, FlexibleTenantMixin):
    __tablename__ = "domains"
    # workspace_id: UUID (sem FK)
```

## Context API

### Definir Tenant

```python
from core.tenancy import set_tenant, get_tenant, require_tenant, clear_tenant

# Definir tenant (normalmente feito pelo middleware)
set_tenant(workspace_id)

# Obter tenant atual (pode ser None)
tenant_id = get_tenant()

# Obter tenant ou levantar exceção
tenant_id = require_tenant()  # RuntimeError se None

# Limpar tenant
clear_tenant()
```

### Context Manager para Testes

```python
from core.tenancy import tenant_context

# Em testes
async def test_list_domains():
    with tenant_context(workspace_id):
        domains = await Domain.objects.using(db).for_tenant().all()
        assert all(d.workspace_id == workspace_id for d in domains)

# Async também funciona
async with tenant_context(workspace_id):
    ...
```

## Dependency para FastAPI

```python
from fastapi import Depends
from core.tenancy import get_tenant_dependency
from uuid import UUID

@router.get("/items")
async def list_items(
    tenant_id: UUID = Depends(get_tenant_dependency),
    db: AsyncSession = Depends(get_db),
):
    # tenant_id garantido (400 se não definido)
    items = await Item.objects.using(db).filter(workspace_id=tenant_id).all()
    return items
```

## QuerySets com Tenant

### TenantQuerySet

QuerySet com método `for_tenant()` integrado.

```python
from core.querysets import TenantQuerySet

# Uso manual
qs = TenantQuerySet(Domain, session)
domains = await qs.for_tenant().all()

# Com tenant específico
domains = await qs.for_tenant(tenant_id=some_uuid).all()
```

### TenantSoftDeleteQuerySet

Combina tenant + soft delete.

```python
from core.querysets import TenantSoftDeleteQuerySet

# Filtra por tenant E exclui deletados
items = await TenantSoftDeleteQuerySet(Item, session).for_tenant().all()

# Filtra por tenant E inclui deletados
items = await TenantSoftDeleteQuerySet(Item, session).for_tenant().with_deleted().all()
```

## Exemplo Completo

### Model

```python
from core import Model, Field
from core.fields import AdvancedField
from core.tenancy import TenantMixin
from uuid import UUID
from sqlalchemy.orm import Mapped

class Workspace(Model):
    """Tabela de workspaces (tenants)."""
    __tablename__ = "workspaces"
    
    id: Mapped[UUID] = AdvancedField.uuid_pk()
    name: Mapped[str] = Field.string(max_length=100)
    slug: Mapped[str] = AdvancedField.slug()

class Domain(Model, TenantMixin):
    """Domínios pertencem a um workspace."""
    __tablename__ = "domains"
    
    id: Mapped[UUID] = AdvancedField.uuid_pk()
    domain: Mapped[str] = Field.string(max_length=255)
    is_verified: Mapped[bool] = Field.boolean(default=False)
```

### ViewSet

```python
from core import ModelViewSet
from core.tenancy import for_tenant

class DomainViewSet(ModelViewSet):
    model = Domain
    
    def get_queryset(self, db):
        """Filtra automaticamente pelo workspace do usuário."""
        return for_tenant(super().get_queryset(db))
    
    async def perform_create(self, db, data):
        """Adiciona workspace_id automaticamente na criação."""
        from core.tenancy import require_tenant
        data["workspace_id"] = require_tenant()
        return await super().perform_create(db, data)
```

### App

```python
from fastapi import FastAPI
from core.tenancy import TenantMiddleware

app = FastAPI()
app.add_middleware(TenantMiddleware)

# Rotas...
```

## Extração de Tenant

O middleware extrai o tenant de (em ordem):

1. **Usuário autenticado**: `request.state.user.workspace_id`
2. **Header**: `X-Tenant-ID`
3. **Query param**: `?tenant_id=...`

```python
# Customizar extração
from core.tenancy import extract_tenant_from_request

async def custom_middleware(request, call_next):
    tenant_id = await extract_tenant_from_request(
        request,
        user_tenant_attr="organization_id",
    )
    if tenant_id:
        set_tenant(tenant_id)
    
    response = await call_next(request)
    clear_tenant()
    return response
```

## Segurança

### Isolamento de Dados

O sistema garante que:

1. Queries filtram automaticamente por tenant
2. Usuário só acessa dados do seu workspace
3. Criação de registros inclui workspace_id

### Bypass (Admin)

Para operações administrativas que precisam acessar todos os tenants:

```python
# Não use for_tenant() - acessa todos
all_domains = await Domain.objects.using(db).all()

# Ou limpe o contexto temporariamente
clear_tenant()
all_domains = await Domain.objects.using(db).all()
```

**Cuidado**: Só faça isso em endpoints administrativos protegidos.

## Performance

### Índices

O `TenantMixin` já cria índice em `workspace_id`:

```python
workspace_id: Mapped[UUID] = mapped_column(
    ...,
    index=True,  # Índice automático
)
```

### Índices Compostos

Para queries frequentes, considere índices compostos:

```sql
-- Para queries: WHERE workspace_id = ? AND is_active = ?
CREATE INDEX ix_domains_workspace_active 
ON domains (workspace_id, is_active);

-- Para queries: WHERE workspace_id = ? ORDER BY created_at DESC
CREATE INDEX ix_domains_workspace_created 
ON domains (workspace_id, created_at DESC);
```

## Troubleshooting

### "No tenant set in current context"

```python
# Causa: Chamou require_tenant() ou for_tenant() sem tenant definido

# Solução 1: Adicione TenantMiddleware
app.add_middleware(TenantMiddleware)

# Solução 2: Use tenant_context em testes
with tenant_context(workspace_id):
    ...

# Solução 3: Defina manualmente
set_tenant(workspace_id)
```

### Tenant não extraído do usuário

```python
# Causa: Atributo do usuário diferente de "workspace_id"

# Solução: Configure o middleware
app.add_middleware(
    TenantMiddleware,
    user_tenant_attr="organization_id",  # Nome correto
)
```

---

Próximo: [Read/Write Replicas](22-replicas.md) - Separação de leitura e escrita.
