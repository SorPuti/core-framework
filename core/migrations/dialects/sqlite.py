"""SQLite dialect compiler."""

from __future__ import annotations

from core.migrations.dialects.base import DialectCompiler


class SQLiteCompiler(DialectCompiler):
    """
    SQL compiler for SQLite.

    Key differences:
    - AUTOINCREMENT only allowed on INTEGER PRIMARY KEY
    - No ALTER COLUMN support
    - No ADD/DROP CONSTRAINT support
    - BOOLEAN stored as INTEGER (0/1)
    - UUID stored as TEXT
    - No native ENUM support
    """

    name = "sqlite"
    display_name = "SQLite"

    supports_alter_column = False
    supports_add_constraint = False
    supports_drop_constraint = False
    supports_enum = False

    type_mapping = {
        "DATETIME": "DATETIME",
        "TIMESTAMP": "DATETIME",
        "BOOLEAN": "BOOLEAN",
        "UUID": "TEXT",
        "ADAPTIVEJSON": "JSON",
    }

    @property
    def _autoincrement_types(self) -> set[str]:
        # SQLite: AUTOINCREMENT is ONLY valid on INTEGER PRIMARY KEY
        return {"INTEGER"}

    def autoincrement_clause(self, col_type: str) -> str | None:
        if self.should_autoincrement(col_type):
            return "AUTOINCREMENT"
        return None

    def _format_bool_default(self, value: bool) -> str:
        return f"DEFAULT {1 if value else 0}"

    def migrations_table_sql(self, table_name: str) -> str:
        return f"""
            CREATE TABLE IF NOT EXISTS "{table_name}" (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app VARCHAR(255) NOT NULL,
                name VARCHAR(255) NOT NULL,
                applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(app, name)
            )
        """

    def list_tables_sql(self) -> str:
        return (
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )

    def foreign_key_check_sql(self, table_name: str) -> str | None:
        return (
            f"SELECT * FROM sqlite_master WHERE type='table' "
            f"AND sql LIKE '%REFERENCES \"{table_name}\"%'"
        )
