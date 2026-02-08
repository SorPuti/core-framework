# Read/Write Replicas

Sistema para separar queries de leitura (SELECT) das de escrita (INSERT/UPDATE/DELETE), permitindo escalar horizontalmente.

## Conceito

```
┌─────────────────────────────────────────────────┐
│                   Aplicação                      │
│                                                  │
│  ┌─────────────┐         ┌─────────────┐       │
│  │   Escrita   │         │   Leitura   │       │
│  │  (INSERT,   │         │  (SELECT)   │       │
│  │   UPDATE,   │         │             │       │
│  │   DELETE)   │         │             │       │
│  └──────┬──────┘         └──────┬──────┘       │
└─────────┼───────────────────────┼───────────────┘
          │                       │
          ▼                       ▼
    ┌──────────┐           ┌──────────┐
    │ Primary  │──────────▶│ Replica  │
    │ (Write)  │ replicação│ (Read)   │
    └──────────┘           └──────────┘
```

**Benefícios:**

- Escala horizontal para leituras
- Primary dedicado a escritas
- Melhor performance geral
- Alta disponibilidade

## Configuração via Settings (Recomendado)

A forma mais simples é configurar via `.env`. O CoreApp configura tudo automaticamente.

```env
# .env
# Primary (escrita)
DATABASE_URL=postgresql+asyncpg://user:pass@primary:5432/db
DATABASE_POOL_SIZE=5
DATABASE_MAX_OVERFLOW=10

# Replica (leitura) - OPCIONAL
DATABASE_READ_URL=postgresql+asyncpg://user:pass@replica:5432/db
DATABASE_READ_POOL_SIZE=10
DATABASE_READ_MAX_OVERFLOW=20
```

| Campo | Tipo | Default | Descrição |
|-------|------|---------|-----------|
| `DATABASE_URL` | str | sqlite... | URL do primary (escrita) |
| `DATABASE_READ_URL` | str \| None | None | URL da replica (leitura) |
| `DATABASE_READ_POOL_SIZE` | int \| None | None | Pool da replica (2x write se None) |
| `DATABASE_READ_MAX_OVERFLOW` | int \| None | None | Overflow da replica (2x write se None) |

```python
# main.py - nada a configurar manualmente!
from core import CoreApp
from src.api.config import settings

app = CoreApp(settings=settings)
# Se DATABASE_READ_URL estiver definido, usa replicas automaticamente
# Senão, usa DATABASE_URL para tudo
```

**Verificar se replica está ativa:**

```python
from src.api.config import settings

if settings.has_read_replica:
    print("Usando replica separada")
else:
    print("Usando apenas primary")
```

## Configuração Manual (Alternativa)

Se preferir configurar manualmente:

```python
from core.database import init_replicas, close_replicas

# Startup
await init_replicas(
    write_url="postgresql+asyncpg://user:pass@primary:5432/db",
    read_url="postgresql+asyncpg://user:pass@replica:5432/db",
)

# Shutdown
await close_replicas()
```

Ou usando valores das settings:

```python
# init_replicas() sem argumentos usa settings automaticamente
await init_replicas()
```

## Uso Básico

### DatabaseSession

Container que fornece sessões separadas para read e write.

```python
from fastapi import Depends
from core.database import get_db_replicas, DatabaseSession

@router.get("/users")
async def list_users(db: DatabaseSession = Depends(get_db_replicas)):
    # Leitura vai para replica
    users = await User.objects.using(db.read).all()
    return users

@router.post("/users")
async def create_user(
    data: UserCreate,
    db: DatabaseSession = Depends(get_db_replicas),
):
    # Escrita vai para primary
    user = await User.objects.using(db.write).create(**data.model_dump())
    return user
```

### Type Aliases

```python
from core.database import DBSession, WriteSession, ReadSession

# Equivalente a Annotated[DatabaseSession, Depends(get_db_replicas)]
@router.get("/users")
async def list_users(db: DBSession):
    return await User.objects.using(db.read).all()

# Apenas escrita
@router.post("/users")
async def create_user(db: WriteSession):
    return await User.objects.using(db).create(...)

# Apenas leitura (mais eficiente para endpoints read-only)
@router.get("/users/{id}")
async def get_user(id: int, db: ReadSession):
    return await User.objects.using(db).get(id=id)
```

## Dependencies Disponíveis

| Dependency | Retorno | Uso |
|------------|---------|-----|
| `get_db_replicas` | `DatabaseSession` | Read + Write |
| `get_write_db` | `AsyncSession` | Apenas Write |
| `get_read_db` | `AsyncSession` | Apenas Read |

### Quando usar cada uma

```python
# get_db_replicas - Operações mistas
@router.put("/users/{id}")
async def update_user(id: int, data: UserUpdate, db: DBSession):
    # Lê do replica
    user = await User.objects.using(db.read).get(id=id)
    # Escreve no primary
    for key, value in data.model_dump().items():
        setattr(user, key, value)
    await user.save(db.write)
    return user

# get_read_db - Apenas leitura (mais eficiente)
@router.get("/stats")
async def get_stats(db: ReadSession):
    return await User.objects.using(db).aggregate(
        total=Count("id"),
        active=Count("id", filter=User.is_active == True),
    )

# get_write_db - Apenas escrita
@router.post("/bulk-create")
async def bulk_create(items: list[ItemCreate], db: WriteSession):
    return await Item.objects.using(db).bulk_create(
        [item.model_dump() for item in items]
    )
```

## DatabaseSession API

```python
class DatabaseSession:
    # Sessões
    write: AsyncSession      # Primary (escrita)
    read: AsyncSession       # Replica (leitura)
    primary: AsyncSession    # Alias para write
    replica: AsyncSession    # Alias para read
    
    # Métodos
    def is_using_replica() -> bool  # True se replica separada
    async def commit()              # Commit no write
    async def rollback()            # Rollback no write
    async def close()               # Fecha ambas sessões
```

## Padrões de Uso

### ViewSet com Replicas

```python
from core import ModelViewSet
from core.database import DatabaseSession

class UserViewSet(ModelViewSet):
    model = User
    
    def get_queryset(self, db: DatabaseSession):
        # Leitura usa replica
        return User.objects.using(db.read)
    
    async def create(self, request, db: DatabaseSession, data, **kwargs):
        # Criação usa primary
        return await User.objects.using(db.write).create(**data)
    
    async def update(self, request, db: DatabaseSession, data, **kwargs):
        # Lê do replica, escreve no primary
        obj = await self.get_object(db.read, **kwargs)
        for key, value in data.items():
            setattr(obj, key, value)
        await obj.save(db.write)
        return obj
```

### Transações

```python
@router.post("/transfer")
async def transfer(data: TransferData, db: DBSession):
    # Transações sempre no primary
    async with db.write.begin():
        # Débito
        from_account = await Account.objects.using(db.write).get(id=data.from_id)
        from_account.balance -= data.amount
        await from_account.save(db.write)
        
        # Crédito
        to_account = await Account.objects.using(db.write).get(id=data.to_id)
        to_account.balance += data.amount
        await to_account.save(db.write)
    
    return {"status": "success"}
```

## Configuração Avançada

### Pool de Conexões

```python
await init_replicas(
    write_url="postgresql+asyncpg://...",
    read_url="postgresql+asyncpg://...",
    
    # Pool do primary
    pool_size=5,
    max_overflow=10,
    
    # Replica automaticamente usa pool maior (2x)
    # pool_size=10, max_overflow=20
    
    # Outras opções
    pool_pre_ping=True,    # Verifica conexão antes de usar
    pool_recycle=3600,     # Recicla conexões após 1h
    echo=False,            # Log de SQL
)
```

### Health Check

```python
from core.database import check_database_health

@router.get("/health")
async def health():
    return await check_database_health()
    # {
    #     "write": {"status": "healthy"},
    #     "read": {"status": "healthy"},
    #     "replica_configured": True
    # }
```

### Verificar Configuração

```python
from core.database import is_replica_configured

if is_replica_configured():
    print("Usando replica separada")
else:
    print("Usando apenas primary")
```

## Considerações

### Replication Lag

Replicas podem ter pequeno atraso em relação ao primary.

```python
# Problema: Criar e ler imediatamente
@router.post("/users")
async def create_user(data: UserCreate, db: DBSession):
    user = await User.objects.using(db.write).create(**data.model_dump())
    
    # ❌ Pode não encontrar - replication lag
    # user = await User.objects.using(db.read).get(id=user.id)
    
    # ✅ Lê do primary após escrita
    await db.write.refresh(user)
    return user
```

### Read-After-Write

Para garantir leitura após escrita, use o primary:

```python
@router.put("/users/{id}")
async def update_user(id: int, data: UserUpdate, db: DBSession):
    # Lê do primary para garantir dados atuais
    user = await User.objects.using(db.write).get(id=id)
    
    for key, value in data.model_dump().items():
        setattr(user, key, value)
    
    await user.save(db.write)
    return user
```

### Quando NÃO usar replica

- Operações que precisam de dados 100% atuais
- Transações que envolvem leitura + escrita
- Verificações de unicidade
- Contadores críticos

```python
# ❌ Não use replica para verificar unicidade
exists = await User.objects.using(db.read).exists(email=email)

# ✅ Use primary
exists = await User.objects.using(db.write).exists(email=email)
```

## Fallback Automático

Se `read_url` não for fornecido, o sistema usa `write_url` para tudo:

```python
# Sem replica - db.read == db.write
await init_replicas(
    write_url="postgresql+asyncpg://localhost:5432/db",
)

# Código funciona igual
users = await User.objects.using(db.read).all()  # Usa primary
```

Isso permite desenvolver localmente sem replica e usar replica em produção sem mudar código.

## Exemplo Completo

```python
from fastapi import FastAPI
from contextlib import asynccontextmanager
from core import Model, Field, ModelViewSet
from core.fields import AdvancedField
from core.database import (
    init_replicas,
    close_replicas,
    DBSession,
    ReadSession,
)

# Model
class User(Model):
    __tablename__ = "users"
    id: Mapped[UUID] = AdvancedField.uuid_pk()
    email: Mapped[str] = AdvancedField.email()
    name: Mapped[str] = Field.string(max_length=100)

# Lifecycle
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_replicas(
        write_url=settings.database_write_url,
        read_url=settings.database_read_url,
    )
    yield
    await close_replicas()

app = FastAPI(lifespan=lifespan)

# Endpoints
@app.get("/users")
async def list_users(db: ReadSession):
    """Lista usuários (replica)."""
    return await User.objects.using(db).all()

@app.post("/users")
async def create_user(data: UserCreate, db: DBSession):
    """Cria usuário (primary)."""
    return await User.objects.using(db.write).create(**data.model_dump())

@app.get("/users/{id}")
async def get_user(id: UUID, db: ReadSession):
    """Busca usuário (replica)."""
    return await User.objects.using(db).get(id=id)
```

---

Próximo: [Soft Delete](23-soft-delete.md) - Exclusão lógica de registros.
