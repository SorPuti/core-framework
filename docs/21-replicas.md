# Database Replicas

Read/write split for database scaling.

## Configuration

```python
# src/settings.py
class AppSettings(Settings):
    # Primary (write)
    database_url: str = "postgresql+asyncpg://user:pass@primary:5432/db"
    
    # Replica (read)
    database_read_url: str = "postgresql+asyncpg://user:pass@replica:5432/db"
```

Or via environment:

```bash
# .env
DATABASE_URL=postgresql+asyncpg://user:pass@primary:5432/db
DATABASE_READ_URL=postgresql+asyncpg://user:pass@replica:5432/db
```

## How It Works

When `database_read_url` is configured:

1. Write operations → Primary database
2. Read operations → Replica database
3. You choose which to use via dependencies

## Dependencies

### get_db_replicas

Returns `DatabaseSession` with `.read` and `.write` properties.

```python
from core.database import get_db_replicas, DatabaseSession
from fastapi import Depends

async def my_view(db: DatabaseSession = Depends(get_db_replicas)):
    # Read from replica
    users = await User.objects.using(db.read).all()
    
    # Write to primary
    user = User(name="John")
    await user.save(db.write)
```

### get_write_db

Write-only session.

```python
from core.database import get_write_db
from sqlalchemy.ext.asyncio import AsyncSession

async def create_user(db: AsyncSession = Depends(get_write_db)):
    user = User(name="John")
    await user.save(db)
```

### get_read_db

Read-only session.

```python
from core.database import get_read_db

async def list_users(db: AsyncSession = Depends(get_read_db)):
    return await User.objects.using(db).all()
```

## Type Aliases

```python
from core.database import DBSession, WriteSession, ReadSession

async def my_view(
    db: DBSession,           # DatabaseSession with .read/.write
    write_db: WriteSession,  # AsyncSession for writes
    read_db: ReadSession,    # AsyncSession for reads
):
    pass
```

## QuerySet Usage

```python
# Explicit read
users = await User.objects.using(db.read).filter(active=True).all()

# Explicit write
await User.objects.using(db.write).filter(id=1).update(name="Jane")
```

## Pool Configuration

```python
# src/settings.py
class AppSettings(Settings):
    # Write pool
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_pool_timeout: int = 30
    database_pool_recycle: int = 3600
    
    # Read pool (defaults to 2x write)
    database_read_pool_size: int | None = None  # Default: 10
    database_read_max_overflow: int | None = None  # Default: 20
```

## Check Replica Status

```python
from core.database import is_replica_configured

if is_replica_configured():
    print("Using separate read replica")
else:
    print("Using single database")
```

## DatabaseSession Methods

```python
db: DatabaseSession = Depends(get_db_replicas)

# Properties
db.write    # Write session (primary)
db.read     # Read session (replica)
db.primary  # Alias for write
db.replica  # Alias for read

# Check if using replica
db.is_using_replica()  # True if read != write

# Transaction control
await db.commit()    # Commit write session
await db.rollback()  # Rollback write session
await db.close()     # Close both sessions
```

## Read-After-Write Consistency

**Important:** Replicas may have replication lag.

```python
async def create_and_read(db: DatabaseSession = Depends(get_db_replicas)):
    # Create on primary
    user = User(name="John")
    await user.save(db.write)
    await db.commit()
    
    # Read from primary (not replica) for consistency
    user = await User.objects.using(db.write).get(id=user.id)
    
    # Or wait for replication
    await asyncio.sleep(0.1)
    user = await User.objects.using(db.read).get(id=user.id)
```

## Fallback Behavior

If `database_read_url` is not set or equals `database_url`:

- `db.read` and `db.write` return the same session
- `is_replica_configured()` returns `False`
- No behavior change needed in code

## ViewSet Integration

ViewSets use `get_db` by default (single session). For replicas:

```python
from core.database import get_db_replicas

class UserViewSet(ModelViewSet):
    model = User
    
    # Override to use replicas
    async def get_queryset(self, db):
        # db is from get_db, but you can use replicas
        return User.objects.using(db)
```

Or configure globally:

```python
# In CoreApp setup
from core.dependencies import set_session_factory
from core.database import get_db_replicas

set_session_factory(get_db_replicas)
```

## Initialization

Replicas are auto-initialized by CoreApp when `database_read_url` is set.

Manual initialization:

```python
from core.database import init_replicas

await init_replicas(
    write_url="postgresql+asyncpg://...",
    read_url="postgresql+asyncpg://...",
    pool_size=5,
    max_overflow=10,
)
```

## Next

- [QuerySets](12-querysets.md) — Querying data
- [Settings](02-settings.md) — Configuration
