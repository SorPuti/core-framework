"""
Relationship helpers for SQLAlchemy models.

Padrão obrigatório para targets de relacionamento: app_label.ModelName (estilo Django).
- app_label = nome da pasta do app em src.apps (ex: core, strategies)
- ModelName = nome da classe do model em src.apps.<app_label>.models

Exemplo:
    Rel.many_to_one("core.User", ...)
    Rel.one_to_many("strategies.Strategy", ...)

Se o target não seguir esse padrão, o app interrompe (exit 0) com mensagem explicativa.

Example:
    from strider import Model, Field
    from strider.relations import Rel
    
    class Author(Model):
        __tablename__ = "authors"
        
        id: Mapped[int] = Field.pk()
        name: Mapped[str] = Field.string(max_length=100)
        
        # One-to-Many: Author has many Posts
        posts: Mapped[list["Post"]] = Rel.one_to_many(
            "Post",
            back_populates="author",
        )
    
    class Post(Model):
        __tablename__ = "posts"
        
        id: Mapped[int] = Field.pk()
        title: Mapped[str] = Field.string(max_length=200)
        
        # Foreign Key
        author_id: Mapped[int] = Rel.foreign_key("authors.id")
        
        # Many-to-One: Post belongs to Author
        author: Mapped["Author"] = Rel.many_to_one(
            "Author",
            back_populates="posts",
        )
    
    class Tag(Model):
        __tablename__ = "tags"
        
        id: Mapped[int] = Field.pk()
        name: Mapped[str] = Field.string(max_length=50)
        
        # Many-to-Many: Tag has many Posts
        posts: Mapped[list["Post"]] = Rel.many_to_many(
            "Post",
            secondary="post_tags",
            back_populates="tags",
        )
"""

from __future__ import annotations

import logging
import re
import sys
from typing import TYPE_CHECKING, Any, TypeVar, overload
from uuid import UUID

from sqlalchemy import Column, ForeignKey, Integer, String, Table
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from strider.models import Model

T = TypeVar("T", bound="Model")

logger = logging.getLogger("strider.relations")

# Padrão obrigatório para targets de relacionamento: app_label.ModelName
# Corresponde a src.apps.<app_label>.models.<ModelName>
RELATIONSHIP_TARGET_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*$")


# =============================================================================
# Association Table Builder
# =============================================================================

class AssociationTable:
    """
    Helper for creating many-to-many association tables.
    
    Example:
        # Simple association
        post_tags = AssociationTable.create(
            "post_tags",
            left=("post_id", "posts.id"),
            right=("tag_id", "tags.id"),
        )
        
        # With extra columns
        user_roles = AssociationTable.create(
            "user_roles",
            left=("user_id", "users.id"),
            right=("role_id", "roles.id"),
            extra_columns=[
                Column("assigned_at", DateTime, default=func.now()),
                Column("assigned_by", Integer, nullable=True),
            ],
        )
    """
    
    _tables: dict[str, Table] = {}
    
    @classmethod
    def create(
        cls,
        name: str,
        left: tuple[str, str],
        right: tuple[str, str],
        *,
        metadata: Any = None,
        extra_columns: list[Column] | None = None,
        ondelete: str = "CASCADE",
    ) -> Table:
        """
        Create or get an association table for many-to-many relationships.
        
        Args:
            name: Table name
            left: Tuple of (column_name, foreign_key_target) for left side
            right: Tuple of (column_name, foreign_key_target) for right side
            metadata: SQLAlchemy metadata (uses Model.metadata if not provided)
            extra_columns: Additional columns for the association table
            ondelete: ON DELETE action (default: CASCADE)
        
        Returns:
            SQLAlchemy Table object
        
        Example:
            post_tags = AssociationTable.create(
                "post_tags",
                left=("post_id", "posts.id"),
                right=("tag_id", "tags.id"),
            )
        """
        if name in cls._tables:
            return cls._tables[name]
        
        if metadata is None:
            from strider.models import Model
            metadata = Model.metadata
        
        left_col, left_fk = left
        right_col, right_fk = right
        
        columns = [
            Column(
                left_col,
                Integer,
                ForeignKey(left_fk, ondelete=ondelete),
                primary_key=True,
            ),
            Column(
                right_col,
                Integer,
                ForeignKey(right_fk, ondelete=ondelete),
                primary_key=True,
            ),
        ]
        
        if extra_columns:
            columns.extend(extra_columns)
        
        table = Table(
            name,
            metadata,
            *columns,
            extend_existing=True,
        )
        
        cls._tables[name] = table
        return table
    
    @classmethod
    def get(cls, name: str) -> Table | None:
        """Get an existing association table by name."""
        return cls._tables.get(name)
    
    @classmethod
    def clear_cache(cls) -> None:
        """Clear the table cache (useful for testing)."""
        cls._tables.clear()


# =============================================================================
# Relationship Helpers
# =============================================================================

def _app_label_from_module(module_name: str) -> str | None:
    """
    Extrai o app_label do módulo do modelo.
    Ex: "src.apps.core.models" -> "core"
    """
    if not module_name or "src.apps." not in module_name:
        return None
    parts = module_name.split(".")
    try:
        idx = parts.index("apps")
        if idx + 2 < len(parts):
            return parts[idx + 2]
    except ValueError:
        pass
    return None


def _validate_relationship_target(target: str, owner: type, attr_name: str) -> None:
    """
    Valida que o target segue o padrão app_label.ModelName.
    Se não seguir, imprime mensagem explicativa e encerra com sys.exit(0).
    """
    if RELATIONSHIP_TARGET_PATTERN.match(target):
        return
    app_label = _app_label_from_module(owner.__module__)
    suggestion = f"{app_label}.{target}" if app_label else f"<app_label>.{target}"
    msg = (
        f"\n{'='*60}\n"
        "Relacionamento fora do padrão obrigatório.\n"
        f"{'='*60}\n\n"
        f"  Modelo:  {owner.__module__}.{owner.__name__}\n"
        f"  Atributo: {attr_name}\n"
        f"  Valor atual: {target!r}\n\n"
        "O framework exige o padrão Django: app_label.ModelName\n"
        "  - app_label = pasta do app em src.apps (ex: core, strategies)\n"
        "  - ModelName = nome da classe do model em src.apps.<app_label>.models\n\n"
        f"Substitua por: {suggestion!r}\n\n"
        "Exemplo: Rel.many_to_one(\"core.User\", ...) em vez de Rel.many_to_one(\"User\", ...)\n"
        f"{'='*60}\n"
    )
    print(msg, file=sys.stderr)
    sys.exit(0)


def _get_registry_from_class(cls: type) -> Any:
    """Obtém o registry do SQLAlchemy a partir de uma classe mapeada."""
    for c in cls.__mro__:
        if hasattr(c, "registry"):
            return c.registry
    return None


def _get_target_class(owner_class: type, target: str) -> type | None:
    """Resolve o nome do modelo (string) para a classe, via registry da base."""
    registry = _get_registry_from_class(owner_class)
    if registry is None:
        return None
    reg = getattr(registry, "_class_registry", None)
    if reg is None:
        return None
    val = reg.get(target)
    if val is None:
        return None
    # Pode ser _MultipleClassMarker com .contents (weakref.ref para classes)
    if hasattr(val, "contents"):
        refs = getattr(val, "contents", ())
        if refs:
            first_ref = next(iter(refs))
            return first_ref() if callable(first_ref) else first_ref
        return None
    return val


def _resolve_foreign_keys_to_columns(
    owner_class: type,
    target: str | type,
    foreign_keys: list[str],
    side: str,
) -> list[Any]:
    """
    Converte nomes de coluna (strings) em Column objects para relationship().
    SQLAlchemy 2.0 exige Column objects em foreign_keys, não strings.
    target pode ser o nome da classe (str) ou a classe (type) para one_to_many.
    """
    if side == "many_to_one":
        return [getattr(owner_class, name) for name in foreign_keys]
    if isinstance(target, type):
        target_class = target
    else:
        target_class = _get_target_class(owner_class, target)
    if target_class is None:
        raise ValueError(
            f"Não foi possível resolver a classe alvo {target!r} para "
            "foreign_keys. Use o padrão app_label.ModelName (ex: core.User)."
        )
    return [getattr(target_class, name) for name in foreign_keys]


class _RelationshipDescriptor:
    """
    Descriptor que atrasa a criação do relationship() até __set_name__,
    quando a classe já existe e podemos resolver foreign_keys (strings -> Columns).
    Necessário porque SQLAlchemy 2.0 exige Column objects em foreign_keys.
    """

    def __init__(
        self,
        target: str,
        side: str,
        kwargs: dict[str, Any],
        foreign_keys_names: list[str],
    ):
        self._target = target
        self._side = side
        self._kwargs = kwargs
        self._foreign_keys_names = foreign_keys_names

    def __set_name__(self, owner: type, name: str) -> None:
        _validate_relationship_target(self._target, owner, name)
        resolved_class = _resolve_target_to_class(self._target)
        fk_columns = _resolve_foreign_keys_to_columns(
            owner, resolved_class, self._foreign_keys_names, self._side
        )
        kwargs = {**self._kwargs, "foreign_keys": fk_columns}
        rel = relationship(resolved_class, **kwargs)
        setattr(owner, name, rel)


class _SelfReferentialDescriptor:
    """
    Descriptor para self_referential que resolve foreign_keys e remote_side
    (strings) para Column objects em __set_name__.
    """

    def __init__(
        self,
        *,
        back_populates: str | None,
        lazy: str,
        cascade: str,
        uselist: bool,
        foreign_keys: str | None,
        remote_side: str | None,
    ):
        self._back_populates = back_populates
        self._lazy = lazy
        self._cascade = cascade
        self._uselist = uselist
        self._foreign_keys = foreign_keys
        self._remote_side = remote_side

    def __set_name__(self, owner: type, name: str) -> None:
        kwargs: dict[str, Any] = {
            "back_populates": self._back_populates,
            "lazy": self._lazy,
            "cascade": self._cascade,
            "uselist": self._uselist,
        }
        if self._foreign_keys:
            kwargs["foreign_keys"] = [getattr(owner, self._foreign_keys)]
        if self._remote_side:
            kwargs["remote_side"] = [getattr(owner, self._remote_side)]
        argument = "self" if self._back_populates else None
        setattr(owner, name, relationship(argument, **kwargs))


def _resolve_target(target: str) -> str:
    """
    (Deprecated) Mantido para compatibilidade. Use _resolve_target_to_class.
    """
    cls = _resolve_target_to_class(target)
    return cls.__name__


def _resolve_target_to_class(target: str) -> type:
    """
    Resolve target no formato app_label.ModelName para a classe do model.
    Convenção: model em src.apps.<app_label>.models.<ModelName>.
    """
    if not RELATIONSHIP_TARGET_PATTERN.match(target):
        raise ValueError(
            "Target de relacionamento deve ser app_label.ModelName "
            "(ex: core.User, strategies.Strategy). "
            "O model deve estar em src.apps.<app_label>.models"
        )
    from importlib import import_module
    app_label, model_name = target.split(".", 1)
    module_path = f"src.apps.{app_label}.models"
    try:
        module = import_module(module_path)
    except ImportError as e:
        raise ImportError(
            f"Não foi possível importar {module_path!r} para o target {target!r}. "
            "Verifique que o app existe em src.apps e que o model está em models.py."
        ) from e
    if not hasattr(module, model_name):
        raise AttributeError(
            f"Model {model_name!r} não encontrado em {module_path}. "
            f"Classes disponíveis: {[x for x in dir(module) if not x.startswith('_')]}"
        )
    return getattr(module, model_name)


# Cache de módulos já tentados (evita importações repetidas)
_model_import_cache: dict[str, bool] = {}


def clear_model_cache() -> None:
    """
    Limpa o cache de importação de models.
    
    Útil para testes ou quando models são recarregados dinamicamente.
    """
    global _model_import_cache
    _model_import_cache.clear()
    logger.debug("Model import cache cleared")


class Rel:
    """
    Relationship helper class providing Django-like relationship definitions.
    
    This class provides static methods for defining relationships between models
    with sensible defaults and clear naming conventions.
    
    Relationship Types:
        - foreign_key: Define a foreign key column
        - many_to_one: Many records point to one (belongs_to)
        - one_to_many: One record has many (has_many)
        - one_to_one: One-to-one relationship
        - many_to_many: Many-to-many with association table
    
    Example:
        class Post(Model):
            __tablename__ = "posts"
            
            # Foreign key column
            author_id: Mapped[int] = Rel.foreign_key("authors.id")
            
            # Relationship to Author
            author: Mapped["Author"] = Rel.many_to_one("Author", back_populates="posts")
            
            # Relationship to Comments
            comments: Mapped[list["Comment"]] = Rel.one_to_many("Comment", back_populates="post")
            
            # Many-to-many with Tags
            tags: Mapped[list["Tag"]] = Rel.many_to_many("Tag", secondary="post_tags")
    """
    
    # -------------------------------------------------------------------------
    # Foreign Key
    # -------------------------------------------------------------------------
    
    @staticmethod
    def foreign_key(
        target: str,
        *,
        nullable: bool = False,
        ondelete: str = "CASCADE",
        index: bool = True,
        type_: str = "int",
    ) -> Mapped[int] | Mapped[int | None] | Mapped[UUID] | Mapped[UUID | None]:
        """
        Create a foreign key column.
        
        Args:
            target: Target column in format "table.column" (e.g., "users.id")
            nullable: Whether the FK can be NULL (default: False)
            ondelete: ON DELETE action - CASCADE, SET NULL, RESTRICT, NO ACTION
            index: Whether to create an index (default: True, recommended for FKs)
            type_: Column type - "int" (default), "uuid", "bigint"
        
        Returns:
            Mapped column with foreign key constraint
        
        Example:
            # Integer FK (most common)
            author_id: Mapped[int] = Rel.foreign_key("authors.id")
            
            # Nullable FK
            parent_id: Mapped[int | None] = Rel.foreign_key(
                "categories.id",
                nullable=True,
                ondelete="SET NULL",
            )
            
            # UUID FK
            workspace_id: Mapped[UUID] = Rel.foreign_key(
                "workspaces.id",
                type_="uuid",
            )
        """
        from sqlalchemy import BigInteger
        from sqlalchemy.dialects.postgresql import UUID as PgUUID
        
        if type_ == "uuid":
            return mapped_column(
                PgUUID(as_uuid=True),
                ForeignKey(target, ondelete=ondelete),
                nullable=nullable,
                index=index,
            )
        elif type_ == "bigint":
            return mapped_column(
                BigInteger,
                ForeignKey(target, ondelete=ondelete),
                nullable=nullable,
                index=index,
            )
        else:
            return mapped_column(
                Integer,
                ForeignKey(target, ondelete=ondelete),
                nullable=nullable,
                index=index,
            )
    
    # -------------------------------------------------------------------------
    # Many-to-One (belongs_to)
    # -------------------------------------------------------------------------
    
    @staticmethod
    def many_to_one(
        target: str,
        *,
        back_populates: str | None = None,
        backref: str | None = None,
        lazy: str = "selectin",
        foreign_keys: list[str] | None = None,
        uselist: bool = False,
    ) -> Mapped[Any]:
        """
        Create a many-to-one relationship (belongs_to).
        
        Use this on the "many" side of a relationship, where multiple records
        point to a single record in another table.
        
        Args:
            target: Target model class name (string for forward reference)
            back_populates: Name of the reverse relationship on the target model
            backref: Auto-create reverse relationship (alternative to back_populates)
            lazy: Loading strategy - "selectin" (default), "joined", "subquery", "select"
            foreign_keys: Explicit foreign key columns (for ambiguous relationships)
            uselist: Always False for many-to-one (returns single object)
        
        Returns:
            Mapped relationship
        
        Example:
            class Post(Model):
                author_id: Mapped[int] = Rel.foreign_key("authors.id")
                
                # Many posts belong to one author
                author: Mapped["Author"] = Rel.many_to_one(
                    "Author",
                    back_populates="posts",
                )
        
        Note:
            Also known as: belongs_to, ForeignKey relationship
        """
        if foreign_keys and isinstance(foreign_keys, list) and all(
            isinstance(x, str) for x in foreign_keys
        ):
            return _RelationshipDescriptor(
                target,
                "many_to_one",
                dict(
                    back_populates=back_populates,
                    backref=backref,
                    lazy=lazy,
                    uselist=False,
                ),
                foreign_keys,
            )
        resolved = _resolve_target_to_class(target)
        return relationship(
            resolved,
            back_populates=back_populates,
            backref=backref,
            lazy=lazy,
            foreign_keys=foreign_keys,
            uselist=False,  # Many-to-one always returns single object
        )
    
    # Alias for Django users
    belongs_to = many_to_one
    
    # -------------------------------------------------------------------------
    # One-to-Many (has_many)
    # -------------------------------------------------------------------------
    
    @staticmethod
    def one_to_many(
        target: str,
        *,
        back_populates: str | None = None,
        backref: str | None = None,
        lazy: str = "selectin",
        foreign_keys: list[str] | None = None,
        cascade: str = "all, delete-orphan",
        passive_deletes: bool = True,
        order_by: str | None = None,
    ) -> Mapped[list[Any]]:
        """
        Create a one-to-many relationship (has_many).
        
        Use this on the "one" side of a relationship, where a single record
        has multiple related records in another table.
        
        Args:
            target: Target model class name (string for forward reference)
            back_populates: Name of the reverse relationship on the target model
            backref: Auto-create reverse relationship (alternative to back_populates)
            lazy: Loading strategy - "selectin" (default), "joined", "subquery", "select"
            foreign_keys: Explicit foreign key columns (for ambiguous relationships)
            cascade: Cascade options (default: "all, delete-orphan")
            passive_deletes: Let database handle cascades (default: True)
            order_by: Column to order related records by
        
        Returns:
            Mapped relationship (list)
        
        Example:
            class Author(Model):
                # One author has many posts
                posts: Mapped[list["Post"]] = Rel.one_to_many(
                    "Post",
                    back_populates="author",
                    order_by="created_at",
                )
        
        Note:
            Also known as: has_many, reverse ForeignKey
        """
        if foreign_keys and isinstance(foreign_keys, list) and all(
            isinstance(x, str) for x in foreign_keys
        ):
            kwargs: dict[str, Any] = {
                "back_populates": back_populates,
                "backref": backref,
                "lazy": lazy,
                "cascade": cascade,
                "passive_deletes": passive_deletes,
            }
            if order_by:
                kwargs["order_by"] = order_by
            return _RelationshipDescriptor(
                target,
                "one_to_many",
                kwargs,
                foreign_keys,
            )
        resolved = _resolve_target_to_class(target)
        kwargs = {
            "back_populates": back_populates,
            "backref": backref,
            "lazy": lazy,
            "foreign_keys": foreign_keys,
            "cascade": cascade,
            "passive_deletes": passive_deletes,
        }
        if order_by:
            kwargs["order_by"] = order_by
        return relationship(resolved, **kwargs)
    
    # Alias for Rails users
    has_many = one_to_many
    
    # -------------------------------------------------------------------------
    # One-to-One
    # -------------------------------------------------------------------------
    
    @staticmethod
    def one_to_one(
        target: str,
        *,
        back_populates: str | None = None,
        backref: str | None = None,
        lazy: str = "selectin",
        foreign_keys: list[str] | None = None,
        cascade: str = "all, delete-orphan",
        uselist: bool = False,
    ) -> Mapped[Any]:
        """
        Create a one-to-one relationship.
        
        Use this when each record in one table corresponds to exactly one
        record in another table.
        
        Args:
            target: Target model class name (string for forward reference)
            back_populates: Name of the reverse relationship on the target model
            backref: Auto-create reverse relationship (alternative to back_populates)
            lazy: Loading strategy - "selectin" (default), "joined", "subquery", "select"
            foreign_keys: Explicit foreign key columns (for ambiguous relationships)
            cascade: Cascade options (default: "all, delete-orphan")
            uselist: Always False for one-to-one
        
        Returns:
            Mapped relationship (single object)
        
        Example:
            class User(Model):
                # One user has one profile
                profile: Mapped["Profile"] = Rel.one_to_one(
                    "Profile",
                    back_populates="user",
                )
            
            class Profile(Model):
                user_id: Mapped[int] = Rel.foreign_key("users.id", unique=True)
                
                # One profile belongs to one user
                user: Mapped["User"] = Rel.one_to_one(
                    "User",
                    back_populates="profile",
                )
        """
        if foreign_keys and isinstance(foreign_keys, list) and all(
            isinstance(x, str) for x in foreign_keys
        ):
            return _RelationshipDescriptor(
                target,
                "many_to_one",
                dict(
                    back_populates=back_populates,
                    backref=backref,
                    lazy=lazy,
                    cascade=cascade,
                    uselist=False,
                ),
                foreign_keys,
            )
        resolved = _resolve_target_to_class(target)
        return relationship(
            resolved,
            back_populates=back_populates,
            backref=backref,
            lazy=lazy,
            foreign_keys=foreign_keys,
            cascade=cascade,
            uselist=False,
        )
    
    # Alias
    has_one = one_to_one
    
    # -------------------------------------------------------------------------
    # Many-to-Many
    # -------------------------------------------------------------------------
    
    @staticmethod
    def many_to_many(
        target: str,
        *,
        secondary: str | Table,
        back_populates: str | None = None,
        backref: str | None = None,
        lazy: str = "selectin",
        cascade: str = "all",
        passive_deletes: bool = True,
        order_by: str | None = None,
    ) -> Mapped[list[Any]]:
        """
        Create a many-to-many relationship.
        
        Use this when records in both tables can be related to multiple
        records in the other table (requires an association table).
        
        Args:
            target: Target model class name (string for forward reference)
            secondary: Association table name (string) or Table object
            back_populates: Name of the reverse relationship on the target model
            backref: Auto-create reverse relationship (alternative to back_populates)
            lazy: Loading strategy - "selectin" (default), "joined", "subquery", "select"
            cascade: Cascade options (default: "all")
            passive_deletes: Let database handle cascades (default: True)
            order_by: Column to order related records by
        
        Returns:
            Mapped relationship (list)
        
        Example:
            # First, create the association table
            post_tags = AssociationTable.create(
                "post_tags",
                left=("post_id", "posts.id"),
                right=("tag_id", "tags.id"),
            )
            
            class Post(Model):
                # Many posts have many tags
                tags: Mapped[list["Tag"]] = Rel.many_to_many(
                    "Tag",
                    secondary=post_tags,  # or "post_tags"
                    back_populates="posts",
                )
            
            class Tag(Model):
                # Many tags have many posts
                posts: Mapped[list["Post"]] = Rel.many_to_many(
                    "Post",
                    secondary=post_tags,
                    back_populates="tags",
                )
        
        Note:
            The association table must have foreign keys to both tables.
            Use AssociationTable.create() for easy table creation.
        """
        # If secondary is a string, try to get it from cache or use as-is
        if isinstance(secondary, str):
            cached_table = AssociationTable.get(secondary)
            if cached_table is not None:
                secondary = cached_table
        
        resolved = _resolve_target_to_class(target)
        kwargs: dict[str, Any] = {
            "secondary": secondary,
            "back_populates": back_populates,
            "backref": backref,
            "lazy": lazy,
            "cascade": cascade,
            "passive_deletes": passive_deletes,
        }
        
        if order_by:
            kwargs["order_by"] = order_by
        
        return relationship(resolved, **kwargs)
    
    # -------------------------------------------------------------------------
    # Self-referential relationships
    # -------------------------------------------------------------------------
    
    @staticmethod
    def self_referential(
        *,
        back_populates: str | None = None,
        remote_side: str | None = None,
        lazy: str = "selectin",
        cascade: str = "all",
        foreign_keys: str | None = None,
        uselist: bool = True,
    ) -> Mapped[Any]:
        """
        Create a self-referential relationship (e.g., parent-child in same table).
        
        Args:
            back_populates: Name of the reverse relationship
            remote_side: Column that identifies the "one" side (usually "id")
            lazy: Loading strategy
            cascade: Cascade options
            foreign_keys: Foreign key column name
            uselist: True for one-to-many, False for many-to-one
        
        Returns:
            Mapped relationship
        
        Example:
            class Category(Model):
                __tablename__ = "categories"
                
                id: Mapped[int] = Field.pk()
                name: Mapped[str] = Field.string(max_length=100)
                parent_id: Mapped[int | None] = Rel.foreign_key(
                    "categories.id",
                    nullable=True,
                    ondelete="SET NULL",
                )
                
                # Children (one-to-many)
                children: Mapped[list["Category"]] = Rel.self_referential(
                    back_populates="parent",
                    foreign_keys="parent_id",
                )
                
                # Parent (many-to-one)
                parent: Mapped["Category | None"] = Rel.self_referential(
                    back_populates="children",
                    remote_side="id",
                    uselist=False,
                )
        """
        # Note: This is a simplified helper. For complex self-referential
        # relationships, you may need to use relationship() directly with
        # proper remote_side configuration.
        if (foreign_keys and isinstance(foreign_keys, str)) or (
            remote_side and isinstance(remote_side, str)
        ):
            return _SelfReferentialDescriptor(
                back_populates=back_populates,
                lazy=lazy,
                cascade=cascade,
                uselist=uselist,
                foreign_keys=foreign_keys,
                remote_side=remote_side,
            )
        kwargs: dict[str, Any] = {
            "back_populates": back_populates,
            "lazy": lazy,
            "cascade": cascade,
            "uselist": uselist,
        }
        if remote_side:
            kwargs["remote_side"] = remote_side
        if foreign_keys:
            kwargs["foreign_keys"] = foreign_keys
        return relationship(
            kwargs.pop("back_populates", None) and "self" or None, **kwargs
        )


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "Rel",
    "AssociationTable",
    "clear_model_cache",
    "validate_relationship_target_format",
]
