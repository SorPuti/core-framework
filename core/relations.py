"""
Relationship helpers for SQLAlchemy models.

Provides a cleaner, Django-like API for defining relationships between models.
Handles common patterns like ForeignKey, OneToMany, ManyToOne, ManyToMany,
and OneToOne with sensible defaults and validation.

Example:
    from core import Model, Field
    from core.relations import Rel
    
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
from typing import TYPE_CHECKING, Any, TypeVar, overload
from uuid import UUID

from sqlalchemy import Column, ForeignKey, Integer, String, Table
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from core.models import Model

T = TypeVar("T", bound="Model")

logger = logging.getLogger("core.relations")


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
            from core.models import Model
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

def _resolve_target(target: str) -> str:
    """
    Resolve target de relacionamento com suporte a lazy loading.
    
    Estratégia de resolução (ordem de prioridade):
    
    1. **Fully-qualified paths** (3+ pontos): Usados diretamente pelo SQLAlchemy
       para lazy resolution em runtime. Ex: "src.apps.workspaces.models.Workspace"
       
    2. **Sintaxe app.Model** (exatamente 1 ponto): Resolve para nome simples
       após garantir que o model está registrado no SQLAlchemy registry.
       Ex: "workspaces.Workspace" → "Workspace" (após importar o módulo)
       
    3. **"User" especial**: Resolve via get_user_model() para o User configurado.
    
    4. **Nomes simples**: Passados diretamente para SQLAlchemy resolver no mesmo
       registry/módulo. Funciona apenas se o model estiver no mesmo arquivo ou
       já registrado.
    
    Args:
        target: Nome do modelo. Formatos suportados:
            - "src.apps.posts.models.Post" (fully-qualified)
            - "posts.Post" (app.Model syntax - RECOMENDADO)
            - "User" (resolve via auth config)
            - "Post" (nome simples - mesmo módulo)
    
    Returns:
        Target string para SQLAlchemy (nome simples quando possível)
    
    Raises:
        ValueError: Se target "User" não puder ser resolvido
    
    Examples:
        >>> _resolve_target("src.apps.posts.models.Post")
        "src.apps.posts.models.Post"
        
        >>> _resolve_target("posts.Post")  # app.Model syntax
        "Post"  # Retorna nome simples após garantir que está no registry
        
        >>> _resolve_target("User")  # resolve via get_user_model()
        "User"  # Nome simples após garantir que está no registry
        
        >>> _resolve_target("Comment")  # nome simples
        "Comment"
    """
    # 1. Fully-qualified paths (múltiplos ".") → usar diretamente
    # Ex: "src.apps.workspaces.models.Workspace"
    if target.count(".") > 1:
        logger.debug("Using fully-qualified target: %s", target)
        return target
    
    # 2. Sintaxe app.Model (exatamente um ".") → importar e retornar nome simples
    # Ex: "workspaces.Workspace" → "Workspace"
    if "." in target:
        app_name, model_name = target.split(".", 1)
        
        # Tenta importar o model e retorna nome simples
        if _ensure_model_loaded(app_name, model_name):
            logger.debug("Resolved '%s' -> '%s' (model loaded into registry)", target, model_name)
            return model_name
        
        # Se não conseguiu carregar, tenta retornar path fully-qualified como fallback
        resolved = _get_model_path(app_name, model_name)
        if resolved:
            logger.debug("Resolved '%s' -> '%s' (fallback to full path)", target, resolved)
            return resolved
        
        # Último recurso: retorna nome simples e espera que esteja no registry
        logger.debug("Could not load '%s', using simple name '%s' (hope it's in registry)", target, model_name)
        return model_name
    
    # 3. Caso especial: "User" → resolve via get_user_model()
    if target == "User":
        try:
            from core.auth.models import get_user_model
            User = get_user_model()
            # Retorna nome simples - o model já está no registry
            logger.debug("Resolved 'User' -> '%s' (from auth config)", User.__name__)
            return User.__name__
        except Exception as e:
            # Se não conseguiu resolver, retorna "User" e espera que esteja no registry
            logger.debug("Could not resolve 'User' via auth config: %s. Using simple name.", e)
            return "User"
    
    # 4. Nomes simples → SQLAlchemy resolve em runtime no mesmo registry
    # Ex: "Comment" quando definido no mesmo arquivo
    logger.debug("Using simple target '%s' (SQLAlchemy will resolve in registry)", target)
    return target


# Cache de módulos já tentados (evita importações repetidas)
_model_import_cache: dict[str, bool] = {}


def _ensure_model_loaded(app_name: str, model_name: str) -> bool:
    """
    Garante que um model está carregado no SQLAlchemy registry.
    
    Tenta importar o módulo do model se ainda não estiver carregado.
    Usa cache para evitar tentativas repetidas de importação.
    
    Args:
        app_name: Nome da app (ex: "workspaces", "users")
        model_name: Nome do model (ex: "Workspace", "User")
    
    Returns:
        True se o model foi encontrado/carregado, False caso contrário
    """
    import sys
    from importlib import import_module
    
    cache_key = f"{app_name}.{model_name}"
    
    # Verifica cache primeiro
    if cache_key in _model_import_cache:
        return _model_import_cache[cache_key]
    
    # Convenções de módulo a tentar (ordem de prioridade)
    module_conventions = [
        f"src.apps.{app_name}.models",
        f"src.{app_name}.models",
        f"apps.{app_name}.models",
        f"{app_name}.models",
    ]
    
    # Primeiro, verifica se algum módulo já está carregado
    for module_path in module_conventions:
        if module_path in sys.modules:
            module = sys.modules[module_path]
            if hasattr(module, model_name):
                logger.debug("Found '%s' in already-loaded module '%s'", model_name, module_path)
                _model_import_cache[cache_key] = True
                return True
    
    # Tenta importar cada convenção
    for module_path in module_conventions:
        try:
            module = import_module(module_path)
            if hasattr(module, model_name):
                logger.debug("Loaded '%s' from module '%s'", model_name, module_path)
                _model_import_cache[cache_key] = True
                return True
        except ImportError:
            continue
        except Exception as e:
            logger.debug("Error importing '%s': %s", module_path, e)
            continue
    
    # Não encontrou em nenhuma convenção
    logger.debug("Could not find model '%s' in app '%s'", model_name, app_name)
    _model_import_cache[cache_key] = False
    return False


def _get_model_path(app_name: str, model_name: str) -> str | None:
    """
    Retorna o path fully-qualified de um model se encontrado.
    
    Verifica módulos já carregados para encontrar o path correto.
    
    Args:
        app_name: Nome da app (ex: "workspaces", "users")
        model_name: Nome do model (ex: "Workspace", "User")
    
    Returns:
        Path fully-qualified ou None se não encontrado
    """
    import sys
    
    # Convenções de path a tentar
    conventions = [
        f"src.apps.{app_name}.models",
        f"src.{app_name}.models",
        f"apps.{app_name}.models",
        f"{app_name}.models",
    ]
    
    for module_path in conventions:
        if module_path in sys.modules:
            module = sys.modules[module_path]
            if hasattr(module, model_name):
                return f"{module_path}.{model_name}"
    
    return None


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
        resolved = _resolve_target(target)
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
        resolved = _resolve_target(target)
        kwargs: dict[str, Any] = {
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
        resolved = _resolve_target(target)
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
        
        resolved = _resolve_target(target)
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
        
        # For self-referential, we return a partial that needs the class name
        # This is a limitation - user should use the class name explicitly
        return relationship(kwargs.pop("back_populates", None) and "self" or None, **kwargs)


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "Rel",
    "AssociationTable",
    "clear_model_cache",
]
