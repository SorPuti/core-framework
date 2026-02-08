"""
Model system. Docs: https://github.com/your-org/core-framework/docs/03-models.md

Usage:
    from core import Model, Field
    from sqlalchemy.orm import Mapped
    
    class Item(Model):
        __tablename__ = "items"
        id: Mapped[int] = Field.pk()
        name: Mapped[str] = Field.string(200)
"""

from __future__ import annotations

from typing import Any, ClassVar, Self, TYPE_CHECKING
from collections.abc import Sequence

from pydantic import BaseModel as PydanticBaseModel, ConfigDict
from sqlalchemy import MetaData, Column, Integer, String, Boolean, DateTime as SADateTime, Float, Text, ForeignKey
from sqlalchemy import select, update, delete, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from core.datetime import timezone, DateTime

if TYPE_CHECKING:
    from core.querysets import QuerySet, SoftDeleteQuerySet, TenantSoftDeleteQuerySet

# Convenção de nomes para constraints (evita problemas de migração)
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=convention)


class Base(DeclarativeBase):
    """Base declarativa do SQLAlchemy com metadata customizada."""
    metadata = metadata


# Tipos de campos disponíveis
class Field:
    """
    Namespace para tipos de campos.
    
    Uso:
        class User(Model):
            name: Mapped[str] = Field.string(max_length=100)
            email: Mapped[str] = Field.string(max_length=255, unique=True)
            is_active: Mapped[bool] = Field.boolean(default=True)
    """
    
    @staticmethod
    def integer(
        *,
        primary_key: bool = False,
        autoincrement: bool = False,
        nullable: bool = False,
        default: int | None = None,
        index: bool = False,
    ) -> Mapped[int]:
        """Campo inteiro."""
        return mapped_column(
            Integer,
            primary_key=primary_key,
            autoincrement=autoincrement,
            nullable=nullable,
            default=default,
            index=index,
        )
    
    @staticmethod
    def string(
        *,
        max_length: int = 255,
        nullable: bool = False,
        default: str | None = None,
        unique: bool = False,
        index: bool = False,
    ) -> Mapped[str]:
        """Campo string com tamanho máximo."""
        return mapped_column(
            String(max_length),
            nullable=nullable,
            default=default,
            unique=unique,
            index=index,
        )
    
    @staticmethod
    def text(
        *,
        nullable: bool = False,
        default: str | None = None,
    ) -> Mapped[str]:
        """Campo texto sem limite de tamanho."""
        return mapped_column(
            Text,
            nullable=nullable,
            default=default,
        )
    
    @staticmethod
    def boolean(
        *,
        nullable: bool = False,
        default: bool = False,
        index: bool = False,
    ) -> Mapped[bool]:
        """Campo booleano."""
        return mapped_column(
            Boolean,
            nullable=nullable,
            default=default,
            index=index,
        )
    
    @staticmethod
    def datetime(
        *,
        nullable: bool = False,
        default: datetime | None = None,
        auto_now: bool = False,
        auto_now_add: bool = False,
        index: bool = False,
    ) -> Mapped[DateTime]:
        """
        Campo datetime.
        
        Sempre usa UTC via timezone.now().
        
        Args:
            nullable: Se o campo pode ser NULL
            default: Valor default customizado
            auto_now: Se True, atualiza para now() em cada save (INSERT e UPDATE)
            auto_now_add: Se True, define now() apenas no INSERT
            index: Se True, cria índice no banco
        
        Note:
            - auto_now=True: Define default E onupdate para timezone.now
            - auto_now_add=True: Define apenas default para timezone.now
            - Ambos usam UTC via timezone.now()
        """
        actual_default = default
        if auto_now_add or auto_now:
            actual_default = timezone.now
        
        return mapped_column(
            SADateTime(timezone=True),
            nullable=nullable,
            default=actual_default,
            onupdate=timezone.now if auto_now else None,
            index=index,
        )
    
    @staticmethod
    def float(
        *,
        nullable: bool = False,
        default: float | None = None,
        index: bool = False,
    ) -> Mapped[float]:
        """Campo float."""
        return mapped_column(
            Float,
            nullable=nullable,
            default=default,
            index=index,
        )
    
    @staticmethod
    def foreign_key(
        target: str,
        *,
        nullable: bool = False,
        ondelete: str = "CASCADE",
        index: bool = True,
    ) -> Mapped[int]:
        """Campo de chave estrangeira."""
        return mapped_column(
            Integer,
            ForeignKey(target, ondelete=ondelete),
            nullable=nullable,
            index=index,
        )
    
    @staticmethod
    def pk() -> Mapped[int]:
        """Campo de chave primária autoincrement."""
        return mapped_column(
            Integer,
            primary_key=True,
            autoincrement=True,
        )
    
    @staticmethod
    def choice(
        choices_class: type,
        *,
        default: Any = None,
        nullable: bool = False,
        index: bool = False,
        use_native_enum: bool = False,
    ) -> Mapped[Any]:
        """
        Campo para enums com TextChoices ou IntegerChoices.
        
        Armazena o valor do enum no banco e permite comparação direta.
        
        Args:
            choices_class: Classe TextChoices ou IntegerChoices
            default: Valor default (pode ser o enum member ou o valor)
            nullable: Se o campo pode ser NULL
            index: Se deve criar índice
            use_native_enum: Se True, usa tipo ENUM nativo do PostgreSQL
                           (migrations detectam e gerenciam automaticamente)
        
        Example:
            from core.choices import TextChoices, IntegerChoices
            
            class Status(TextChoices):
                DRAFT = "draft", "Draft"
                PUBLISHED = "published", "Published"
            
            class Priority(IntegerChoices):
                LOW = 1, "Low"
                HIGH = 3, "High"
            
            class Post(Model):
                status: Mapped[str] = Field.choice(Status, default=Status.DRAFT)
                priority: Mapped[int] = Field.choice(Priority, default=Priority.LOW)
                
                # Com ENUM nativo do PostgreSQL (migrations gerenciam)
                status_native: Mapped[str] = Field.choice(
                    Status, 
                    default=Status.DRAFT,
                    use_native_enum=True,
                )
            
            # Usage
            post = Post(status=Status.PUBLISHED, priority=Priority.HIGH)
            post.status == "published"  # True
            post.status == Status.PUBLISHED  # True
            
            # Get label
            Status.get_label(post.status)  # "Published"
        
        Note:
            Quando use_native_enum=True:
            - PostgreSQL: Cria tipo ENUM nativo
            - SQLite/MySQL: Usa VARCHAR (fallback automático)
            - Migrations detectam alterações nos valores do enum
        """
        from core.choices import TextChoices, IntegerChoices
        
        # Determine column type based on choices class
        if issubclass(choices_class, str):
            # TextChoices - use String with max_length from choices
            max_length = choices_class.max_length + 10  # Add buffer
            column_type = String(max(max_length, 50))  # Minimum 50
        else:
            # IntegerChoices - use Integer
            column_type = Integer
        
        # Handle default value
        actual_default = default
        if default is not None and hasattr(default, "value"):
            actual_default = default.value
        
        # Create the column with choices metadata stored in info dict
        # SQLAlchemy's info parameter allows storing arbitrary metadata
        column = mapped_column(
            column_type,
            nullable=nullable,
            default=actual_default,
            index=index,
            info={
                "choices_class": choices_class,
                "use_native_enum": use_native_enum,
            }
        )
        
        return column


class Manager[T: "Model"]:
    """
    Manager para operações de banco de dados.
    
    Inspirado no Django ORM Manager, mas async e explícito.
    
    Uso:
        users = await User.objects.filter(is_active=True).all()
        user = await User.objects.get(id=1)
    """
    
    def __init__(self, model_class: type[T]) -> None:
        self._model_class = model_class
        self._session: AsyncSession | None = None
    
    def using(self, session: AsyncSession) -> "Manager[T]":
        """Define a sessão a ser usada nas queries."""
        new_manager = Manager(self._model_class)
        new_manager._session = session
        return new_manager
    
    def _get_session(self) -> AsyncSession:
        """Retorna a sessão atual ou levanta erro."""
        if self._session is None:
            raise RuntimeError(
                "Nenhuma sessão definida. Use 'Model.objects.using(session)' "
                "ou passe a sessão via dependency injection."
            )
        return self._session
    
    # Query methods
    def filter(self, **kwargs: Any) -> "QuerySet[T]":
        """Filtra registros por condições."""
        from core.querysets import QuerySet
        qs = QuerySet(self._model_class, self._session)
        return qs.filter(**kwargs)
    
    def exclude(self, **kwargs: Any) -> "QuerySet[T]":
        """Exclui registros por condições."""
        from core.querysets import QuerySet
        qs = QuerySet(self._model_class, self._session)
        return qs.exclude(**kwargs)
    
    def order_by(self, *fields: str) -> "QuerySet[T]":
        """Ordena resultados."""
        from core.querysets import QuerySet
        qs = QuerySet(self._model_class, self._session)
        return qs.order_by(*fields)
    
    def limit(self, value: int) -> "QuerySet[T]":
        """Limita o número de resultados."""
        from core.querysets import QuerySet
        qs = QuerySet(self._model_class, self._session)
        return qs.limit(value)
    
    def offset(self, value: int) -> "QuerySet[T]":
        """Define o offset dos resultados."""
        from core.querysets import QuerySet
        qs = QuerySet(self._model_class, self._session)
        return qs.offset(value)
    
    async def all(self) -> Sequence[T]:
        """Retorna todos os registros."""
        from core.querysets import QuerySet
        qs = QuerySet(self._model_class, self._session)
        return await qs.all()
    
    async def get(self, **kwargs: Any) -> T:
        """Retorna um único registro ou levanta exceção."""
        from core.querysets import QuerySet
        qs = QuerySet(self._model_class, self._session)
        return await qs.filter(**kwargs).get()
    
    async def get_or_none(self, **kwargs: Any) -> T | None:
        """Retorna um único registro ou None."""
        from core.querysets import QuerySet
        qs = QuerySet(self._model_class, self._session)
        return await qs.filter(**kwargs).first()
    
    async def first(self) -> T | None:
        """Retorna o primeiro registro ou None."""
        from core.querysets import QuerySet
        qs = QuerySet(self._model_class, self._session)
        return await qs.first()
    
    async def count(self) -> int:
        """Conta registros."""
        from core.querysets import QuerySet
        qs = QuerySet(self._model_class, self._session)
        return await qs.count()
    
    async def exists(self, **kwargs: Any) -> bool:
        """Verifica se existem registros."""
        from core.querysets import QuerySet
        qs = QuerySet(self._model_class, self._session)
        if kwargs:
            qs = qs.filter(**kwargs)
        return await qs.exists()
    
    async def last(self) -> T | None:
        """Retorna o último registro ou None."""
        from core.querysets import QuerySet
        qs = QuerySet(self._model_class, self._session)
        return await qs.last()
    
    async def values(self, *fields: str) -> list[dict[str, Any]]:
        """
        Retorna dicionários com os campos especificados.
        
        Se nenhum campo for especificado, retorna todos.
        """
        from core.querysets import QuerySet
        qs = QuerySet(self._model_class, self._session)
        return await qs.values(*fields)
    
    async def values_list(self, *fields: str, flat: bool = False) -> list[Any]:
        """
        Retorna tuplas com os valores dos campos especificados.
        
        Se flat=True e apenas um campo, retorna lista simples.
        """
        from core.querysets import QuerySet
        qs = QuerySet(self._model_class, self._session)
        return await qs.values_list(*fields, flat=flat)
    
    async def aggregate(self, **kwargs: Any) -> dict[str, Any]:
        """
        Executa funções de agregação.
        
        Exemplo:
            from core.querysets import Count, Sum, Avg, Max, Min
            result = await User.objects.using(db).aggregate(
                total=Count("*"),
                avg_age=Avg("age"),
            )
        """
        from core.querysets import QuerySet
        qs = QuerySet(self._model_class, self._session)
        return await qs.aggregate(**kwargs)
    
    def select_related(self, *fields: str) -> "QuerySet[T]":
        """Carrega relacionamentos junto com a query principal (JOIN)."""
        from core.querysets import QuerySet
        qs = QuerySet(self._model_class, self._session)
        return qs.select_related(*fields)
    
    def prefetch_related(self, *fields: str) -> "QuerySet[T]":
        """Pré-carrega relacionamentos em queries separadas."""
        from core.querysets import QuerySet
        qs = QuerySet(self._model_class, self._session)
        return qs.prefetch_related(*fields)
    
    async def create(self, **kwargs: Any) -> T:
        """Cria um novo registro."""
        session = self._get_session()
        instance = self._model_class(**kwargs)
        await instance.before_create()
        session.add(instance)
        await session.flush()
        await instance.after_create()
        return instance
    
    async def bulk_create(self, objects: list[dict[str, Any]]) -> list[T]:
        """Cria múltiplos registros de uma vez."""
        session = self._get_session()
        instances = [self._model_class(**obj) for obj in objects]
        for instance in instances:
            await instance.before_create()
        session.add_all(instances)
        await session.flush()
        for instance in instances:
            await instance.after_create()
        return instances
    
    async def update(self, filters: dict[str, Any], **values: Any) -> int:
        """Atualiza registros em massa."""
        session = self._get_session()
        stmt = update(self._model_class)
        for key, value in filters.items():
            stmt = stmt.where(getattr(self._model_class, key) == value)
        stmt = stmt.values(**values)
        result = await session.execute(stmt)
        return result.rowcount
    
    async def delete(self, **filters: Any) -> int:
        """Deleta registros em massa."""
        session = self._get_session()
        stmt = delete(self._model_class)
        for key, value in filters.items():
            stmt = stmt.where(getattr(self._model_class, key) == value)
        result = await session.execute(stmt)
        return result.rowcount


class ModelMeta(type(Base)):
    """
    Metaclass para Models.
    
    Adiciona automaticamente o Manager 'objects' a cada Model.
    """
    
    def __new__(mcs, name: str, bases: tuple, namespace: dict[str, Any], **kwargs: Any):
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        
        # Não adiciona manager à classe Base
        if name != "Model" and name != "Base":
            cls.objects = Manager(cls)
        
        return cls


class Model(Base, metaclass=ModelMeta):
    """
    Classe base para todos os Models.
    
    Características:
    - Campos tipados via SQLAlchemy 2.0 Mapped
    - Manager 'objects' para queries
    - Hooks de ciclo de vida
    - Métodos save/delete async
    
    Exemplo:
        class User(Model):
            __tablename__ = "users"
            
            id: Mapped[int] = Field.pk()
            email: Mapped[str] = Field.string(max_length=255, unique=True)
            name: Mapped[str] = Field.string(max_length=100)
            is_active: Mapped[bool] = Field.boolean(default=True)
            created_at: Mapped[DateTime] = Field.datetime(auto_now_add=True)
    """
    
    __abstract__ = True

    # Manager será adicionado pela metaclass
    objects: ClassVar[Manager[Self]]
    
    # Hooks de ciclo de vida
    async def before_create(self) -> None:
        """Hook executado antes de criar o registro."""
        pass
    
    async def after_create(self) -> None:
        """Hook executado após criar o registro."""
        pass
    
    async def before_save(self) -> None:
        """Hook executado antes de salvar (create ou update)."""
        pass
    
    async def after_save(self) -> None:
        """Hook executado após salvar."""
        pass
    
    async def before_delete(self) -> None:
        """Hook executado antes de deletar."""
        pass
    
    async def after_delete(self) -> None:
        """Hook executado após deletar."""
        pass
    
    async def save(self, session: AsyncSession) -> Self:
        """
        Save the record to the database.
        
        This method:
        1. Calls before_save() hook
        2. Adds the instance to the session
        3. Flushes changes to the database (but does NOT commit)
        4. Refreshes the instance to get auto-generated values (id, timestamps)
        5. Calls after_save() hook
        
        Note: This does NOT commit the transaction. The commit happens
        when the session context exits or when you call session.commit().
        
        Args:
            session: Async SQLAlchemy session
            
        Returns:
            The updated instance with refreshed values
        """
        await self.before_save()
        
        # Identify columns with default/onupdate that need refresh
        # This ensures auto-generated values (defaults, auto_now, etc) are loaded
        columns_to_refresh = [
            col.name for col in self.__table__.columns
            if col.default is not None or col.onupdate is not None or col.server_default is not None
        ]
        
        session.add(self)
        await session.flush()
        
        # Refresh columns that may have been generated by the database
        # Using explicit attribute_names ensures values are reloaded even with expire_on_commit=False
        if columns_to_refresh:
            await session.refresh(self, attribute_names=columns_to_refresh)
        else:
            await session.refresh(self)
        
        await self.after_save()
        return self
    
    async def delete(self, session: AsyncSession) -> None:
        """
        Deleta o registro do banco de dados.
        
        Args:
            session: Sessão async do SQLAlchemy
        """
        await self.before_delete()
        await session.delete(self)
        await session.flush()
        await self.after_delete()
    
    async def refresh(self, session: AsyncSession) -> Self:
        """Recarrega o registro do banco de dados."""
        await session.refresh(self)
        return self
    
    def to_dict(self) -> dict[str, Any]:
        """Converte o model para dicionário."""
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns
        }
    
    def __repr__(self) -> str:
        pk_cols = [col.name for col in self.__table__.primary_key.columns]
        pk_values = ", ".join(f"{col}={getattr(self, col, None)}" for col in pk_cols)
        return f"<{self.__class__.__name__}({pk_values})>"


# Engine e Session factory globais
_engine = None
_session_factory = None


async def init_database(
    database_url: str,
    echo: bool = False,
    pool_size: int = 5,
    max_overflow: int = 10,
) -> None:
    """
    Inicializa a conexão com o banco de dados.
    
    Args:
        database_url: URL de conexão async (ex: sqlite+aiosqlite:///./app.db)
        echo: Habilita logging de SQL
        pool_size: Tamanho do pool de conexões
        max_overflow: Conexões extras além do pool
    """
    global _engine, _session_factory
    
    _engine = create_async_engine(
        database_url,
        echo=echo,
        pool_size=pool_size if "sqlite" not in database_url else 0,
        max_overflow=max_overflow if "sqlite" not in database_url else 0,
    )
    
    _session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


def _sync_missing_columns(connection, _log) -> None:
    """
    Detecta e adiciona colunas faltantes em tabelas existentes.
    
    Usa SQLAlchemy Inspector para comparar o schema do banco com
    o metadata dos models e executa ALTER TABLE ADD COLUMN para
    cada coluna nova detectada.
    
    Chamado dentro de conn.run_sync() — roda em contexto síncrono.
    
    Compatível com PostgreSQL, SQLite, MySQL.
    """
    from sqlalchemy import inspect as sa_inspect, text
    
    try:
        inspector = sa_inspect(connection)
    except Exception as e:
        _log.warning("Schema sync: could not create inspector: %s", e)
        return
    
    existing_tables = set(inspector.get_table_names())
    dialect_name = connection.dialect.name
    total_added = 0
    
    for table_name, table in Base.metadata.tables.items():
        if table_name not in existing_tables:
            continue  # Tabela nova — já foi criada pelo create_all
        
        try:
            db_columns = {col["name"] for col in inspector.get_columns(table_name)}
        except Exception:
            continue
        
        model_columns = {col.name for col in table.columns}
        missing = model_columns - db_columns
        
        if not missing:
            continue
        
        _log.warning(
            "Schema sync: table '%s' needs %d new column(s): %s",
            table_name, len(missing), ", ".join(sorted(missing)),
        )
        
        for col_name in sorted(missing):
            col = table.c[col_name]
            try:
                col_type = col.type.compile(dialect=connection.dialect)
                
                # Estratégia: adicionar sempre como NULL primeiro, depois
                # podemos aplicar NOT NULL se necessário. Isso evita erros
                # com "column cannot be NOT NULL without default" em todos DBs.
                # Para tabelas internas do framework, NULL é aceitável para
                # colunas legadas (já tinham dados antes da coluna existir).
                sql = f'ALTER TABLE "{table_name}" ADD COLUMN "{col_name}" {col_type}'
                
                connection.execute(text(sql))
                total_added += 1
                _log.warning("  + Added column '%s.%s' (%s)", table_name, col_name, col_type)
                
            except Exception as e:
                _log.error(
                    "  ! Failed to add column '%s.%s': %s",
                    table_name, col_name, e,
                )
    
    if total_added:
        _log.warning("Schema sync: added %d column(s) total.", total_added)
    else:
        _log.debug("Schema sync: all tables up to date.")


async def create_tables() -> None:
    """
    Cria tabelas no banco de dados e sincroniza colunas faltantes.
    
    Além de criar tabelas novas (comportamento padrão do create_all),
    detecta colunas que foram adicionadas aos models mas não existem
    nas tabelas do banco e executa ALTER TABLE ADD COLUMN automaticamente.
    
    Isso resolve o problema de schema mismatch quando o framework é
    atualizado e novos campos são adicionados aos models internos
    (ex: TaskExecution, WorkerHeartbeat) sem migration explícita.
    """
    import logging
    _log = logging.getLogger("core.database")
    
    if _engine is None:
        raise RuntimeError("Database não inicializado. Chame init_database() primeiro.")
    
    _log.info("create_tables: creating missing tables + syncing columns...")
    
    async with _engine.begin() as conn:
        # 1. Criar tabelas novas (create_all só cria, nunca altera existentes)
        await conn.run_sync(Base.metadata.create_all)
        
        # 2. Sincronizar colunas faltantes em tabelas existentes
        await conn.run_sync(_sync_missing_columns, _log)
    
    _log.info("create_tables: done.")


async def drop_tables() -> None:
    """Remove todas as tabelas do banco de dados."""
    if _engine is None:
        raise RuntimeError("Database não inicializado. Chame init_database() primeiro.")
    
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def get_session() -> AsyncSession:
    """Retorna uma nova sessão do banco de dados."""
    if _session_factory is None:
        raise RuntimeError("Database não inicializado. Chame init_database() primeiro.")
    
    return _session_factory()


async def close_database() -> None:
    """Fecha a conexão com o banco de dados."""
    global _engine, _session_factory
    
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


# =============================================================================
# Soft Delete Mixin
# =============================================================================

class SoftDeleteMixin:
    """
    Mixin para soft delete (exclusão lógica).
    
    Adiciona campo deleted_at e métodos para soft delete/restore.
    Não deleta fisicamente o registro, apenas marca como deletado.
    
    Características:
    - Campo deleted_at (NULL = ativo, timestamp = deletado)
    - Método soft_delete() para marcar como deletado
    - Método restore() para restaurar
    - Propriedade is_deleted para verificar status
    
    Uso:
        class User(Model, SoftDeleteMixin):
            __tablename__ = "users"
            objects = SoftDeleteManager["User"]()  # Manager especial
            
            id: Mapped[int] = Field.pk()
            name: Mapped[str] = Field.string(max_length=100)
        
        # Soft delete
        await user.soft_delete(session)
        
        # Verificar
        if user.is_deleted:
            ...
        
        # Restaurar
        await user.restore(session)
    
    Nota:
        Use SoftDeleteManager para filtrar deletados automaticamente.
        O Manager padrão NÃO filtra deletados.
    """
    
    deleted_at: Mapped[DateTime | None] = mapped_column(
        SADateTime(timezone=True),
        nullable=True,
        default=None,
        index=True,
    )
    
    @property
    def is_deleted(self) -> bool:
        """
        Verifica se o registro está deletado.
        
        Returns:
            True se deleted_at não é None
        """
        return self.deleted_at is not None
    
    @property
    def is_active(self) -> bool:
        """
        Verifica se o registro está ativo (não deletado).
        
        Returns:
            True se deleted_at é None
        """
        return self.deleted_at is None
    
    async def soft_delete(self, session: AsyncSession) -> Self:
        """
        Marca o registro como deletado.
        
        Define deleted_at com timestamp atual.
        
        Args:
            session: Sessão do banco de dados
            
        Returns:
            A própria instância
            
        Exemplo:
            await user.soft_delete(session)
        """
        self.deleted_at = timezone.now()
        session.add(self)
        await session.flush()
        return self
    
    async def restore(self, session: AsyncSession) -> Self:
        """
        Restaura um registro deletado.
        
        Define deleted_at como None.
        
        Args:
            session: Sessão do banco de dados
            
        Returns:
            A própria instância
            
        Exemplo:
            await user.restore(session)
        """
        self.deleted_at = None
        session.add(self)
        await session.flush()
        return self
    
    async def hard_delete(self, session: AsyncSession) -> None:
        """
        Deleta o registro permanentemente.
        
        Use com cuidado - não pode ser desfeito.
        
        Args:
            session: Sessão do banco de dados
        """
        await session.delete(self)
        await session.flush()


class SoftDeleteManager[T: "Model"](Manager[T]):
    """
    Manager que filtra registros deletados automaticamente.
    
    Todas as queries excluem registros com deleted_at preenchido.
    Use with_deleted() para incluir deletados.
    Use only_deleted() para retornar apenas deletados.
    
    O nome do campo de soft delete pode ser configurado via:
    - Parâmetro deleted_field no construtor
    - settings.soft_delete_field (usado automaticamente se não especificado)
    
    Uso:
        class User(Model, SoftDeleteMixin):
            __tablename__ = "users"
            objects = SoftDeleteManager["User"]()
        
        # Retorna apenas ativos (deleted_at IS NULL)
        users = await User.objects.using(db).all()
        
        # Inclui deletados
        all_users = await User.objects.using(db).with_deleted().all()
        
        # Apenas deletados
        deleted = await User.objects.using(db).only_deleted().all()
    """
    
    def __init__(
        self,
        model_class: type[T] | None = None,
        deleted_field: str | None = None,
    ) -> None:
        # model_class pode ser None quando usado com type hint
        if model_class is not None:
            super().__init__(model_class)
        
        # Usa settings se deleted_field não especificado
        if deleted_field is None:
            try:
                from core.config import get_settings
                deleted_field = get_settings().soft_delete_field
            except Exception:
                deleted_field = "deleted_at"
        
        self._deleted_field = deleted_field
    
    def _create_queryset(self) -> "SoftDeleteQuerySet[T]":
        """Cria SoftDeleteQuerySet em vez de QuerySet normal."""
        from core.querysets import SoftDeleteQuerySet
        return SoftDeleteQuerySet(
            self._model_class,
            self._session,
            self._deleted_field,
        )
    
    def filter(self, **kwargs: Any) -> "SoftDeleteQuerySet[T]":
        """Filtra registros (exclui deletados por padrão)."""
        qs = self._create_queryset()
        return qs.filter(**kwargs)
    
    def exclude(self, **kwargs: Any) -> "SoftDeleteQuerySet[T]":
        """Exclui registros por condições."""
        qs = self._create_queryset()
        return qs.exclude(**kwargs)
    
    def order_by(self, *fields: str) -> "SoftDeleteQuerySet[T]":
        """Ordena resultados."""
        qs = self._create_queryset()
        return qs.order_by(*fields)
    
    def limit(self, value: int) -> "SoftDeleteQuerySet[T]":
        """Limita o número de resultados."""
        qs = self._create_queryset()
        return qs.limit(value)
    
    def offset(self, value: int) -> "SoftDeleteQuerySet[T]":
        """Define o offset dos resultados."""
        qs = self._create_queryset()
        return qs.offset(value)
    
    async def all(self) -> Sequence[T]:
        """Retorna todos os registros ativos."""
        qs = self._create_queryset()
        return await qs.all()
    
    async def get(self, **kwargs: Any) -> T:
        """Retorna um único registro ativo."""
        qs = self._create_queryset()
        return await qs.filter(**kwargs).get()
    
    async def get_or_none(self, **kwargs: Any) -> T | None:
        """Retorna um único registro ativo ou None."""
        qs = self._create_queryset()
        return await qs.filter(**kwargs).first()
    
    async def first(self) -> T | None:
        """Retorna o primeiro registro ativo."""
        qs = self._create_queryset()
        return await qs.first()
    
    async def count(self) -> int:
        """Conta registros ativos."""
        qs = self._create_queryset()
        return await qs.count()
    
    async def exists(self, **kwargs: Any) -> bool:
        """Verifica se existem registros ativos."""
        qs = self._create_queryset()
        if kwargs:
            qs = qs.filter(**kwargs)
        return await qs.exists()
    
    def with_deleted(self) -> "SoftDeleteQuerySet[T]":
        """
        Retorna QuerySet que inclui registros deletados.
        
        Returns:
            SoftDeleteQuerySet com include_deleted=True
        """
        qs = self._create_queryset()
        return qs.with_deleted()
    
    def only_deleted(self) -> "SoftDeleteQuerySet[T]":
        """
        Retorna QuerySet apenas com registros deletados.
        
        Returns:
            SoftDeleteQuerySet com only_deleted=True
        """
        qs = self._create_queryset()
        return qs.only_deleted()
    
    def active(self) -> "SoftDeleteQuerySet[T]":
        """
        Retorna QuerySet apenas com registros ativos.
        
        Este é o comportamento padrão, mas torna o código mais explícito.
        
        Returns:
            SoftDeleteQuerySet filtrando apenas ativos
        """
        return self._create_queryset()
    
    async def soft_delete_by(self, **filters: Any) -> int:
        """
        Soft delete em massa por filtros.
        
        Args:
            **filters: Condições de filtro
            
        Returns:
            Número de registros afetados
            
        Exemplo:
            # Soft delete todos os usuários inativos
            count = await User.objects.using(db).soft_delete_by(is_active=False)
        """
        session = self._get_session()
        stmt = update(self._model_class).values(deleted_at=timezone.now())
        
        for key, value in filters.items():
            stmt = stmt.where(getattr(self._model_class, key) == value)
        
        # Não afeta registros já deletados
        deleted_col = getattr(self._model_class, self._deleted_field)
        stmt = stmt.where(deleted_col.is_(None))
        
        result = await session.execute(stmt)
        return result.rowcount
    
    async def restore_by(self, **filters: Any) -> int:
        """
        Restaura registros em massa por filtros.
        
        Args:
            **filters: Condições de filtro
            
        Returns:
            Número de registros restaurados
            
        Exemplo:
            # Restaura todos os usuários deletados de um workspace
            count = await User.objects.using(db).restore_by(workspace_id=ws_id)
        """
        session = self._get_session()
        stmt = update(self._model_class).values(deleted_at=None)
        
        for key, value in filters.items():
            stmt = stmt.where(getattr(self._model_class, key) == value)
        
        # Só afeta registros deletados
        deleted_col = getattr(self._model_class, self._deleted_field)
        stmt = stmt.where(deleted_col.is_not(None))
        
        result = await session.execute(stmt)
        return result.rowcount


class TenantSoftDeleteManager[T: "Model"](SoftDeleteManager[T]):
    """
    Manager combining soft delete and multi-tenancy filtering.
    
    Inherits all soft delete functionality and adds tenant filtering via for_tenant().
    Uses TenantSoftDeleteQuerySet which combines both features.
    
    Usage:
        class Project(Model, SoftDeleteMixin, TenantMixin):
            __tablename__ = "projects"
            objects = TenantSoftDeleteManager["Project"]()
            
            id: Mapped[int] = Field.pk()
            name: Mapped[str] = Field.string(max_length=100)
        
        # Filter by tenant (excludes soft-deleted by default)
        projects = await Project.objects.using(db).for_tenant().all()
        
        # Include soft-deleted for tenant
        all_projects = await Project.objects.using(db).for_tenant().with_deleted().all()
        
        # Only soft-deleted for tenant
        deleted = await Project.objects.using(db).for_tenant().only_deleted().all()
    """
    
    def __init__(
        self,
        model_class: type[T] | None = None,
        deleted_field: str | None = None,
        tenant_field: str | None = None,
    ) -> None:
        super().__init__(model_class, deleted_field)
        
        # Usa settings se tenant_field não especificado
        if tenant_field is None:
            try:
                from core.config import get_settings
                tenant_field = get_settings().tenancy_field
            except Exception:
                tenant_field = "workspace_id"
        
        self._tenant_field = tenant_field
    
    def _create_queryset(self) -> "TenantSoftDeleteQuerySet[T]":
        """Cria TenantSoftDeleteQuerySet em vez de SoftDeleteQuerySet."""
        from core.querysets import TenantSoftDeleteQuerySet
        return TenantSoftDeleteQuerySet(
            self._model_class,
            self._session,
            self._deleted_field,
            self._tenant_field,
        )
    
    def for_tenant(
        self,
        tenant_id: Any | None = None,
        tenant_field: str | None = None,
    ) -> "TenantSoftDeleteQuerySet[T]":
        """
        Filter by current or specified tenant.
        
        Uses context tenant if tenant_id not provided.
        Excludes soft-deleted records by default.
        
        Args:
            tenant_id: Specific tenant ID (uses context if None)
            tenant_field: Override tenant field name
        
        Returns:
            TenantSoftDeleteQuerySet filtered by tenant
        
        Example:
            # Uses tenant from context (set by middleware)
            projects = await Project.objects.using(db).for_tenant().all()
            
            # Explicit tenant
            projects = await Project.objects.using(db).for_tenant(workspace_id).all()
        """
        qs = self._create_queryset()
        return qs.for_tenant(tenant_id, tenant_field)
