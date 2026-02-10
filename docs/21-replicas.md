# Database Replicas

Separação read/write para escalabilidade de banco de dados.

## Arquitetura

```mermaid
flowchart LR
    subgraph App["Aplicação"]
        VS[ViewSet]
    end
    
    subgraph "Database Layer"
        VS --> |SELECT| READ[(Replica<br/>Read-only)]
        VS --> |INSERT/UPDATE/DELETE| WRITE[(Primary<br/>Read-Write)]
        WRITE --> |Replicação| READ
    end
    
    style READ fill:#e3f2fd
    style WRITE fill:#fff3e0
```

## Quando Usar

```mermaid
flowchart TB
    subgraph "Usar Replica (db.read)"
        R1[Queries de listagem]
        R2[Busca/Filtro]
        R3[Relatórios]
        R4[Analytics]
    end
    
    subgraph "Usar Primary (db.write)"
        W1[Criar registros]
        W2[Atualizar registros]
        W3[Deletar registros]
        W4[Transações]
    end
    
    style R1 fill:#e3f2fd
    style R2 fill:#e3f2fd
    style R3 fill:#e3f2fd
    style R4 fill:#e3f2fd
    style W1 fill:#fff3e0
    style W2 fill:#fff3e0
    style W3 fill:#fff3e0
    style W4 fill:#fff3e0
```

## Configuração via Settings

```python
# src/settings.py
class AppSettings(Settings):
    # Primary (write)
    database_url: str = "postgresql+asyncpg://user:pass@primary:5432/db"
    
    # Replica (read)
    database_read_url: str = "postgresql+asyncpg://user:pass@replica:5432/db"
    
    # Pool da replica (opcional, default: 2x do write)
    database_read_pool_size: int = 10
    database_read_max_overflow: int = 20
```

Ou via ambiente:

```bash
# .env
DATABASE_URL=postgresql+asyncpg://user:pass@primary:5432/db
DATABASE_READ_URL=postgresql+asyncpg://user:pass@replica:5432/db
```

## Settings de Replicas

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `database_read_url` | `str \| None` | `None` | URL do banco de leitura (replica) |
| `database_read_pool_size` | `int \| None` | `None` | Pool size para replica (default: 2x write) |
| `database_read_max_overflow` | `int \| None` | `None` | Max overflow para replica (default: 2x write) |

## Como Funciona

Quando `database_read_url` está configurado:

1. Operações de escrita → Banco Primary
2. Operações de leitura → Banco Replica
3. Você escolhe qual usar via dependencies

## Dependencies

### get_db_replicas

Retorna `DatabaseSession` com propriedades `.read` e `.write`.

```python
from core.database import get_db_replicas, DatabaseSession
from fastapi import Depends

async def my_view(db: DatabaseSession = Depends(get_db_replicas)):
    # Lê da replica
    users = await User.objects.using(db.read).all()
    
    # Escreve no primary
    user = User(name="John")
    await user.save(db.write)
```

### get_write_db

Sessão somente escrita.

```python
from core.database import get_write_db
from sqlalchemy.ext.asyncio import AsyncSession

async def create_user(db: AsyncSession = Depends(get_write_db)):
    user = User(name="John")
    await user.save(db)
```

### get_read_db

Sessão somente leitura.

```python
from core.database import get_read_db

async def list_users(db: AsyncSession = Depends(get_read_db)):
    return await User.objects.using(db).all()
```

## Type Aliases

```python
from core.database import DBSession, WriteSession, ReadSession

async def my_view(
    db: DBSession,           # DatabaseSession com .read/.write
    write_db: WriteSession,  # AsyncSession para escrita
    read_db: ReadSession,    # AsyncSession para leitura
):
    pass
```

## Uso com QuerySet

```python
# Leitura explícita
users = await User.objects.using(db.read).filter(active=True).all()

# Escrita explícita
await User.objects.using(db.write).filter(id=1).update(name="Jane")
```

## Configuração de Pool

```python
# src/settings.py
class AppSettings(Settings):
    # Pool de escrita
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_pool_timeout: int = 30
    database_pool_recycle: int = 3600
    
    # Pool de leitura (default: 2x escrita)
    database_read_pool_size: int | None = None  # Default: 10
    database_read_max_overflow: int | None = None  # Default: 20
```

## Verificar Status da Replica

```python
from core.database import is_replica_configured

if is_replica_configured():
    print("Usando replica de leitura separada")
else:
    print("Usando banco único")
```

## Métodos de DatabaseSession

```python
db: DatabaseSession = Depends(get_db_replicas)

# Propriedades
db.write    # Sessão de escrita (primary)
db.read     # Sessão de leitura (replica)
db.primary  # Alias para write
db.replica  # Alias para read

# Verificar se usa replica
db.is_using_replica()  # True se read != write

# Controle de transação
await db.commit()    # Commit da sessão de escrita
await db.rollback()  # Rollback da sessão de escrita
await db.close()     # Fecha ambas as sessões
```

## Consistência Read-After-Write

**Importante:** Replicas podem ter lag de replicação.

```python
async def create_and_read(db: DatabaseSession = Depends(get_db_replicas)):
    # Cria no primary
    user = User(name="John")
    await user.save(db.write)
    await db.commit()
    
    # Lê do primary (não da replica) para consistência
    user = await User.objects.using(db.write).get(id=user.id)
    
    # Ou aguarda replicação
    await asyncio.sleep(0.1)
    user = await User.objects.using(db.read).get(id=user.id)
```

## Comportamento de Fallback

Se `database_read_url` não está definido ou é igual a `database_url`:

- `db.read` e `db.write` retornam a mesma sessão
- `is_replica_configured()` retorna `False`
- Nenhuma mudança de comportamento necessária no código

## Integração com ViewSet

ViewSets usam `get_db` por padrão (sessão única). Para replicas:

```python
from core.database import get_db_replicas

class UserViewSet(ModelViewSet):
    model = User
    
    # Sobrescreve para usar replicas
    async def get_queryset(self, db):
        # db é de get_db, mas você pode usar replicas
        return User.objects.using(db)
```

Ou configure globalmente:

```python
# No setup do CoreApp
from core.dependencies import set_session_factory
from core.database import get_db_replicas

set_session_factory(get_db_replicas)
```

## Inicialização

Replicas são auto-inicializadas pelo CoreApp quando `database_read_url` está definido.

Inicialização manual:

```python
from core.database import init_replicas

await init_replicas(
    write_url="postgresql+asyncpg://...",
    read_url="postgresql+asyncpg://...",
    pool_size=5,
    max_overflow=10,
)
```

## Próximos Passos

- [QuerySets](12-querysets.md) — Consultas de dados
- [Settings](02-settings.md) — Todas as configurações
