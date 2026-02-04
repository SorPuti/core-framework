"""Estado do schema do banco de dados."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from sqlalchemy import inspect, Integer, String, Boolean, DateTime, Float, Text
from sqlalchemy.orm import Mapped

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection
    from core.models import Model


# Tipos equivalentes entre dialetos (para comparação)
# O valor do modelo e o valor do banco devem ser considerados iguais
EQUIVALENT_TYPES: dict[str, set[str]] = {
    "DATETIME": {"DATETIME", "TIMESTAMP", "TIMESTAMP WITH TIME ZONE", "TIMESTAMP WITHOUT TIME ZONE"},
    "TIMESTAMP": {"DATETIME", "TIMESTAMP", "TIMESTAMP WITH TIME ZONE", "TIMESTAMP WITHOUT TIME ZONE"},
    "TIMESTAMP WITH TIME ZONE": {"DATETIME", "TIMESTAMP", "TIMESTAMP WITH TIME ZONE"},
    "TIMESTAMP WITHOUT TIME ZONE": {"DATETIME", "TIMESTAMP", "TIMESTAMP WITHOUT TIME ZONE"},
    "BOOLEAN": {"BOOLEAN", "BOOL", "TINYINT(1)", "TINYINT"},
    "BOOL": {"BOOLEAN", "BOOL"},
    "JSON": {"JSON", "JSONB", "ADAPTIVEJSON"},
    "JSONB": {"JSON", "JSONB", "ADAPTIVEJSON"},
    "ADAPTIVEJSON": {"JSON", "JSONB", "ADAPTIVEJSON"},
    "TEXT": {"TEXT", "LONGTEXT", "MEDIUMTEXT"},
    "LONGTEXT": {"TEXT", "LONGTEXT"},
    "UUID": {"UUID", "TEXT", "CHAR(36)", "VARCHAR(36)"},
    "DOUBLE": {"DOUBLE", "DOUBLE PRECISION", "FLOAT8"},
    "DOUBLE PRECISION": {"DOUBLE", "DOUBLE PRECISION", "FLOAT8"},
    "INTEGER": {"INTEGER", "INT", "INT4", "SERIAL"},
    "BIGINT": {"BIGINT", "INT8", "BIGSERIAL"},
    "SMALLINT": {"SMALLINT", "INT2", "TINYINT"},
}


def types_are_equivalent(type1: str, type2: str) -> bool:
    """Check if two SQL types are equivalent across dialects."""
    if type1 == type2:
        return True
    
    # Normalize: extract base type (remove size like VARCHAR(255))
    base1 = type1.split("(")[0].upper().strip()
    base2 = type2.split("(")[0].upper().strip()
    
    if base1 == base2:
        return True
    
    # Check equivalence mapping
    equiv1 = EQUIVALENT_TYPES.get(base1, {base1})
    equiv2 = EQUIVALENT_TYPES.get(base2, {base2})
    
    return bool(equiv1 & equiv2)


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
            and types_are_equivalent(self.type, other.type)
            and self.nullable == other.nullable
            and self.primary_key == other.primary_key
        )
    
    def diff(self, other: "ColumnState") -> dict[str, tuple[Any, Any]]:
        """Retorna diferenças entre dois estados."""
        diffs = {}
        # Use type equivalence check instead of direct comparison
        if not types_are_equivalent(self.type, other.type):
            diffs["type"] = (self.type, other.type)
        if self.nullable != other.nullable:
            diffs["nullable"] = (self.nullable, other.nullable)
        # Skip default comparison for callable defaults (handled by ORM)
        if self.default != other.default and not callable(self.default) and not callable(other.default):
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
class EnumState:
    """Estado de um tipo ENUM."""
    
    name: str
    values: list[str] = field(default_factory=list)
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EnumState):
            return False
        return self.name == other.name and set(self.values) == set(other.values)
    
    def diff(self, other: "EnumState") -> dict[str, Any]:
        """Retorna diferenças entre dois estados de enum."""
        diffs = {}
        old_values = set(self.values)
        new_values = set(other.values)
        
        added = new_values - old_values
        removed = old_values - new_values
        
        if added:
            diffs["added"] = list(added)
        if removed:
            diffs["removed"] = list(removed)
        
        return diffs


@dataclass
class SchemaState:
    """Estado completo do schema."""
    
    tables: dict[str, TableState] = field(default_factory=dict)
    enums: dict[str, EnumState] = field(default_factory=dict)
    
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
    
    # Enums
    enums_to_create: list[EnumState] = field(default_factory=list)
    enums_to_drop: list[str] = field(default_factory=list)
    enums_to_alter: list[tuple[EnumState, EnumState]] = field(default_factory=list)
    
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
        
        # Enums
        old_enums = set(old.enums.keys())
        new_enums = set(new.enums.keys())
        
        # Enums novos
        for enum_name in new_enums - old_enums:
            diff.enums_to_create.append(new.enums[enum_name])
        
        # Enums removidos
        for enum_name in old_enums - new_enums:
            diff.enums_to_drop.append(enum_name)
        
        # Enums alterados
        for enum_name in old_enums & new_enums:
            old_enum = old.enums[enum_name]
            new_enum = new.enums[enum_name]
            if old_enum != new_enum:
                diff.enums_to_alter.append((old_enum, new_enum))
        
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
            or self.enums_to_create
            or self.enums_to_drop
            or self.enums_to_alter
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


def _extract_enum_from_model(model_class: type["Model"]) -> dict[str, EnumState]:
    """
    Extrai enums definidos em um Model.
    
    Detecta campos que usam TextChoices ou IntegerChoices e extrai
    seus valores para criar tipos ENUM no banco.
    """
    enums = {}
    
    # Procura por atributos que são classes de Choices
    for attr_name in dir(model_class):
        if attr_name.startswith("_"):
            continue
        
        try:
            attr = getattr(model_class, attr_name)
            
            # Verifica se é uma classe de Choices
            if isinstance(attr, type):
                # Importa aqui para evitar circular import
                try:
                    from core.choices import Choices
                    if issubclass(attr, Choices) and attr is not Choices:
                        # Gera nome do enum baseado no model e campo
                        enum_name = f"{model_class.__tablename__}_{attr_name.lower()}"
                        enums[enum_name] = EnumState(
                            name=enum_name,
                            values=list(attr.values),
                        )
                except (ImportError, TypeError):
                    pass
        except Exception:
            pass
    
    return enums


def _extract_enums_from_annotations(model_class: type["Model"]) -> dict[str, EnumState]:
    """
    Extrai enums de campos que usam Field.choice().
    
    Analisa os campos do model para encontrar aqueles que referenciam
    classes de Choices.
    """
    enums = {}
    
    # Verifica se o model tem __enum_fields__ definido
    # Isso é setado pelo Field.choice() quando use_native_enum=True
    enum_fields = getattr(model_class, "__enum_fields__", {})
    
    for field_name, choices_class in enum_fields.items():
        try:
            from core.choices import Choices
            if issubclass(choices_class, Choices):
                enum_name = f"{model_class.__tablename__}_{field_name}"
                enums[enum_name] = EnumState(
                    name=enum_name,
                    values=list(choices_class.values),
                )
        except (ImportError, TypeError):
            pass
    
    return enums


def models_to_schema_state(models: list[type["Model"]]) -> SchemaState:
    """Extrai estado do schema de uma lista de Models."""
    state = SchemaState()
    
    for model in models:
        if hasattr(model, "__table__"):
            table_state = model_to_table_state(model)
            state.tables[table_state.name] = table_state
            
            # Extrai enums do model
            model_enums = _extract_enums_from_annotations(model)
            state.enums.update(model_enums)
    
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
