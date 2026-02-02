"""
Interface de linha de comando para migrações.

Funções que podem ser chamadas diretamente ou via CLI.
Todas as funções usam settings automaticamente se parâmetros não forem fornecidos.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from core.migrations.engine import MigrationEngine

if TYPE_CHECKING:
    from core.models import Model


def _get_database_url(database_url: str | None = None) -> str:
    """
    Obtém URL do banco de dados.
    
    Prioridade:
    1. Parâmetro fornecido
    2. Settings (database_url - sempre usa primary para migrations)
    3. Default SQLite
    """
    if database_url is not None:
        return database_url
    
    try:
        from core.config import get_settings
        settings = get_settings()
        # Migrations sempre usam o primary (write), nunca replica
        return settings.database_url
    except Exception:
        return "sqlite+aiosqlite:///./app.db"


async def makemigrations(
    models: list[type["Model"]],
    database_url: str | None = None,
    migrations_dir: str | Path = "./migrations",
    app_label: str = "main",
    name: str | None = None,
    empty: bool = False,
    dry_run: bool = False,
) -> str | None:
    """
    Detecta mudanças nos models e gera arquivo de migração.
    
    Equivalente ao `python manage.py makemigrations` do Django.
    
    Se database_url não for fornecido, usa settings.database_url automaticamente.
    Migrations sempre usam o banco primary (nunca replica).
    
    Args:
        models: Lista de classes Model para verificar
        database_url: URL de conexão (default: settings.database_url)
        migrations_dir: Diretório para salvar migrações
        app_label: Label do app (usado para namespacing)
        name: Nome descritivo da migração
        empty: Se True, cria migração vazia
        dry_run: Se True, apenas mostra o que seria gerado
        
    Returns:
        Caminho do arquivo gerado ou None
        
    Exemplo:
        from core.migrations import makemigrations
        from myapp.models import User, Post
        
        # Usa settings automaticamente
        await makemigrations(models=[User, Post], name="add_user_avatar")
        
        # Ou especifica URL manualmente
        await makemigrations(
            models=[User, Post],
            database_url="postgresql+asyncpg://...",
        )
    """
    engine = MigrationEngine(
        database_url=_get_database_url(database_url),
        migrations_dir=migrations_dir,
        app_label=app_label,
    )
    
    return await engine.makemigrations(
        models=models,
        name=name,
        empty=empty,
        dry_run=dry_run,
    )


async def migrate(
    database_url: str | None = None,
    migrations_dir: str | Path = "./migrations",
    app_label: str = "main",
    target: str | None = None,
    fake: bool = False,
    dry_run: bool = False,
) -> list[str]:
    """
    Aplica migrações pendentes.
    
    Equivalente ao `python manage.py migrate` do Django.
    
    Se database_url não for fornecido, usa settings.database_url automaticamente.
    Migrations sempre usam o banco primary (nunca replica).
    
    Args:
        database_url: URL de conexão (default: settings.database_url)
        migrations_dir: Diretório das migrações
        app_label: Label do app
        target: Nome da migração alvo (aplica até ela)
        fake: Se True, marca como aplicada sem executar
        dry_run: Se True, apenas mostra o que seria executado
        
    Returns:
        Lista de migrações aplicadas
        
    Exemplo:
        from core.migrations import migrate
        
        # Usa settings automaticamente
        await migrate()
        
        # Aplica até uma migração específica
        await migrate(target="0003_add_posts")
        
        # Apenas marca como aplicada (útil para sync manual)
        await migrate(fake=True)
    """
    engine = MigrationEngine(
        database_url=_get_database_url(database_url),
        migrations_dir=migrations_dir,
        app_label=app_label,
    )
    
    return await engine.migrate(
        target=target,
        fake=fake,
        dry_run=dry_run,
    )


async def showmigrations(
    database_url: str | None = None,
    migrations_dir: str | Path = "./migrations",
    app_label: str = "main",
) -> dict[str, list[tuple[str, bool]]]:
    """
    Mostra status das migrações.
    
    Equivalente ao `python manage.py showmigrations` do Django.
    
    Se database_url não for fornecido, usa settings.database_url automaticamente.
    
    Args:
        database_url: URL de conexão (default: settings.database_url)
        migrations_dir: Diretório das migrações
        app_label: Label do app
        
    Returns:
        Dict com app_label -> lista de (nome, aplicada)
        
    Exemplo:
        from core.migrations import showmigrations
        
        # Usa settings automaticamente
        status = await showmigrations()
        # Output:
        # main:
        #   [X] 0001_initial
        #   [X] 0002_add_users
        #   [ ] 0003_add_posts
    """
    engine = MigrationEngine(
        database_url=_get_database_url(database_url),
        migrations_dir=migrations_dir,
        app_label=app_label,
    )
    
    return await engine.showmigrations()


async def rollback(
    database_url: str | None = None,
    migrations_dir: str | Path = "./migrations",
    app_label: str = "main",
    target: str | None = None,
    fake: bool = False,
    dry_run: bool = False,
) -> list[str]:
    """
    Reverte migrações.
    
    Equivalente ao `python manage.py migrate app_name zero` do Django.
    
    Se database_url não for fornecido, usa settings.database_url automaticamente.
    Migrations sempre usam o banco primary (nunca replica).
    
    Args:
        database_url: URL de conexão (default: settings.database_url)
        migrations_dir: Diretório das migrações
        app_label: Label do app
        target: Nome da migração alvo (reverte até ela, exclusive)
        fake: Se True, desmarca sem executar
        dry_run: Se True, apenas mostra o que seria executado
        
    Returns:
        Lista de migrações revertidas
        
    Exemplo:
        from core.migrations import rollback
        
        # Usa settings automaticamente
        await rollback()
        
        # Reverte até uma migração específica
        await rollback(target="0002_add_users")
        
        # Reverte todas as migrações
        await rollback(target="zero")
    """
    engine = MigrationEngine(
        database_url=_get_database_url(database_url),
        migrations_dir=migrations_dir,
        app_label=app_label,
    )
    
    # "zero" significa reverter tudo
    if target == "zero":
        target = ""
    
    return await engine.rollback(
        target=target,
        fake=fake,
        dry_run=dry_run,
    )


async def squash(
    start: str,
    end: str,
    database_url: str | None = None,
    migrations_dir: str | Path = "./migrations",
    app_label: str = "main",
    name: str | None = None,
) -> str | None:
    """
    Combina múltiplas migrações em uma só.
    
    Equivalente ao `python manage.py squashmigrations` do Django.
    
    Se database_url não for fornecido, usa settings.database_url automaticamente.
    
    Args:
        start: Nome da primeira migração
        end: Nome da última migração
        database_url: URL de conexão (default: settings.database_url)
        migrations_dir: Diretório das migrações
        app_label: Label do app
        name: Nome da migração combinada
        
    Returns:
        Caminho do arquivo gerado
        
    Exemplo:
        from core.migrations import squash
        
        # Usa settings automaticamente
        await squash(
            start="0001_initial",
            end="0010_final_changes",
            name="squashed_initial",
        )
    """
    engine = MigrationEngine(
        database_url=_get_database_url(database_url),
        migrations_dir=migrations_dir,
        app_label=app_label,
    )
    
    return await engine.squash(start, end, name)


# CLI runner
def run_cli():
    """
    Executa comandos de migração via CLI.
    
    Uso:
        python -m core.migrations makemigrations
        python -m core.migrations migrate
        python -m core.migrations showmigrations
        python -m core.migrations rollback
    """
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Core Framework Migration CLI",
        prog="python -m core.migrations",
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # makemigrations
    make_parser = subparsers.add_parser(
        "makemigrations",
        help="Generate migration files",
    )
    make_parser.add_argument("--name", "-n", help="Migration name")
    make_parser.add_argument("--empty", action="store_true", help="Create empty migration")
    make_parser.add_argument("--dry-run", action="store_true", help="Show what would be generated")
    
    # migrate
    migrate_parser = subparsers.add_parser(
        "migrate",
        help="Apply migrations",
    )
    migrate_parser.add_argument("--target", "-t", help="Target migration")
    migrate_parser.add_argument("--fake", action="store_true", help="Mark as applied without running")
    migrate_parser.add_argument("--dry-run", action="store_true", help="Show what would be applied")
    
    # showmigrations
    subparsers.add_parser(
        "showmigrations",
        help="Show migration status",
    )
    
    # rollback
    rollback_parser = subparsers.add_parser(
        "rollback",
        help="Rollback migrations",
    )
    rollback_parser.add_argument("--target", "-t", help="Target migration")
    rollback_parser.add_argument("--fake", action="store_true", help="Unmark without running")
    rollback_parser.add_argument("--dry-run", action="store_true", help="Show what would be rolled back")
    
    # Common arguments
    for p in [make_parser, migrate_parser, rollback_parser]:
        p.add_argument("--database", "-d", default="sqlite+aiosqlite:///./app.db", help="Database URL")
        p.add_argument("--migrations-dir", "-m", default="./migrations", help="Migrations directory")
        p.add_argument("--app", "-a", default="main", help="App label")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Note: Para makemigrations via CLI, precisaria de uma forma de descobrir models
    # Isso geralmente é feito via configuração ou importação dinâmica
    
    if args.command == "makemigrations":
        print("Error: makemigrations via CLI requires model discovery.")
        print("Use the Python API instead:")
        print("  from core.migrations import makemigrations")
        print("  await makemigrations(models=[User, Post], name='my_migration')")
        sys.exit(1)
    
    elif args.command == "migrate":
        asyncio.run(migrate(
            database_url=args.database,
            migrations_dir=args.migrations_dir,
            app_label=args.app,
            target=args.target,
            fake=args.fake,
            dry_run=args.dry_run,
        ))
    
    elif args.command == "showmigrations":
        asyncio.run(showmigrations(
            database_url=getattr(args, "database", "sqlite+aiosqlite:///./app.db"),
            migrations_dir=getattr(args, "migrations_dir", "./migrations"),
            app_label=getattr(args, "app", "main"),
        ))
    
    elif args.command == "rollback":
        asyncio.run(rollback(
            database_url=args.database,
            migrations_dir=args.migrations_dir,
            app_label=args.app,
            target=args.target,
            fake=args.fake,
            dry_run=args.dry_run,
        ))


if __name__ == "__main__":
    run_cli()
