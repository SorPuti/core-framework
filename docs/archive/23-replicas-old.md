# Read/Write Replicas

Split database reads and writes for scalability.

## Setup

```python
# src/settings.py
class AppSettings(Settings):
    # Primary (writes)
    database_url: str = "postgresql+asyncpg://user:pass@primary:5432/db"
    
    # Replica (reads)
    database_read_url: str = "postgresql+asyncpg://user:pass@replica:5432/db"
```

## Automatic Routing

Queries are automatically routed:

```python
# Reads go to replica
posts = await Post.objects.all()
post = await Post.objects.get(id=1)

# Writes go to primary
post = Post(title="New")
await post.save()

await Post.objects.filter(id=1).update(title="Updated")
await Post.objects.filter(id=1).delete()
```

## Explicit Database

```python
from core.database import get_write_db, get_read_db

# Force write database
async with get_write_db() as db:
    posts = await Post.objects.using(db).all()

# Force read database
async with get_read_db() as db:
    post = await Post.objects.using(db).get(id=1)
```

## Read After Write

For consistency after writes:

```python
# Create on primary
post = Post(title="New")
await post.save()

# Read from primary (not replica) to avoid replication lag
from core.database import get_write_db

async with get_write_db() as db:
    fresh_post = await Post.objects.using(db).get(id=post.id)
```

## Multiple Replicas

```python
# src/settings.py
class AppSettings(Settings):
    database_url: str = "postgresql+asyncpg://primary/db"
    database_read_urls: list[str] = [
        "postgresql+asyncpg://replica1/db",
        "postgresql+asyncpg://replica2/db",
    ]
```

Reads are load-balanced across replicas.

## Connection Pools

```python
class AppSettings(Settings):
    # Primary pool
    database_pool_size: int = 10
    database_max_overflow: int = 20
    
    # Replica pool (can be larger for reads)
    database_read_pool_size: int = 20
    database_read_max_overflow: int = 40
```

## Health Checks

```python
# Built-in health checks
# GET /healthz - Basic health
# GET /readyz - Database connectivity (both primary and replica)
```

## Monitoring

```python
from core.database import get_replica_stats

stats = await get_replica_stats()
# {
#     "primary": {"connections": 5, "available": 5},
#     "replica": {"connections": 10, "available": 10},
# }
```

## Fallback

If replica is unavailable, reads fall back to primary:

```python
class AppSettings(Settings):
    database_replica_fallback: bool = True  # Default
```

## Next

- [Settings](02-settings.md) — Database settings
- [Models](03-models.md) — Model definitions
