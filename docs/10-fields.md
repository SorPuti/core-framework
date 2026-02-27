# Fields

All field types for models.

## Basic Fields (`Field`)

### `Field.pk()`

Auto-increment integer primary key.

```python
id: Mapped[int] = Field.pk()
```

### `Field.integer()`

```python
Field.integer(
    primary_key=False,
    autoincrement=False,
    nullable=False,
    default=None,
    index=False,
)

# Examples
age: Mapped[int] = Field.integer()
score: Mapped[int] = Field.integer(default=0, index=True)
count: Mapped[int | None] = Field.integer(nullable=True)
```

### `Field.string()`

```python
Field.string(
    max_length=255,
    nullable=False,
    default=None,
    unique=False,
    index=False,
)

# Examples
name: Mapped[str] = Field.string(max_length=100)
code: Mapped[str] = Field.string(max_length=10, unique=True)
title: Mapped[str | None] = Field.string(nullable=True)
```

### `Field.text()`

Unlimited text.

```python
Field.text(nullable=False, default=None)

# Examples
content: Mapped[str] = Field.text()
bio: Mapped[str | None] = Field.text(nullable=True)
```

### `Field.boolean()`

```python
Field.boolean(nullable=False, default=False, index=False)

# Examples
is_active: Mapped[bool] = Field.boolean(default=True)
is_verified: Mapped[bool] = Field.boolean(default=False, index=True)
```

### `Field.datetime()`

```python
Field.datetime(
    nullable=False,
    default=None,
    auto_now=False,       # Update on INSERT and UPDATE
    auto_now_add=False,   # Set only on INSERT
    index=False,
)

# Examples
created_at: Mapped[DateTime] = Field.datetime(auto_now_add=True)
updated_at: Mapped[DateTime] = Field.datetime(auto_now=True)
expires_at: Mapped[DateTime | None] = Field.datetime(nullable=True)
```

### `Field.float()`

```python
Field.float(nullable=False, default=None, index=False)

# Examples
price: Mapped[float] = Field.float()
rating: Mapped[float] = Field.float(default=0.0)
```

### `Field.foreign_key()`

```python
Field.foreign_key(
    target="table.column",
    nullable=False,
    ondelete="CASCADE",  # CASCADE, SET NULL, RESTRICT, NO ACTION
    index=True,
)

# Examples
user_id: Mapped[int] = Field.foreign_key("users.id")
category_id: Mapped[int | None] = Field.foreign_key(
    "categories.id",
    nullable=True,
    ondelete="SET NULL"
)
```

### `Field.choice()`

```python
Field.choice(
    choices_class,        # TextChoices or IntegerChoices
    default=None,
    nullable=False,
    index=False,
    use_native_enum=False,  # PostgreSQL ENUM type
)

# Example
from core.choices import TextChoices

class Status(TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"

status: Mapped[str] = Field.choice(Status, default=Status.DRAFT)
```

## Advanced Fields (`AdvancedField`)

### `AdvancedField.uuid_pk()`

UUID primary key (uses UUID7 by default).

```python
from core.fields import AdvancedField
from uuid import UUID

id: Mapped[UUID] = AdvancedField.uuid_pk()
```

### `AdvancedField.uuid()`

```python
AdvancedField.uuid(
    nullable=False,
    default=None,
    unique=False,
    index=False,
    use_uuid7=True,  # Time-sortable
)

# Examples
public_id: Mapped[UUID] = AdvancedField.uuid(unique=True)
reference: Mapped[UUID | None] = AdvancedField.uuid(nullable=True)
```

### `AdvancedField.uuid4()`

Random UUID4 (no temporal ordering).

```python
token: Mapped[UUID] = AdvancedField.uuid4(unique=True)
```

### `AdvancedField.json_field()`

JSON/JSONB field.

```python
AdvancedField.json_field(nullable=False, default=None)

# Examples
metadata: Mapped[dict] = AdvancedField.json_field(default={})
tags: Mapped[list] = AdvancedField.json_field(default=[])
config: Mapped[dict | None] = AdvancedField.json_field(nullable=True)
```

PostgreSQL uses JSONB (supports indexing). SQLite/MySQL use JSON.

### `AdvancedField.long_text()`

Alias for `Field.text()`.

```python
description: Mapped[str] = AdvancedField.long_text()
```

### `AdvancedField.slug()`

URL-friendly slug.

```python
AdvancedField.slug(
    max_length=255,
    nullable=False,
    unique=True,   # Default: True
    index=True,    # Default: True
)

# Example
slug: Mapped[str] = AdvancedField.slug()
```

### `AdvancedField.email()`

Email field.

```python
AdvancedField.email(
    max_length=255,
    nullable=False,
    unique=True,   # Default: True
    index=True,    # Default: True
)

# Example
email: Mapped[str] = AdvancedField.email()
```

### `AdvancedField.bigint_pk()`

BigInteger primary key.

```python
id: Mapped[int] = AdvancedField.bigint_pk()
```

### `AdvancedField.file()` — FileField (Django-style)

Campo de arquivo com interface rica para upload, download e URLs assinadas.

```python
AdvancedField.file(
    db_column="cover_url",           # Coluna do banco que armazena o path
    upload_to="courses/covers/",     # Diretório de upload ou função
    url_expiration=3600,             # Expiração da signed URL (segundos)
)
```

**Exemplo completo:**

```python
from core import Model, Field
from core.fields import AdvancedField

class Course(Model):
    __tablename__ = "courses"
    
    id: Mapped[int] = Field.pk()
    name: Mapped[str] = Field.string(255)
    
    # Coluna do banco (string que armazena o path)
    cover_url: Mapped[str | None] = Field.string(500, nullable=True)
    
    # FileField - interface rica para arquivos
    cover = AdvancedField.file("cover_url", upload_to="courses/covers/")

# Uso:
course.cover.name     # "courses/covers/abc.jpg"
course.cover.url      # "https://...?X-Goog-Signature=..." (signed URL)
course.cover.save("foto.jpg", content, "image/jpeg")  # Upload
course.cover.delete() # Remove do storage
bool(course.cover)    # True se tem arquivo
course.cover.exists() # Verifica se existe
```

**Upload com path dinâmico:**

```python
def course_path(instance, filename):
    return f"courses/{instance.id}/{filename}"

cover = AdvancedField.file("cover_url", upload_to=course_path)
```

**Ver também:** [Storage](37-storage.md) para configuração de GCS e signed URLs.

## Complete Model Example

```python
from core import Model, Field
from core.fields import AdvancedField
from core.choices import TextChoices
from core.datetime import DateTime
from sqlalchemy.orm import Mapped
from uuid import UUID

class Status(TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    ARCHIVED = "archived", "Archived"

class Post(Model):
    __tablename__ = "posts"
    
    # Primary key
    id: Mapped[int] = Field.pk()
    
    # Basic fields
    title: Mapped[str] = Field.string(max_length=200)
    slug: Mapped[str] = AdvancedField.slug()
    content: Mapped[str] = Field.text()
    
    # Status with choices
    status: Mapped[str] = Field.choice(Status, default=Status.DRAFT)
    
    # JSON metadata
    metadata: Mapped[dict] = AdvancedField.json_field(default={})
    
    # Foreign key
    author_id: Mapped[int] = Field.foreign_key("users.id")
    
    # Timestamps
    created_at: Mapped[DateTime] = Field.datetime(auto_now_add=True)
    updated_at: Mapped[DateTime] = Field.datetime(auto_now=True)
    published_at: Mapped[DateTime | None] = Field.datetime(nullable=True)
    
    # Flags
    is_featured: Mapped[bool] = Field.boolean(default=False, index=True)
```

## Database Type Mapping

| Field | PostgreSQL | SQLite | MySQL |
|-------|------------|--------|-------|
| `Field.pk()` | `SERIAL` | `INTEGER` | `INT AUTO_INCREMENT` |
| `Field.integer()` | `INTEGER` | `INTEGER` | `INT` |
| `Field.string()` | `VARCHAR(n)` | `VARCHAR(n)` | `VARCHAR(n)` |
| `Field.text()` | `TEXT` | `TEXT` | `TEXT` |
| `Field.boolean()` | `BOOLEAN` | `INTEGER` | `TINYINT(1)` |
| `Field.datetime()` | `TIMESTAMP WITH TIME ZONE` | `DATETIME` | `DATETIME` |
| `Field.float()` | `FLOAT` | `REAL` | `FLOAT` |
| `AdvancedField.uuid_pk()` | `UUID` | `VARCHAR(36)` | `VARCHAR(36)` |
| `AdvancedField.json_field()` | `JSONB` | `JSON` | `JSON` |

## Next

- [Relations](11-relations.md) — Relationships
- [Models](03-models.md) — Model basics
