# Relations (`Rel`)

Helpers em `strider/relations.py` para colunas de chave estrangeira e `relationship()` do SQLAlchemy com convenções próximas ao Django.

## Dois formatos de string (não confundir)

| Uso | Formato | Exemplo | Onde |
|-----|---------|---------|------|
| Coluna FK SQL | `tabela.coluna` (≥ um ponto; com schema, usam-se os **dois últimos** segmentos como tabela e coluna) | `"users.id"`, `"public.accounts.id"` | `Rel.foreign_key` |
| Alvo de `relationship` | `app_label.ModelName` (regex: um ponto, identificadores válidos) | `"core.User"` | `many_to_one`, `one_to_many`, `one_to_one`, `many_to_many` |

- **`app_label`**: pasta do app em `src/apps` (ex.: `core`, `strategies`).
- **`ModelName`**: nome da classe no módulo `src.apps.<app_label>.models`.
- Resolução: `importlib.import_module("src.apps.<app_label>.models")` e `getattr(..., ModelName)`.

### Erros na resolução do modelo (`relationship`)

- `ValueError`: `target` não coincide com o padrão `app_label.ModelName`.
- `ImportError`: módulo `src.apps.<app_label>.models` não importável.
- `AttributeError`: classe não existe nesse módulo.

### Validação estrita (`sys.exit(0)`)

Se usar `foreign_keys=[...]` como **lista de nomes de atributos** (strings) em `many_to_one` / `one_to_many` / `one_to_one`, o framework instala um descriptor que chama `_validate_relationship_target`. Se `target` **não** for `app_label.ModelName`, imprime-se uma mensagem em stderr e o processo termina com **código 0** (falha explícita em desenvolvimento).

## `Rel.foreign_key`

```python
Rel.foreign_key(
    target: str,               # "tabela.coluna"
    *,
    nullable: bool = False,
    ondelete: str = "CASCADE",
    index: bool = True,
    type_: str | None = None,  # None = inferir int / uuid / bigint
)
```

- **`type_`**: `None` (padrão) infere o tipo SQLAlchemy a partir de um `Model` cujo `__tablename__` seja a tabela referenciada (PK ou coluna). O modelo alvo deve estar **já definido** quando a classe que declara a FK é construída (ordem de declaração / imports). Se não for encontrado, assume-se **inteiro**.
- Valores explícitos: `"int"`, `"uuid"`, `"bigint"` sobrescrevem a inferência.
- `ondelete` típicos: `CASCADE`, `SET NULL` (combinar com `nullable=True`), `RESTRICT`, `NO ACTION`.

```python
from uuid import UUID
from sqlalchemy.orm import Mapped
from strider import Model, Field
from strider.relations import Rel

class Post(Model):
    __tablename__ = "posts"

    author_id: Mapped[int] = Rel.foreign_key("users.id")
    workspace_id: Mapped[UUID] = Rel.foreign_key("workspaces.id")  # inferência UUID se o modelo workspaces tiver PK UUID

    category_id: Mapped[int | None] = Rel.foreign_key(
        "categories.id",
        nullable=True,
        ondelete="SET NULL",
    )
```

## `Rel.many_to_one` / `Rel.belongs_to`

Lado **N** de N:1. `target` = `"app_label.ModelName"`.

```python
Rel.many_to_one(
    target: str,
    *,
    back_populates: str | None = None,
    backref: str | None = None,
    lazy: str = "selectin",
    foreign_keys: list[str] | None = None,
    uselist: bool = False,
)
```

## `Rel.one_to_many` / `Rel.has_many`

Lado **1** de 1:N.

```python
Rel.one_to_many(
    target: str,
    *,
    back_populates: str | None = None,
    backref: str | None = None,
    lazy: str = "selectin",
    foreign_keys: list[str] | None = None,
    cascade: str = "all, delete-orphan",
    passive_deletes: bool = True,
    order_by: str | None = None,
)
```

## `Rel.one_to_one` / `Rel.has_one`

1:1; no lado que possui a FK, use `unique=True` na coluna (ou equivalente) para garantir unicidade.

## `Rel.many_to_many`

```python
Rel.many_to_many(
    target: str,
    *,
    secondary: str | Table,
    back_populates: str | None = None,
    backref: str | None = None,
    lazy: str = "selectin",
    cascade: str = "all",
    passive_deletes: bool = True,
    order_by: str | None = None,
)
```

- `secondary`: nome da tabela (string) ou objeto `Table`. Se a tabela foi criada com `AssociationTable.create` e está em cache, o nome pode resolver para essa instância.

## `Rel.self_referential`

Relação na **mesma** classe. `foreign_keys` e `remote_side` são **nomes de atributos Python** na classe (ex.: `"parent_id"`, `"id"`), não strings qualificadas com o nome da classe.

```python
class Category(Model):
    __tablename__ = "categories"

    id: Mapped[int] = Field.pk()
    parent_id: Mapped[int | None] = Rel.foreign_key(
        "categories.id",
        nullable=True,
        ondelete="SET NULL",
    )

    parent: Mapped["Category | None"] = Rel.self_referential(
        back_populates="children",
        remote_side="id",
        uselist=False,
    )
    children: Mapped[list["Category"]] = Rel.self_referential(
        back_populates="parent",
        foreign_keys="parent_id",
    )
```

## `AssociationTable`

Cria tabelas de junção para N:N com **duas FKs inteiras** por defeito. Para PKs UUID/`bigint` nas entidades, construa a `Table` manualmente com os tipos correctos.

```python
post_tags = AssociationTable.create(
    "post_tags",
    left=("post_id", "posts.id"),
    right=("tag_id", "tags.id"),
)
```

- `get("post_tags")` — obtém tabela em cache.
- `clear_cache()` — limpa o cache (testes).

## `clear_model_cache`

Limpa cache interno de importação de models em `relations.py` (uso principal: testes).

## Lazy loading

| Valor | Comportamento |
|-------|----------------|
| `"selectin"` | `SELECT IN` separado (recomendado, padrão) |
| `"joined"` | `JOIN` na mesma query |
| `"subquery"` | Subquery |
| `"select"` | Lazy clássico |
| `"raise"` / `"noload"` | Conforme SQLAlchemy |

## Cascade (SQLAlchemy)

| Valor | Comportamento |
|-------|----------------|
| `"all"` | Operações em cascata amplas |
| `"save-update"` | Propaga save/update |
| `"merge"` | Propaga merge |
| `"delete"` | Propaga delete |
| `"delete-orphan"` | Remove órfãos |
| `"all, delete-orphan"` | Comum em 1:N (padrão em `one_to_many`) |

## `ON DELETE` (FK / `foreign_key`)

| Valor | Comportamento |
|-------|----------------|
| `"CASCADE"` | Apaga filhos quando o pai é apagado (padrão) |
| `"SET NULL"` | Põe FK a `NULL` (requer coluna anulável) |
| `"RESTRICT"` / `"NO ACTION"` | Impede ou delega ao motor |

## Exemplo completo (targets `app_label.ModelName`)

```python
from strider import Model, Field
from strider.relations import Rel
from sqlalchemy.orm import Mapped

class User(Model):
    __tablename__ = "users"
    id: Mapped[int] = Field.pk()
    posts: Mapped[list["Post"]] = Rel.one_to_many(
        "core.Post",
        back_populates="author",
    )

class Post(Model):
    __tablename__ = "posts"
    id: Mapped[int] = Field.pk()
    author_id: Mapped[int] = Rel.foreign_key("users.id")
    author: Mapped["User"] = Rel.many_to_one(
        "core.User",
        back_populates="posts",
    )
```

(Ajuste `core` ao `app_label` real do projecto.)

## Eager loading em queries

```python
user = await User.objects.using(db).select_related("posts").get(id=1)
post = await Post.objects.using(db).select_related("author").get(id=1)
```

## Seguinte

- [QuerySets](12-querysets.md)
- [Fields](10-fields.md)
