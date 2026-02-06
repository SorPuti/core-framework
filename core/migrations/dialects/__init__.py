"""
Dialect compilers for the migration system.

Each dialect (SQLite, PostgreSQL, MySQL) has its own compiler that
generates the correct SQL for that database engine.

Usage:
    from core.migrations.dialects import get_compiler

    compiler = get_compiler("postgresql")
    sql = compiler.column_to_sql(col_def)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.migrations.dialects.base import DialectCompiler


_COMPILERS: dict[str, type["DialectCompiler"]] = {}


def register_compiler(name: str, compiler_class: type["DialectCompiler"]) -> None:
    """Register a dialect compiler."""
    _COMPILERS[name] = compiler_class


def get_compiler(dialect: str) -> "DialectCompiler":
    """
    Get a compiler instance for the given dialect.

    Args:
        dialect: Database dialect name (sqlite, postgresql, mysql)

    Returns:
        DialectCompiler instance

    Raises:
        ValueError: If dialect is unknown
    """
    # Lazy-load built-in compilers on first call
    if not _COMPILERS:
        from core.migrations.dialects.sqlite import SQLiteCompiler
        from core.migrations.dialects.postgresql import PostgreSQLCompiler
        from core.migrations.dialects.mysql import MySQLCompiler

        register_compiler("sqlite", SQLiteCompiler)
        register_compiler("postgresql", PostgreSQLCompiler)
        register_compiler("mysql", MySQLCompiler)

    compiler_class = _COMPILERS.get(dialect)
    if compiler_class is None:
        available = ", ".join(sorted(_COMPILERS.keys()))
        raise ValueError(
            f"Unknown dialect '{dialect}'. Available: {available}. "
            f"You can register a custom compiler with register_compiler()."
        )
    return compiler_class()


def detect_dialect(database_url: str) -> str:
    """
    Detect dialect from a database URL.

    Args:
        database_url: SQLAlchemy-style database URL

    Returns:
        Dialect name string

    Examples:
        >>> detect_dialect("sqlite+aiosqlite:///./app.db")
        'sqlite'
        >>> detect_dialect("postgresql+asyncpg://localhost/db")
        'postgresql'
        >>> detect_dialect("mysql+aiomysql://localhost/db")
        'mysql'
    """
    url_lower = database_url.lower()
    if url_lower.startswith("sqlite") or "sqlite" in url_lower.split("://")[0]:
        return "sqlite"
    if url_lower.startswith("postgresql") or url_lower.startswith("postgres"):
        return "postgresql"
    if url_lower.startswith("mysql") or url_lower.startswith("mariadb"):
        return "mysql"
    return "unknown"


__all__ = [
    "get_compiler",
    "detect_dialect",
    "register_compiler",
]
