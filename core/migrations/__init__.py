"""
Sistema de Migrations inspirado no Django.

Características:
- makemigrations: Detecta mudanças nos models e gera arquivos de migração
- migrate: Aplica migrações pendentes
- showmigrations: Lista status das migrações
- rollback: Reverte migrações
- check: Analisa migrações antes de aplicar (detecta problemas)
- Suporte a operações: CreateTable, DropTable, AddColumn, DropColumn, AlterColumn, CreateIndex, etc.
- Detecção automática de mudanças
- Migrações reversíveis
- Suporte a migrações de dados (RunPython)
- Análise pré-produção para evitar erros
"""

from core.migrations.engine import MigrationEngine
from core.migrations.operations import (
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
)
from core.migrations.migration import Migration
from core.migrations.cli import (
    makemigrations,
    migrate,
    showmigrations,
    rollback,
)
from core.migrations.analyzer import (
    MigrationAnalyzer,
    MigrationIssue,
    AnalysisResult,
    Severity,
    IssueCode,
    analyze_migration,
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
]
