# Core Framework

Django-style framework for FastAPI. Models, ViewSets, Auth, Admin — batteries included.

## Install

```bash
pipx install core-framework
core init my-api && cd my-api
core run
# → http://localhost:8000/docs
```

## Documentation

### Getting Started

| Doc | Description |
|-----|-------------|
| [Quickstart](01-quickstart.md) | First API in 5 minutes |
| [Settings](02-settings.md) | Configuration system |
| [Models](03-models.md) | Database models |
| [ViewSets](04-viewsets.md) | CRUD endpoints |

### Authentication

| Doc | Description |
|-----|-------------|
| [Auth](05-auth.md) | JWT authentication |
| [Auth Backends](06-auth-backends.md) | Custom auth backends |
| [CLI](07-cli.md) | Command reference |

### Data Layer

| Doc | Description |
|-----|-------------|
| [Permissions](09-permissions.md) | Access control |
| [Fields](10-fields.md) | All field types |
| [Relations](11-relations.md) | Relationships |
| [QuerySets](12-querysets.md) | Django-style queries |
| [Serializers](13-serializers.md) | Input/Output schemas |
| [Validators](14-validators.md) | Data validation |

### Infrastructure

| Doc | Description |
|-----|-------------|
| [Middleware](20-middleware.md) | Request/response hooks |
| [Database Replicas](21-replicas.md) | Read/write split |
| [Soft Delete](22-soft-delete.md) | Logical deletion |
| [Routing](23-routing.md) | URL routing |
| [Dependencies](24-dependencies.md) | Dependency injection |

### Advanced

| Doc | Description |
|-----|-------------|
| [Messaging](30-messaging.md) | Kafka/Redis integration |
| [Workers](31-workers.md) | Background workers |
| [Tenancy](32-tenancy.md) | Multi-tenant |
| [Choices](33-choices.md) | TextChoices/IntegerChoices |
| [Exceptions](34-exceptions.md) | Error handling |
| [DateTime](35-datetime.md) | Timezone handling |
| [Security](36-security.md) | Security best practices |

### Reference

| Doc | Description |
|-----|-------------|
| [Admin](40-admin.md) | Admin panel |
| [Migrations](41-migrations.md) | Database migrations |

## Project Structure

```
my-api/
├── src/
│   ├── settings.py      # All config here
│   ├── main.py          # App entry point
│   └── apps/
│       ├── models.py    # Model imports (barrel)
│       └── items/
│           ├── models.py
│           ├── views.py
│           └── routes.py
├── migrations/
├── .env
└── pyproject.toml
```

## Minimal Example

```python
# src/settings.py
from core.config import Settings, configure

class AppSettings(Settings):
    app_name: str = "My API"

settings = configure(settings_class=AppSettings)
```

```python
# src/apps/items/models.py
from core import Model, Field
from sqlalchemy.orm import Mapped

class Item(Model):
    __tablename__ = "items"
    id: Mapped[int] = Field.pk()
    name: Mapped[str] = Field.string(max_length=200)
```

```python
# src/apps/items/views.py
from core import ModelViewSet
from .models import Item

class ItemViewSet(ModelViewSet):
    model = Item
```

```python
# src/main.py
from core import CoreApp, AutoRouter
from src.apps.items.routes import router as items_router

api = AutoRouter(prefix="/api/v1")
api.include_router(items_router)

app = CoreApp(routers=[api])
```

## Quick Commands

```bash
core init my-api          # Create project
core init my-api --minimal # Minimal project
core makemigrations       # Generate migrations
core migrate              # Apply migrations
core run                  # Start server
core createsuperuser      # Create admin user
```

## Links

- [GitHub](https://github.com/your-org/core-framework)
- [PyPI](https://pypi.org/project/core-framework/)
- [Changelog](CHANGELOG.md)
