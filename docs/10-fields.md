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
from strider.choices import TextChoices

class Status(TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"

status: Mapped[str] = Field.choice(Status, default=Status.DRAFT)
```

## Advanced Fields (`AdvancedField`)

### `AdvancedField.uuid_pk()`

UUID primary key (uses UUID7 by default).

```python
from strider.fields import AdvancedField
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
from strider import Model, Field
from strider.fields import AdvancedField

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

## StructSchema em models

Campos JSON estruturados com validação, defaults e acesso tipado. O banco armazena JSON/JSONB; em Python você usa um schema (classe herdando de `StructSchema`) para definir formato, validação e conversão.

### Definir o schema

Em `strider.schema` use os campos disponíveis: `StringField`, `IntegerField`, `FloatField`, `BooleanField`, `ListField`, `NestedField`, `DictField`, `ChoiceField`.

```python
from strider.schema import (
    StructSchema,
    StringField,
    BooleanField,
    IntegerField,
    NestedField,
)

class UserPreferences(StructSchema):
    theme = StringField(
        default="system",
        choices=["light", "dark", "system"],
    )
    language = StringField(default="pt-BR", aliases=["lang"])
    notifications = NestedField({
        "email": BooleanField(default=True),
        "push": BooleanField(default=True),
    })
    items_per_page = IntegerField(default=20, min_value=5, max_value=100)
```

- **aliases**: nomes alternativos ao ler do banco (ex.: `"lang"` → `language`). Útil para migrar dados antigos sem alterar o schema.
- **NestedField**: objeto aninhado; pode ser um `dict` de campos ou outra classe `StructSchema`.
- Campos ausentes no JSON usam o **default** do campo; campos desconhecidos ficam em `_extra_data` e são preservados ao salvar.

### Usar na model com tipagem

Use `Field.struct(schema_class)` e anote com `Mapped[SeuSchema]`:

```python
from strider import Model, Field
from strider.schema import StructSchema, StringField, BooleanField, NestedField
from sqlalchemy.orm import Mapped

class UserPreferences(StructSchema):
    theme = StringField(default="system", choices=["light", "dark", "system"])
    language = StringField(default="pt-BR", aliases=["lang"])
    notifications = NestedField({
        "email": BooleanField(default=True),
        "push": BooleanField(default=True),
    })

class User(Model):
    __tablename__ = "users"
    id: Mapped[int] = Field.pk()
    name: Mapped[str] = Field.string(255)
    preferences: Mapped[dict] = Field.struct(
        UserPreferences,
        default=None,   # opcional; se None, usa UserPreferences.default_dict()
        nullable=False,
        index=False,    # True = índice GIN no PostgreSQL
    )
```

Parâmetros de `Field.struct()`:

| Parâmetro     | Descrição |
|---------------|-----------|
| `schema_class`| Classe que herda de `StructSchema`. |
| `default`     | `None` (usa defaults do schema), `dict` ou instância do schema. |
| `nullable`    | Se a coluna pode ser NULL. |
| `index`       | Se deve criar índice GIN no PostgreSQL (útil para filtros em JSON). |

O tipo na coluna é **AdaptiveJSON**: no PostgreSQL vira **JSONB**, nos demais dialetos **JSON**. A anotação `Mapped[dict]` reflete o que o banco guarda; para tipo “schema” use `Mapped[dict]` e converta com o schema quando precisar de atributos tipados.

### Acesso tipado e leitura/gravação

O valor carregado do banco é um **dict**. Para acesso por atributos e validação, converta com o schema:

```python
# Carregar do banco (instance.preferences é um dict)
prefs = UserPreferences.from_dict_safe(user.preferences)
prefs.theme           # "system"
prefs.notifications.email  # True

# Atribuir: pode passar dict (será normalizado/validado pelo default_factory ao inserir)
user.preferences = {"theme": "dark", "language": "en"}
# Ou construir e serializar
prefs = UserPreferences(theme="dark", language="en")
user.preferences = prefs.to_dict()
```

- **from_dict_safe**: tolerante a dados faltando, aliases e campos extras; preenche com defaults e mapeia aliases.
- **to_dict**: serializa para gravar no banco; usa sempre os nomes oficiais dos campos e inclui `_extra_data`.

Validação ao atribuir em código pode ser feita com `prefs.validate()` ou `prefs.is_valid()`; ao definir via model, o default é montado com `schema_class.default_dict()` e, se você passar dict, pode normalizar com `schema_class.from_dict_safe(d).to_dict()` antes de setar.

### Migrações

- A coluna gerada é **JSON/JSONB** (tipo interno `AdaptiveJSON`). O sistema de migrações trata esse tipo como equivalente a JSON/JSONB (`state.EQUIVALENT_TYPES`: `JSON`, `JSONB`, `ADAPTIVEJSON`).
- **makemigrations** gera `CreateTable` / `AddColumn` com tipo mapeado para o dialeto (ex.: PostgreSQL → JSONB).
- **Não existe migração automática do “formato” do StructSchema**: mudar campos ou defaults no Python não altera o banco. Só a coluna (JSON) existe no schema do BD.
- **Evolução de dados**: ao adicionar um novo campo no StructSchema, registros antigos continuam com o JSON que tinham; ao serem lidos, `from_dict_safe` preenche o novo campo com o **default** definido no schema. Renomear campos pode ser tratado com **aliases** (ex.: alias `"lang"` para `language`) para compatibilidade com dados antigos.

Resumo: migrações cuidam apenas da coluna JSON/JSONB; a “migração” dos dados dentro do JSON é feita em tempo de leitura pelo schema (defaults + aliases).

### Filtros em QuerySet (path JSON)

Colunas com `struct_schema` no `info` são tratadas como JSON para filtros por path:

```python
# Filtro por campo interno do struct
users = await User.objects.filter(preferences__theme="dark").all()
users = await User.objects.filter(preferences__language__exact="pt-BR").all()
```

O mesmo mecanismo de path JSON usado em `AdvancedField.json_field()` se aplica a campos definidos com `Field.struct()`.

### Admin

No admin, colunas que têm `info["struct_schema"]` usam o widget **struct_editor** para editar o JSON de acordo com os campos do schema (tipos e opções vêm de `_fields` do schema).

### Resumo

| Aspecto        | Comportamento |
|----------------|----------------|
| Tipo no banco  | JSON (SQLite/MySQL) ou JSONB (PostgreSQL). |
| Tipo em Python | `dict` na coluna; use `Schema.from_dict_safe()` para acesso tipado. |
| Default        | `schema_class.default_dict()` ou o que você passar em `default`. |
| Migrações      | Apenas coluna JSON/JSONB; evolução de “schema” via defaults e aliases ao ler. |
| Filtros        | Suporte a path (`preferences__theme=...`). |
| Admin          | Widget `struct_editor` para edição do struct. |

## Complete Model Example

```python
from strider import Model, Field
from strider.fields import AdvancedField
from strider.choices import TextChoices
from strider.datetime import DateTime
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
| `Field.struct(StructSchema)` | `JSONB` | `JSON` | `JSON` |

(O campo struct usa internamente `AdaptiveJSON`; no PostgreSQL vira JSONB, nos demais JSON.)

## Next

- [Relations](11-relations.md) — Relationships
- [Models](03-models.md) — Model basics
