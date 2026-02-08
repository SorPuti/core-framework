# Relations

Relationship helpers for models.

## Rel Class

All relationships use the `Rel` class from `core/relations.py`.

## Foreign Key

```python
Rel.foreign_key(
    target="table.column",
    nullable=False,
    ondelete="CASCADE",
    index=True,
    type_="int",  # "int", "uuid", "bigint"
)
```

```python
from core.relations import Rel

class Post(Model):
    __tablename__ = "posts"
    
    # Integer FK (default)
    author_id: Mapped[int] = Rel.foreign_key("users.id")
    
    # UUID FK
    workspace_id: Mapped[UUID] = Rel.foreign_key(
        "workspaces.id",
        type_="uuid"
    )
    
    # Nullable FK
    category_id: Mapped[int | None] = Rel.foreign_key(
        "categories.id",
        nullable=True,
        ondelete="SET NULL"
    )
```

## Many-to-One (belongs_to)

```python
Rel.many_to_one(
    target="TargetModel",
    back_populates=None,
    backref=None,
    lazy="selectin",
    foreign_keys=None,
    uselist=False,
)
```

```python
class Post(Model):
    __tablename__ = "posts"
    
    author_id: Mapped[int] = Rel.foreign_key("users.id")
    author: Mapped["User"] = Rel.many_to_one(
        "User",
        back_populates="posts"
    )
```

Alias: `Rel.belongs_to()`

## One-to-Many (has_many)

```python
Rel.one_to_many(
    target="TargetModel",
    back_populates=None,
    backref=None,
    lazy="selectin",
    foreign_keys=None,
    cascade="all, delete-orphan",
    passive_deletes=True,
    order_by=None,
)
```

```python
class User(Model):
    __tablename__ = "users"
    
    posts: Mapped[list["Post"]] = Rel.one_to_many(
        "Post",
        back_populates="author",
        order_by="created_at"
    )
```

Alias: `Rel.has_many()`

## One-to-One (has_one)

```python
Rel.one_to_one(
    target="TargetModel",
    back_populates=None,
    backref=None,
    lazy="selectin",
    foreign_keys=None,
    cascade="all, delete-orphan",
    uselist=False,
)
```

```python
class User(Model):
    __tablename__ = "users"
    
    profile: Mapped["Profile"] = Rel.one_to_one(
        "Profile",
        back_populates="user"
    )

class Profile(Model):
    __tablename__ = "profiles"
    
    user_id: Mapped[int] = Rel.foreign_key("users.id", unique=True)
    user: Mapped["User"] = Rel.one_to_one(
        "User",
        back_populates="profile"
    )
```

Alias: `Rel.has_one()`

## Many-to-Many

```python
Rel.many_to_many(
    target="TargetModel",
    secondary="association_table",
    back_populates=None,
    backref=None,
    lazy="selectin",
    cascade="all",
    passive_deletes=True,
    order_by=None,
)
```

```python
from sqlalchemy import Table, Column, Integer, ForeignKey
from core import metadata

# Association table
post_tags = Table(
    "post_tags",
    metadata,
    Column("post_id", Integer, ForeignKey("posts.id"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id"), primary_key=True),
)

class Post(Model):
    __tablename__ = "posts"
    
    tags: Mapped[list["Tag"]] = Rel.many_to_many(
        "Tag",
        secondary=post_tags,
        back_populates="posts"
    )

class Tag(Model):
    __tablename__ = "tags"
    
    posts: Mapped[list["Post"]] = Rel.many_to_many(
        "Post",
        secondary=post_tags,
        back_populates="tags"
    )
```

## Self-Referential

```python
Rel.self_referential(
    back_populates=None,
    remote_side=None,
    lazy="selectin",
    cascade="all",
    foreign_keys=None,
    uselist=True,
)
```

```python
class Category(Model):
    __tablename__ = "categories"
    
    id: Mapped[int] = Field.pk()
    name: Mapped[str] = Field.string(max_length=100)
    parent_id: Mapped[int | None] = Rel.foreign_key(
        "categories.id",
        nullable=True
    )
    
    # Parent relationship
    parent: Mapped["Category | None"] = Rel.self_referential(
        back_populates="children",
        remote_side="Category.id",
        uselist=False
    )
    
    # Children relationship
    children: Mapped[list["Category"]] = Rel.self_referential(
        back_populates="parent",
        foreign_keys="Category.parent_id"
    )
```

## Lazy Loading Options

| Value | Behavior |
|-------|----------|
| `"selectin"` | Separate SELECT IN query (default, recommended) |
| `"joined"` | JOIN in same query |
| `"subquery"` | Subquery for loading |
| `"raise"` | Raise error if accessed without explicit load |
| `"noload"` | Never load |

## Cascade Options

| Value | Behavior |
|-------|----------|
| `"all"` | All operations |
| `"save-update"` | Cascade save/update |
| `"merge"` | Cascade merge |
| `"delete"` | Cascade delete |
| `"delete-orphan"` | Delete orphaned children |
| `"all, delete-orphan"` | All + delete orphan (default for one-to-many) |

## OnDelete Options

| Value | Behavior |
|-------|----------|
| `"CASCADE"` | Delete children when parent deleted (default) |
| `"SET NULL"` | Set FK to NULL when parent deleted |
| `"RESTRICT"` | Prevent deletion if children exist |
| `"NO ACTION"` | Database default behavior |

## Complete Example

```python
from core import Model, Field
from core.relations import Rel
from core.datetime import DateTime
from sqlalchemy.orm import Mapped
from sqlalchemy import Table, Column, Integer, ForeignKey
from core import metadata

# Association table for many-to-many
post_tags = Table(
    "post_tags",
    metadata,
    Column("post_id", Integer, ForeignKey("posts.id"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id"), primary_key=True),
)

class User(Model):
    __tablename__ = "users"
    
    id: Mapped[int] = Field.pk()
    name: Mapped[str] = Field.string(max_length=100)
    
    # One-to-many: User has many posts
    posts: Mapped[list["Post"]] = Rel.has_many(
        "Post",
        back_populates="author"
    )

class Post(Model):
    __tablename__ = "posts"
    
    id: Mapped[int] = Field.pk()
    title: Mapped[str] = Field.string(max_length=200)
    
    # Many-to-one: Post belongs to User
    author_id: Mapped[int] = Rel.foreign_key("users.id")
    author: Mapped["User"] = Rel.belongs_to(
        "User",
        back_populates="posts"
    )
    
    # Many-to-many: Post has many tags
    tags: Mapped[list["Tag"]] = Rel.many_to_many(
        "Tag",
        secondary=post_tags,
        back_populates="posts"
    )

class Tag(Model):
    __tablename__ = "tags"
    
    id: Mapped[int] = Field.pk()
    name: Mapped[str] = Field.string(max_length=50, unique=True)
    
    # Many-to-many: Tag has many posts
    posts: Mapped[list["Post"]] = Rel.many_to_many(
        "Post",
        secondary=post_tags,
        back_populates="tags"
    )
```

## Eager Loading in Queries

```python
# Load author with posts
user = await User.objects.using(db).select_related("posts").get(id=1)

# Load post with author and tags
post = await Post.objects.using(db).select_related("author", "tags").get(id=1)
```

## Next

- [QuerySets](12-querysets.md) — Querying data
- [Fields](10-fields.md) — Field types
