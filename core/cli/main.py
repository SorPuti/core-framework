"""
CLI principal do Core Framework.

Uso:
    core <command> [options]

Comandos:
    init            Inicializa um novo projeto
    makemigrations  Gera arquivos de migração
    migrate         Aplica migrações pendentes
    showmigrations  Mostra status das migrações
    rollback        Reverte migrações
    run             Executa servidor de desenvolvimento
    shell           Abre shell interativo async
    routes          Lista rotas registradas
    version         Mostra versão do framework
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

# Cores para output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def color(text: str, c: str) -> str:
    """Aplica cor ao texto."""
    return f"{c}{text}{Colors.ENDC}"


def success(text: str) -> str:
    return color(text, Colors.GREEN)


def error(text: str) -> str:
    return color(text, Colors.FAIL)


def warning(text: str) -> str:
    return color(text, Colors.WARNING)


def info(text: str) -> str:
    return color(text, Colors.CYAN)


def bold(text: str) -> str:
    return color(text, Colors.BOLD)


# Configuração padrão
DEFAULT_CONFIG = {
    "database_url": "sqlite+aiosqlite:///./app.db",
    "migrations_dir": "./migrations",
    "app_label": "main",
    "models_module": "app.models",
    "app_module": "app.main",
    "host": "0.0.0.0",
    "port": 8000,
}


def load_config() -> dict[str, Any]:
    """Carrega configuração do projeto."""
    config = DEFAULT_CONFIG.copy()
    
    # Tenta carregar de core.toml ou pyproject.toml
    config_file = Path("core.toml")
    if config_file.exists():
        try:
            import tomllib
            with open(config_file, "rb") as f:
                file_config = tomllib.load(f)
                config.update(file_config.get("core", {}))
        except ImportError:
            pass
    
    # Tenta pyproject.toml
    pyproject = Path("pyproject.toml")
    if pyproject.exists():
        try:
            import tomllib
            with open(pyproject, "rb") as f:
                file_config = tomllib.load(f)
                config.update(file_config.get("tool", {}).get("core", {}))
        except ImportError:
            pass
    
    # Variáveis de ambiente sobrescrevem
    if os.environ.get("DATABASE_URL"):
        config["database_url"] = os.environ["DATABASE_URL"]
    if os.environ.get("MIGRATIONS_DIR"):
        config["migrations_dir"] = os.environ["MIGRATIONS_DIR"]
    
    return config


def discover_models(models_module: str) -> list[type]:
    """Descobre models em um módulo."""
    try:
        module = importlib.import_module(models_module)
    except ImportError as e:
        print(error(f"Cannot import models module '{models_module}': {e}"))
        print(info("Tip: Make sure the module exists and is in your PYTHONPATH"))
        return []
    
    from core.models import Model
    
    models = []
    for name in dir(module):
        obj = getattr(module, name)
        if (
            isinstance(obj, type)
            and issubclass(obj, Model)
            and obj is not Model
            and hasattr(obj, "__table__")
        ):
            models.append(obj)
    
    return models


def load_app(app_module: str):
    """Carrega a aplicação FastAPI."""
    try:
        module = importlib.import_module(app_module)
        
        # Procura por 'app' ou 'application'
        app = getattr(module, "app", None) or getattr(module, "application", None)
        
        if app is None:
            print(error(f"No 'app' found in module '{app_module}'"))
            return None
        
        return app
    except ImportError as e:
        print(error(f"Cannot import app module '{app_module}': {e}"))
        return None


# ============================================================
# Comandos
# ============================================================

def cmd_version(args: argparse.Namespace) -> int:
    """Mostra versão do framework."""
    from core import __version__
    print(f"Core Framework {bold(__version__)}")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    """Inicializa um novo projeto."""
    project_name = args.name or "myproject"
    
    print(info(f"Initializing new Core Framework project: {project_name}"))
    
    # Cria estrutura de diretórios
    dirs = [
        project_name,
        f"{project_name}/app",
        f"{project_name}/app/api",
        f"{project_name}/migrations",
        f"{project_name}/tests",
    ]
    
    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)
        print(f"  Created {d}/")
    
    # Cria arquivos
    files = {
        f"{project_name}/app/__init__.py": '"""Application package."""\n',
        f"{project_name}/app/models.py": '''"""
Models da aplicação.
"""

from datetime import datetime
from sqlalchemy.orm import Mapped

from core import Model, Field


class User(Model):
    """Model de usuário."""
    
    __tablename__ = "users"
    
    id: Mapped[int] = Field.pk()
    email: Mapped[str] = Field.string(max_length=255, unique=True)
    name: Mapped[str] = Field.string(max_length=100)
    is_active: Mapped[bool] = Field.boolean(default=True)
    created_at: Mapped[datetime] = Field.datetime(auto_now_add=True)
''',
        f"{project_name}/app/schemas.py": '''"""
Schemas de validação e serialização.
"""

from datetime import datetime
from pydantic import EmailStr

from core import InputSchema, OutputSchema


class UserInput(InputSchema):
    """Schema de entrada para usuário."""
    email: EmailStr
    name: str


class UserOutput(OutputSchema):
    """Schema de saída para usuário."""
    id: int
    email: str
    name: str
    is_active: bool
    created_at: datetime
''',
        f"{project_name}/app/views.py": '''"""
Views e ViewSets.
"""

from core import ModelViewSet
from core.permissions import AllowAny

from app.models import User
from app.schemas import UserInput, UserOutput


class UserViewSet(ModelViewSet):
    """ViewSet para usuários."""
    
    model = User
    input_schema = UserInput
    output_schema = UserOutput
    permission_classes = [AllowAny]
    tags = ["users"]
''',
        f"{project_name}/app/main.py": '''"""
Aplicação principal.
"""

from core import CoreApp, AutoRouter

from app.views import UserViewSet


# Cria router
router = AutoRouter(prefix="/api/v1")
router.register("/users", UserViewSet, basename="user")

# Cria aplicação
app = CoreApp(
    title="My API",
    description="API criada com Core Framework",
    version="1.0.0",
    routers=[router],
)


@app.get("/")
async def root():
    return {"message": "Welcome to My API", "docs": "/docs"}
''',
        f"{project_name}/app/api/__init__.py": '"""API package."""\n',
        f"{project_name}/migrations/__init__.py": '"""Migrations package."""\n',
        f"{project_name}/tests/__init__.py": '"""Tests package."""\n',
        f"{project_name}/core.toml": f'''# Core Framework Configuration

[core]
database_url = "sqlite+aiosqlite:///./app.db"
migrations_dir = "./migrations"
app_label = "main"
models_module = "app.models"
app_module = "app.main"
host = "0.0.0.0"
port = 8000
''',
        f"{project_name}/requirements.txt": '''# Core Framework
core-framework @ git+https://github.com/SorPuti/core-framework.git

# Optional: for production
# uvicorn[standard]
# gunicorn
''',
        f"{project_name}/.gitignore": '''# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
dist/
*.egg-info/
.eggs/

# Virtual environments
.venv/
venv/
ENV/

# Database
*.db
*.sqlite

# IDE
.idea/
.vscode/
*.swp

# Environment
.env
.env.local

# Logs
*.log
''',
    }
    
    for filepath, content in files.items():
        Path(filepath).write_text(content)
        print(f"  Created {filepath}")
    
    print()
    print(success("✓ Project initialized successfully!"))
    print()
    print("Next steps:")
    print(f"  cd {project_name}")
    print("  pip install -r requirements.txt")
    print("  core makemigrations --name initial")
    print("  core migrate")
    print("  core run")
    
    return 0


def cmd_makemigrations(args: argparse.Namespace) -> int:
    """Gera arquivos de migração."""
    config = load_config()
    
    print(info("Detecting model changes..."))
    
    # Adiciona diretório atual ao path
    sys.path.insert(0, os.getcwd())
    
    # Descobre models
    models = discover_models(config["models_module"])
    
    if not models and not args.empty:
        print(warning("No models found."))
        print(info(f"Tip: Check if '{config['models_module']}' exists and contains Model classes"))
        return 1
    
    print(f"  Found {len(models)} model(s): {', '.join(m.__name__ for m in models)}")
    
    # Executa makemigrations
    from core.migrations import makemigrations
    
    async def run():
        return await makemigrations(
            models=models,
            database_url=config["database_url"],
            migrations_dir=config["migrations_dir"],
            app_label=config["app_label"],
            name=args.name,
            empty=args.empty,
            dry_run=args.dry_run,
        )
    
    result = asyncio.run(run())
    
    if result:
        print(success(f"✓ Migration created: {result}"))
    
    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    """Aplica migrações pendentes."""
    config = load_config()
    
    print(info("Applying migrations..."))
    
    from core.migrations import migrate
    
    async def run():
        return await migrate(
            database_url=config["database_url"],
            migrations_dir=config["migrations_dir"],
            app_label=config["app_label"],
            target=args.target,
            fake=args.fake,
            dry_run=args.dry_run,
        )
    
    applied = asyncio.run(run())
    
    if applied:
        print(success(f"✓ Applied {len(applied)} migration(s)"))
    
    return 0


def cmd_showmigrations(args: argparse.Namespace) -> int:
    """Mostra status das migrações."""
    config = load_config()
    
    from core.migrations import showmigrations
    
    async def run():
        return await showmigrations(
            database_url=config["database_url"],
            migrations_dir=config["migrations_dir"],
            app_label=config["app_label"],
        )
    
    asyncio.run(run())
    return 0


def cmd_rollback(args: argparse.Namespace) -> int:
    """Reverte migrações."""
    config = load_config()
    
    print(info("Rolling back migrations..."))
    
    from core.migrations import rollback
    
    async def run():
        return await rollback(
            database_url=config["database_url"],
            migrations_dir=config["migrations_dir"],
            app_label=config["app_label"],
            target=args.target,
            fake=args.fake,
            dry_run=args.dry_run,
        )
    
    reverted = asyncio.run(run())
    
    if reverted:
        print(success(f"✓ Rolled back {len(reverted)} migration(s)"))
    
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Executa servidor de desenvolvimento."""
    config = load_config()
    
    host = args.host or config["host"]
    port = args.port or config["port"]
    app_module = args.app or config["app_module"]
    
    print(info(f"Starting development server at http://{host}:{port}"))
    print(info("Press CTRL+C to stop"))
    print()
    
    try:
        import uvicorn
        uvicorn.run(
            f"{app_module}:app",
            host=host,
            port=port,
            reload=args.reload,
            log_level="info",
        )
    except ImportError:
        print(error("uvicorn not installed. Run: pip install uvicorn"))
        return 1
    except KeyboardInterrupt:
        print()
        print(info("Server stopped."))
    
    return 0


def cmd_shell(args: argparse.Namespace) -> int:
    """Abre shell interativo async."""
    config = load_config()
    
    print(info("Core Framework Interactive Shell"))
    print(info("Type 'exit()' or Ctrl+D to exit"))
    print()
    
    # Adiciona diretório atual ao path
    sys.path.insert(0, os.getcwd())
    
    # Prepara contexto
    context = {
        "asyncio": asyncio,
    }
    
    # Importa core
    try:
        import core
        context["core"] = core
        context.update({
            "Model": core.Model,
            "Field": core.Field,
            "CoreApp": core.CoreApp,
        })
    except ImportError:
        pass
    
    # Importa models
    try:
        models_module = importlib.import_module(config["models_module"])
        context["models"] = models_module
        
        # Adiciona models individuais
        from core.models import Model
        for name in dir(models_module):
            obj = getattr(models_module, name)
            if isinstance(obj, type) and issubclass(obj, Model) and obj is not Model:
                context[name] = obj
    except ImportError:
        pass
    
    # Inicializa banco de dados
    async def init_db():
        from core.models import init_database, get_session
        await init_database(config["database_url"])
        return await get_session()
    
    session = asyncio.run(init_db())
    context["db"] = session
    context["session"] = session
    
    print(f"Available: {', '.join(context.keys())}")
    print()
    
    # Usa IPython se disponível, senão code.interact
    try:
        from IPython import embed
        embed(user_ns=context, colors="neutral")
    except ImportError:
        import code
        
        # Wrapper para executar código async
        class AsyncConsole(code.InteractiveConsole):
            def runsource(self, source, filename="<input>", symbol="single"):
                # Tenta executar como async se começar com await
                if source.strip().startswith("await "):
                    try:
                        coro = eval(source.replace("await ", "", 1), self.locals)
                        result = asyncio.run(coro)
                        if result is not None:
                            print(result)
                        return False
                    except Exception as e:
                        print(error(f"Error: {e}"))
                        return False
                return super().runsource(source, filename, symbol)
        
        console = AsyncConsole(locals=context)
        console.interact(banner="")
    
    return 0


def cmd_routes(args: argparse.Namespace) -> int:
    """Lista rotas registradas."""
    config = load_config()
    
    # Adiciona diretório atual ao path
    sys.path.insert(0, os.getcwd())
    
    app = load_app(config["app_module"])
    if app is None:
        return 1
    
    # Obtém FastAPI app
    from core import CoreApp
    if isinstance(app, CoreApp):
        fastapi_app = app.app
    else:
        fastapi_app = app
    
    print(bold("\nRegistered Routes:\n"))
    print(f"{'Method':<10} {'Path':<40} {'Name':<30}")
    print("-" * 80)
    
    for route in fastapi_app.routes:
        if hasattr(route, "methods"):
            methods = ", ".join(route.methods)
            name = route.name or ""
            print(f"{methods:<10} {route.path:<40} {name:<30}")
    
    print()
    return 0


def cmd_createapp(args: argparse.Namespace) -> int:
    """Cria um novo app/módulo."""
    app_name = args.name
    
    print(info(f"Creating app: {app_name}"))
    
    # Cria estrutura
    dirs = [
        app_name,
        f"{app_name}/api",
    ]
    
    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)
        print(f"  Created {d}/")
    
    files = {
        f"{app_name}/__init__.py": f'"""{app_name} app."""\n',
        f"{app_name}/models.py": f'''"""
Models do app {app_name}.
"""

from sqlalchemy.orm import Mapped
from core import Model, Field


# Defina seus models aqui
''',
        f"{app_name}/schemas.py": f'''"""
Schemas do app {app_name}.
"""

from core import InputSchema, OutputSchema


# Defina seus schemas aqui
''',
        f"{app_name}/views.py": f'''"""
Views do app {app_name}.
"""

from core import ModelViewSet


# Defina seus ViewSets aqui
''',
        f"{app_name}/api/__init__.py": '"""API endpoints."""\n',
        f"{app_name}/api/routes.py": f'''"""
Rotas do app {app_name}.
"""

from core import AutoRouter

# from {app_name}.views import ...

router = AutoRouter(prefix="/{app_name}")

# router.register("/resource", ResourceViewSet)
''',
    }
    
    for filepath, content in files.items():
        Path(filepath).write_text(content)
        print(f"  Created {filepath}")
    
    print()
    print(success(f"✓ App '{app_name}' created successfully!"))
    
    return 0


# ============================================================
# Parser principal
# ============================================================

def create_parser() -> argparse.ArgumentParser:
    """Cria o parser de argumentos."""
    parser = argparse.ArgumentParser(
        prog="core",
        description="Core Framework CLI - Django-inspired, FastAPI-powered",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  core init myproject          Create a new project
  core makemigrations          Generate migrations
  core migrate                 Apply migrations
  core run                     Start development server
  core shell                   Open interactive shell

For more information, visit: https://github.com/SorPuti/core-framework
        """,
    )
    
    parser.add_argument(
        "-v", "--version",
        action="store_true",
        help="Show version",
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # init
    init_parser = subparsers.add_parser("init", help="Initialize a new project")
    init_parser.add_argument("name", nargs="?", help="Project name")
    init_parser.set_defaults(func=cmd_init)
    
    # makemigrations
    make_parser = subparsers.add_parser("makemigrations", help="Generate migration files")
    make_parser.add_argument("-n", "--name", help="Migration name")
    make_parser.add_argument("--empty", action="store_true", help="Create empty migration")
    make_parser.add_argument("--dry-run", action="store_true", help="Show what would be generated")
    make_parser.set_defaults(func=cmd_makemigrations)
    
    # migrate
    migrate_parser = subparsers.add_parser("migrate", help="Apply migrations")
    migrate_parser.add_argument("-t", "--target", help="Target migration name")
    migrate_parser.add_argument("--fake", action="store_true", help="Mark as applied without running")
    migrate_parser.add_argument("--dry-run", action="store_true", help="Show what would be applied")
    migrate_parser.set_defaults(func=cmd_migrate)
    
    # showmigrations
    show_parser = subparsers.add_parser("showmigrations", help="Show migration status")
    show_parser.set_defaults(func=cmd_showmigrations)
    
    # rollback
    rollback_parser = subparsers.add_parser("rollback", help="Rollback migrations")
    rollback_parser.add_argument("-t", "--target", help="Target migration (exclusive)")
    rollback_parser.add_argument("--fake", action="store_true", help="Unmark without running")
    rollback_parser.add_argument("--dry-run", action="store_true", help="Show what would be rolled back")
    rollback_parser.set_defaults(func=cmd_rollback)
    
    # run
    run_parser = subparsers.add_parser("run", help="Run development server")
    run_parser.add_argument("--host", help="Host to bind (default: 0.0.0.0)")
    run_parser.add_argument("-p", "--port", type=int, help="Port to bind (default: 8000)")
    run_parser.add_argument("--app", help="App module (default: app.main)")
    run_parser.add_argument("--reload", action="store_true", default=True, help="Enable auto-reload")
    run_parser.add_argument("--no-reload", action="store_false", dest="reload", help="Disable auto-reload")
    run_parser.set_defaults(func=cmd_run)
    
    # shell
    shell_parser = subparsers.add_parser("shell", help="Open interactive shell")
    shell_parser.set_defaults(func=cmd_shell)
    
    # routes
    routes_parser = subparsers.add_parser("routes", help="List registered routes")
    routes_parser.set_defaults(func=cmd_routes)
    
    # createapp
    createapp_parser = subparsers.add_parser("createapp", help="Create a new app/module")
    createapp_parser.add_argument("name", help="App name")
    createapp_parser.set_defaults(func=cmd_createapp)
    
    # version (também como subcomando)
    version_parser = subparsers.add_parser("version", help="Show version")
    version_parser.set_defaults(func=cmd_version)
    
    return parser


def cli(args: list[str] | None = None) -> int:
    """Executa o CLI."""
    parser = create_parser()
    parsed_args = parser.parse_args(args)
    
    # Se pediu versão via flag
    if parsed_args.version:
        return cmd_version(parsed_args)
    
    # Se não especificou comando
    if not parsed_args.command:
        parser.print_help()
        return 0
    
    # Executa comando
    return parsed_args.func(parsed_args)


def main():
    """Entry point principal."""
    sys.exit(cli())


if __name__ == "__main__":
    main()
