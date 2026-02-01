"""
Estado do schema do banco de dados.

Usado para detectar mudanças entre o estado atual dos models
e o estado do banco de dados.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from sqlalchemy import inspect, Integer, String, Boolean, DateTime, Float, Text
from sqlalchemy.orm import Mapped

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection
    from core.models import Model


@dataclass
class ColumnState:
    """Estado de uma coluna."""
    
    name: str
    type: str
    nullable: bool = True
    default: Any = None
    primary_key: bool = False
    autoincrement: bool = False
    unique: bool = False
    index: bool = False
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ColumnState):
            return False
        return (
            self.name == other.name
            and self.type == other.type
            and self.nullable == other.nullable
            and self.primary_key == other.primary_key
        )
    
    def diff(self, other: "ColumnState") -> dict[str, tuple[Any, Any]]:
        """Retorna diferenças entre dois estados."""
        diffs = {}
        if self.type != other.type:
            diffs["type"] = (self.type, other.type)
        if self.nullable != other.nullable:
            diffs["nullable"] = (self.nullable, other.nullable)
        if self.default != other.default:
            diffs["default"] = (self.default, other.default)
        if self.unique != other.unique:
            diffs["unique"] = (self.unique, other.unique)
        return diffs


@dataclass
class ForeignKeyState:
    """Estado de uma chave estrangeira."""
    
    column: str
    references_table: str
    references_column: str = "id"
    on_delete: str = "CASCADE"


@dataclass
class IndexState:
    """Estado de um índice."""
    
    name: str
    columns: list[str]
    unique: bool = False


@dataclass
class TableState:
    """Estado de uma tabela."""
    
    name: str
    columns: dict[str, ColumnState] = field(default_factory=dict)
    foreign_keys: list[ForeignKeyState] = field(default_factory=list)
    indexes: list[IndexState] = field(default_factory=list)
    
    def get_primary_key(self) -> ColumnState | None:
        """Retorna a coluna de chave primária."""
        for col in self.columns.values():
            if col.primary_key:
                return col
        return None


@dataclass
class SchemaState:
    """Estado completo do schema."""
    
    tables: dict[str, TableState] = field(default_factory=dict)
    
    def diff(self, other: "SchemaState") -> "SchemaDiff":
        """Calcula diferenças entre dois estados."""
        return SchemaDiff.from_states(self, other)


@dataclass
class SchemaDiff:
    """Diferenças entre dois estados de schema."""
    
    # Tabelas
    tables_to_create: list[TableState] = field(default_factory=list)
    tables_to_drop: list[str] = field(default_factory=list)
    
    # Colunas
    columns_to_add: dict[str, list[ColumnState]] = field(default_factory=dict)
    columns_to_drop: dict[str, list[str]] = field(default_factory=dict)
    columns_to_alter: dict[str, list[tuple[ColumnState, ColumnState]]] = field(default_factory=dict)
    
    # Índices
    indexes_to_create: dict[str, list[IndexState]] = field(default_factory=dict)
    indexes_to_drop: dict[str, list[str]] = field(default_factory=dict)
    
    @classmethod
    def from_states(cls, old: SchemaState, new: SchemaState) -> "SchemaDiff":
        """Cria diff a partir de dois estados."""
        diff = cls()
        
        old_tables = set(old.tables.keys())
        new_tables = set(new.tables.keys())
        
        # Tabelas novas
        for table_name in new_tables - old_tables:
            diff.tables_to_create.append(new.tables[table_name])
        
        # Tabelas removidas
        for table_name in old_tables - new_tables:
            diff.tables_to_drop.append(table_name)
        
        # Tabelas existentes - verificar colunas
        for table_name in old_tables & new_tables:
            old_table = old.tables[table_name]
            new_table = new.tables[table_name]
            
            old_cols = set(old_table.columns.keys())
            new_cols = set(new_table.columns.keys())
            
            # Colunas novas
            added = new_cols - old_cols
            if added:
                diff.columns_to_add[table_name] = [
                    new_table.columns[col] for col in added
                ]
            
            # Colunas removidas
            dropped = old_cols - new_cols
            if dropped:
                diff.columns_to_drop[table_name] = list(dropped)
            
            # Colunas alteradas
            for col_name in old_cols & new_cols:
                old_col = old_table.columns[col_name]
                new_col = new_table.columns[col_name]
                if old_col != new_col:
                    if table_name not in diff.columns_to_alter:
                        diff.columns_to_alter[table_name] = []
                    diff.columns_to_alter[table_name].append((old_col, new_col))
        
        return diff
    
    @property
    def has_changes(self) -> bool:
        """Verifica se há mudanças."""
        return bool(
            self.tables_to_create
            or self.tables_to_drop
            or self.columns_to_add
            or self.columns_to_drop
            or self.columns_to_alter
            or self.indexes_to_create
            or self.indexes_to_drop
        )


def get_sqlalchemy_type_string(sa_type: Any) -> str:
    """Converte tipo SQLAlchemy para string SQL."""
    type_name = type(sa_type).__name__
    
    if type_name == "Integer":
        return "INTEGER"
    elif type_name == "String":
        length = getattr(sa_type, "length", 255) or 255
        return f"VARCHAR({length})"
    elif type_name == "Text":
        return "TEXT"
    elif type_name == "Boolean":
        return "BOOLEAN"
    elif type_name == "DateTime":
        return "DATETIME"
    elif type_name == "Float":
        return "FLOAT"
    elif type_name == "Numeric":
        return "NUMERIC"
    else:
        return type_name.upper()


def model_to_table_state(model_class: type["Model"]) -> TableState:
    """Extrai estado de tabela de um Model."""
    table = model_class.__table__
    
    columns = {}
    for col in table.columns:
        # SQLAlchemy autoincrement pode ser True, False, ou "auto"
        # Convertemos para bool: True se for True ou "auto" com primary_key
        auto_inc = col.autoincrement
        if auto_inc == "auto":
            auto_inc = col.primary_key  # "auto" significa autoincrement se for PK
        else:
            auto_inc = bool(auto_inc)
        
        columns[col.name] = ColumnState(
            name=col.name,
            type=get_sqlalchemy_type_string(col.type),
            nullable=col.nullable,
            default=col.default.arg if col.default is not None else None,
            primary_key=col.primary_key,
            autoincrement=auto_inc,
            unique=col.unique if col.unique else False,
            index=col.index if col.index else False,
        )
    
    foreign_keys = []
    for fk in table.foreign_keys:
        foreign_keys.append(ForeignKeyState(
            column=fk.parent.name,
            references_table=fk.column.table.name,
            references_column=fk.column.name,
        ))
    
    indexes = []
    for idx in table.indexes:
        indexes.append(IndexState(
            name=idx.name,
            columns=[col.name for col in idx.columns],
            unique=idx.unique,
        ))
    
    return TableState(
        name=table.name,
        columns=columns,
        foreign_keys=foreign_keys,
        indexes=indexes,
    )


def models_to_schema_state(models: list[type["Model"]]) -> SchemaState:
    """Extrai estado do schema de uma lista de Models."""
    state = SchemaState()
    
    for model in models:
        if hasattr(model, "__table__"):
            table_state = model_to_table_state(model)
            state.tables[table_state.name] = table_state
    
    return state


# Tabelas internas do framework que devem ser ignoradas em migrações
# Estas tabelas são gerenciadas pelo Core Framework e não devem ser
# modificadas por makemigrations ou migrate
INTERNAL_TABLES = {
    # Sistema de migrações
    "_core_migrations",
    
    # SQLite interno
    "sqlite_sequence",
    
    # Sistema de autenticação (quando usando auth nativo)
    "auth_users",
    "auth_groups", 
    "auth_permissions",
    "auth_users_groups",
    "auth_users_permissions",
    "auth_group_permissions",
}

# Tabelas que NUNCA podem ser dropadas via migrate
# Só podem ser removidas via reset_db com confirmação
PROTECTED_TABLES = {
    "_core_migrations",
    "auth_users",
    "auth_groups",
    "auth_permissions",
    "auth_users_groups",
    "auth_users_permissions", 
    "auth_group_permissions",
}


async def get_database_schema_state(conn: "AsyncConnection") -> SchemaState:
    """Extrai estado atual do schema do banco de dados."""
    state = SchemaState()
    
    # Usa o inspector do SQLAlchemy
    def inspect_db(connection):
        inspector = inspect(connection)
        tables = {}
        
        for table_name in inspector.get_table_names():
            # Ignora tabelas internas do sistema
            if table_name in INTERNAL_TABLES:
                continue
            columns = {}
            for col in inspector.get_columns(table_name):
                columns[col["name"]] = ColumnState(
                    name=col["name"],
                    type=str(col["type"]),
                    nullable=col.get("nullable", True),
                    default=col.get("default"),
                    primary_key=col.get("primary_key", False),
                    autoincrement=col.get("autoincrement", False),
                )
            
            foreign_keys = []
            for fk in inspector.get_foreign_keys(table_name):
                if fk.get("constrained_columns"):
                    foreign_keys.append(ForeignKeyState(
                        column=fk["constrained_columns"][0],
                        references_table=fk["referred_table"],
                        references_column=fk["referred_columns"][0] if fk.get("referred_columns") else "id",
                    ))
            
            indexes = []
            for idx in inspector.get_indexes(table_name):
                indexes.append(IndexState(
                    name=idx["name"],
                    columns=idx["column_names"],
                    unique=idx.get("unique", False),
                ))
            
            tables[table_name] = TableState(
                name=table_name,
                columns=columns,
                foreign_keys=foreign_keys,
                indexes=indexes,
            )
        
        return tables
    
    tables = await conn.run_sync(inspect_db)
    state.tables = tables
    
    return state
