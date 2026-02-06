"""
Abstract base class for dialect compilers.

Each database dialect (SQLite, PostgreSQL, MySQL) implements this interface
to generate correct SQL for its specific engine.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime, date, time
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.migrations.dialects import DialectCompiler as DialectCompilerType


class DialectCompiler(ABC):
    """
    Abstract base for dialect-specific SQL compilers.

    Subclass this to add support for a new database engine.
    Each method encapsulates one aspect of dialect-specific SQL generation,
    keeping operations.py clean and dialect-agnostic.
    """

    # ── Identity ──────────────────────────────────────────────────────
    name: str = "unknown"
    display_name: str = "Unknown"

    # ── Feature flags ─────────────────────────────────────────────────
    supports_alter_column: bool = True
    supports_add_constraint: bool = True
    supports_drop_constraint: bool = True
    supports_enum: bool = False
    supports_if_not_exists_index: bool = True

    # ── Type mapping ──────────────────────────────────────────────────
    type_mapping: dict[str, str] = {}

    def map_type(self, sql_type: str) -> str:
        """Convert a generic SQL type to the dialect-specific equivalent."""
        base = sql_type.split("(")[0].upper()
        mapped = self.type_mapping.get(base)
        if mapped:
            # Preserve size spec if the mapping doesn't include one
            if "(" in sql_type and "(" not in mapped:
                return sql_type
            return mapped
        return sql_type

    # ── Autoincrement ─────────────────────────────────────────────────

    def should_autoincrement(self, col_type: str) -> bool:
        """
        Check whether autoincrement is valid for the given column type.

        For example, SQLite only supports AUTOINCREMENT on INTEGER PRIMARY KEY.
        UUID/TEXT primary keys should NEVER get autoincrement.
        """
        mapped = self.map_type(col_type).upper()
        return mapped in self._autoincrement_types

    @property
    @abstractmethod
    def _autoincrement_types(self) -> set[str]:
        """Set of mapped types that support autoincrement."""
        ...

    @abstractmethod
    def autoincrement_clause(self, col_type: str) -> str | None:
        """
        Return the autoincrement SQL clause for this dialect, or None.

        For PostgreSQL this returns None because auto-increment is handled
        by changing the type to SERIAL/BIGSERIAL.
        """
        ...

    def resolve_autoincrement_type(self, col_type: str) -> str:
        """
        Transform column type to handle autoincrement if the dialect
        uses a special type (e.g., PostgreSQL SERIAL).

        Default: return the type unchanged.
        """
        return col_type

    # ── Default formatting ────────────────────────────────────────────

    def format_default(self, value: Any) -> str | None:
        """Format a Python value as a SQL DEFAULT clause."""
        if value is None:
            return None
        if isinstance(value, bool):
            return self._format_bool_default(value)
        if isinstance(value, (datetime, date, time)):
            return f"DEFAULT '{value.isoformat()}'"
        if isinstance(value, str):
            escaped = value.replace("'", "''")
            return f"DEFAULT '{escaped}'"
        if isinstance(value, (int, float)):
            return f"DEFAULT {value}"
        if isinstance(value, (dict, list)):
            escaped = json.dumps(value).replace("'", "''")
            return f"DEFAULT '{escaped}'"
        return f"DEFAULT '{str(value)}'"

    def _format_bool_default(self, value: bool) -> str:
        """Format boolean default — overridden by PostgreSQL."""
        return f"DEFAULT {1 if value else 0}"

    # ── Column SQL ────────────────────────────────────────────────────

    def column_to_sql(
        self,
        name: str,
        col_type: str,
        *,
        nullable: bool = True,
        default: Any = None,
        primary_key: bool = False,
        autoincrement: bool = False,
        unique: bool = False,
        include_pk: bool = True,
    ) -> str:
        """
        Generate a full column definition SQL fragment.

        This is the main method that replaces ColumnDef.to_sql() inline logic.
        """
        mapped_type = self.map_type(col_type)

        # Resolve autoincrement at the type level (e.g., PostgreSQL SERIAL)
        if autoincrement and primary_key and self.should_autoincrement(col_type):
            mapped_type = self.resolve_autoincrement_type(mapped_type)

        parts = [f'"{name}"', mapped_type]

        # Primary key
        if primary_key and include_pk:
            parts.append("PRIMARY KEY")
            # Append dialect-specific autoincrement keyword
            if autoincrement and self.should_autoincrement(col_type):
                clause = self.autoincrement_clause(col_type)
                if clause:
                    parts.append(clause)

        # NOT NULL
        if not nullable and not primary_key:
            parts.append("NOT NULL")
        elif primary_key and not include_pk:
            # Composite PK: column must be NOT NULL
            parts.append("NOT NULL")

        # DEFAULT
        if default is not None:
            default_sql = self.format_default(default)
            if default_sql:
                parts.append(default_sql)

        # UNIQUE
        if unique and not primary_key:
            parts.append("UNIQUE")

        return " ".join(parts)

    # ── Migrations table ──────────────────────────────────────────────

    @abstractmethod
    def migrations_table_sql(self, table_name: str) -> str:
        """Return CREATE TABLE SQL for the migrations tracking table."""
        ...

    # ── Database info queries ─────────────────────────────────────────

    @abstractmethod
    def list_tables_sql(self) -> str:
        """Return SQL to list user tables."""
        ...

    @abstractmethod
    def foreign_key_check_sql(self, table_name: str) -> str | None:
        """Return SQL to find tables referencing `table_name`, or None."""
        ...

    # ── Quoting ───────────────────────────────────────────────────────

    def quote_table(self, name: str) -> str:
        """Quote a table name."""
        return f'"{name}"'

    def quote_column(self, name: str) -> str:
        """Quote a column name."""
        return f'"{name}"'
