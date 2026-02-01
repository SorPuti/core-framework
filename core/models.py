"""
Sistema de Models inspirado no Django, mas com Pydantic + SQLAlchemy 2.0.

Características:
- Sintaxe declarativa e limpa
- Campos tipados
- Hooks (before_save, after_save, before_delete, after_delete)
- Query API fluente via Manager
- Async por padrão
- Zero magia obscura
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
    from core.querysets import QuerySet

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
        """
        actual_default = default
        if auto_now_add:
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
        Salva o registro no banco de dados.
        
        Args:
            session: Sessão async do SQLAlchemy
            
        Returns:
            A própria instância atualizada
        """
        await self.before_save()
        session.add(self)
        await session.flush()
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


async def create_tables() -> None:
    """Cria todas as tabelas no banco de dados."""
    if _engine is None:
        raise RuntimeError("Database não inicializado. Chame init_database() primeiro.")
    
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


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
