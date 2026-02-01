"""
Operações de migração.

Cada operação representa uma mudança no schema do banco de dados.
Todas as operações são reversíveis quando possível.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, TYPE_CHECKING
from collections.abc import Awaitable

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection


@dataclass
class ColumnDef:
    """Definição de uma coluna."""
    
    name: str
    type: str  # Ex: "VARCHAR(255)", "INTEGER", "BOOLEAN", "TEXT", "DATETIME"
    nullable: bool = True
    default: Any = None
    primary_key: bool = False
    autoincrement: bool = False
    unique: bool = False
    index: bool = False
    
    def to_sql(self, dialect: str = "sqlite") -> str:
        """Gera SQL para a coluna."""
        parts = [f'"{self.name}"', self.type]
        
        if self.primary_key:
            parts.append("PRIMARY KEY")
            if self.autoincrement:
                if dialect == "sqlite":
                    parts.append("AUTOINCREMENT")
                elif dialect == "postgresql":
                    # PostgreSQL usa SERIAL ou IDENTITY
                    pass
                else:
                    parts.append("AUTO_INCREMENT")
        
        if not self.nullable and not self.primary_key:
            parts.append("NOT NULL")
        
        if self.default is not None:
            if isinstance(self.default, str):
                parts.append(f"DEFAULT '{self.default}'")
            elif isinstance(self.default, bool):
                parts.append(f"DEFAULT {1 if self.default else 0}")
            else:
                parts.append(f"DEFAULT {self.default}")
        
        if self.unique and not self.primary_key:
            parts.append("UNIQUE")
        
        return " ".join(parts)


@dataclass
class ForeignKeyDef:
    """Definição de uma chave estrangeira."""
    
    column: str
    references_table: str
    references_column: str = "id"
    on_delete: str = "CASCADE"
    on_update: str = "CASCADE"
    
    def to_sql(self, table_name: str) -> str:
        """Gera SQL para a FK."""
        return (
            f'FOREIGN KEY ("{self.column}") '
            f'REFERENCES "{self.references_table}" ("{self.references_column}") '
            f"ON DELETE {self.on_delete} ON UPDATE {self.on_update}"
        )


class Operation(ABC):
    """Classe base para operações de migração."""
    
    # Se True, a operação pode causar perda de dados
    destructive: bool = False
    
    # Se True, a operação é reversível
    reversible: bool = True
    
    @abstractmethod
    async def forward(self, conn: "AsyncConnection", dialect: str) -> None:
        """Executa a operação."""
        ...
    
    @abstractmethod
    async def backward(self, conn: "AsyncConnection", dialect: str) -> None:
        """Reverte a operação."""
        ...
    
    @abstractmethod
    def describe(self) -> str:
        """Descrição legível da operação."""
        ...
    
    def to_code(self) -> str:
        """Gera código Python para a operação."""
        return repr(self)


@dataclass
class CreateTable(Operation):
    """Cria uma nova tabela."""
    
    table_name: str
    columns: list[ColumnDef] = field(default_factory=list)
    foreign_keys: list[ForeignKeyDef] = field(default_factory=list)
    
    async def forward(self, conn: "AsyncConnection", dialect: str) -> None:
        columns_sql = ",\n    ".join(col.to_sql(dialect) for col in self.columns)
        
        if self.foreign_keys:
            fk_sql = ",\n    ".join(fk.to_sql(self.table_name) for fk in self.foreign_keys)
            columns_sql += f",\n    {fk_sql}"
        
        sql = f'CREATE TABLE IF NOT EXISTS "{self.table_name}" (\n    {columns_sql}\n)'
        await conn.execute(text(sql))
    
    async def backward(self, conn: "AsyncConnection", dialect: str) -> None:
        sql = f'DROP TABLE IF EXISTS "{self.table_name}"'
        await conn.execute(text(sql))
    
    def describe(self) -> str:
        return f"Create table '{self.table_name}'"
    
    def to_code(self) -> str:
        cols = ",\n            ".join(
            f"ColumnDef(name='{c.name}', type='{c.type}', nullable={c.nullable}, "
            f"default={repr(c.default)}, primary_key={c.primary_key}, "
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
    """Remove uma tabela."""
    
    table_name: str
    destructive: bool = True
    
    # Para reversão, precisamos guardar a estrutura
    columns: list[ColumnDef] = field(default_factory=list)
    foreign_keys: list[ForeignKeyDef] = field(default_factory=list)
    
    async def forward(self, conn: "AsyncConnection", dialect: str) -> None:
        sql = f'DROP TABLE IF EXISTS "{self.table_name}"'
        await conn.execute(text(sql))
    
    async def backward(self, conn: "AsyncConnection", dialect: str) -> None:
        if not self.columns:
            raise RuntimeError(
                f"Cannot reverse DropTable for '{self.table_name}': "
                "column definitions not provided"
            )
        create_op = CreateTable(self.table_name, self.columns, self.foreign_keys)
        await create_op.forward(conn, dialect)
    
    def describe(self) -> str:
        return f"Drop table '{self.table_name}'"


@dataclass
class AddColumn(Operation):
    """Adiciona uma coluna a uma tabela existente."""
    
    table_name: str
    column: ColumnDef
    
    async def forward(self, conn: "AsyncConnection", dialect: str) -> None:
        col_sql = self.column.to_sql(dialect)
        sql = f'ALTER TABLE "{self.table_name}" ADD COLUMN {col_sql}'
        await conn.execute(text(sql))
    
    async def backward(self, conn: "AsyncConnection", dialect: str) -> None:
        drop_op = DropColumn(self.table_name, self.column.name)
        await drop_op.forward(conn, dialect)
    
    def describe(self) -> str:
        return f"Add column '{self.column.name}' to table '{self.table_name}'"
    
    def to_code(self) -> str:
        c = self.column
        return f"""AddColumn(
        table_name='{self.table_name}',
        column=ColumnDef(
            name='{c.name}', type='{c.type}', nullable={c.nullable},
            default={repr(c.default)}, primary_key={c.primary_key},
            autoincrement={c.autoincrement}, unique={c.unique}
        ),
    )"""


@dataclass
class DropColumn(Operation):
    """Remove uma coluna de uma tabela."""
    
    table_name: str
    column_name: str
    destructive: bool = True
    
    # Para reversão
    column_def: ColumnDef | None = None
    
    async def forward(self, conn: "AsyncConnection", dialect: str) -> None:
        if dialect == "sqlite":
            # SQLite não suporta DROP COLUMN diretamente em versões antigas
            # Mas SQLite 3.35+ suporta
            sql = f'ALTER TABLE "{self.table_name}" DROP COLUMN "{self.column_name}"'
        else:
            sql = f'ALTER TABLE "{self.table_name}" DROP COLUMN "{self.column_name}"'
        await conn.execute(text(sql))
    
    async def backward(self, conn: "AsyncConnection", dialect: str) -> None:
        if not self.column_def:
            raise RuntimeError(
                f"Cannot reverse DropColumn for '{self.column_name}': "
                "column definition not provided"
            )
        add_op = AddColumn(self.table_name, self.column_def)
        await add_op.forward(conn, dialect)
    
    def describe(self) -> str:
        return f"Drop column '{self.column_name}' from table '{self.table_name}'"


@dataclass
class AlterColumn(Operation):
    """Altera uma coluna existente."""
    
    table_name: str
    column_name: str
    new_type: str | None = None
    new_nullable: bool | None = None
    new_default: Any = None
    set_default: bool = False  # True para definir default, mesmo que seja None
    
    # Para reversão
    old_type: str | None = None
    old_nullable: bool | None = None
    old_default: Any = None
    
    async def forward(self, conn: "AsyncConnection", dialect: str) -> None:
        if dialect == "sqlite":
            # SQLite tem suporte limitado a ALTER COLUMN
            # Precisaria recriar a tabela
            raise NotImplementedError(
                "SQLite não suporta ALTER COLUMN diretamente. "
                "Use uma migração manual com RunSQL."
            )
        
        alterations = []
        
        if self.new_type:
            alterations.append(f'ALTER COLUMN "{self.column_name}" TYPE {self.new_type}')
        
        if self.new_nullable is not None:
            if self.new_nullable:
                alterations.append(f'ALTER COLUMN "{self.column_name}" DROP NOT NULL')
            else:
                alterations.append(f'ALTER COLUMN "{self.column_name}" SET NOT NULL')
        
        if self.set_default:
            if self.new_default is None:
                alterations.append(f'ALTER COLUMN "{self.column_name}" DROP DEFAULT')
            else:
                alterations.append(
                    f'ALTER COLUMN "{self.column_name}" SET DEFAULT {repr(self.new_default)}'
                )
        
        for alt in alterations:
            sql = f'ALTER TABLE "{self.table_name}" {alt}'
            await conn.execute(text(sql))
    
    async def backward(self, conn: "AsyncConnection", dialect: str) -> None:
        reverse_op = AlterColumn(
            table_name=self.table_name,
            column_name=self.column_name,
            new_type=self.old_type,
            new_nullable=self.old_nullable,
            new_default=self.old_default,
            set_default=self.set_default,
        )
        await reverse_op.forward(conn, dialect)
    
    def describe(self) -> str:
        changes = []
        if self.new_type:
            changes.append(f"type to {self.new_type}")
        if self.new_nullable is not None:
            changes.append(f"nullable to {self.new_nullable}")
        if self.set_default:
            changes.append(f"default to {self.new_default}")
        return f"Alter column '{self.column_name}' in '{self.table_name}': {', '.join(changes)}"


@dataclass
class RenameColumn(Operation):
    """Renomeia uma coluna."""
    
    table_name: str
    old_name: str
    new_name: str
    
    async def forward(self, conn: "AsyncConnection", dialect: str) -> None:
        if dialect == "sqlite":
            sql = f'ALTER TABLE "{self.table_name}" RENAME COLUMN "{self.old_name}" TO "{self.new_name}"'
        elif dialect == "postgresql":
            sql = f'ALTER TABLE "{self.table_name}" RENAME COLUMN "{self.old_name}" TO "{self.new_name}"'
        else:
            sql = f'ALTER TABLE "{self.table_name}" CHANGE "{self.old_name}" "{self.new_name}"'
        await conn.execute(text(sql))
    
    async def backward(self, conn: "AsyncConnection", dialect: str) -> None:
        reverse_op = RenameColumn(self.table_name, self.new_name, self.old_name)
        await reverse_op.forward(conn, dialect)
    
    def describe(self) -> str:
        return f"Rename column '{self.old_name}' to '{self.new_name}' in '{self.table_name}'"


@dataclass
class CreateIndex(Operation):
    """Cria um índice."""
    
    table_name: str
    index_name: str
    columns: list[str]
    unique: bool = False
    
    async def forward(self, conn: "AsyncConnection", dialect: str) -> None:
        unique_str = "UNIQUE " if self.unique else ""
        cols = ", ".join(f'"{c}"' for c in self.columns)
        sql = f'CREATE {unique_str}INDEX IF NOT EXISTS "{self.index_name}" ON "{self.table_name}" ({cols})'
        await conn.execute(text(sql))
    
    async def backward(self, conn: "AsyncConnection", dialect: str) -> None:
        sql = f'DROP INDEX IF EXISTS "{self.index_name}"'
        await conn.execute(text(sql))
    
    def describe(self) -> str:
        unique_str = "unique " if self.unique else ""
        return f"Create {unique_str}index '{self.index_name}' on '{self.table_name}'"


@dataclass
class DropIndex(Operation):
    """Remove um índice."""
    
    table_name: str
    index_name: str
    
    # Para reversão
    columns: list[str] = field(default_factory=list)
    unique: bool = False
    
    async def forward(self, conn: "AsyncConnection", dialect: str) -> None:
        sql = f'DROP INDEX IF EXISTS "{self.index_name}"'
        await conn.execute(text(sql))
    
    async def backward(self, conn: "AsyncConnection", dialect: str) -> None:
        if not self.columns:
            raise RuntimeError(
                f"Cannot reverse DropIndex for '{self.index_name}': "
                "column list not provided"
            )
        create_op = CreateIndex(self.table_name, self.index_name, self.columns, self.unique)
        await create_op.forward(conn, dialect)
    
    def describe(self) -> str:
        return f"Drop index '{self.index_name}'"


@dataclass
class AddForeignKey(Operation):
    """Adiciona uma chave estrangeira."""
    
    table_name: str
    constraint_name: str
    column: str
    references_table: str
    references_column: str = "id"
    on_delete: str = "CASCADE"
    on_update: str = "CASCADE"
    
    async def forward(self, conn: "AsyncConnection", dialect: str) -> None:
        if dialect == "sqlite":
            # SQLite não suporta ADD CONSTRAINT para FK
            raise NotImplementedError(
                "SQLite não suporta adicionar FK após criação da tabela. "
                "Defina a FK na criação da tabela."
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
        drop_op = DropForeignKey(self.table_name, self.constraint_name)
        await drop_op.forward(conn, dialect)
    
    def describe(self) -> str:
        return f"Add foreign key '{self.constraint_name}' to '{self.table_name}'"


@dataclass
class DropForeignKey(Operation):
    """Remove uma chave estrangeira."""
    
    table_name: str
    constraint_name: str
    
    # Para reversão
    column: str | None = None
    references_table: str | None = None
    references_column: str = "id"
    on_delete: str = "CASCADE"
    
    async def forward(self, conn: "AsyncConnection", dialect: str) -> None:
        if dialect == "sqlite":
            raise NotImplementedError("SQLite não suporta DROP CONSTRAINT")
        
        sql = f'ALTER TABLE "{self.table_name}" DROP CONSTRAINT "{self.constraint_name}"'
        await conn.execute(text(sql))
    
    async def backward(self, conn: "AsyncConnection", dialect: str) -> None:
        if not self.column or not self.references_table:
            raise RuntimeError(
                f"Cannot reverse DropForeignKey for '{self.constraint_name}': "
                "FK definition not provided"
            )
        add_op = AddForeignKey(
            self.table_name,
            self.constraint_name,
            self.column,
            self.references_table,
            self.references_column,
            self.on_delete,
        )
        await add_op.forward(conn, dialect)
    
    def describe(self) -> str:
        return f"Drop foreign key '{self.constraint_name}' from '{self.table_name}'"


@dataclass
class RunPython(Operation):
    """Executa código Python arbitrário."""
    
    forward_func: Callable[["AsyncConnection"], Awaitable[None]]
    backward_func: Callable[["AsyncConnection"], Awaitable[None]] | None = None
    description: str = "Run Python code"
    
    reversible: bool = field(init=False)
    
    def __post_init__(self):
        self.reversible = self.backward_func is not None
    
    async def forward(self, conn: "AsyncConnection", dialect: str) -> None:
        await self.forward_func(conn)
    
    async def backward(self, conn: "AsyncConnection", dialect: str) -> None:
        if self.backward_func is None:
            raise RuntimeError("This RunPython operation is not reversible")
        await self.backward_func(conn)
    
    def describe(self) -> str:
        return self.description


@dataclass
class RunSQL(Operation):
    """Executa SQL arbitrário."""
    
    forward_sql: str
    backward_sql: str | None = None
    description: str = "Run SQL"
    
    reversible: bool = field(init=False)
    
    def __post_init__(self):
        self.reversible = self.backward_sql is not None
    
    async def forward(self, conn: "AsyncConnection", dialect: str) -> None:
        await conn.execute(text(self.forward_sql))
    
    async def backward(self, conn: "AsyncConnection", dialect: str) -> None:
        if self.backward_sql is None:
            raise RuntimeError("This RunSQL operation is not reversible")
        await conn.execute(text(self.backward_sql))
    
    def describe(self) -> str:
        return self.description
