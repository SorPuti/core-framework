# Models

SQLAlchemy models with Django-style conveniences.

## Basic Model

```python
from core import Model, Field
from sqlalchemy.orm import Mapped

class Post(Model):
    __tablename__ = "posts"
    
    id: Mapped[int] = Field.pk()
    title: Mapped[str] = Field.string(max_length=200)
    content: Mapped[str] = Field.text()
    views: Mapped[int] = Field.integer(default=0)
    published: Mapped[bool] = Field.boolean(default=False)
    created_at: Mapped[datetime] = Field.datetime(auto_now_add=True)
```

## Field Types

| Field | SQL Type | Example |
|-------|----------|---------|
| `Field.pk()` | INTEGER PRIMARY KEY | `id: Mapped[int] = Field.pk()` |
| `Field.uuid_pk()` | UUID PRIMARY KEY | `id: Mapped[UUID] = Field.uuid_pk()` |
| `Field.string(max_length)` | VARCHAR | `name: Mapped[str] = Field.string(100)` |
| `Field.text()` | TEXT | `bio: Mapped[str] = Field.text()` |
| `Field.integer()` | INTEGER | `age: Mapped[int] = Field.integer()` |
| `Field.float_()` | FLOAT | `price: Mapped[float] = Field.float_()` |
| `Field.boolean()` | BOOLEAN | `active: Mapped[bool] = Field.boolean()` |
| `Field.datetime()` | TIMESTAMP | `created: Mapped[datetime] = Field.datetime()` |
| `Field.date()` | DATE | `birth: Mapped[date] = Field.date()` |
| `Field.json()` | JSON/JSONB | `meta: Mapped[dict] = Field.json()` |

## Field Options

```python
Field.string(
    max_length=200,      # VARCHAR length
    nullable=True,       # Allow NULL
    default="draft",     # Python default
    index=True,          # Create index
    unique=True,         # Unique constraint
)
```

## Auto Timestamps

```python
class Post(Model):
    __tablename__ = "posts"
    
    id: Mapped[int] = Field.pk()
    created_at: Mapped[datetime] = Field.datetime(auto_now_add=True)  # Set on create
    updated_at: Mapped[datetime] = Field.datetime(auto_now=True)      # Set on update
```

## Relationships

```python
from core.relations import Rel

class Post(Model):
    __tablename__ = "posts"
    
    id: Mapped[int] = Field.pk()
    author_id: Mapped[int] = Field.fk("users.id")
    
    # Relationship (for ORM access)
    author: Mapped["User"] = Rel.many_to_one("User", back_populates="posts")

class User(Model):
    __tablename__ = "users"
    
    id: Mapped[int] = Field.pk()
    posts: Mapped[list["Post"]] = Rel.one_to_many("Post", back_populates="author")
```

### Relationship Types

```python
# Many-to-One (FK on this model)
author: Mapped["User"] = Rel.many_to_one("User")

# One-to-Many (FK on other model)
posts: Mapped[list["Post"]] = Rel.one_to_many("Post")

# Many-to-Many
tags: Mapped[list["Tag"]] = Rel.many_to_many("Tag", secondary="post_tags")
```

## User Model

Extend `AbstractUser` for authentication:

```python
from core.auth import AbstractUser, PermissionsMixin
from core import Field
from sqlalchemy.orm import Mapped

class User(AbstractUser, PermissionsMixin):
    __tablename__ = "users"
    
    # AbstractUser provides: id, email, password, is_active, is_staff, is_superuser
    # PermissionsMixin provides: groups, user_permissions
    
    # Add custom fields
    first_name: Mapped[str | None] = Field.string(max_length=100, nullable=True)
    avatar_url: Mapped[str | None] = Field.string(max_length=500, nullable=True)
```

## Model Discovery

All models must be imported in `src/apps/models.py`:

```python
# src/apps/models.py
from src.apps.users.models import User  # noqa
from src.apps.posts.models import Post  # noqa
```

This ensures models are registered before migrations run.

## QuerySet (Django-style)

```python
# Get all
posts = await Post.objects.all()

# Filter
posts = await Post.objects.filter(published=True).all()

# Get one
post = await Post.objects.get(id=1)

# First
post = await Post.objects.filter(author_id=1).first()

# Count
count = await Post.objects.filter(published=True).count()

# Order
posts = await Post.objects.order_by("-created_at").all()

# Limit
posts = await Post.objects.limit(10).all()
```

See [QuerySets](10-querysets.md) for full reference.

## Next

- [ViewSets](04-viewsets.md) — CRUD endpoints
- [Migrations](08-migrations.md) — Schema changes
- [QuerySets](10-querysets.md) — Advanced queries
