"""
Sistema de Migrations inspirado no Django.

Características:
- makemigrations: Detecta mudanças nos models e gera arquivos de migração
- migrate: Aplica migrações pendentes
- showmigrations: Lista status das migrações
- rollback: Reverte migrações
- check: Analisa migrações antes de aplicar (detecta problemas)
- Suporte multi-dialeto: SQLite, PostgreSQL, MySQL (via dialect compilers)
- Detecção automática de mudanças
- Migrações reversíveis
- Suporte a migrações de dados (RunPython)
- Análise pré-produção para evitar erros
"""

from stride.migrations.engine import MigrationEngine
from stride.migrations.operations import (
    Operation,
    CreateTable,
    DropTable,
    AddColumn,
    DropColumn,
    AlterColumn,
    RenameColumn,
    CreateIndex,
    DropIndex,
    AddForeignKey,
    DropForeignKey,
    RunPython,
    RunSQL,
    # Enum operations
    CreateEnum,
    DropEnum,
    AlterEnum,
)
from stride.migrations.migration import Migration
from stride.migrations.cli import (
    makemigrations,
    migrate,
    showmigrations,
    rollback,
)
from stride.migrations.analyzer import (
    MigrationAnalyzer,
    MigrationIssue,
    AnalysisResult,
    Severity,
    IssueCode,
    analyze_migration,
)
from stride.migrations.dialects import (
    get_compiler,
    detect_dialect,
    register_compiler,
)

__all__ = [
    # Engine
    "MigrationEngine",
    # Operations
    "Operation",
    "CreateTable",
    "DropTable",
    "AddColumn",
    "DropColumn",
    "AlterColumn",
    "RenameColumn",
    "CreateIndex",
    "DropIndex",
    "AddForeignKey",
    "DropForeignKey",
    "RunPython",
    "RunSQL",
    # Enum operations
    "CreateEnum",
    "DropEnum",
    "AlterEnum",
    # Migration
    "Migration",
    # CLI
    "makemigrations",
    "migrate",
    "showmigrations",
    "rollback",
    # Analyzer
    "MigrationAnalyzer",
    "MigrationIssue",
    "AnalysisResult",
    "Severity",
    "IssueCode",
    "analyze_migration",
    # Dialect compilers
    "get_compiler",
    "detect_dialect",
    "register_compiler",
]
