"""PostgreSQL dialect compiler."""

from __future__ import annotations

from core.migrations.dialects.base import DialectCompiler


class PostgreSQLCompiler(DialectCompiler):
    """
    SQL compiler for PostgreSQL.

    Key differences:
    - Uses SERIAL/BIGSERIAL for auto-increment (type-level, not keyword)
    - Boolean defaults are TRUE/FALSE
    - TIMESTAMP → TIMESTAMP WITH TIME ZONE
    - JSON → JSONB
    - Native ENUM support
    - Full ALTER COLUMN support
    """

    name = "postgresql"
    display_name = "PostgreSQL"

    supports_alter_column = True
    supports_add_constraint = True
    supports_drop_constraint = True
    supports_enum = True

    type_mapping = {
        "DATETIME": "TIMESTAMP WITH TIME ZONE",
        "TIMESTAMP": "TIMESTAMP WITH TIME ZONE",
        "BOOLEAN": "BOOLEAN",
        "TINYINT": "SMALLINT",
        "LONGTEXT": "TEXT",
        "DOUBLE": "DOUBLE PRECISION",
        "ADAPTIVEJSON": "JSONB",
        "JSON": "JSONB",
    }

    @property
    def _autoincrement_types(self) -> set[str]:
        # PostgreSQL: auto-increment via SERIAL type for integer types
        return {"INTEGER", "INT", "BIGINT", "SMALLINT"}

    def autoincrement_clause(self, col_type: str) -> str | None:
        # PostgreSQL doesn't use a keyword — it uses SERIAL type instead
        return None

    def resolve_autoincrement_type(self, col_type: str) -> str:
        """PostgreSQL uses SERIAL/BIGSERIAL instead of a keyword."""
        upper = col_type.upper()
        if upper in ("INTEGER", "INT"):
            return "SERIAL"
        if upper == "BIGINT":
            return "BIGSERIAL"
        if upper == "SMALLINT":
            return "SMALLSERIAL"
        return col_type

    def _format_bool_default(self, value: bool) -> str:
        return f"DEFAULT {'TRUE' if value else 'FALSE'}"

    def migrations_table_sql(self, table_name: str) -> str:
        return f"""
            CREATE TABLE IF NOT EXISTS "{table_name}" (
                id SERIAL PRIMARY KEY,
                app VARCHAR(255) NOT NULL,
                name VARCHAR(255) NOT NULL,
                applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(app, name)
            )
        """

    def list_tables_sql(self) -> str:
        return (
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public'"
        )

    def foreign_key_check_sql(self, table_name: str) -> str | None:
        return f"""
            SELECT tc.table_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.constraint_column_usage ccu
                ON tc.constraint_name = ccu.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
                AND ccu.table_name = '{table_name}'
        """

    def quote_table(self, name: str) -> str:
        return f'"{name}"'
