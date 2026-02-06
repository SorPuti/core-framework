"""MySQL / MariaDB dialect compiler."""

from __future__ import annotations

from core.migrations.dialects.base import DialectCompiler


class MySQLCompiler(DialectCompiler):
    """
    SQL compiler for MySQL / MariaDB.

    Key differences:
    - AUTO_INCREMENT keyword for auto-increment
    - BOOLEAN → TINYINT(1)
    - TEXT → LONGTEXT
    - UUID → CHAR(36)
    - Backtick quoting
    """

    name = "mysql"
    display_name = "MySQL"

    supports_alter_column = True
    supports_add_constraint = True
    supports_drop_constraint = True
    supports_enum = False  # Could be True, but handled differently
    supports_if_not_exists_index = False

    type_mapping = {
        "DATETIME": "DATETIME",
        "TIMESTAMP": "TIMESTAMP",
        "BOOLEAN": "TINYINT(1)",
        "TEXT": "LONGTEXT",
        "UUID": "CHAR(36)",
        "ADAPTIVEJSON": "JSON",
    }

    @property
    def _autoincrement_types(self) -> set[str]:
        return {"INTEGER", "INT", "BIGINT", "SMALLINT", "MEDIUMINT", "TINYINT"}

    def autoincrement_clause(self, col_type: str) -> str | None:
        if self.should_autoincrement(col_type):
            return "AUTO_INCREMENT"
        return None

    def _format_bool_default(self, value: bool) -> str:
        return f"DEFAULT {1 if value else 0}"

    def migrations_table_sql(self, table_name: str) -> str:
        return f"""
            CREATE TABLE IF NOT EXISTS `{table_name}` (
                id INT AUTO_INCREMENT PRIMARY KEY,
                app VARCHAR(255) NOT NULL,
                name VARCHAR(255) NOT NULL,
                applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(app, name)
            )
        """

    def list_tables_sql(self) -> str:
        return (
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = DATABASE()"
        )

    def foreign_key_check_sql(self, table_name: str) -> str | None:
        return f"""
            SELECT TABLE_NAME
            FROM information_schema.KEY_COLUMN_USAGE
            WHERE REFERENCED_TABLE_NAME = '{table_name}'
                AND TABLE_SCHEMA = DATABASE()
        """

    def quote_table(self, name: str) -> str:
        return f"`{name}`"

    def quote_column(self, name: str) -> str:
        return f"`{name}`"
