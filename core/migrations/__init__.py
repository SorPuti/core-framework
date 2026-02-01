"""
Sistema de Migrations inspirado no Django.

Características:
- makemigrations: Detecta mudanças nos models e gera arquivos de migração
- migrate: Aplica migrações pendentes
- showmigrations: Lista status das migrações
- rollback: Reverte migrações
- Suporte a operações: CreateTable, DropTable, AddColumn, DropColumn, AlterColumn, CreateIndex, etc.
- Detecção automática de mudanças
- Migrações reversíveis
- Suporte a migrações de dados (RunPython)
- Zero downtime migrations (quando possível)
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
]
