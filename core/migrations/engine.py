"""
Engine de migrações.

Responsável por:
- Rastrear migrações aplicadas
- Aplicar/reverter migrações
- Detectar mudanças nos models
- Gerar arquivos de migração
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from core.datetime import timezone

from core.migrations.migration import Migration
from core.migrations.operations import (
    Operation,
    CreateTable,
    DropTable,
    AddColumn,
    DropColumn,
    AlterColumn,
    ColumnDef,
    ForeignKeyDef,
)
from core.migrations.state import (
    SchemaState,
    SchemaDiff,
    TableState,
    ColumnState,
    models_to_schema_state,
    get_database_schema_state,
)

if TYPE_CHECKING:
    from core.models import Model


# Tabela para rastrear migrações aplicadas
MIGRATIONS_TABLE = "_core_migrations"

CREATE_MIGRATIONS_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS "{MIGRATIONS_TABLE}" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(app, name)
)
"""


class MigrationEngine:
    """
    Engine principal de migrações.
    
    Uso:
        engine = MigrationEngine(
            database_url="sqlite+aiosqlite:///./app.db",
            migrations_dir="./migrations",
        )
        
        # Detectar mudanças e gerar migração
        await engine.makemigrations(models=[User, Post], app_label="main")
        
        # Aplicar migrações
        await engine.migrate()
        
        # Ver status
        await engine.showmigrations()
        
        # Reverter última migração
        await engine.rollback()
    """
    
    def __init__(
        self,
        database_url: str,
        migrations_dir: str | Path = "./migrations",
        app_label: str = "main",
    ) -> None:
        self.database_url = database_url
        self.migrations_dir = Path(migrations_dir)
        self.app_label = app_label
        self._engine = create_async_engine(database_url, echo=False)
    
    @property
    def dialect(self) -> str:
        """Retorna o dialeto do banco de dados."""
        if "sqlite" in self.database_url:
            return "sqlite"
        elif "postgresql" in self.database_url:
            return "postgresql"
        elif "mysql" in self.database_url:
            return "mysql"
        return "unknown"
    
    async def _ensure_migrations_table(self, conn: AsyncConnection) -> None:
        """Garante que a tabela de migrações existe."""
        await conn.execute(text(CREATE_MIGRATIONS_TABLE_SQL))
        await conn.commit()
    
    async def _get_applied_migrations(self, conn: AsyncConnection) -> list[tuple[str, str]]:
        """Retorna lista de migrações já aplicadas."""
        await self._ensure_migrations_table(conn)
        
        result = await conn.execute(
            text(f'SELECT app, name FROM "{MIGRATIONS_TABLE}" ORDER BY id')
        )
        return [(row[0], row[1]) for row in result.fetchall()]
    
    async def _mark_migration_applied(
        self,
        conn: AsyncConnection,
        app: str,
        name: str,
    ) -> None:
        """Marca uma migração como aplicada."""
        await conn.execute(
            text(f'INSERT INTO "{MIGRATIONS_TABLE}" (app, name, applied_at) VALUES (:app, :name, :applied_at)'),
            {"app": app, "name": name, "applied_at": timezone.now().replace(tzinfo=None)},
        )
    
    async def _unmark_migration_applied(
        self,
        conn: AsyncConnection,
        app: str,
        name: str,
    ) -> None:
        """Remove marcação de migração aplicada."""
        await conn.execute(
            text(f'DELETE FROM "{MIGRATIONS_TABLE}" WHERE app = :app AND name = :name'),
            {"app": app, "name": name},
        )
    
    def _get_migration_files(self) -> list[Path]:
        """Lista arquivos de migração ordenados."""
        if not self.migrations_dir.exists():
            return []
        
        files = []
        for f in self.migrations_dir.glob("*.py"):
            if f.name.startswith("_"):
                continue
            # Verifica se segue o padrão NNNN_name.py
            if re.match(r"^\d{4}_", f.name):
                files.append(f)
        
        return sorted(files, key=lambda f: f.name)
    
    def _load_migration(self, path: Path) -> Migration:
        """Carrega uma migração de um arquivo."""
        spec = importlib.util.spec_from_file_location(
            f"migrations.{path.stem}",
            path,
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load migration from {path}")
        
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # Procura classe Migration no módulo
        migration_class = getattr(module, "migration", None)
        if migration_class is None:
            # Tenta encontrar instância de Migration
            for name in dir(module):
                obj = getattr(module, name)
                if isinstance(obj, Migration):
                    migration_class = obj
                    break
        
        if migration_class is None:
            raise ValueError(f"No Migration found in {path}")
        
        if isinstance(migration_class, type):
            migration = migration_class()
        else:
            migration = migration_class
        
        migration.name = path.stem
        migration.app_label = self.app_label
        
        return migration
    
    def _get_next_migration_number(self) -> str:
        """Retorna o próximo número de migração."""
        files = self._get_migration_files()
        if not files:
            return "0001"
        
        last_file = files[-1]
        match = re.match(r"^(\d{4})_", last_file.name)
        if match:
            last_num = int(match.group(1))
            return f"{last_num + 1:04d}"
        
        return f"{len(files) + 1:04d}"
    
    def _column_state_to_def(self, col: ColumnState) -> ColumnDef:
        """Converte ColumnState para ColumnDef."""
        return ColumnDef(
            name=col.name,
            type=col.type,
            nullable=col.nullable,
            default=col.default,
            primary_key=col.primary_key,
            autoincrement=col.autoincrement,
            unique=col.unique,
            index=col.index,
        )
    
    def _diff_to_operations(self, diff: SchemaDiff) -> list[Operation]:
        """Converte SchemaDiff em lista de operações."""
        operations: list[Operation] = []
        
        # Criar tabelas
        for table in diff.tables_to_create:
            columns = [self._column_state_to_def(col) for col in table.columns.values()]
            foreign_keys = [
                ForeignKeyDef(
                    column=fk.column,
                    references_table=fk.references_table,
                    references_column=fk.references_column,
                    on_delete=fk.on_delete,
                )
                for fk in table.foreign_keys
            ]
            operations.append(CreateTable(
                table_name=table.name,
                columns=columns,
                foreign_keys=foreign_keys,
            ))
        
        # Adicionar colunas
        for table_name, columns in diff.columns_to_add.items():
            for col in columns:
                operations.append(AddColumn(
                    table_name=table_name,
                    column=self._column_state_to_def(col),
                ))
        
        # Remover colunas
        for table_name, col_names in diff.columns_to_drop.items():
            for col_name in col_names:
                operations.append(DropColumn(
                    table_name=table_name,
                    column_name=col_name,
                ))
        
        # Alterar colunas
        for table_name, alterations in diff.columns_to_alter.items():
            for old_col, new_col in alterations:
                # Ignora alterações em colunas de chave primária
                # (PKs não devem ter nullable alterado)
                if old_col.primary_key or new_col.primary_key:
                    continue
                
                col_diff = old_col.diff(new_col)
                if col_diff:
                    operations.append(AlterColumn(
                        table_name=table_name,
                        column_name=old_col.name,
                        new_type=col_diff.get("type", (None, None))[1],
                        new_nullable=col_diff.get("nullable", (None, None))[1],
                        new_default=col_diff.get("default", (None, None))[1],
                        old_type=col_diff.get("type", (None, None))[0],
                        old_nullable=col_diff.get("nullable", (None, None))[0],
                        old_default=col_diff.get("default", (None, None))[0],
                    ))
        
        # Remover tabelas (por último para evitar problemas de FK)
        for table_name in diff.tables_to_drop:
            operations.append(DropTable(table_name=table_name))
        
        return operations
    
    def _generate_migration_code(
        self,
        name: str,
        operations: list[Operation],
        dependencies: list[tuple[str, str]] | None = None,
    ) -> str:
        """Gera código Python para uma migração."""
        deps = dependencies or []
        deps_str = repr(deps)
        
        ops_code = []
        for op in operations:
            if hasattr(op, "to_code"):
                ops_code.append(f"    {op.to_code()}")
            else:
                ops_code.append(f"    # {op.describe()}")
        
        ops_str = ",\n".join(ops_code) if ops_code else "    # No operations"
        
        return f'''"""
Migration: {name}
Generated at: {timezone.now().isoformat()}
"""

from core.migrations import (
    Migration,
    CreateTable,
    DropTable,
    AddColumn,
    DropColumn,
    AlterColumn,
    RenameColumn,
    CreateIndex,
    DropIndex,
    RunSQL,
    RunPython,
)
from core.migrations.operations import ColumnDef, ForeignKeyDef


migration = Migration(
    name="{name}",
    dependencies={deps_str},
    operations=[
{ops_str}
    ],
)
'''
    
    async def detect_changes(
        self,
        models: list[type["Model"]],
    ) -> SchemaDiff:
        """Detecta mudanças entre models e banco de dados."""
        # Estado atual dos models
        models_state = models_to_schema_state(models)
        
        # Estado atual do banco
        async with self._engine.connect() as conn:
            db_state = await get_database_schema_state(conn)
        
        # Calcula diferenças
        return db_state.diff(models_state)
    
    async def makemigrations(
        self,
        models: list[type["Model"]],
        name: str | None = None,
        empty: bool = False,
        dry_run: bool = False,
    ) -> str | None:
        """
        Detecta mudanças e gera arquivo de migração.
        
        Args:
            models: Lista de classes Model
            name: Nome descritivo da migração (opcional)
            empty: Se True, cria migração vazia
            dry_run: Se True, apenas mostra o que seria gerado
            
        Returns:
            Caminho do arquivo gerado ou None se não houver mudanças
        """
        if empty:
            operations = []
        else:
            diff = await self.detect_changes(models)
            
            if not diff.has_changes:
                print("No changes detected.")
                return None
            
            operations = self._diff_to_operations(diff)
        
        # Gera nome da migração
        number = self._get_next_migration_number()
        migration_name = f"{number}_{name or 'auto'}"
        
        # Dependências (última migração aplicada)
        files = self._get_migration_files()
        dependencies = []
        if files:
            last_migration = files[-1].stem
            dependencies = [(self.app_label, last_migration)]
        
        # Gera código
        code = self._generate_migration_code(migration_name, operations, dependencies)
        
        if dry_run:
            print(f"Would create migration: {migration_name}")
            print("-" * 50)
            print(code)
            return None
        
        # Cria diretório se não existir
        self.migrations_dir.mkdir(parents=True, exist_ok=True)
        
        # Cria __init__.py se não existir
        init_file = self.migrations_dir / "__init__.py"
        if not init_file.exists():
            init_file.write_text('"""Migrations package."""\n')
        
        # Salva arquivo
        file_path = self.migrations_dir / f"{migration_name}.py"
        file_path.write_text(code)
        
        print(f"Created migration: {file_path}")
        
        # Mostra operações
        for op in operations:
            print(f"  - {op.describe()}")
        
        return str(file_path)
    
    async def migrate(
        self,
        target: str | None = None,
        fake: bool = False,
        dry_run: bool = False,
        check: bool = True,
        interactive: bool = True,
    ) -> list[str]:
        """
        Aplica migrações pendentes.
        
        Args:
            target: Nome da migração alvo (aplica até ela)
            fake: Se True, marca como aplicada sem executar
            dry_run: Se True, apenas mostra o que seria executado
            check: Se True, analisa migrações antes de aplicar
            interactive: Se True, pergunta antes de prosseguir com problemas
            
        Returns:
            Lista de migrações aplicadas
        """
        from core.migrations.analyzer import (
            MigrationAnalyzer,
            format_analysis_report,
            Severity,
        )
        
        applied = []
        
        async with self._engine.connect() as conn:
            await self._ensure_migrations_table(conn)
            
            applied_migrations = await self._get_applied_migrations(conn)
            applied_set = {(app, name) for app, name in applied_migrations}
            
            migration_files = self._get_migration_files()
            
            # Coleta migrações pendentes
            pending_migrations = []
            for file_path in migration_files:
                migration_name = file_path.stem
                
                if (self.app_label, migration_name) in applied_set:
                    continue
                
                if target and migration_name > target:
                    break
                
                pending_migrations.append((file_path, migration_name))
            
            if not pending_migrations:
                print("No migrations to apply.")
                return applied
            
            # Analisa todas as migrações pendentes
            if check and not fake:
                analyzer = MigrationAnalyzer(dialect=self.dialect)
                all_issues = []
                all_results = []
                
                print("\nChecking migrations...")
                
                for file_path, migration_name in pending_migrations:
                    migration = self._load_migration(file_path)
                    result = await analyzer.analyze(
                        migration.operations,
                        conn,
                        migration_name,
                    )
                    all_results.append(result)
                    all_issues.extend(result.issues)
                
                # Verifica se pode prosseguir
                has_errors = any(
                    i.severity in (Severity.ERROR, Severity.CRITICAL)
                    for i in all_issues
                )
                has_warnings = any(
                    i.severity == Severity.WARNING
                    for i in all_issues
                )
                
                # Mostra resultados
                for result in all_results:
                    print(format_analysis_report(result))
                
                if has_errors:
                    print("\nBlocked: Fix the errors above before migrating.")
                    print("Options:")
                    print("  1. Edit the migration file to fix the issues")
                    print("  2. Use --no-check to skip (not recommended)")
                    print("  3. Use --fake to mark as applied without executing")
                    return []
                
                if has_warnings and interactive:
                    try:
                        response = input("\nProceed with warnings? [y/N]: ").strip().lower()
                        if response not in ("y", "yes"):
                            print("Cancelled.")
                            return []
                    except (EOFError, KeyboardInterrupt):
                        print("\nCancelled.")
                        return []
                
                if all_issues and not has_errors:
                    print()  # Linha em branco antes de aplicar
            
            # Aplica migrações
            print("\nApplying migrations...")
            for file_path, migration_name in pending_migrations:
                migration = self._load_migration(file_path)
                
                if dry_run:
                    print(f"  {migration_name} (dry-run)")
                    for op in migration.operations:
                        print(f"    - {op.describe()}")
                    applied.append(migration_name)
                    continue
                
                print(f"  {migration_name}...", end=" ", flush=True)
                
                if not fake:
                    for op in migration.operations:
                        await op.forward(conn, self.dialect)
                
                await self._mark_migration_applied(conn, self.app_label, migration_name)
                await conn.commit()
                
                applied.append(migration_name)
                print("OK")
        
        if applied:
            print(f"\nDone. Applied {len(applied)} migration(s).")
        
        return applied
    
    async def rollback(
        self,
        target: str | None = None,
        fake: bool = False,
        dry_run: bool = False,
    ) -> list[str]:
        """
        Reverte migrações.
        
        Args:
            target: Nome da migração alvo (reverte até ela, exclusive)
            fake: Se True, desmarca sem executar
            dry_run: Se True, apenas mostra o que seria executado
            
        Returns:
            Lista de migrações revertidas
        """
        reverted = []
        
        async with self._engine.connect() as conn:
            applied_migrations = await self._get_applied_migrations(conn)
            
            # Reverte na ordem inversa
            for app, name in reversed(applied_migrations):
                if app != self.app_label:
                    continue
                
                if target and name <= target:
                    break
                
                file_path = self.migrations_dir / f"{name}.py"
                if not file_path.exists():
                    print(f"Warning: Migration file not found: {file_path}")
                    continue
                
                migration = self._load_migration(file_path)
                
                if not migration.is_reversible:
                    raise RuntimeError(
                        f"Migration {name} is not reversible. "
                        "Cannot rollback."
                    )
                
                if dry_run:
                    print(f"Would rollback: {name}")
                    for op in reversed(migration.operations):
                        print(f"  - Reverse: {op.describe()}")
                    reverted.append(name)
                    continue
                
                print(f"Rolling back {name}...")
                
                if not fake:
                    for op in reversed(migration.operations):
                        print(f"  - Reverse: {op.describe()}")
                        await op.backward(conn, self.dialect)
                
                await self._unmark_migration_applied(conn, self.app_label, name)
                await conn.commit()
                
                reverted.append(name)
                print(f"  OK")
                
                # Se não especificou target, reverte apenas uma
                if target is None:
                    break
        
        if not reverted:
            print("No migrations to rollback.")
        
        return reverted
    
    async def showmigrations(self) -> dict[str, list[tuple[str, bool]]]:
        """
        Mostra status das migrações.
        
        Returns:
            Dict com app_label -> lista de (nome, aplicada)
        """
        result: dict[str, list[tuple[str, bool]]] = {self.app_label: []}
        
        async with self._engine.connect() as conn:
            await self._ensure_migrations_table(conn)
            applied_migrations = await self._get_applied_migrations(conn)
            applied_set = {(app, name) for app, name in applied_migrations}
        
        migration_files = self._get_migration_files()
        
        print(f"\n{self.app_label}:")
        for file_path in migration_files:
            name = file_path.stem
            is_applied = (self.app_label, name) in applied_set
            status = "[X]" if is_applied else "[ ]"
            print(f"  {status} {name}")
            result[self.app_label].append((name, is_applied))
        
        if not migration_files:
            print("  (no migrations)")
        
        return result
    
    async def squash(
        self,
        start: str,
        end: str,
        name: str | None = None,
    ) -> str | None:
        """
        Combina múltiplas migrações em uma só.
        
        Args:
            start: Nome da primeira migração
            end: Nome da última migração
            name: Nome da migração combinada
            
        Returns:
            Caminho do arquivo gerado
        """
        migration_files = self._get_migration_files()
        
        # Encontra migrações no range
        migrations_to_squash = []
        in_range = False
        
        for file_path in migration_files:
            migration_name = file_path.stem
            
            if migration_name == start:
                in_range = True
            
            if in_range:
                migration = self._load_migration(file_path)
                migrations_to_squash.append(migration)
            
            if migration_name == end:
                break
        
        if not migrations_to_squash:
            print(f"No migrations found between {start} and {end}")
            return None
        
        # Combina operações
        all_operations = []
        for migration in migrations_to_squash:
            all_operations.extend(migration.operations)
        
        # Otimiza operações (remove redundâncias)
        optimized = self._optimize_operations(all_operations)
        
        # Gera nova migração
        number = self._get_next_migration_number()
        squash_name = f"{number}_{name or 'squashed'}"
        
        code = self._generate_migration_code(squash_name, optimized, [])
        
        file_path = self.migrations_dir / f"{squash_name}.py"
        file_path.write_text(code)
        
        print(f"Created squashed migration: {file_path}")
        print(f"  Squashed {len(migrations_to_squash)} migrations into 1")
        print(f"  Operations: {len(all_operations)} -> {len(optimized)}")
        
        return str(file_path)
    
    def _optimize_operations(self, operations: list[Operation]) -> list[Operation]:
        """Otimiza lista de operações removendo redundâncias."""
        # Implementação básica - pode ser expandida
        optimized = []
        
        created_tables: set[str] = set()
        dropped_tables: set[str] = set()
        
        for op in operations:
            if isinstance(op, CreateTable):
                if op.table_name in dropped_tables:
                    # Tabela foi criada, dropada e criada de novo
                    dropped_tables.remove(op.table_name)
                created_tables.add(op.table_name)
                optimized.append(op)
            
            elif isinstance(op, DropTable):
                if op.table_name in created_tables:
                    # Tabela foi criada e dropada - remove ambas
                    created_tables.remove(op.table_name)
                    optimized = [
                        o for o in optimized
                        if not (isinstance(o, CreateTable) and o.table_name == op.table_name)
                    ]
                else:
                    dropped_tables.add(op.table_name)
                    optimized.append(op)
            
            else:
                optimized.append(op)
        
        return optimized
