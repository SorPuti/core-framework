"""
QuerySet - API fluente para queries de banco de dados.

Inspirado no Django QuerySet, mas async e com tipagem forte.

Características:
- Encadeamento de métodos (filter, exclude, order_by, etc.)
- Lazy evaluation (queries só executam quando necessário)
- Suporte a lookups (field__gt, field__contains, etc.)
- Async por padrão
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING
from collections.abc import Sequence

from sqlalchemy import select, func, and_, or_, not_, asc, desc, Boolean, Integer, Float
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

if TYPE_CHECKING:
    from stride.models import Model


class DoesNotExist(Exception):
    """Exceção levantada quando um registro não é encontrado."""
    pass


class MultipleObjectsReturned(Exception):
    """Exceção levantada quando múltiplos registros são retornados para get()."""
    pass


# Operadores de lookup suportados
LOOKUP_OPERATORS = {
    "exact": lambda col, val: col == val,
    "iexact": lambda col, val: col.ilike(val),
    "contains": lambda col, val: col.contains(val),
    "icontains": lambda col, val: col.ilike(f"%{val}%"),
    "startswith": lambda col, val: col.startswith(val),
    "istartswith": lambda col, val: col.ilike(f"{val}%"),
    "endswith": lambda col, val: col.endswith(val),
    "iendswith": lambda col, val: col.ilike(f"%{val}"),
    "gt": lambda col, val: col > val,
    "gte": lambda col, val: col >= val,
    "lt": lambda col, val: col < val,
    "lte": lambda col, val: col <= val,
    "in": lambda col, val: col.in_(val),
    "isnull": lambda col, val: col.is_(None) if val else col.is_not(None),
    "range": lambda col, val: col.between(val[0], val[1]),
    # JSON operators
    "has_key": lambda col, val: col.has_key(val),
    "json_contains": lambda col, val: col.op("@>")(val),
}


def _is_json_column(column) -> bool:
    """Check if column is a JSON/JSONB type."""
    from sqlalchemy import JSON
    from sqlalchemy.dialects.postgresql import JSONB
    
    col_type = getattr(column, "type", None)
    if col_type is None:
        return False
    
    return isinstance(col_type, (JSON, JSONB)) or hasattr(col_type, "impl") and isinstance(col_type.impl, (JSON, JSONB))


def _build_json_path(column, path_parts: list[str], operator: str, value: Any) -> Any:
    """
    Build SQLAlchemy expression for JSON path lookup.
    
    Examples:
        - settings__theme="dark" -> column['theme'].astext == "dark"
        - settings__nested__key="value" -> column['nested']['key'].astext == "value"
    """
    # Build the JSON path traversal
    expr = column
    for part in path_parts:
        expr = expr[part]
    
    # For comparison operators, we need to cast to text first (astext)
    # then apply the operator
    if operator in ("exact", "iexact", "contains", "icontains", 
                    "startswith", "istartswith", "endswith", "iendswith"):
        # These need string comparison
        text_expr = expr.astext
        return LOOKUP_OPERATORS[operator](text_expr, value)
    
    elif operator in ("gt", "gte", "lt", "lte"):
        # Try to determine type from value
        if isinstance(value, bool):
            # Boolean comparison
            bool_expr = expr.astext.cast(Boolean)
            return LOOKUP_OPERATORS[operator](bool_expr, value)
        elif isinstance(value, int):
            # Integer comparison
            int_expr = expr.astext.cast(Integer)
            return LOOKUP_OPERATORS[operator](int_expr, value)
        elif isinstance(value, float):
            # Float comparison
            float_expr = expr.astext.cast(Float)
            return LOOKUP_OPERATORS[operator](float_expr, value)
        else:
            # Default to text comparison
            return LOOKUP_OPERATORS[operator](expr.astext, str(value))
    
    elif operator == "isnull":
        # Check if JSON path is null
        if value:
            return expr.is_(None) | (expr.astext == "null")
        else:
            return expr.is_not(None) & (expr.astext != "null")
    
    elif operator == "in":
        # For IN operator with JSON paths, convert to text
        return expr.astext.in_([str(v) for v in value])
    
    elif operator in ("has_key", "json_contains"):
        # These work on the column level, not the path
        return LOOKUP_OPERATORS[operator](column, value)
    
    # Default: exact match as text
    return expr.astext == str(value)


def parse_lookup(model_class: type, field_lookup: str, value: Any) -> Any:
    """
    Parseia um lookup do estilo Django e retorna a condição SQLAlchemy.
    
    Suporta lookups em campos JSON/Struct (path com __):
        - name="John" -> User.name == "John"
        - age__gt=18 -> User.age > 18
        - email__icontains="@gmail" -> User.email.ilike("%@gmail%")
        - settings__theme="dark" -> User.settings['theme'].astext == "dark"
        - settings__nested__key__gt=10 -> User.settings['nested']['key'].astext.cast(Integer) > 10
    """
    parts = field_lookup.split("__")
    field_name = parts[0]
    
    if not hasattr(model_class, field_name):
        raise AttributeError(f"Model {model_class.__name__} não tem campo '{field_name}'")
    
    column = getattr(model_class, field_name)
    
    # Check if this is a JSON column with nested path
    if len(parts) > 1:
        # Check if the column is a JSON/Struct column
        is_json = _is_json_column(column)
        
        # Also check if column has struct_schema in info (our StructSchema fields)
        col_info = getattr(column, "info", {}) or {}
        has_struct_schema = "struct_schema" in col_info
        
        if is_json or has_struct_schema:
            # JSON path lookup: settings__theme__exact="dark"
            # parts = ["settings", "theme", "exact"]
            # path_parts = ["theme"]
            # operator = "exact"
            
            path_parts = parts[1:-1] if len(parts) > 2 else parts[1:]
            operator = parts[-1] if len(parts) > 2 and parts[-1] in LOOKUP_OPERATORS else "exact"
            
            if not path_parts or (len(parts) == 2 and parts[-1] in LOOKUP_OPERATORS):
                # Single path part with operator: settings__exact={}
                path_parts = parts[1:2] if parts[-1] not in LOOKUP_OPERATORS else parts[1:1]
            
            return _build_json_path(column, path_parts, operator, value)
    
    # Standard lookup (non-JSON)
    operator = parts[1] if len(parts) > 1 else "exact"
    
    if operator not in LOOKUP_OPERATORS:
        raise ValueError(f"Operador de lookup '{operator}' não suportado")
    
    return LOOKUP_OPERATORS[operator](column, value)


class QuerySet[T: "Model"]:
    """
    QuerySet para operações de banco de dados.
    
    Suporta encadeamento de métodos e lazy evaluation.
    
    Exemplo:
        users = await User.objects.using(session)\\
            .filter(is_active=True)\\
            .exclude(role="admin")\\
            .order_by("-created_at")\\
            .limit(10)\\
            .all()
    """
    
    def __init__(
        self,
        model_class: type[T],
        session: AsyncSession | None = None,
    ) -> None:
        self._model_class = model_class
        self._session = session
        self._filters: list[Any] = []
        self._excludes: list[Any] = []
        self._order_by: list[Any] = []
        self._limit_value: int | None = None
        self._offset_value: int | None = None
        self._select_related: list[str] = []
        self._prefetch_related: list[str] = []
    
    def _clone(self) -> "QuerySet[T]":
        """Cria uma cópia do QuerySet."""
        qs = QuerySet(self._model_class, self._session)
        qs._filters = self._filters.copy()
        qs._excludes = self._excludes.copy()
        qs._order_by = self._order_by.copy()
        qs._limit_value = self._limit_value
        qs._offset_value = self._offset_value
        qs._select_related = self._select_related.copy()
        qs._prefetch_related = self._prefetch_related.copy()
        return qs
    
    def _get_session(self) -> AsyncSession:
        """Retorna a sessão atual ou levanta erro."""
        if self._session is None:
            raise RuntimeError(
                "Nenhuma sessão definida. Use 'Model.objects.using(session)' "
                "ou passe a sessão via dependency injection."
            )
        return self._session
    
    def using(self, session: AsyncSession) -> "QuerySet[T]":
        """Define a sessão a ser usada nas queries."""
        qs = self._clone()
        qs._session = session
        return qs
    
    def _build_query(self) -> Select:
        """Constrói a query SQLAlchemy."""
        stmt = select(self._model_class)
        
        # Aplica filtros
        if self._filters:
            stmt = stmt.where(and_(*self._filters))
        
        # Aplica exclusões
        if self._excludes:
            stmt = stmt.where(not_(or_(*self._excludes)))
        
        # Aplica ordenação
        for order in self._order_by:
            stmt = stmt.order_by(order)
        
        # Aplica limit
        if self._limit_value is not None:
            stmt = stmt.limit(self._limit_value)
        
        # Aplica offset
        if self._offset_value is not None:
            stmt = stmt.offset(self._offset_value)
        
        return stmt
    
    # Métodos de filtragem
    def filter(self, **kwargs: Any) -> "QuerySet[T]":
        """
        Filtra registros por condições.
        
        Suporta lookups do estilo Django:
            - field=value (exact)
            - field__gt=value (greater than)
            - field__contains=value (contains)
            - etc.
        """
        qs = self._clone()
        for field_lookup, value in kwargs.items():
            condition = parse_lookup(self._model_class, field_lookup, value)
            qs._filters.append(condition)
        return qs
    
    def exclude(self, **kwargs: Any) -> "QuerySet[T]":
        """
        Exclui registros por condições.
        
        Suporta os mesmos lookups que filter().
        """
        qs = self._clone()
        for field_lookup, value in kwargs.items():
            condition = parse_lookup(self._model_class, field_lookup, value)
            qs._excludes.append(condition)
        return qs
    
    def order_by(self, *fields: str) -> "QuerySet[T]":
        """
        Ordena resultados.
        
        Use prefixo '-' para ordem decrescente:
            .order_by("-created_at", "name")
        """
        qs = self._clone()
        for field in fields:
            if field.startswith("-"):
                column = getattr(self._model_class, field[1:])
                qs._order_by.append(desc(column))
            else:
                column = getattr(self._model_class, field)
                qs._order_by.append(asc(column))
        return qs
    
    def limit(self, value: int) -> "QuerySet[T]":
        """Limita o número de resultados."""
        qs = self._clone()
        qs._limit_value = value
        return qs
    
    def offset(self, value: int) -> "QuerySet[T]":
        """Define o offset dos resultados."""
        qs = self._clone()
        qs._offset_value = value
        return qs
    
    def select_related(self, *fields: str) -> "QuerySet[T]":
        """
        Carrega relacionamentos junto com a query principal.
        
        Equivalente ao select_related do Django.
        """
        qs = self._clone()
        qs._select_related.extend(fields)
        return qs
    
    def prefetch_related(self, *fields: str) -> "QuerySet[T]":
        """
        Pré-carrega relacionamentos em queries separadas.
        
        Equivalente ao prefetch_related do Django.
        """
        qs = self._clone()
        qs._prefetch_related.extend(fields)
        return qs
    
    # Métodos de execução
    async def all(self) -> Sequence[T]:
        """Executa a query e retorna todos os resultados."""
        session = self._get_session()
        stmt = self._build_query()
        result = await session.execute(stmt)
        return result.scalars().all()
    
    async def first(self) -> T | None:
        """Retorna o primeiro resultado ou None."""
        qs = self.limit(1)
        results = await qs.all()
        return results[0] if results else None
    
    async def last(self) -> T | None:
        """Retorna o último resultado ou None."""
        # Inverte a ordenação para pegar o último
        results = await self.all()
        return results[-1] if results else None
    
    async def get(self) -> T:
        """
        Retorna exatamente um resultado.
        
        Raises:
            DoesNotExist: Se nenhum registro for encontrado
            MultipleObjectsReturned: Se mais de um registro for encontrado
        """
        results = await self.limit(2).all()
        
        if not results:
            raise DoesNotExist(
                f"{self._model_class.__name__} matching query does not exist."
            )
        
        if len(results) > 1:
            raise MultipleObjectsReturned(
                f"get() returned more than one {self._model_class.__name__}"
            )
        
        return results[0]
    
    async def count(self) -> int:
        """Conta o número de registros."""
        session = self._get_session()
        stmt = select(func.count()).select_from(self._model_class)
        
        # Aplica filtros
        if self._filters:
            stmt = stmt.where(and_(*self._filters))
        
        # Aplica exclusões
        if self._excludes:
            stmt = stmt.where(not_(or_(*self._excludes)))
        
        result = await session.execute(stmt)
        return result.scalar() or 0
    
    async def exists(self) -> bool:
        """Verifica se existem registros."""
        count = await self.limit(1).count()
        return count > 0
    
    async def values(self, *fields: str) -> list[dict[str, Any]]:
        """
        Retorna dicionários com os campos especificados.
        
        Se nenhum campo for especificado, retorna todos.
        """
        results = await self.all()
        
        if not fields:
            return [obj.to_dict() for obj in results]
        
        return [
            {field: getattr(obj, field) for field in fields}
            for obj in results
        ]
    
    async def values_list(self, *fields: str, flat: bool = False) -> list[Any]:
        """
        Retorna tuplas com os valores dos campos especificados.
        
        Se flat=True e apenas um campo for especificado, retorna lista simples.
        """
        results = await self.all()
        
        if flat and len(fields) == 1:
            return [getattr(obj, fields[0]) for obj in results]
        
        return [
            tuple(getattr(obj, field) for field in fields)
            for obj in results
        ]
    
    async def delete(self) -> int:
        """
        Deleta todos os registros que correspondem à query.
        
        Returns:
            Número de registros deletados
        """
        from sqlalchemy import delete as sql_delete
        
        session = self._get_session()
        stmt = sql_delete(self._model_class)
        
        # Aplica filtros
        if self._filters:
            stmt = stmt.where(and_(*self._filters))
        
        # Aplica exclusões
        if self._excludes:
            stmt = stmt.where(not_(or_(*self._excludes)))
        
        result = await session.execute(stmt)
        return result.rowcount
    
    async def update(self, **kwargs: Any) -> int:
        """
        Atualiza todos os registros que correspondem à query.
        
        Returns:
            Número de registros atualizados
        """
        from sqlalchemy import update as sql_update
        
        session = self._get_session()
        stmt = sql_update(self._model_class).values(**kwargs)
        
        # Aplica filtros
        if self._filters:
            stmt = stmt.where(and_(*self._filters))
        
        # Aplica exclusões
        if self._excludes:
            stmt = stmt.where(not_(or_(*self._excludes)))
        
        result = await session.execute(stmt)
        return result.rowcount
    
    # Métodos de agregação
    async def aggregate(self, **kwargs: Any) -> dict[str, Any]:
        """
        Executa funções de agregação.
        
        As funções recebem nomes de campos como string e resolvem
        automaticamente para colunas SQLAlchemy do modelo.
        
        Exemplo:
            from stride.querysets import Count, Sum, Avg, Max, Min
            
            result = await User.objects.using(session).aggregate(
                total=Count("id"),
                avg_age=Avg("age"),
            )
            # {"total": 42, "avg_age": 28.5}
        """
        session = self._get_session()
        
        # Constrói as expressões de agregação
        agg_exprs = []
        labels = []
        
        for label, expr in kwargs.items():
            # Resolve a coluna do modelo para a expressão de agregação
            resolved = expr.resolve(self._model_class)
            agg_exprs.append(resolved.label(label))
            labels.append(label)
        
        stmt = select(*agg_exprs).select_from(self._model_class)
        
        # Aplica filtros
        if self._filters:
            stmt = stmt.where(and_(*self._filters))
        
        # Aplica exclusões
        if self._excludes:
            stmt = stmt.where(not_(or_(*self._excludes)))
        
        result = await session.execute(stmt)
        row = result.first()
        
        if row is None:
            return {label: None for label in labels}
        
        return dict(zip(labels, row))
    
    # Iteração async
    async def __aiter__(self):
        """Permite iteração async sobre os resultados."""
        results = await self.all()
        for item in results:
            yield item


# Funções de agregação
class Count:
    """
    Função de agregação COUNT.
    
    Uso:
        Count("*")   -> COUNT(*)
        Count("id")  -> COUNT(model.id)
    """
    
    def __init__(self, field: str = "*"):
        self.field = field
    
    def resolve(self, model_class: type) -> Any:
        """Resolve o campo para expressão SQLAlchemy."""
        if self.field == "*":
            return func.count()
        column = getattr(model_class, self.field)
        return func.count(column)


class Sum:
    """
    Função de agregação SUM.
    
    Uso:
        Sum("price")  -> SUM(model.price)
    """
    
    def __init__(self, field: str):
        self.field = field
    
    def resolve(self, model_class: type) -> Any:
        """Resolve o campo para expressão SQLAlchemy."""
        column = getattr(model_class, self.field)
        return func.sum(column)


class Avg:
    """
    Função de agregação AVG.
    
    Uso:
        Avg("price")  -> AVG(model.price)
    """
    
    def __init__(self, field: str):
        self.field = field
    
    def resolve(self, model_class: type) -> Any:
        """Resolve o campo para expressão SQLAlchemy."""
        column = getattr(model_class, self.field)
        return func.avg(column)


class Max:
    """
    Função de agregação MAX.
    
    Uso:
        Max("price")  -> MAX(model.price)
    """
    
    def __init__(self, field: str):
        self.field = field
    
    def resolve(self, model_class: type) -> Any:
        """Resolve o campo para expressão SQLAlchemy."""
        column = getattr(model_class, self.field)
        return func.max(column)


class Min:
    """
    Função de agregação MIN.
    
    Uso:
        Min("price")  -> MIN(model.price)
    """
    
    def __init__(self, field: str):
        self.field = field
    
    def resolve(self, model_class: type) -> Any:
        """Resolve o campo para expressão SQLAlchemy."""
        column = getattr(model_class, self.field)
        return func.min(column)


# =============================================================================
# Soft Delete QuerySet
# =============================================================================

def _get_soft_delete_field() -> str:
    """Return soft delete field name from settings."""
    try:
        from stride.config import get_settings
        return get_settings().soft_delete_field
    except Exception:
        return "deleted_at"


class SoftDeleteQuerySet[T: "Model"](QuerySet[T]):
    """
    QuerySet that filters deleted records automatically.

    Excludes records where deleted_at is not NULL by default.
    """
    # users = await User.objects.using(db).all()  # Only active
    # users = await User.objects.using(db).with_deleted().all()  # All

    def __init__(
        self,
        model_class: type[T],
        session: AsyncSession | None = None,
        deleted_field: str | None = None,
    ) -> None:
        """
        Initialize with model and optional field override.

        Uses settings.soft_delete_field if not specified.
        """
        super().__init__(model_class, session)
        self._deleted_field = deleted_field or _get_soft_delete_field()
        self._include_deleted = False
        self._only_deleted = False

    def _clone(self) -> "SoftDeleteQuerySet[T]":
        """Create copy preserving soft delete configuration."""
        qs = SoftDeleteQuerySet(
            self._model_class,
            self._session,
            self._deleted_field,
        )
        qs._filters = self._filters.copy()
        qs._excludes = self._excludes.copy()
        qs._order_by = self._order_by.copy()
        qs._limit_value = self._limit_value
        qs._offset_value = self._offset_value
        qs._select_related = self._select_related.copy()
        qs._prefetch_related = self._prefetch_related.copy()
        qs._include_deleted = self._include_deleted
        qs._only_deleted = self._only_deleted
        return qs

    def _build_query(self) -> Select:
        """Build query with soft delete filter applied."""
        stmt = super()._build_query()

        deleted_col = getattr(self._model_class, self._deleted_field, None)

        if deleted_col is not None:
            if self._only_deleted:
                stmt = stmt.where(deleted_col.is_not(None))
            elif not self._include_deleted:
                stmt = stmt.where(deleted_col.is_(None))

        return stmt

    def with_deleted(self) -> "SoftDeleteQuerySet[T]":
        """
        Include deleted records in results.

        Returns QuerySet with both active and deleted records.
        """
        # users = await User.objects.using(db).with_deleted().all()
        qs = self._clone()
        qs._include_deleted = True
        qs._only_deleted = False
        return qs

    def only_deleted(self) -> "SoftDeleteQuerySet[T]":
        """
        Return only deleted records.

        Filters to records where deleted_at is not NULL.
        """
        # deleted = await User.objects.using(db).only_deleted().all()
        qs = self._clone()
        qs._include_deleted = True
        qs._only_deleted = True
        return qs

    def active(self) -> "SoftDeleteQuerySet[T]":
        """
        Return only active records explicitly.

        Default behavior, useful for code clarity.
        """
        # active = await User.objects.using(db).active().all()
        qs = self._clone()
        qs._include_deleted = False
        qs._only_deleted = False
        return qs


# =============================================================================
# Tenant-Aware QuerySet
# =============================================================================

def _get_tenant_field() -> str:
    """Return tenant field name from settings."""
    try:
        from stride.config import get_settings
        return get_settings().tenancy_field
    except Exception:
        return "workspace_id"


class TenantQuerySet[T: "Model"](QuerySet[T]):
    """
    QuerySet with multi-tenancy filtering support.

    Adds for_tenant() method for automatic tenant filtering.
    """
    # domains = await Domain.objects.using(db).for_tenant().all()

    def __init__(
        self,
        model_class: type[T],
        session: AsyncSession | None = None,
        tenant_field: str | None = None,
    ) -> None:
        """
        Initialize with model and optional field override.

        Uses settings.tenancy_field if not specified.
        """
        super().__init__(model_class, session)
        self._tenant_field = tenant_field or _get_tenant_field()

    def _clone(self) -> "TenantQuerySet[T]":
        """Create copy preserving tenant configuration."""
        qs = TenantQuerySet(
            self._model_class,
            self._session,
            self._tenant_field,
        )
        qs._filters = self._filters.copy()
        qs._excludes = self._excludes.copy()
        qs._order_by = self._order_by.copy()
        qs._limit_value = self._limit_value
        qs._offset_value = self._offset_value
        qs._select_related = self._select_related.copy()
        qs._prefetch_related = self._prefetch_related.copy()
        return qs

    def for_tenant(
        self,
        tenant_id: Any | None = None,
        tenant_field: str | None = None,
    ) -> "TenantQuerySet[T]":
        """
        Filter by current or specified tenant.

        Uses context tenant if tenant_id not provided.
        """
        # items = await Item.objects.using(db).for_tenant().all()
        from stride.tenancy import get_tenant, require_tenant

        field = tenant_field or self._tenant_field

        if tenant_id is None:
            tenant_id = require_tenant()

        return self.filter(**{field: tenant_id})


# =============================================================================
# Combined QuerySet (Soft Delete + Tenant)
# =============================================================================

class TenantSoftDeleteQuerySet[T: "Model"](SoftDeleteQuerySet[T]):
    """
    QuerySet combining soft delete and multi-tenancy.

    Inherits soft delete filtering and adds tenant support.
    """
    # items = await Item.objects.using(db).for_tenant().all()
    # items = await Item.objects.using(db).for_tenant().with_deleted().all()

    def __init__(
        self,
        model_class: type[T],
        session: AsyncSession | None = None,
        deleted_field: str | None = None,
        tenant_field: str | None = None,
    ) -> None:
        """
        Initialize with model and optional field overrides.

        Uses settings for field names if not specified.
        """
        super().__init__(model_class, session, deleted_field)
        self._tenant_field = tenant_field or _get_tenant_field()

    def _clone(self) -> "TenantSoftDeleteQuerySet[T]":
        """Create copy preserving all configuration."""
        qs = TenantSoftDeleteQuerySet(
            self._model_class,
            self._session,
            self._deleted_field,
            self._tenant_field,
        )
        qs._filters = self._filters.copy()
        qs._excludes = self._excludes.copy()
        qs._order_by = self._order_by.copy()
        qs._limit_value = self._limit_value
        qs._offset_value = self._offset_value
        qs._select_related = self._select_related.copy()
        qs._prefetch_related = self._prefetch_related.copy()
        qs._include_deleted = self._include_deleted
        qs._only_deleted = self._only_deleted
        return qs

    def for_tenant(
        self,
        tenant_id: Any | None = None,
        tenant_field: str | None = None,
    ) -> "TenantSoftDeleteQuerySet[T]":
        """
        Filter by current or specified tenant.

        Uses context tenant if tenant_id not provided.
        """
        # items = await Item.objects.using(db).for_tenant().all()
        from stride.tenancy import require_tenant

        field = tenant_field or self._tenant_field

        if tenant_id is None:
            tenant_id = require_tenant()

        return self.filter(**{field: tenant_id})
