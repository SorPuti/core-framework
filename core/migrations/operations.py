"""Migration operations."""
from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, ClassVar, TYPE_CHECKING
from collections.abc import Awaitable

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection
    from core.migrations.dialects.base import DialectCompiler


def fingerprint(operations: list[Operation]) -> str:
    """Generate fingersprint for migrations"""
    payload = json.dumps(
        sorted(
            (op.to_fingerprint() for op in operations),
            key=lambda o: (o["op"], json.dumps(o, sort_keys=True))
        ),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()

# =============================================================================
# Compiler helper
# =============================================================================

def _get_compiler(dialect: str) -> "DialectCompiler":
    """Get the dialect compiler — thin wrapper to keep imports lazy."""
    from core.migrations.dialects import get_compiler
    return get_compiler(dialect)


# =============================================================================
# Serialization
# =============================================================================

# Global registry for imports needed during serialization
_SERIALIZATION_IMPORTS: set[str] = set()


def _serialize_default(value: Any) -> str:
    """Serialize default value for migration file."""
    from datetime import datetime, date, time
    
    if value is None:
        return "None"
    
    if callable(value):
        module = getattr(value, "__module__", "")
        qualname = getattr(value, "__qualname__", "") or getattr(value, "__name__", "")
        
        # Non-importable: closures, lambdas, __main__ -> execute and serialize result
        if "<locals>" in qualname or "<lambda>" in qualname or module == "__main__":
            try:
                return _serialize_default(value())
            except TypeError:
                try:
                    return _serialize_default(value(None))
                except Exception:
                    return "None"
            except Exception:
                return "None"
        
        # Importable function: register import and return short name
        if module and qualname:
            # Get the top-level name to import
            top_name = qualname.split(".")[0]
            _SERIALIZATION_IMPORTS.add(f"from {module} import {top_name}")
            return qualname
        
        # Fallback: execute and serialize result
        try:
            return _serialize_default(value())
        except Exception:
            return "None"
    
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (datetime, date, time)):
        return "None"
    if isinstance(value, str):
        return repr(value)
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        return "{}" if not value else repr(value)
    if isinstance(value, list):
        return "[]" if not value else repr(value)
    return repr(value)


def get_serialization_imports() -> list[str]:
    """Get and clear the imports collected during serialization."""
    global _SERIALIZATION_IMPORTS
    imports = sorted(_SERIALIZATION_IMPORTS)
    _SERIALIZATION_IMPORTS = set()
    return imports


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ColumnDef:
    """Column definition."""
    name: str
    type: str
    nullable: bool = True
    default: Any = None
    primary_key: bool = False
    autoincrement: bool = False
    unique: bool = False
    index: bool = False

    def to_fingerprint(self) -> dict:
        """Generate fingersprin from object."""
        default = self.default

        if callable(default):
            default_repr = getattr(default, "__name__", repr(default))
        else:
            default_repr = default

        return {
            "name": self.name,
            "type": self.type,
            "nullable": self.nullable,
            "primary_key": self.primary_key,
            "autoincrement": self.autoincrement,
            "unique": self.unique,
            "index": self.index,
            "default": default_repr,
        }

    def get_type(self, dialect: str) -> str:
        compiler = _get_compiler(dialect)
        return compiler.map_type(self.type)
    
    def get_default_sql(self, dialect: str) -> str | None:
        if self.default is None:
            return None
        compiler = _get_compiler(dialect)
        if callable(self.default):
            try:
                result = self.default()
            except TypeError:
                try:
                    result = self.default(None)
                except Exception:
                    return None
            except Exception:
                return None
            return compiler.format_default(result)
        return compiler.format_default(self.default)
    
    def to_sql(self, dialect: str = "sqlite", *, include_pk: bool = True) -> str:
        """Generate SQL for column definition.
        
        Delegates to the dialect compiler for correct, dialect-specific SQL.
        
        Args:
            dialect: Database dialect
            include_pk: If False, skip PRIMARY KEY clause (for composite PKs)
        """
        compiler = _get_compiler(dialect)
        
        # Resolve callable defaults to their values for SQL generation
        default_value = self.default
        if callable(default_value):
            try:
                default_value = default_value()
            except TypeError:
                try:
                    default_value = default_value(None)
                except Exception:
                    default_value = None
            except Exception:
                default_value = None
        
        return compiler.column_to_sql(
            name=self.name,
            col_type=self.type,
            nullable=self.nullable,
            default=default_value,
            primary_key=self.primary_key,
            autoincrement=self.autoincrement,
            unique=self.unique,
            include_pk=include_pk,
        )


@dataclass
class ForeignKeyDef:
    """Foreign key definition."""
    column: str
    references_table: str
    references_column: str = "id"
    on_delete: str = "CASCADE"
    on_update: str = "CASCADE"
    
    def to_fingerprint(self) -> dict:
        """Generate fingersprin from object."""
        return {
            "column": self.column,
            "references_table": self.references_table,
            "references_column": self.references_column,
            "on_delete": self.on_delete,
            "on_update": self.on_update,
        }

    def to_sql(self, table_name: str) -> str:
        return (
            f'FOREIGN KEY ("{self.column}") '
            f'REFERENCES "{self.references_table}" ("{self.references_column}") '
            f"ON DELETE {self.on_delete} ON UPDATE {self.on_update}"
        )




# =============================================================================
# Base Operation
# =============================================================================

class Operation(ABC):
    """Base migration operation."""
    destructive: bool = False
    reversible: bool = True

    @abstractmethod
    def to_fingerprint(self) -> dict | None:
        """Stable, semantic representation for hashing."""

    @abstractmethod
    async def forward(self, conn: "AsyncConnection", dialect: str) -> None: ...

    @abstractmethod
    async def backward(self, conn: "AsyncConnection", dialect: str) -> None: ...

    @abstractmethod
    def describe(self) -> str: ...

    def to_code(self) -> str:
        return repr(self)


# =============================================================================
# Table Operations
# =============================================================================

@dataclass
class CreateTable(Operation):
    """Create a new table."""
    table_name: str
    columns: list[ColumnDef] = field(default_factory=list)
    foreign_keys: list[ForeignKeyDef] = field(default_factory=list)

    def to_fingerprint(self) -> dict:
        """Generate fingersprin from object."""
        return {
            "op": "CreateTable",
            "table": self.table_name,
            "columns": [
                col.to_fingerprint() for col in self.columns
            ],
            "foreign_keys": [
                fk.to_fingerprint() for fk in self.foreign_keys
            ],
        }

    async def forward(self, conn: "AsyncConnection", dialect: str) -> None:
        # Detect composite primary key
        pk_columns = [c for c in self.columns if c.primary_key]
        is_composite_pk = len(pk_columns) > 1
        
        # Generate column definitions
        col_defs = []
        for c in self.columns:
            # For composite PK, don't include PRIMARY KEY in column def
            col_sql = c.to_sql(dialect, include_pk=not is_composite_pk)
            col_defs.append(col_sql)
        
        parts = col_defs.copy()
        
        # Add composite PRIMARY KEY constraint if needed
        if is_composite_pk:
            pk_names = ", ".join(f'"{c.name}"' for c in pk_columns)
            parts.append(f"PRIMARY KEY ({pk_names})")
        
        # Add foreign keys
        if self.foreign_keys:
            for fk in self.foreign_keys:
                parts.append(fk.to_sql(self.table_name))
        
        cols = ",\n    ".join(parts)
        sql = f'CREATE TABLE IF NOT EXISTS "{self.table_name}" (\n    {cols}\n)'
        await conn.execute(text(sql))
    
    async def backward(self, conn: "AsyncConnection", dialect: str) -> None:
        await conn.execute(text(f'DROP TABLE IF EXISTS "{self.table_name}"'))
    
    def describe(self) -> str:
        return f"Create table '{self.table_name}'"
    
    def to_code(self) -> str:
        cols = ",\n            ".join(
            f"ColumnDef(name='{c.name}', type='{c.type}', nullable={c.nullable}, "
            f"default={_serialize_default(c.default)}, primary_key={c.primary_key}, "
            f"autoincrement={c.autoincrement}, unique={c.unique})"
            for c in self.columns
        )
        fks = ",\n            ".join(
            f"ForeignKeyDef(column='{fk.column}', references_table='{fk.references_table}', "
            f"references_column='{fk.references_column}', on_delete='{fk.on_delete}')"
            for fk in self.foreign_keys
        )
        return f"""CreateTable(
        table_name='{self.table_name}',
        columns=[
            {cols}
        ],
        foreign_keys=[
            {fks}
        ] if {bool(self.foreign_keys)} else [],
    )"""


@dataclass
class DropTable(Operation):
    """Drop a table."""
    table_name: str
    destructive: bool = True
    columns: list[ColumnDef] = field(default_factory=list)
    foreign_keys: list[ForeignKeyDef] = field(default_factory=list)
    
    def to_fingerprint(self) -> dict:
        """Generate fingersprin from object."""
        return {
            "op": "CreateTable",
            "table": self.table_name,
            "columns": [
                col.to_fingerprint() for col in self.columns
            ],
            "foreign_keys": [
                fk.to_fingerprint() for fk in self.foreign_keys
            ],
        }

    async def forward(self, conn: "AsyncConnection", dialect: str) -> None:
        await conn.execute(text(f'DROP TABLE IF EXISTS "{self.table_name}"'))
    
    async def backward(self, conn: "AsyncConnection", dialect: str) -> None:
        if not self.columns:
            raise RuntimeError(f"Cannot reverse DropTable '{self.table_name}': no columns")
        await CreateTable(self.table_name, self.columns, self.foreign_keys).forward(conn, dialect)
    
    def describe(self) -> str:
        return f"Drop table '{self.table_name}'"


# =============================================================================
# Column Operations
# =============================================================================

@dataclass
class AddColumn(Operation):
    """Add a column to a table."""
    table_name: str
    column: ColumnDef

    def to_fingerprint(self) -> dict:
        """Generate fingersprin from object."""
        return {
            "op": "CreateTable",
            "table": self.table_name,
            "columns": [self.column.to_fingerprint() if self.column else None],
        }

    async def forward(self, conn: "AsyncConnection", dialect: str) -> None:
        sql = f'ALTER TABLE "{self.table_name}" ADD COLUMN {self.column.to_sql(dialect)}'
        await conn.execute(text(sql))
    
    async def backward(self, conn: "AsyncConnection", dialect: str) -> None:
        await DropColumn(self.table_name, self.column.name).forward(conn, dialect)
    
    def describe(self) -> str:
        return f"Add column '{self.column.name}' to '{self.table_name}'"
    
    def to_code(self) -> str:
        c = self.column
        return f"""AddColumn(
        table_name='{self.table_name}',
        column=ColumnDef(
            name='{c.name}', type='{c.type}', nullable={c.nullable},
            default={_serialize_default(c.default)}, primary_key={c.primary_key},
            autoincrement={c.autoincrement}, unique={c.unique}
        ),
    )"""


@dataclass
class DropColumn(Operation):
    """Drop a column from a table."""
    table_name: str
    column_name: str
    destructive: bool = True
    column_def: ColumnDef | None = None
    
    def to_fingerprint(self) -> dict:
        """Generate fingersprin from object."""
        return {
            "op": "CreateTable",
            "table": self.table_name,
            "columns": [self.column_def.to_fingerprint() if self.column_def else None],
        }

    async def forward(self, conn: "AsyncConnection", dialect: str) -> None:
        await conn.execute(text(f'ALTER TABLE "{self.table_name}" DROP COLUMN "{self.column_name}"'))
    
    async def backward(self, conn: "AsyncConnection", dialect: str) -> None:
        if not self.column_def:
            raise RuntimeError(f"Cannot reverse DropColumn '{self.column_name}': no definition")
        await AddColumn(self.table_name, self.column_def).forward(conn, dialect)
    
    def describe(self) -> str:
        return f"Drop column '{self.column_name}' from '{self.table_name}'"


@dataclass
class AlterColumn(Operation):
    """Alter a column."""
    table_name: str
    column_name: str
    new_type: str | None = None
    new_nullable: bool | None = None
    new_default: Any = None
    set_default: bool = False
    old_type: str | None = None
    old_nullable: bool | None = None
    old_default: Any = None

    def to_fingerprint(self) -> dict:
        """Generate fingersprin from object."""
        def normalize_default(val):
            if callable(val):
                return getattr(val, "__name__", repr(val))
            return val

        return {
            "op": "AlterColumn",
            "table": self.table_name,
            "column": self.column_name,

            "new": {
                "type": self.new_type,
                "nullable": self.new_nullable,
                "default": normalize_default(self.new_default) if self.set_default else None,
                "set_default": self.set_default,
            },

            "old": {
                "type": self.old_type,
                "nullable": self.old_nullable,
                "default": normalize_default(self.old_default) if self.set_default else None,
            },
        }

    async def forward(self, conn: "AsyncConnection", dialect: str) -> None:
        compiler = _get_compiler(dialect)
        if not compiler.supports_alter_column:
            raise NotImplementedError(
                f"{compiler.display_name} does not support ALTER COLUMN. "
                f"Consider recreating the table instead."
            )
        
        for alt in self._build_alterations(dialect):
            await conn.execute(text(f'ALTER TABLE "{self.table_name}" {alt}'))
    
    def _build_alterations(self, dialect: str) -> list[str]:
        compiler = _get_compiler(dialect)
        alts = []
        if self.new_type:
            mapped = compiler.map_type(self.new_type)
            alts.append(f'ALTER COLUMN "{self.column_name}" TYPE {mapped}')
        if self.new_nullable is not None:
            if self.new_nullable:
                alts.append(f'ALTER COLUMN "{self.column_name}" DROP NOT NULL')
            else:
                alts.append(f'ALTER COLUMN "{self.column_name}" SET NOT NULL')
        if self.set_default:
            if self.new_default is None:
                alts.append(f'ALTER COLUMN "{self.column_name}" DROP DEFAULT')
            else:
                default_sql = compiler.format_default(
                    self.new_default() if callable(self.new_default) else self.new_default,
                )
                if default_sql:
                    alts.append(f'ALTER COLUMN "{self.column_name}" SET {default_sql}')
        return alts
    
    async def backward(self, conn: "AsyncConnection", dialect: str) -> None:
        await AlterColumn(
            self.table_name, self.column_name,
            self.old_type, self.old_nullable, self.old_default, self.set_default
        ).forward(conn, dialect)
    
    def describe(self) -> str:
        changes = []
        if self.new_type:
            changes.append(f"type={self.new_type}")
        if self.new_nullable is not None:
            changes.append(f"nullable={self.new_nullable}")
        if self.set_default:
            changes.append(f"default={self.new_default}")
        return f"Alter '{self.column_name}' in '{self.table_name}': {', '.join(changes)}"
    
    def to_code(self) -> str:
        return f"""AlterColumn(
        table_name='{self.table_name}',
        column_name='{self.column_name}',
        new_type={repr(self.new_type)},
        new_nullable={self.new_nullable},
        new_default={_serialize_default(self.new_default)},
        set_default={self.set_default},
        old_type={repr(self.old_type)},
        old_nullable={self.old_nullable},
        old_default={_serialize_default(self.old_default)},
    )"""


@dataclass
class RenameColumn(Operation):
    """Rename a column."""
    table_name: str
    old_name: str
    new_name: str

    def to_fingerprint(self) -> dict:
        """Generate fingersprin from object."""
        return {
            "op": "RenameColumn",
            "table": self.table_name,
            "from": self.old_name,
            "to": self.new_name,
        }

    async def forward(self, conn: "AsyncConnection", dialect: str) -> None:
        sql = f'ALTER TABLE "{self.table_name}" RENAME COLUMN "{self.old_name}" TO "{self.new_name}"'
        await conn.execute(text(sql))
    
    async def backward(self, conn: "AsyncConnection", dialect: str) -> None:
        await RenameColumn(self.table_name, self.new_name, self.old_name).forward(conn, dialect)
    
    def describe(self) -> str:
        return f"Rename '{self.old_name}' to '{self.new_name}' in '{self.table_name}'"


# =============================================================================
# Index Operations
# =============================================================================

@dataclass
class CreateIndex(Operation):
    """Create an index."""
    table_name: str
    index_name: str
    columns: list[str]
    unique: bool = False

    def to_fingerprint(self) -> dict:
        """Generate fingersprin from object."""
        return {
            "op": "CreateIndex",
            "table": self.table_name,
            "name": self.index_name,
            "columns": list(self.columns),
            "unique": self.unique,
        }

    async def forward(self, conn: "AsyncConnection", dialect: str) -> None:
        unique = "UNIQUE " if self.unique else ""
        cols = ", ".join(f'"{c}"' for c in self.columns)
        sql = f'CREATE {unique}INDEX IF NOT EXISTS "{self.index_name}" ON "{self.table_name}" ({cols})'
        await conn.execute(text(sql))
    
    async def backward(self, conn: "AsyncConnection", dialect: str) -> None:
        await conn.execute(text(f'DROP INDEX IF EXISTS "{self.index_name}"'))
    
    def describe(self) -> str:
        return f"Create {'unique ' if self.unique else ''}index '{self.index_name}'"


@dataclass
class DropIndex(Operation):
    """Drop an index."""
    table_name: str
    index_name: str
    columns: list[str] = field(default_factory=list)
    unique: bool = False

    def to_fingerprint(self) -> dict:
        """Generate fingersprin from object."""
        return {
            "op": "DropIndex",
            "table": self.table_name,
            "name": self.index_name,
            "columns": list(self.columns),
            "unique": self.unique,
        }

    async def forward(self, conn: "AsyncConnection", dialect: str) -> None:
        await conn.execute(text(f'DROP INDEX IF EXISTS "{self.index_name}"'))
    
    async def backward(self, conn: "AsyncConnection", dialect: str) -> None:
        if not self.columns:
            raise RuntimeError(f"Cannot reverse DropIndex '{self.index_name}': no columns")
        await CreateIndex(self.table_name, self.index_name, self.columns, self.unique).forward(conn, dialect)
    
    def describe(self) -> str:
        return f"Drop index '{self.index_name}'"


# =============================================================================
# Foreign Key Operations
# =============================================================================

@dataclass
class AddForeignKey(Operation):
    """Add a foreign key."""
    table_name: str
    constraint_name: str
    column: str
    references_table: str
    references_column: str = "id"
    on_delete: str = "CASCADE"
    on_update: str = "CASCADE"

    def to_fingerprint(self) -> dict:
        """Generate fingersprin from object."""
        return {
            "op": "AddForeignKey",
            "table": self.table_name,
            "constraint": self.constraint_name,
            "column": self.column,
            "references": {
                "table": self.references_table,
                "column": self.references_column,
            },
            "on_delete": self.on_delete,
            "on_update": self.on_update,
        }

    async def forward(self, conn: "AsyncConnection", dialect: str) -> None:
        compiler = _get_compiler(dialect)
        if not compiler.supports_add_constraint:
            raise NotImplementedError(
                f"{compiler.display_name} does not support ADD CONSTRAINT. "
                f"Define foreign keys inline in CREATE TABLE instead."
            )
        sql = (
            f'ALTER TABLE "{self.table_name}" '
            f'ADD CONSTRAINT "{self.constraint_name}" '
            f'FOREIGN KEY ("{self.column}") '
            f'REFERENCES "{self.references_table}" ("{self.references_column}") '
            f"ON DELETE {self.on_delete} ON UPDATE {self.on_update}"
        )
        await conn.execute(text(sql))
    
    async def backward(self, conn: "AsyncConnection", dialect: str) -> None:
        await DropForeignKey(self.table_name, self.constraint_name).forward(conn, dialect)
    
    def describe(self) -> str:
        return f"Add FK '{self.constraint_name}' to '{self.table_name}'"


@dataclass
class DropForeignKey(Operation):
    """Drop a foreign key."""
    table_name: str
    constraint_name: str
    column: str | None = None
    references_table: str | None = None
    references_column: str = "id"
    on_delete: str = "CASCADE"

    def to_fingerprint(self) -> dict:
        """Generate fingersprin from object."""
        return {
            "op": "DropForeignKey",
            "table": self.table_name,
            "constraint": self.constraint_name,
            "column": self.column,
            "references": {
                "table": self.references_table,
                "column": self.references_column,
            } if self.references_table else None,
            "on_delete": self.on_delete,
        }

    async def forward(self, conn: "AsyncConnection", dialect: str) -> None:
        compiler = _get_compiler(dialect)
        if not compiler.supports_drop_constraint:
            raise NotImplementedError(
                f"{compiler.display_name} does not support DROP CONSTRAINT. "
                f"Consider recreating the table without the foreign key."
            )
        await conn.execute(text(f'ALTER TABLE "{self.table_name}" DROP CONSTRAINT "{self.constraint_name}"'))
    
    async def backward(self, conn: "AsyncConnection", dialect: str) -> None:
        if not self.column or not self.references_table:
            raise RuntimeError(f"Cannot reverse DropForeignKey '{self.constraint_name}'")
        await AddForeignKey(
            self.table_name, self.constraint_name, self.column,
            self.references_table, self.references_column, self.on_delete
        ).forward(conn, dialect)
    
    def describe(self) -> str:
        return f"Drop FK '{self.constraint_name}'"


# =============================================================================
# Custom SQL/Python Operations
# =============================================================================

@dataclass
class RunPython(Operation):
    """Run Python code."""
    forward_func: Callable[["AsyncConnection"], Awaitable[None]]
    backward_func: Callable[["AsyncConnection"], Awaitable[None]] | None = None
    description: str = "Run Python"
    reversible: bool = field(init=False)

    def to_fingerprint(self) -> dict:
        """Generate fingersprin from object."""
        return {
            "op": "RunPython",
            "description": self.description,
        }

    def __post_init__(self):
        self.reversible = self.backward_func is not None
    
    async def forward(self, conn: "AsyncConnection", dialect: str) -> None:
        await self.forward_func(conn)
    
    async def backward(self, conn: "AsyncConnection", dialect: str) -> None:
        if not self.backward_func:
            raise RuntimeError("Operation not reversible")
        await self.backward_func(conn)
    
    def describe(self) -> str:
        return self.description


@dataclass
class RunSQL(Operation):
    """Run SQL."""
    forward_sql: str
    backward_sql: str | None = None
    description: str = "Run SQL"
    reversible: bool = field(init=False)

    def to_fingerprint(self) -> dict:
        """Generate fingersprin from object."""
        return {
            "op": "RunSQL",
            "forward": self.forward_sql.strip(),
            "backward": self.backward_sql.strip() if self.backward_sql else None,
        }

    def __post_init__(self):
        self.reversible = self.backward_sql is not None
    
    async def forward(self, conn: "AsyncConnection", dialect: str) -> None:
        await conn.execute(text(self.forward_sql))
    
    async def backward(self, conn: "AsyncConnection", dialect: str) -> None:
        if not self.backward_sql:
            raise RuntimeError("Operation not reversible")
        await conn.execute(text(self.backward_sql))
    
    def describe(self) -> str:
        return self.description


# =============================================================================
# Enum Operations (PostgreSQL)
# =============================================================================

@dataclass
class CreateEnum(Operation):
    """Create PostgreSQL ENUM type."""
    enum_name: str
    values: list[str]

    def to_fingerprint(self) -> dict:
        """Generate fingersprin from object."""
        return {
            "op": "CreateEnum",
            "name": self.enum_name,
            "values": list(self.values),
        }

    async def forward(self, conn: "AsyncConnection", dialect: str) -> None:
        compiler = _get_compiler(dialect)
        if not compiler.supports_enum:
            return  # Silently skip for dialects without native ENUM
        check = await conn.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = :name)"),
            {"name": self.enum_name}
        )
        if not check.scalar():
            vals = ", ".join(f"'{v}'" for v in self.values)
            await conn.execute(text(f"CREATE TYPE {self.enum_name} AS ENUM ({vals})"))
    
    async def backward(self, conn: "AsyncConnection", dialect: str) -> None:
        compiler = _get_compiler(dialect)
        if compiler.supports_enum:
            await conn.execute(text(f"DROP TYPE IF EXISTS {self.enum_name}"))
    
    def describe(self) -> str:
        return f"Create enum '{self.enum_name}'"
    
    def to_code(self) -> str:
        return f"CreateEnum(enum_name='{self.enum_name}', values={repr(self.values)})"


@dataclass
class DropEnum(Operation):
    """Drop PostgreSQL ENUM type."""
    enum_name: str
    values: list[str] = field(default_factory=list)
    destructive: bool = True

    def to_fingerprint(self) -> dict:
        """Generate fingersprin from object."""
        return {
            "op": "DropEnum",
            "name": self.enum_name,
            "values": list(self.values),
        }

    async def forward(self, conn: "AsyncConnection", dialect: str) -> None:
        compiler = _get_compiler(dialect)
        if compiler.supports_enum:
            await conn.execute(text(f"DROP TYPE IF EXISTS {self.enum_name} CASCADE"))
    
    async def backward(self, conn: "AsyncConnection", dialect: str) -> None:
        if not self.values:
            raise RuntimeError(f"Cannot reverse DropEnum '{self.enum_name}'")
        await CreateEnum(self.enum_name, self.values).forward(conn, dialect)
    
    def describe(self) -> str:
        return f"Drop enum '{self.enum_name}'"
    
    def to_code(self) -> str:
        return f"DropEnum(enum_name='{self.enum_name}', values={repr(self.values)})"


@dataclass
class AlterEnum(Operation):
    """Alter PostgreSQL ENUM type."""
    enum_name: str
    add_values: list[str] = field(default_factory=list)
    remove_values: list[str] = field(default_factory=list)
    old_values: list[str] = field(default_factory=list)
    new_values: list[str] = field(default_factory=list)

    def to_fingerprint(self) -> dict:
        """Generate fingersprin from object."""
        return {
            "op": "AlterEnum",
            "name": self.enum_name,
            "add": sorted(self.add_values),
            "remove": sorted(self.remove_values),
            "old": list(self.old_values),
            "new": list(self.new_values),
        }

    async def forward(self, conn: "AsyncConnection", dialect: str) -> None:
        compiler = _get_compiler(dialect)
        if not compiler.supports_enum:
            return
        if self.add_values and not self.remove_values:
            for v in self.add_values:
                await conn.execute(text(f"ALTER TYPE {self.enum_name} ADD VALUE IF NOT EXISTS '{v}'"))
        else:
            await self._recreate(conn, self.new_values)
    
    async def backward(self, conn: "AsyncConnection", dialect: str) -> None:
        compiler = _get_compiler(dialect)
        if not compiler.supports_enum or not self.old_values:
            return
        await self._recreate(conn, self.old_values)
    
    async def _recreate(self, conn: "AsyncConnection", values: list[str]) -> None:
        result = await conn.execute(text("""
            SELECT c.table_name, c.column_name
            FROM information_schema.columns c
            JOIN pg_type t ON c.udt_name = t.typname
            WHERE t.typname = :name
        """), {"name": self.enum_name})
        cols = [(r[0], r[1]) for r in result.fetchall()]
        
        for t, c in cols:
            await conn.execute(text(f'ALTER TABLE "{t}" ALTER COLUMN "{c}" TYPE VARCHAR(255)'))
        await conn.execute(text(f"DROP TYPE IF EXISTS {self.enum_name}"))
        vals = ", ".join(f"'{v}'" for v in values)
        await conn.execute(text(f"CREATE TYPE {self.enum_name} AS ENUM ({vals})"))
        for t, c in cols:
            await conn.execute(text(
                f'ALTER TABLE "{t}" ALTER COLUMN "{c}" TYPE {self.enum_name} USING "{c}"::{self.enum_name}'
            ))
    
    def describe(self) -> str:
        return f"Alter enum '{self.enum_name}'"
    
    def to_code(self) -> str:
        return (
            f"AlterEnum(enum_name='{self.enum_name}', add_values={repr(self.add_values)}, "
            f"remove_values={repr(self.remove_values)}, old_values={repr(self.old_values)}, "
            f"new_values={repr(self.new_values)})"
        )
