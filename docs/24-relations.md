# Relations - Relacionamentos entre Models

O Core Framework fornece helpers para definir relacionamentos entre models de forma mais intuitiva, similar ao Django/Rails.

## Visão Geral

Em vez de usar `relationship()` do SQLAlchemy diretamente, você pode usar a classe `Rel` que oferece:

- Nomes mais descritivos (`many_to_one`, `one_to_many`, `many_to_many`)
- Defaults sensatos (lazy loading, cascade, etc.)
- Aliases familiares (`belongs_to`, `has_many`)
- Helper para tabelas de associação

## Importação

```python
from core import Rel, AssociationTable
# ou
from core.relations import Rel, AssociationTable
```

## Foreign Key

Use `Rel.foreign_key()` para criar colunas de chave estrangeira:

```python
from core import Model, Field
from core.relations import Rel

class Post(Model):
    __tablename__ = "posts"
    
    id: Mapped[int] = Field.pk()
    title: Mapped[str] = Field.string(max_length=200)
    
    # FK simples (integer)
    author_id: Mapped[int] = Rel.foreign_key("authors.id")
    
    # FK nullable
    category_id: Mapped[int | None] = Rel.foreign_key(
        "categories.id",
        nullable=True,
        ondelete="SET NULL",
    )
    
    # FK com UUID
    workspace_id: Mapped[UUID] = Rel.foreign_key(
        "workspaces.id",
        type_="uuid",
    )
```

### Parâmetros

| Parâmetro | Tipo | Default | Descrição |
|-----------|------|---------|-----------|
| `target` | str | - | Tabela.coluna alvo (ex: "users.id") |
| `nullable` | bool | False | Se pode ser NULL |
| `ondelete` | str | "CASCADE" | Ação ON DELETE |
| `index` | bool | True | Criar índice |
| `type_` | str | "int" | Tipo: "int", "uuid", "bigint" |

## Many-to-One (belongs_to)

Use quando **muitos** registros apontam para **um** registro:

```python
class Post(Model):
    __tablename__ = "posts"
    
    author_id: Mapped[int] = Rel.foreign_key("authors.id")
    
    # Muitos posts pertencem a um autor
    author: Mapped["Author"] = Rel.many_to_one(
        "Author",
        back_populates="posts",
    )
```

Alias disponível: `Rel.belongs_to()`

## One-to-Many (has_many)

Use quando **um** registro tem **muitos** relacionados:

```python
class Author(Model):
    __tablename__ = "authors"
    
    id: Mapped[int] = Field.pk()
    name: Mapped[str] = Field.string(max_length=100)
    
    # Um autor tem muitos posts
    posts: Mapped[list["Post"]] = Rel.one_to_many(
        "Post",
        back_populates="author",
        order_by="created_at",
    )
```

Alias disponível: `Rel.has_many()`

### Parâmetros

| Parâmetro | Tipo | Default | Descrição |
|-----------|------|---------|-----------|
| `target` | str | - | Nome da classe do model |
| `back_populates` | str | None | Nome do relacionamento reverso |
| `lazy` | str | "selectin" | Estratégia de loading |
| `cascade` | str | "all, delete-orphan" | Opções de cascade |
| `order_by` | str | None | Coluna para ordenação |

## One-to-One

Use quando cada registro corresponde a exatamente um em outra tabela:

```python
class User(Model):
    __tablename__ = "users"
    
    profile: Mapped["Profile"] = Rel.one_to_one(
        "Profile",
        back_populates="user",
    )

class Profile(Model):
    __tablename__ = "profiles"
    
    user_id: Mapped[int] = Rel.foreign_key("users.id")
    
    user: Mapped["User"] = Rel.one_to_one(
        "User",
        back_populates="profile",
    )
```

Alias disponível: `Rel.has_one()`

## Many-to-Many

Use quando registros em ambas as tabelas podem se relacionar com múltiplos:

### 1. Criar tabela de associação

```python
from core.relations import AssociationTable

# Tabela simples
post_tags = AssociationTable.create(
    "post_tags",
    left=("post_id", "posts.id"),
    right=("tag_id", "tags.id"),
)

# Com colunas extras
user_roles = AssociationTable.create(
    "user_roles",
    left=("user_id", "users.id"),
    right=("role_id", "roles.id"),
    extra_columns=[
        Column("assigned_at", DateTime, default=func.now()),
    ],
)
```

### 2. Definir relacionamentos

```python
class Post(Model):
    __tablename__ = "posts"
    
    tags: Mapped[list["Tag"]] = Rel.many_to_many(
        "Tag",
        secondary=post_tags,
        back_populates="posts",
    )

class Tag(Model):
    __tablename__ = "tags"
    
    posts: Mapped[list["Post"]] = Rel.many_to_many(
        "Post",
        secondary=post_tags,
        back_populates="tags",
    )
```

## Relacionamento Self-Referencial

Para hierarquias (ex: categorias com subcategorias):

```python
class Category(Model):
    __tablename__ = "categories"
    
    id: Mapped[int] = Field.pk()
    name: Mapped[str] = Field.string(max_length=100)
    parent_id: Mapped[int | None] = Rel.foreign_key(
        "categories.id",
        nullable=True,
        ondelete="SET NULL",
    )
    
    # Filhos
    children: Mapped[list["Category"]] = Rel.one_to_many(
        "Category",
        back_populates="parent",
    )
    
    # Pai
    parent: Mapped["Category | None"] = Rel.many_to_one(
        "Category",
        back_populates="children",
    )
```

## Estratégias de Loading

O parâmetro `lazy` controla como os relacionamentos são carregados:

| Valor | Descrição |
|-------|-----------|
| `"selectin"` | (Default) Query separada com IN clause - bom para listas |
| `"joined"` | JOIN na query principal - bom para single objects |
| `"subquery"` | Subquery separada - bom para grandes conjuntos |
| `"select"` | Query lazy quando acessado - N+1 queries |
| `"raise"` | Levanta erro se não carregado explicitamente |

## Exemplo Completo

```python
from sqlalchemy.orm import Mapped
from core import Model, Field
from core.relations import Rel, AssociationTable

# Tabela de associação
post_tags = AssociationTable.create(
    "post_tags",
    left=("post_id", "posts.id"),
    right=("tag_id", "tags.id"),
)

class Author(Model):
    __tablename__ = "authors"
    
    id: Mapped[int] = Field.pk()
    name: Mapped[str] = Field.string(max_length=100)
    email: Mapped[str] = Field.string(max_length=255, unique=True)
    
    # Um autor tem muitos posts
    posts: Mapped[list["Post"]] = Rel.one_to_many(
        "Post",
        back_populates="author",
    )

class Post(Model):
    __tablename__ = "posts"
    
    id: Mapped[int] = Field.pk()
    title: Mapped[str] = Field.string(max_length=200)
    content: Mapped[str] = Field.text()
    
    # FK para autor
    author_id: Mapped[int] = Rel.foreign_key("authors.id")
    
    # Muitos posts pertencem a um autor
    author: Mapped["Author"] = Rel.many_to_one(
        "Author",
        back_populates="posts",
    )
    
    # Muitos posts têm muitas tags
    tags: Mapped[list["Tag"]] = Rel.many_to_many(
        "Tag",
        secondary=post_tags,
        back_populates="posts",
    )
    
    # Um post tem muitos comentários
    comments: Mapped[list["Comment"]] = Rel.one_to_many(
        "Comment",
        back_populates="post",
    )

class Tag(Model):
    __tablename__ = "tags"
    
    id: Mapped[int] = Field.pk()
    name: Mapped[str] = Field.string(max_length=50, unique=True)
    
    posts: Mapped[list["Post"]] = Rel.many_to_many(
        "Post",
        secondary=post_tags,
        back_populates="tags",
    )

class Comment(Model):
    __tablename__ = "comments"
    
    id: Mapped[int] = Field.pk()
    content: Mapped[str] = Field.text()
    
    post_id: Mapped[int] = Rel.foreign_key("posts.id")
    
    post: Mapped["Post"] = Rel.many_to_one(
        "Post",
        back_populates="comments",
    )
```

## Comparação com SQLAlchemy Puro

| Core Framework | SQLAlchemy |
|----------------|------------|
| `Rel.foreign_key("users.id")` | `mapped_column(Integer, ForeignKey("users.id"))` |
| `Rel.many_to_one("User")` | `relationship("User", uselist=False)` |
| `Rel.one_to_many("Post")` | `relationship("Post", back_populates="...")` |
| `Rel.many_to_many("Tag", secondary=t)` | `relationship("Tag", secondary=t)` |

## Boas Práticas

1. **Sempre use `back_populates`** para relacionamentos bidirecionais
2. **Prefira `lazy="selectin"`** para evitar N+1 queries
3. **Use `cascade="all, delete-orphan"`** para one-to-many quando apropriado
4. **Crie índices em FKs** (default é True)
5. **Use `ondelete="CASCADE"` ou `"SET NULL"`** conforme a lógica de negócio
