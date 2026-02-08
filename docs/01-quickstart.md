# Quickstart

Create a working API in 5 minutes.

## Architecture Overview

```mermaid
flowchart TB
    subgraph Client
        REQ[HTTP Request]
    end
    
    subgraph "Core Framework"
        MW[Middleware Stack]
        RT[AutoRouter]
        VS[ViewSet]
        MD[Model]
        DB[(Database)]
    end
    
    REQ --> MW
    MW --> RT
    RT --> VS
    VS --> MD
    MD --> DB
    
    style MW fill:#e1f5fe
    style VS fill:#fff3e0
    style MD fill:#e8f5e9
```

## Requirements

- Python 3.12+
- PostgreSQL (or SQLite for dev)

## Install

```bash
# Global install (recommended)
pipx install core-framework

# Or per-project
pip install core-framework
```

## Create Project

```bash
core init my-api
cd my-api
```

This creates:

```
my-api/
├── src/
│   ├── settings.py      # Configuration
│   ├── main.py          # Entry point
│   └── apps/
│       ├── models.py    # Model imports
│       └── users/       # Example app
├── migrations/
├── .env
└── pyproject.toml
```

## Configure

Edit `src/settings.py`:

```python
from core.config import Settings, configure

class AppSettings(Settings):
    app_name: str = "My API"
    user_model: str = "src.apps.users.models.User"  # Required for auth

settings = configure(settings_class=AppSettings)
```

Edit `.env`:

```env
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/mydb
SECRET_KEY=change-me-in-production
DEBUG=true
```

## Create Model

```python
# src/apps/posts/models.py
from core import Model, Field
from sqlalchemy.orm import Mapped

class Post(Model):
    __tablename__ = "posts"
    
    id: Mapped[int] = Field.pk()
    title: Mapped[str] = Field.string(max_length=200, index=True)
    content: Mapped[str] = Field.text()
    published: Mapped[bool] = Field.boolean(default=False)
```

Import in barrel file:

```python
# src/apps/models.py
from src.apps.posts.models import Post  # noqa
```

## Create ViewSet

```python
# src/apps/posts/views.py
from core import ModelViewSet
from core.permissions import AllowAny
from .models import Post

class PostViewSet(ModelViewSet):
    model = Post
    permission_classes = [AllowAny]  # Public access
```

## Create Routes

```python
# src/apps/posts/routes.py
from core import AutoRouter
from .views import PostViewSet

router = AutoRouter(prefix="/posts", tags=["Posts"])
router.register("", PostViewSet)
```

## Register Routes

```python
# src/main.py
from core import CoreApp, AutoRouter
from core.config import get_settings
from src.apps.posts.routes import router as posts_router

settings = get_settings()

api = AutoRouter(prefix="/api/v1")
api.include_router(posts_router)

app = CoreApp(routers=[api])
```

## Run

```bash
# Create migration
core makemigrations --name add_posts

# Apply migration
core migrate

# Start server
core run
```

## Test

Open http://localhost:8000/docs

Generated endpoints:

| Method | Path | Action |
|--------|------|--------|
| GET | /api/v1/posts/ | List |
| POST | /api/v1/posts/ | Create |
| GET | /api/v1/posts/{id} | Get one |
| PUT | /api/v1/posts/{id} | Update |
| PATCH | /api/v1/posts/{id} | Partial update |
| DELETE | /api/v1/posts/{id} | Delete |

## Next

- [Settings](02-settings.md) — Configuration options
- [Models](03-models.md) — Field types, relationships
- [ViewSets](04-viewsets.md) — Custom actions, hooks
- [Auth](05-auth.md) — JWT authentication
