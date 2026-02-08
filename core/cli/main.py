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
    test            Executa testes com ambiente isolado
    version         Mostra versão do framework

Comando test:
    core test                       # Roda todos os testes em tests/
    core test tests/test_auth.py    # Roda arquivo específico
    core test -v                    # Saída verbosa
    core test --cov                 # Com cobertura de código
    core test -k "test_login"       # Filtrar por keyword
    core test -m unit               # Apenas testes unitários
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
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


# =============================================================================
# Connection Health Checks
# =============================================================================

def check_database_connection(database_url: str) -> bool:
    """
    Check if database is accessible.
    
    Args:
        database_url: Database connection URL
    
    Returns:
        True if connection successful, False otherwise (prints error message)
    """
    import asyncio
    from urllib.parse import urlparse
    
    parsed = urlparse(database_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    
    async def check():
        try:
            # Quick socket check first
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((host, port))
            sock.close()
            
            if result != 0:
                return False, "connection_refused"
            
            # Try actual database connection
            from sqlalchemy.ext.asyncio import create_async_engine
            from sqlalchemy import text
            
            engine = create_async_engine(database_url, pool_pre_ping=True)
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            await engine.dispose()
            return True, None
            
        except socket.gaierror:
            return False, "dns_error"
        except Exception as e:
            error_str = str(e).lower()
            if "authentication" in error_str or "password" in error_str:
                return False, "auth_error"
            return False, "connection_refused"
    
    success, error_type = asyncio.run(check())
    
    if not success:
        print()
        print(error("✗ Database Connection Failed"))
        print()
        print(f"  URL: {database_url}")
        print(f"  Host: {host}:{port}")
        print()
        
        if error_type == "dns_error":
            print(error("  Could not resolve hostname."))
            print()
            print("  Solutions:")
            print("    1. Check if the hostname is correct")
            print("    2. If using Docker, ensure the database container is running")
            print("    3. Try using IP address (127.0.0.1) instead of hostname")
        elif error_type == "auth_error":
            print(error("  Authentication failed."))
            print()
            print("  Solutions:")
            print("    1. Check username and password in DATABASE_URL")
            print("    2. Verify the user has access to the database")
        else:
            print(error("  Could not connect to the database server."))
            print()
            print("  Solutions:")
            print("    1. Start your database: docker compose up -d db")
            print("    2. Check if PostgreSQL/MySQL is running")
            print("    3. Verify DATABASE_URL in .env file")
            print("    4. Check firewall/network settings")
        print()
        return False
    
    return True


def check_kafka_connection(bootstrap_servers: str = None) -> bool:
    """
    Check if Kafka is accessible.
    
    Args:
        bootstrap_servers: Kafka bootstrap servers (uses config if None)
    
    Returns:
        True if connection successful, False otherwise (prints error message)
    """
    from core.config import get_settings
    
    settings = get_settings()
    servers = bootstrap_servers or settings.kafka_bootstrap_servers
    kafka_backend = getattr(settings, "kafka_backend", "aiokafka")
    
    # Parse first server for socket check
    first_server = servers.split(",")[0]
    if ":" in first_server:
        host, port_str = first_server.rsplit(":", 1)
        port = int(port_str)
    else:
        host = first_server
        port = 9092
    
    # Quick socket check
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3)
    
    try:
        result = sock.connect_ex((host, port))
        sock.close()
        
        if result != 0:
            raise ConnectionRefusedError()
        
        return True
        
    except socket.gaierror:
        print()
        print(error("✗ Kafka Connection Failed"))
        print()
        print(f"  Servers: {servers}")
        print()
        print(error("  Could not resolve hostname."))
        print()
        print("  Solutions:")
        print("    1. Check KAFKA_BOOTSTRAP_SERVERS in .env")
        print("    2. If using Docker, ensure Kafka container is running")
        print("    3. Try using IP address instead of hostname")
        print()
        return False
        
    except (ConnectionRefusedError, OSError):
        print()
        print(error("✗ Kafka Connection Failed"))
        print()
        print(f"  Servers: {servers}")
        print(f"  Backend: {kafka_backend}")
        print()
        print(error("  Could not connect to Kafka broker."))
        print()
        print("  Solutions:")
        print("    1. Start Kafka: docker compose up -d kafka zookeeper")
        print("    2. Check KAFKA_BOOTSTRAP_SERVERS in .env")
        print("    3. Verify Kafka is accessible at the configured address")
        print("    4. Check if the port is correct (default: 9092)")
        print()
        return False


def check_required_package(package_name: str, install_cmd: str = None) -> bool:
    """
    Check if a required package is installed.
    
    Args:
        package_name: Name of the package to check
        install_cmd: Install command to show (defaults to pip install package_name)
    
    Returns:
        True if installed, False otherwise (prints error message)
    """
    try:
        __import__(package_name.replace("-", "_"))
        return True
    except ImportError:
        print()
        print(error(f"✗ Missing Dependency: {package_name}"))
        print()
        print(f"  Install with: {install_cmd or f'pip install {package_name}'}")
        print()
        return False


# =============================================================================
# Configuração — delegada ao Settings centralizado
# =============================================================================

def load_config() -> dict[str, Any]:
    """
    Carrega configuração do projeto via Settings centralizado.
    
    Fonte única de verdade: core.config.Settings
    
    Retrocompatibilidade: se core.toml ou pyproject.toml existirem,
    seus valores são lidos como fallback (Settings sempre prevalece).
    
    Retorna dict para compatibilidade com código existente do CLI.
    """
    from core.config import get_settings
    
    settings = get_settings()
    
    # Base: valores do Settings centralizado
    config: dict[str, Any] = {
        "database_url": settings.database_url,
        "migrations_dir": settings.migrations_dir,
        "app_label": settings.app_label,
        "models_module": settings.models_module,
        "workers_module": settings.workers_module,
        "tasks_module": settings.tasks_module,
        "app_module": settings.app_module,
        "host": settings.host,
        "port": settings.port,
        "user_model": getattr(settings, "user_model", None),
    }
    
    # Retrocompatibilidade: merge TOML como fallback para campos
    # não configurados via env vars (Settings prevalece)
    _toml_fallback = _load_toml_config()
    for key, value in _toml_fallback.items():
        if key not in config or config[key] is None:
            config[key] = value
    
    return config


def _load_toml_config() -> dict[str, Any]:
    """
    Carrega configuração de core.toml ou pyproject.toml (fallback).
    
    Mantido para retrocompatibilidade com projetos que usam TOML.
    Settings (.env) é a fonte primária recomendada.
    """
    toml_config: dict[str, Any] = {}
    
    config_file = Path("core.toml")
    if config_file.exists():
        try:
            import tomllib
            with open(config_file, "rb") as f:
                file_config = tomllib.load(f)
                toml_config.update(file_config.get("core", {}))
        except ImportError:
            pass
    
    pyproject = Path("pyproject.toml")
    if pyproject.exists():
        try:
            import tomllib
            with open(pyproject, "rb") as f:
                file_config = tomllib.load(f)
                toml_config.update(file_config.get("tool", {}).get("core", {}))
        except ImportError:
            pass
    
    return toml_config


MODELS_CACHE_FILE = ".core_models_cache.json"


def _get_project_root() -> Path:
    """Find project root (where pyproject.toml or core.toml is)."""
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        if (parent / "pyproject.toml").exists() or (parent / "core.toml").exists():
            return parent
    return cwd


def _scan_for_models(root_dir: Path) -> list[str]:
    """
    Recursively scan for Python files containing Model subclasses.
    
    Looks for patterns like 'class X(Model)' or 'from core.models import Model'.
    """
    model_modules = []
    
    for py_file in root_dir.rglob("*.py"):
        # Skip common non-model directories
        if any(part in py_file.parts for part in [
            "__pycache__", ".venv", "venv", "node_modules", 
            "migrations", ".git", "tests", "test", "site-packages"
        ]):
            continue
        
        try:
            content = py_file.read_text()
            # Quick heuristic: file likely contains models
            if "from core.models import" in content or "from core import Model" in content:
                if "(Model)" in content or "(Model," in content:
                    # Convert path to module
                    rel_path = py_file.relative_to(root_dir)
                    module = str(rel_path.with_suffix("")).replace(os.sep, ".")
                    model_modules.append(module)
        except Exception:
            continue
    
    return model_modules


def _load_models_cache(cache_file: Path) -> dict | None:
    """Load cached model modules if valid."""
    import json
    from datetime import datetime
    
    if not cache_file.exists():
        return None
    
    try:
        data = json.loads(cache_file.read_text())
        # Cache is valid for 1 hour
        cache_time = datetime.fromisoformat(data["timestamp"])
        if (datetime.now() - cache_time).seconds > 3600:
            return None
        return data
    except Exception:
        return None


def _save_models_cache(cache_file: Path, modules: list[str]) -> None:
    """Save discovered modules to cache."""
    import json
    from datetime import datetime
    
    data = {
        "timestamp": datetime.now().isoformat(),
        "modules": modules,
    }
    cache_file.write_text(json.dumps(data, indent=2))


def _get_core_internal_models() -> list[str]:
    """
    Retorna a lista de módulos internos do core-framework que contêm models.
    
    Esses módulos vivem dentro do pacote core (possivelmente em site-packages)
    e NÃO são encontrados pelo scanner de projeto do usuário. Devem sempre
    ser incluídos no discover_models() para que makemigrations/migrate
    detectem automaticamente tabelas internas do framework.
    """
    return [
        "core.admin.models",      # AuditLog, AdminSession, TaskExecution, etc.
        "core.auth.models",       # User, Group, Permission (se existirem)
    ]


def _import_core_module(module_path: str):
    """
    Importa um módulo interno do core-framework com fallback robusto.
    
    Problema: quando o CLI é instalado via pipx ou num venv isolado,
    o pacote `core` já está em sys.modules apontando para o venv,
    e subpacotes como `core.admin` podem não existir nesse venv
    (versão antiga). Nesse caso, tentamos importar diretamente
    do filesystem usando spec_from_file_location.
    """
    import importlib.util
    
    # Tentativa 1: import normal
    try:
        return importlib.import_module(module_path)
    except (ImportError, ModuleNotFoundError):
        pass
    
    # Tentativa 2: localizar o arquivo no pacote core real
    # Resolve o path do core já importado e busca o submodule
    try:
        import core as core_pkg
        core_dir = Path(core_pkg.__file__).parent
        
        # "core.admin.models" → "admin/models.py"
        relative = module_path.replace("core.", "", 1).replace(".", os.sep) + ".py"
        target_file = core_dir / relative
        
        if target_file.exists():
            spec = importlib.util.spec_from_file_location(module_path, target_file)
            if spec and spec.loader:
                # Garantir que o pacote pai está em sys.modules
                parts = module_path.split(".")
                for i in range(1, len(parts)):
                    parent = ".".join(parts[:i])
                    if parent not in sys.modules:
                        parent_path = core_dir / os.sep.join(parts[1:i])
                        parent_init = parent_path / "__init__.py"
                        if parent_init.exists():
                            parent_spec = importlib.util.spec_from_file_location(
                                parent, parent_init,
                                submodule_search_locations=[str(parent_path)]
                            )
                            if parent_spec and parent_spec.loader:
                                parent_mod = importlib.util.module_from_spec(parent_spec)
                                sys.modules[parent] = parent_mod
                                parent_spec.loader.exec_module(parent_mod)
                
                mod = importlib.util.module_from_spec(spec)
                sys.modules[module_path] = mod
                spec.loader.exec_module(mod)
                return mod
    except Exception:
        pass
    
    # Tentativa 3: procurar no diretório de trabalho atual (editable install)
    try:
        cwd_file = Path.cwd() / module_path.replace(".", os.sep) + ".py"
        if cwd_file.exists():
            spec = importlib.util.spec_from_file_location(module_path, cwd_file)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                sys.modules[module_path] = mod
                spec.loader.exec_module(mod)
                return mod
    except Exception:
        pass
    
    return None


def discover_models(models_module: str | list[str] | None = None, rescan: bool = False) -> list[type]:
    """
    Discover all Model subclasses in the project.
    
    Strategy:
    1. Always import core-framework internal models (admin, auth, etc.)
       — these live in site-packages and are invisible to the project scanner.
       Uses _import_core_module() with robust fallback for pipx/isolated venvs.
    2. If models_module provided (string or list), use it directly
    3. Otherwise, check cache file
    4. If no cache or rescan=True, scan project recursively and cache results
    
    Args:
        models_module: Explicit module(s) to import. Can be string or list.
                      If None, auto-discovers models in the project.
        rescan: If True, ignores cache and rescans the project.
    
    Returns:
        List of Model classes ready for migrations.
    """
    from core.models import Model
    
    root_dir = _get_project_root()
    cache_file = root_dir / MODELS_CACHE_FILE
    
    # ── 1. Sempre inclui os models internos do core-framework ──
    # Estes módulos estão dentro do pacote core (ex: site-packages/core/admin/models.py)
    # e não são encontrados pelo _scan_for_models() que varre apenas o projeto do usuário.
    # Usa _import_core_module() para lidar com pipx, venvs isolados, etc.
    core_modules = _get_core_internal_models()
    core_loaded = {}  # module_path → module (já importado)
    
    for mod_path in core_modules:
        mod = _import_core_module(mod_path)
        if mod is not None:
            core_loaded[mod_path] = mod
    
    # Determine which modules to check (user project)
    if models_module:
        # Explicit config - use it
        if isinstance(models_module, str):
            modules_to_check = [models_module]
        else:
            modules_to_check = list(models_module)
    else:
        # Try cache first (unless rescan requested)
        cache = None if rescan else _load_models_cache(cache_file)
        if cache:
            modules_to_check = cache["modules"]
            print(info(f"Using cached model discovery ({len(modules_to_check)} modules)"))
        else:
            # Full scan
            print(info("Scanning project for models..."))
            modules_to_check = _scan_for_models(root_dir)
            if modules_to_check:
                _save_models_cache(cache_file, modules_to_check)
                print(success(f"Found {len(modules_to_check)} model modules, cached for future runs"))
            else:
                print(warning("No model modules found. Make sure your models inherit from core.models.Model"))
    
    # ── Coletar models dos módulos core já carregados ──
    models = []
    core_model_count = 0
    
    for mod_path, module in core_loaded.items():
        for name in dir(module):
            obj = getattr(module, name)
            if (
                isinstance(obj, type)
                and issubclass(obj, Model)
                and obj is not Model
                and hasattr(obj, "__table__")
            ):
                if obj not in models:
                    models.append(obj)
                    core_model_count += 1
    
    if core_model_count:
        print(info(f"Included {core_model_count} core-framework internal model(s)"))
    
    # ── Coletar models do projeto do usuário ──
    for module_path in modules_to_check:
        # Skip se já foi carregado como core module
        if module_path in core_loaded:
            continue
        try:
            module = importlib.import_module(module_path)
            for name in dir(module):
                obj = getattr(module, name)
                if (
                    isinstance(obj, type)
                    and issubclass(obj, Model)
                    and obj is not Model
                    and hasattr(obj, "__table__")
                ):
                    # Avoid duplicates (same model imported in multiple places)
                    if obj not in models:
                        models.append(obj)
        except ImportError as e:
            print(warning(f"Cannot import '{module_path}': {e}"))
            continue
    
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


def cmd_test(args: argparse.Namespace) -> int:
    """
    Run tests with auto-discovery and isolated environment.
    
    This command:
    - Automatically sets up an isolated test environment
    - Initializes database with in-memory SQLite
    - Configures auth, settings, and middleware
    - Runs pytest with appropriate options
    - Supports coverage reporting
    
    Usage:
        core test                    # Run all tests in tests/
        core test tests/test_auth.py # Run specific file
        core test -v                 # Verbose output
        core test --cov              # With coverage
        core test -k "test_login"    # Filter by keyword
        core test -m unit            # Only unit tests
    """
    import subprocess
    import shutil
    
    # Check if pytest is installed
    pytest_path = shutil.which("pytest")
    if not pytest_path:
        print(error("pytest not installed. Install with:"))
        print(info("  pip install pytest pytest-asyncio"))
        return 1
    
    print(bold("🧪 Core Framework Test Runner"))
    print()
    
    # Build pytest command
    cmd = ["python", "-m", "pytest"]
    
    # Add test path
    cmd.append(args.path)
    
    # Verbose
    if args.verbose:
        cmd.append("-v")
    
    # Keyword filter
    if args.keyword:
        cmd.extend(["-k", args.keyword])
    
    # Exit on first failure
    if args.exitfirst:
        cmd.append("-x")
    
    # Marker filter
    if args.marker:
        cmd.extend(["-m", args.marker])
    
    # No header
    if args.no_header:
        cmd.append("--no-header")
    
    # Coverage
    if args.cov:
        # Check if pytest-cov is installed
        if not shutil.which("pytest-cov") and not _check_pytest_cov():
            print(warning("pytest-cov not installed. Install with:"))
            print(info("  pip install pytest-cov"))
            print()
        
        cmd.append(f"--cov={args.cov}")
        cmd.append(f"--cov-report={args.cov_report}")
    
    # Always use asyncio mode auto
    cmd.extend(["--asyncio-mode=auto"])
    
    # Show short traceback
    cmd.append("--tb=short")
    
    print(info(f"Running: {' '.join(cmd)}"))
    print()
    
    # Set environment variables for isolated testing
    env = os.environ.copy()
    env["TESTING"] = "true"
    env["DEBUG"] = "true"
    env.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    env.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")
    
    # Run pytest
    try:
        result = subprocess.run(cmd, env=env)
        return result.returncode
    except KeyboardInterrupt:
        print(warning("\nTests interrupted"))
        return 130
    except Exception as e:
        print(error(f"Error running tests: {e}"))
        return 1


def _check_pytest_cov() -> bool:
    """Check if pytest-cov is installed as a module."""
    try:
        import pytest_cov
        return True
    except ImportError:
        return False


def check_uv_installed() -> bool:
    """Verifica se uv está instalado."""
    import shutil
    return shutil.which("uv") is not None


def install_uv() -> bool:
    """Instala uv se não estiver instalado."""
    import subprocess
    
    print(info("Installing uv package manager..."))
    
    try:
        # Tenta instalar via curl (método oficial)
        result = subprocess.run(
            ["curl", "-LsSf", "https://astral.sh/uv/install.sh"],
            capture_output=True,
            text=True,
        )
        
        if result.returncode == 0:
            # Executa o script de instalação
            install_result = subprocess.run(
                ["sh", "-c", result.stdout],
                capture_output=True,
                text=True,
            )
            
            if install_result.returncode == 0:
                print(success("  ✓ uv installed successfully"))
                return True
        
        # Fallback: tenta via pip
        print(info("  Trying pip install..."))
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "uv"],
            check=True,
            capture_output=True,
        )
        print(success("  ✓ uv installed via pip"))
        return True
        
    except Exception as e:
        print(error(f"  Failed to install uv: {e}"))
        print(info("  Please install manually: curl -LsSf https://astral.sh/uv/install.sh | sh"))
        return False


def show_template_menu() -> str | None:
    """Show interactive menu to select a template."""
    from core.cli.templates import list_available_templates, get_template_metadata
    
    # Try interactive menu first
    try:
        from core.cli.interactive import InteractiveMenu, is_interactive
        
        if is_interactive():
            templates = list_available_templates()
            template_items = []
            for name in templates:
                meta = get_template_metadata(name)
                template_items.append({
                    "value": name,
                    "name": meta["name"],
                    "description": meta["description"],
                    "features": meta.get("features", []),
                    "recommended_for": meta.get("recommended_for", ""),
                })
            
            menu = InteractiveMenu(
                title="📦 Select Template",
                items=template_items,
                show_details=True,
            )
            
            result = menu.run()
            return result["value"] if result else None
    except Exception:
        pass  # Fallback to simple menu
    
    # Fallback: simple numbered menu
    templates = list_available_templates()
    
    print(bold("\n📦 Available Templates:\n"))
    print("-" * 60)
    
    for i, name in enumerate(templates, 1):
        meta = get_template_metadata(name)
        print(f"\n  {bold(f'[{i}]')} {bold(meta['name'])}")
        print(f"      {meta['description']}")
        print(f"      {info('Features:')}")
        for feature in meta.get('features', [])[:4]:
            print(f"        • {feature}")
        if meta.get('recommended_for'):
            print(f"      {warning('Best for:')} {meta['recommended_for']}")
    
    print("\n" + "-" * 60)
    print(f"  {bold('[0]')} Cancel")
    print()
    
    try:
        choice = input(info("Select template [1]: ")).strip()
        if not choice:
            choice = "1"
        
        if choice == "0":
            return None
        
        idx = int(choice) - 1
        if 0 <= idx < len(templates):
            return templates[idx]
        else:
            print(error("Invalid choice."))
            return None
    except (ValueError, KeyboardInterrupt, EOFError):
        print()
        return None


def show_python_menu() -> str | None:
    """Show interactive menu to select Python version."""
    try:
        from core.cli.interactive import InteractiveInput, get_installed_python_versions, get_available_python_versions, is_interactive
        
        if not is_interactive():
            return None
        
        installed = get_installed_python_versions()
        
        if installed:
            version_input = InteractiveInput(
                prompt="🐍 Select Python Version",
                suggestions=installed[:6],
                default=installed[0] if installed else "3.12",
            )
            return version_input.run()
        else:
            # Show available versions to install
            available = get_available_python_versions()
            if available:
                version_input = InteractiveInput(
                    prompt="🐍 Select Python Version (will be installed)",
                    suggestions=available[:6],
                    default="3.12",
                )
                return version_input.run()
    except Exception:
        pass
    
    return None


def ensure_python_version(python_version: str) -> bool:
    """Ensure the requested Python version is available via uv."""
    import subprocess
    
    print(info(f"\nChecking Python {python_version}..."))
    
    try:
        # Try to find the Python version
        result = subprocess.run(
            ["uv", "python", "find", python_version],
            capture_output=True,
            text=True,
        )
        
        if result.returncode == 0:
            print(success(f"  ✓ Python {python_version} found"))
            return True
        
        # Not found, try to install
        print(info(f"  Installing Python {python_version}..."))
        result = subprocess.run(
            ["uv", "python", "install", python_version],
            capture_output=True,
            text=True,
        )
        
        if result.returncode == 0:
            print(success(f"  ✓ Python {python_version} installed"))
            return True
        else:
            print(warning(f"  Could not install Python {python_version}"))
            print(info(f"  {result.stderr.strip()}"))
            return False
            
    except FileNotFoundError:
        print(warning("  uv not found, skipping Python check"))
        return False
    except Exception as e:
        print(warning(f"  Error: {e}"))
        return False


def cmd_init_from_templates(project_name: str, python_version: str, skip_venv: bool, template_name: str | None = None) -> int:
    """
    Create a new project using external templates.
    
    Templates are stored in core/cli/templates/ and can be customized.
    """
    import subprocess
    from core.cli.templates import load_all_templates, get_template_dirs, get_template_metadata
    
    print(bold("\n🚀 Core Framework - New Project\n"))
    
    # Interactive template selection if not specified
    if template_name is None:
        template_name = show_template_menu()
        if template_name is None:
            print(info("Cancelled."))
            return 0
    
    meta = get_template_metadata(template_name)
    
    print(info(f"Project: {project_name}"))
    print(info(f"Template: {meta['name']}"))
    print(info(f"Python: {python_version}"))
    
    # Ensure uv is installed
    if not skip_venv:
        if not check_uv_installed():
            print(warning("\nuv not found. Installing..."))
            if not install_uv():
                print(error("Failed to install uv."))
                print(info("Install manually: curl -LsSf https://astral.sh/uv/install.sh | sh"))
                skip_venv = True
        
        # Ensure Python version is available
        if not skip_venv:
            if not ensure_python_version(python_version):
                print(warning(f"Python {python_version} not available."))
                try:
                    alt = input(info(f"Continue with system Python? [Y/n]: ")).strip().lower()
                    if alt == 'n':
                        return 1
                except (KeyboardInterrupt, EOFError):
                    print()
                    return 1
    
    # Template context
    context = {
        "project_name": project_name,
        "python_version": python_version,
    }
    
    # Create directory structure
    print(info("\nCreating project structure..."))
    Path(project_name).mkdir(parents=True, exist_ok=True)
    print(f"  📁 {project_name}/")
    
    for dir_path in get_template_dirs(template_name):
        full_path = Path(project_name) / dir_path
        full_path.mkdir(parents=True, exist_ok=True)
        print(f"  📁 {project_name}/{dir_path}/")
    
    # Create migrations dir
    (Path(project_name) / "migrations").mkdir(parents=True, exist_ok=True)
    print(f"  📁 {project_name}/migrations/")
    
    # Load and write template files
    print(info("\nCreating files..."))
    files = load_all_templates(template_name, context)
    
    for file_path, content in files.items():
        full_path = Path(project_name) / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
        print(f"  📄 {project_name}/{file_path}")
    
    # Setup virtual environment
    if not skip_venv:
        print(info("\nSetting up virtual environment..."))
        project_path = Path(project_name).absolute()
        
        try:
            subprocess.run(
                ["uv", "venv", "--python", python_version],
                cwd=project_path,
                check=True,
                capture_output=True,
            )
            print(success("  ✓ Virtual environment created"))
            
            subprocess.run(
                ["uv", "sync"],
                cwd=project_path,
                check=True,
                capture_output=True,
            )
            print(success("  ✓ Dependencies installed"))
            
        except subprocess.CalledProcessError as e:
            print(warning(f"  Warning: {e}"))
            print(info(f"  Run manually: cd {project_name} && uv sync"))
    
    # Final message
    print()
    print(success("=" * 60))
    print(success(f"✓ Project '{project_name}' created!"))
    print(success("=" * 60))
    print()
    
    # Template-specific instructions
    print(bold("Next steps:\n"))
    
    # Check if docker-compose exists
    has_docker = (Path(project_name) / "docker-compose.yml").exists()
    
    step = 1
    print(f"  {step}. cd {project_name}")
    step += 1
    
    if has_docker:
        print(f"  {step}. docker-compose up -d  # Start services")
        step += 1
    
    if not skip_venv:
        print(f"  {step}. source .venv/bin/activate")
        step += 1
    else:
        print(f"  {step}. uv sync && source .venv/bin/activate")
        step += 1
    
    print(f"  {step}. core makemigrations --name initial")
    step += 1
    print(f"  {step}. core migrate")
    step += 1
    print(f"  {step}. core run")
    
    print()
    print(f"  Open: {bold('http://localhost:8000/docs')}")
    print()
    
    # Show features
    print(info(f"Template: {meta['name']}"))
    for feature in meta.get('features', []):
        print(f"  • {feature}")
    print()
    
    print(info(f"Customize: core/cli/templates/{template_name}/"))
    print()
    
    return 0


def cmd_templates(args: argparse.Namespace) -> int:
    """List available project templates."""
    from core.cli.templates import get_all_templates_metadata
    
    print(bold("\n📦 Available Project Templates\n"))
    print("-" * 65)
    
    for name, meta in get_all_templates_metadata().items():
        print(f"\n  {bold(name)}")
        print(f"  {meta['description']}")
        print(f"  {info('Features:')}")
        for feature in meta.get('features', []):
            print(f"    • {feature}")
        if meta.get('recommended_for'):
            print(f"  {warning('Best for:')} {meta['recommended_for']}")
    
    print("\n" + "-" * 65)
    print(f"\n{info('Usage:')}")
    print(f"  core init myproject --template <name>")
    print(f"  core init myproject  # Interactive menu")
    print()
    
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    """
    Inicializa um novo projeto usando templates externos.
    
    Templates estão em: core/cli/templates/
    - minimal: CRUD simples com SQLite
    - default: Auth + Users + PostgreSQL
    - kafka: Event-driven com Kafka + Redis
    - tenant: Multi-tenant com isolamento de dados
    - workers: Background tasks com Redis
    
    Para customizar, edite os arquivos .template no diretório de templates.
    """
    skip_venv = args.no_venv
    
    # Check if running with explicit arguments
    has_explicit_template = getattr(args, "minimal", False) or getattr(args, "template", None)
    has_explicit_name = args.name is not None
    has_explicit_python = args.python is not None
    
    # If no explicit arguments, try full interactive wizard
    if not has_explicit_template and not has_explicit_name and not has_explicit_python:
        try:
            from core.cli.interactive import interactive_project_setup, is_interactive
            
            if is_interactive():
                result = interactive_project_setup()
                if result is None:
                    return 0
                
                return cmd_init_from_templates(
                    result["project_name"],
                    result["python_version"],
                    skip_venv,
                    result["template"],
                )
        except Exception as e:
            # Debug: print exception in verbose mode
            import os
            if os.environ.get("DEBUG"):
                print(f"Interactive mode failed: {e}")
            pass  # Fallback to simple mode
    
    # Simple mode with arguments
    project_name = args.name or "myproject"
    python_version = args.python or "3.12"
    
    # Determine template from flags
    template_name = None
    if getattr(args, "minimal", False):
        template_name = "minimal"
    elif getattr(args, "template", None):
        template_name = args.template
    # If no template specified, show interactive menu
    
    return cmd_init_from_templates(project_name, python_version, skip_venv, template_name)


def cmd_makemigrations(args: argparse.Namespace) -> int:
    """Gera arquivos de migração usando registry centralizado."""
    from core.registry import ModelRegistry
    
    config = load_config()
    
    print(info("Detecting model changes..."))
    
    # Adiciona diretório atual ao path
    sys.path.insert(0, os.getcwd())
    
    # Usa registry centralizado para descobrir modelos
    registry = ModelRegistry.get_instance()
    models_module = config.get("models_module")
    rescan = getattr(args, "rescan", False)
    
    # Descobre modelos via registry (cache evita re-imports)
    if not models_module or models_module == "app.models":
        models = registry.discover_models(models_module=None, force_rescan=rescan)
    else:
        models = registry.discover_models(models_module=models_module, force_rescan=rescan)
    
    if not models and not args.empty:
        print(warning("No models found."))
        print(info("Tip: Make sure your models inherit from core.models.Model"))
        print(info("     Or set 'models_module' in core.toml/pyproject.toml"))
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
    
    # Check database connection first
    if not check_database_connection(config["database_url"]):
        return 1
    
    print(info("Applying migrations..."))
    
    from core.migrations.engine import MigrationEngine
    
    async def run():
        engine = MigrationEngine(
            database_url=config["database_url"],
            migrations_dir=config["migrations_dir"],
            app_label=config["app_label"],
        )
        return await engine.migrate(
            target=args.target,
            fake=args.fake,
            dry_run=args.dry_run,
            check=not args.no_check,
            interactive=not args.yes,
        )
    
    applied = asyncio.run(run())
    
    if applied:
        print(success(f"✓ Applied {len(applied)} migration(s)"))
    
    return 0


def cmd_showmigrations(args: argparse.Namespace) -> int:
    """Mostra status das migrações."""
    config = load_config()
    
    # Check database connection first
    if not check_database_connection(config["database_url"]):
        return 1
    
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
    
    # Check database connection first
    if not check_database_connection(config["database_url"]):
        return 1
    
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


def cmd_dbinfo(args: argparse.Namespace) -> int:
    """Mostra informações do driver de banco de dados e capacidades."""
    config = load_config()
    
    from core.migrations.cli import dbinfo
    dbinfo(database_url=config["database_url"])
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Analisa migrações pendentes sem aplicar."""
    config = load_config()
    
    # Check database connection first
    if not check_database_connection(config["database_url"]):
        return 1
    
    print(info("Checking pending migrations..."))
    
    from core.migrations.engine import MigrationEngine
    from core.migrations.analyzer import (
        MigrationAnalyzer,
        format_analysis_report,
        Severity,
    )
    
    async def run():
        engine = MigrationEngine(
            database_url=config["database_url"],
            migrations_dir=config["migrations_dir"],
            app_label=config["app_label"],
        )
        
        analyzer = MigrationAnalyzer(dialect=engine.dialect)
        
        async with engine._engine.connect() as conn:
            await engine._ensure_migrations_table(conn)
            
            applied_migrations = await engine._get_applied_migrations(conn)
            applied_set = {(app, name) for app, name in applied_migrations}
            
            migration_files = engine._get_migration_files()
            
            total_issues = []
            pending_count = 0
            
            for file_path in migration_files:
                migration_name = file_path.stem
                
                if (engine.app_label, migration_name) in applied_set:
                    continue
                
                pending_count += 1
                
                # Try to load migration with error handling for syntax errors
                try:
                    migration = engine._load_migration(file_path)
                except SyntaxError as e:
                    print(error(f"\n  {migration_name}: SYNTAX ERROR"))
                    print(error(f"    File: {file_path}"))
                    print(error(f"    Line {e.lineno}: {e.msg}"))
                    if e.text:
                        print(error(f"    {e.text.strip()}"))
                    print(warning(f"    Fix the syntax error and run check again."))
                    total_issues.append(type('Issue', (), {
                        'severity': Severity.CRITICAL,
                        'message': f"Syntax error in {migration_name}: {e.msg}"
                    })())
                    continue
                except Exception as e:
                    print(error(f"\n  {migration_name}: LOAD ERROR"))
                    print(error(f"    {type(e).__name__}: {e}"))
                    print(warning(f"    Fix the error and run check again."))
                    total_issues.append(type('Issue', (), {
                        'severity': Severity.CRITICAL,
                        'message': f"Load error in {migration_name}: {e}"
                    })())
                    continue
                
                result = await analyzer.analyze(
                    migration.operations,
                    conn,
                    migration_name,
                )
                
                print(format_analysis_report(result, verbose=getattr(args, 'verbose', False)))
                total_issues.extend(result.issues)
            
            if pending_count == 0:
                print("  No pending migrations.")
                return 0
            
            if not total_issues:
                print(success("\nAll migrations OK."))
                return 0
            
            # Resumo final
            errors = sum(1 for i in total_issues if i.severity == Severity.ERROR)
            critical = sum(1 for i in total_issues if i.severity == Severity.CRITICAL)
            warnings = sum(1 for i in total_issues if i.severity == Severity.WARNING)
            
            print()
            if errors or critical:
                print(error(f"Blocked: {errors + critical} error(s) must be fixed."))
                return 1
            
            if warnings:
                print(warning(f"Ready with {warnings} warning(s). Review before migrating."))
            return 0
    
    return asyncio.run(run())


def cmd_reset_db(args: argparse.Namespace) -> int:
    """
    Reset database completely and recreate framework tables.
    
    WARNING: This destroys ALL data including:
    - All user data
    - All migrations history
    - All framework tables
    
    After reset, it recreates:
    - Framework tables (auth_permissions, auth_groups, etc.)
    - Migrations tracking table
    
    Use only in development or when you need a fresh start.
    """
    config = load_config()
    
    # Check database connection first
    if not check_database_connection(config["database_url"]):
        return 1
    
    print()
    print(error("=" * 60))
    print(error("  WARNING: DATABASE RESET"))
    print(error("=" * 60))
    print()
    print(warning("This will PERMANENTLY DELETE:"))
    print(warning("  - All tables and data"))
    print(warning("  - All migration history"))
    print(warning("  - All users, groups, and permissions"))
    print()
    print(info(f"Database: {config['database_url']}"))
    print()
    
    if not args.yes:
        try:
            confirm = input(error("Type 'yes' to confirm: "))
            if confirm.lower() != 'yes':
                print(info("Aborted."))
                return 0
        except (KeyboardInterrupt, EOFError):
            print()
            print(info("Aborted."))
            return 0
    
    import asyncio
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text, inspect
    
    async def reset():
        engine = create_async_engine(config["database_url"])
        
        async with engine.begin() as conn:
            # Get all tables
            def get_tables(connection):
                inspector = inspect(connection)
                return inspector.get_table_names()
            
            tables = await conn.run_sync(get_tables)
            
            if tables:
                print(info(f"\nDropping {len(tables)} table(s)..."))
                
                # Disable foreign key checks for SQLite
                dialect = engine.dialect.name
                if dialect == "sqlite":
                    await conn.execute(text("PRAGMA foreign_keys = OFF"))
                elif dialect == "postgresql":
                    await conn.execute(text("SET session_replication_role = 'replica'"))
                elif dialect == "mysql":
                    await conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
                
                # Drop all tables with CASCADE for PostgreSQL
                for table in tables:
                    print(f"  Dropping: {table}")
                    try:
                        if dialect == "postgresql":
                            # Use CASCADE to handle foreign key dependencies
                            await conn.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))
                        else:
                            await conn.execute(text(f'DROP TABLE IF EXISTS "{table}"'))
                    except Exception as e:
                        print(warning(f"    Warning: {e}"))
                        # Rollback and continue with new transaction
                        try:
                            await conn.rollback()
                        except Exception:
                            pass
                
                # Re-enable foreign key checks
                if dialect == "sqlite":
                    await conn.execute(text("PRAGMA foreign_keys = ON"))
                elif dialect == "postgresql":
                    await conn.execute(text("SET session_replication_role = 'origin'"))
                elif dialect == "mysql":
                    await conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
            else:
                print(info("\nDatabase is already empty."))
            
        # Create new connection for creating tables (outside transaction for SQLite)
        await engine.dispose()
        
        # Recreate framework tables
        print(info("\nRecreating framework tables..."))
        
        engine = create_async_engine(config["database_url"])
        dialect = engine.dialect.name
        
        async with engine.begin() as conn:
            # Create migrations table
            print("  Creating: _core_migrations")
            if dialect == "sqlite":
                await conn.execute(text('''
                    CREATE TABLE IF NOT EXISTS "_core_migrations" (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        app VARCHAR(255) NOT NULL,
                        name VARCHAR(255) NOT NULL,
                        applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(app, name)
                    )
                '''))
            else:
                # PostgreSQL / MySQL
                await conn.execute(text('''
                    CREATE TABLE IF NOT EXISTS "_core_migrations" (
                        id SERIAL PRIMARY KEY,
                        app VARCHAR(255) NOT NULL,
                        name VARCHAR(255) NOT NULL,
                        applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(app, name)
                    )
                '''))
            
            # Create auth_permissions table
            print("  Creating: auth_permissions")
            if dialect == "sqlite":
                await conn.execute(text('''
                    CREATE TABLE IF NOT EXISTS "auth_permissions" (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        codename VARCHAR(100) NOT NULL UNIQUE,
                        name VARCHAR(255) NOT NULL,
                        description TEXT
                    )
                '''))
            else:
                await conn.execute(text('''
                    CREATE TABLE IF NOT EXISTS "auth_permissions" (
                        id SERIAL PRIMARY KEY,
                        codename VARCHAR(100) NOT NULL UNIQUE,
                        name VARCHAR(255) NOT NULL,
                        description TEXT
                    )
                '''))
            await conn.execute(text('CREATE INDEX IF NOT EXISTS "ix_auth_permissions_codename" ON "auth_permissions" (codename)'))
            
            # Create auth_groups table
            print("  Creating: auth_groups")
            if dialect == "sqlite":
                await conn.execute(text('''
                    CREATE TABLE IF NOT EXISTS "auth_groups" (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name VARCHAR(150) NOT NULL UNIQUE,
                        description TEXT
                    )
                '''))
            else:
                await conn.execute(text('''
                    CREATE TABLE IF NOT EXISTS "auth_groups" (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(150) NOT NULL UNIQUE,
                        description TEXT
                    )
                '''))
            await conn.execute(text('CREATE INDEX IF NOT EXISTS "ix_auth_groups_name" ON "auth_groups" (name)'))
            
            # Create auth_group_permissions table (many-to-many)
            print("  Creating: auth_group_permissions")
            await conn.execute(text('''
                CREATE TABLE IF NOT EXISTS "auth_group_permissions" (
                    group_id INTEGER NOT NULL,
                    permission_id INTEGER NOT NULL,
                    PRIMARY KEY (group_id, permission_id),
                    FOREIGN KEY (group_id) REFERENCES "auth_groups" (id) ON DELETE CASCADE,
                    FOREIGN KEY (permission_id) REFERENCES "auth_permissions" (id) ON DELETE CASCADE
                )
            '''))
        
        # Verify tables were created
        print(info("\nVerifying tables..."))
        
        async with engine.connect() as conn:
            created_tables = await conn.run_sync(get_tables)
        
        expected_tables = ["_core_migrations", "auth_permissions", "auth_groups", "auth_group_permissions"]
        missing_tables = [t for t in expected_tables if t not in created_tables]
        
        if missing_tables:
            print(error(f"\nERROR: Failed to create tables: {', '.join(missing_tables)}"))
            print(error("Please check database permissions and try again."))
            await engine.dispose()
            return 1
        
        print(success(f"  Verified: {len(expected_tables)} framework tables created"))
        for table in expected_tables:
            print(success(f"    ✓ {table}"))
        
        await engine.dispose()
        
        print()
        print(success("Database reset complete."))
        print()
        print(info("Next steps:"))
        print(info("  1. core makemigrations --name initial"))
        print(info("  2. core migrate"))
        print(info("  3. core run"))
        return 0
    
    return asyncio.run(reset())


def cmd_run(args: argparse.Namespace) -> int:
    """Executa servidor de desenvolvimento."""
    config = load_config()
    
    host = args.host or config["host"]
    port = args.port or config["port"]
    app_module = args.app or config["app_module"]
    
    # Adiciona diretório atual ao PYTHONPATH para o Uvicorn encontrar o módulo
    # Isso é necessário porque o Uvicorn com reload spawna um novo processo
    cwd = os.getcwd()
    current_pythonpath = os.environ.get("PYTHONPATH", "")
    if cwd not in current_pythonpath.split(os.pathsep):
        os.environ["PYTHONPATH"] = f"{cwd}{os.pathsep}{current_pythonpath}" if current_pythonpath else cwd
    
    # Também adiciona ao sys.path atual
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    
    print(info(f"Starting development server at http://{host}:{port}"))
    print(info("Press CTRL+C to stop"))
    print()
    
    # Bootstrap settings + models BEFORE uvicorn loads the app.
    # Ensures configure_auth() and project settings load first, avoiding
    # "Table already defined" from circular imports when app loads models.
    from core.config import get_settings
    get_settings()
    
    try:
        import uvicorn
        uvicorn.run(
            f"{app_module}:app",
            host=host,
            port=port,
            reload=args.reload,
            reload_dirs=[cwd] if args.reload else None,
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
    """
    Cria um novo app/módulo dentro da estrutura do projeto.
    
    Estrutura criada:
        src/apps/{app_name}/
        ├── __init__.py
        ├── models.py
        ├── schemas.py
        ├── views.py
        ├── services.py
        ├── routes.py
        └── tests/
            ├── __init__.py
            └── test_{app_name}.py
    """
    app_name = args.name.lower().replace("-", "_")
    
    # Detecta estrutura do projeto
    # Procura por src/apps/ ou apps/ ou cria em src/apps/
    cwd = Path.cwd()
    
    # Possíveis locais para apps
    possible_paths = [
        cwd / "src" / "apps",
        cwd / "apps",
        cwd / "src",
    ]
    
    apps_dir = None
    for path in possible_paths:
        if path.exists() and path.is_dir():
            apps_dir = path
            break
    
    # Se não encontrou, cria em src/apps/
    if apps_dir is None:
        apps_dir = cwd / "src" / "apps"
        apps_dir.mkdir(parents=True, exist_ok=True)
        # Cria __init__.py nos diretórios
        (cwd / "src" / "__init__.py").write_text('"""Source package."""\n')
        (apps_dir / "__init__.py").write_text('"""Apps package."""\n')
        print(info(f"Created apps directory: {apps_dir.relative_to(cwd)}"))
    
    app_dir = apps_dir / app_name
    
    if app_dir.exists():
        print(error(f"App '{app_name}' already exists at {app_dir.relative_to(cwd)}"))
        return 1
    
    print(info(f"Creating app: {app_name}"))
    print(info(f"Location: {app_dir.relative_to(cwd)}/"))
    print()
    
    # Calcula o import path
    try:
        relative_path = app_dir.relative_to(cwd)
        import_path = str(relative_path).replace("/", ".").replace("\\", ".")
    except ValueError:
        import_path = app_name
    
    # Cria estrutura de diretórios
    dirs = [
        app_dir,
        app_dir / "tests",
    ]
    
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    
    # Arquivos do app
    files = {
        app_dir / "__init__.py": f'''"""
{app_name.replace("_", " ").title()} App.

Este módulo contém a lógica do app {app_name}.
"""

from {import_path}.models import *  # noqa: F401, F403
from {import_path}.views import *  # noqa: F401, F403
from {import_path}.routes import router  # noqa: F401

__all__ = ["router"]
''',
        app_dir / "models.py": f'''"""
Models do app {app_name}.

Defina seus models SQLAlchemy aqui.
"""

from sqlalchemy.orm import Mapped

from core import Model, Field
from core import timezone, DateTime


# Exemplo de model
# class {app_name.title().replace("_", "")}(Model):
#     __tablename__ = "{app_name}s"
#     
#     id: Mapped[int] = Field.pk()
#     name: Mapped[str] = Field.string(max_length=255)
#     created_at: Mapped[DateTime] = Field.datetime(auto_now_add=True)
#     updated_at: Mapped[DateTime | None] = Field.datetime(auto_now=True)
''',
        app_dir / "schemas.py": f'''"""
Schemas Pydantic do app {app_name}.

Defina seus schemas de entrada/saída aqui.
"""

from pydantic import EmailStr

from core import InputSchema, OutputSchema
from core import timezone, DateTime


# Exemplo de schemas
# class {app_name.title().replace("_", "")}Input(InputSchema):
#     """Schema de entrada para criar/atualizar."""
#     name: str
#     email: EmailStr
#
#
# class {app_name.title().replace("_", "")}Output(OutputSchema):
#     """Schema de saída."""
#     id: int
#     name: str
#     email: str
#     created_at: DateTime
''',
        app_dir / "views.py": f'''"""
Views/ViewSets do app {app_name}.

Defina seus ViewSets e endpoints aqui.
"""

from core import ModelViewSet
from core.dependencies import DatabaseSession

# from {import_path}.models import ...
# from {import_path}.schemas import ...


# Exemplo de ViewSet
# class {app_name.title().replace("_", "")}ViewSet(ModelViewSet):
#     """ViewSet para {app_name}."""
#     
#     model = {app_name.title().replace("_", "")}
#     input_schema = {app_name.title().replace("_", "")}Input
#     output_schema = {app_name.title().replace("_", "")}Output
''',
        app_dir / "services.py": f'''"""
Services/Business Logic do app {app_name}.

Coloque aqui a lógica de negócio complexa.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# Exemplo de service
# class {app_name.title().replace("_", "")}Service:
#     """Service para lógica de negócio de {app_name}."""
#     
#     def __init__(self, db: "AsyncSession"):
#         self.db = db
#     
#     async def process(self, data: dict) -> dict:
#         # Sua lógica aqui
#         return data
''',
        app_dir / "routes.py": f'''"""
Rotas do app {app_name}.

Configure as rotas e registre os ViewSets aqui.
"""

from core import AutoRouter

# from {import_path}.views import ...

router = AutoRouter(prefix="/{app_name.replace("_", "-")}", tags=["{app_name.replace("_", " ").title()}"])

# Registre seus ViewSets
# router.register("", {app_name.title().replace("_", "")}ViewSet, basename="{app_name}")

# Ou adicione rotas customizadas
# @router.get("/custom")
# async def custom_endpoint():
#     return {{"message": "Custom endpoint"}}
''',
        app_dir / "tests" / "__init__.py": f'"""Tests for {app_name} app."""\n',
        app_dir / "tests" / f"test_{app_name}.py": f'''"""
Testes do app {app_name}.
"""

import pytest
from httpx import AsyncClient


# Exemplo de teste
# @pytest.mark.asyncio
# async def test_list_{app_name}(client: AsyncClient):
#     response = await client.get("/{app_name.replace("_", "-")}/")
#     assert response.status_code == 200
''',
    }
    
    for filepath, content in files.items():
        filepath.write_text(content)
        print(f"  📄 {filepath.relative_to(cwd)}")
    
    print()
    print(success(f"✓ App '{app_name}' created successfully!"))
    print()
    print(info("Next steps:"))
    print(f"  1. Edit {app_dir.relative_to(cwd)}/models.py to define your models")
    print(f"  2. Edit {app_dir.relative_to(cwd)}/schemas.py to define your schemas")
    print(f"  3. Edit {app_dir.relative_to(cwd)}/views.py to create your ViewSets")
    print(f"  4. Register the router in your main app:")
    print()
    print(f"     from {import_path} import router as {app_name}_router")
    print(f"     app = CoreApp(routers=[{app_name}_router])")
    print()
    
    return 0


# ============================================================
# Enterprise Commands (Messaging & Tasks)
# ============================================================

def cmd_worker(args: argparse.Namespace) -> int:
    """Start background task worker."""
    print()
    print(bold("Starting Task Worker"))
    print("=" * 50)
    
    queues = args.queues or ["default"]
    concurrency = args.concurrency or 4
    
    print(info(f"Queues: {', '.join(queues)}"))
    print(info(f"Concurrency: {concurrency}"))
    print()
    
    # Add current directory to path
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    os.environ["PYTHONPATH"] = cwd
    
    # Import and discover tasks
    try:
        # Try to import app to register tasks
        config = load_config()
        app_module = config.get("app_module", "src.main")
        try:
            importlib.import_module(app_module)
        except ImportError:
            pass
        
        # Also try to import tasks module
        try:
            importlib.import_module("src.tasks")
        except ImportError:
            pass
    except Exception as e:
        print(warning(f"Warning: Could not import app module: {e}"))
    
    # Run worker
    from core.tasks.worker import run_worker
    
    try:
        asyncio.run(run_worker(queues=queues, concurrency=concurrency))
    except KeyboardInterrupt:
        print()
        print(info("Worker stopped."))
    
    return 0


def cmd_scheduler(args: argparse.Namespace) -> int:
    """Start periodic task scheduler."""
    print()
    print(bold("Starting Task Scheduler"))
    print("=" * 50)
    print()
    
    # Add current directory to path
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    os.environ["PYTHONPATH"] = cwd
    
    # Import and discover tasks
    try:
        config = load_config()
        app_module = config.get("app_module", "src.main")
        try:
            importlib.import_module(app_module)
        except ImportError:
            pass
        
        try:
            importlib.import_module("src.tasks")
        except ImportError:
            pass
    except Exception as e:
        print(warning(f"Warning: Could not import app module: {e}"))
    
    # Run scheduler
    from core.tasks.scheduler import run_scheduler
    
    try:
        asyncio.run(run_scheduler())
    except KeyboardInterrupt:
        print()
        print(info("Scheduler stopped."))
    
    return 0


def cmd_consumer(args: argparse.Namespace) -> int:
    """Start event consumer."""
    print()
    print(bold("Starting Event Consumer"))
    print("=" * 50)
    
    group_id = args.group
    topics = args.topics or []
    
    print(info(f"Group ID: {group_id}"))
    print(info(f"Topics: {', '.join(topics) if topics else 'auto-detect'}"))
    print()
    
    # Add current directory to path
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    os.environ["PYTHONPATH"] = cwd
    
    # Import app to register consumers
    try:
        config = load_config()
        app_module = config.get("app_module", "src.main")
        try:
            importlib.import_module(app_module)
        except ImportError:
            pass
        
        try:
            importlib.import_module("src.consumers")
        except ImportError:
            pass
    except Exception as e:
        print(warning(f"Warning: Could not import app module: {e}"))
    
    async def run_consumer():
        from core.messaging.kafka import KafkaConsumer
        from core.messaging.registry import get_consumer, get_consumers
        
        # Get consumer class if registered
        try:
            consumer_class = get_consumer(group_id)
            topics_to_use = topics or getattr(consumer_class, "_topics", [])
        except ValueError:
            if not topics:
                print(error(f"Consumer '{group_id}' not found and no topics specified."))
                return
            topics_to_use = topics
        
        consumer = KafkaConsumer(group_id=group_id, topics=topics_to_use)
        await consumer.start()
        
        print(success(f"Consumer started, listening on: {topics_to_use}"))
        print(info("Press Ctrl+C to stop"))
        
        # Wait forever
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await consumer.stop()
    
    try:
        asyncio.run(run_consumer())
    except KeyboardInterrupt:
        print()
        print(info("Consumer stopped."))
    
    return 0


def cmd_runworker(args: argparse.Namespace) -> int:
    """Run a message worker."""
    # Check Kafka connection first
    if not check_kafka_connection():
        return 1
    
    print()
    print(bold("Starting Message Worker"))
    print("=" * 50)
    
    worker_name = args.name
    
    # Auto-discover and import workers
    imported = _discover_and_import_workers()
    
    from core.messaging.workers import get_worker, list_workers, run_worker, run_all_workers
    
    if worker_name == "all":
        print(info("Running all registered workers..."))
        workers = list_workers()
        if not workers:
            print(error("No workers registered."))
            return 1
        print(info(f"Workers: {', '.join(workers)}"))
        print()
        
        try:
            asyncio.run(run_all_workers())
        except KeyboardInterrupt:
            print()
            print(info("Workers stopped."))
        return 0
    
    # Run specific worker
    worker_config = get_worker(worker_name)
    if worker_config is None:
        available = list_workers()
        print(error(f"Worker '{worker_name}' not found."))
        if available:
            print(info(f"Available workers: {', '.join(available)}"))
        else:
            print(info("No workers registered. Define workers with @worker decorator or Worker class."))
        return 1
    
    # Get topic name - handle both string and class
    input_topic = worker_config.input_topic
    if hasattr(input_topic, 'name'):
        input_topic = input_topic.name
    elif hasattr(input_topic, '__name__'):
        input_topic = input_topic.__name__
    
    output_topic = worker_config.output_topic
    if output_topic:
        if hasattr(output_topic, 'name'):
            output_topic = output_topic.name
        elif hasattr(output_topic, '__name__'):
            output_topic = output_topic.__name__
    
    print(info(f"Worker: {worker_name}"))
    print(info(f"Input topic: {input_topic}"))
    print(info(f"Output topic: {output_topic or 'None'}"))
    print(info(f"Concurrency: {worker_config.concurrency}"))
    print()
    
    try:
        asyncio.run(run_worker(worker_name))
    except KeyboardInterrupt:
        print()
        print(info("Worker stopped."))
    
    return 0


def _discover_and_import_workers() -> list[str]:
    """
    Auto-discover and import worker modules.
    
    Searches for:
    1. Modules defined in core.toml workers_module
    2. Common patterns: workers.py, */workers.py, src/*/workers.py
    3. App main module (to trigger imports)
    
    Returns:
        List of imported module names
    """
    imported = []
    cwd = os.getcwd()
    
    # Add current directory to path
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    os.environ["PYTHONPATH"] = cwd
    
    config = load_config()
    
    # 1. Try workers_module from config
    workers_module = config.get("workers_module")
    if workers_module:
        try:
            importlib.import_module(workers_module)
            imported.append(workers_module)
        except ImportError as e:
            print(warning(f"Could not import workers_module '{workers_module}': {e}"))
    
    # 2. Try app main module (may import workers)
    app_module = config.get("app_module", "src.main")
    try:
        importlib.import_module(app_module)
        imported.append(app_module)
    except ImportError:
        pass
    
    # 3. Auto-discover workers.py files
    patterns = [
        "workers.py",
        "*/workers.py",
        "src/workers.py",
        "src/*/workers.py",
        "src/**/workers.py",
        "app/workers.py",
        "app/*/workers.py",
    ]
    
    for pattern in patterns:
        for path in Path(cwd).glob(pattern):
            if path.is_file():
                # Convert path to module name
                relative = path.relative_to(cwd)
                module_name = str(relative).replace("/", ".").replace("\\", ".").replace(".py", "")
                
                if module_name not in imported:
                    try:
                        importlib.import_module(module_name)
                        imported.append(module_name)
                    except ImportError:
                        pass
                    except Exception as e:
                        print(warning(f"Error importing {module_name}: {e}"))
    
    # 4. Try common module names
    common_modules = [
        "workers",
        "src.workers",
        "app.workers",
        "src.messaging.workers",
        "src.apps.workers",
    ]
    
    for module_name in common_modules:
        if module_name not in imported:
            try:
                importlib.import_module(module_name)
                imported.append(module_name)
            except ImportError:
                pass
    
    return imported


def cmd_workers_list(args: argparse.Namespace) -> int:
    """List registered message workers."""
    print()
    print(bold("Registered Message Workers"))
    print("=" * 50)
    
    # Auto-discover and import workers
    imported = _discover_and_import_workers()
    
    from core.messaging.workers import get_all_workers
    
    workers = get_all_workers()
    
    if not workers:
        print(info("No workers registered."))
        print()
        print("Workers are auto-discovered from:")
        print("  - workers_module in core.toml")
        print("  - workers.py files in project")
        print("  - src/*/workers.py patterns")
        print()
        print("Example worker definition:")
        print()
        print("  # src/workers.py")
        print("  from core.messaging import worker")
        print()
        print("  @worker(topic='events.raw', output_topic='events.enriched')")
        print("  async def process_event(event: dict) -> dict:")
        print("      return {**event, 'processed': True}")
        print()
        if imported:
            print(f"Modules searched: {', '.join(imported)}")
        return 0
    
    for name, config in workers.items():
        # Get topic name - handle both string and class
        input_topic = config.input_topic
        if hasattr(input_topic, 'name'):
            input_topic = input_topic.name
        elif hasattr(input_topic, '__name__'):
            input_topic = input_topic.__name__
        
        output_topic = config.output_topic
        if output_topic:
            if hasattr(output_topic, 'name'):
                output_topic = output_topic.name
            elif hasattr(output_topic, '__name__'):
                output_topic = output_topic.__name__
        
        print()
        print(f"  {bold(name)}")
        print(f"    Input:  {input_topic}")
        print(f"    Output: {output_topic or '-'}")
        print(f"    Concurrency: {config.concurrency}")
        print(f"    Retries: {config.retry_policy.max_retries}")
    
    print()
    if imported:
        print(info(f"Discovered from: {', '.join(imported)}"))
    return 0


def cmd_topics_list(args: argparse.Namespace) -> int:
    """List Kafka topics."""
    # Check Kafka connection first
    if not check_kafka_connection():
        return 1
    
    print()
    print(bold("Kafka Topics"))
    print("=" * 50)
    
    async def list_topics():
        from core.config import get_settings
        
        settings = get_settings()
        kafka_backend = getattr(settings, "kafka_backend", "aiokafka")
        
        if kafka_backend == "confluent":
            if not check_required_package("confluent_kafka", "pip install confluent-kafka"):
                return
            
            from confluent_kafka.admin import AdminClient
            
            config = {"bootstrap.servers": settings.kafka_bootstrap_servers}
            
            # Add security config if needed
            if settings.kafka_security_protocol != "PLAINTEXT":
                config.update({
                    "security.protocol": settings.kafka_security_protocol,
                    "sasl.mechanism": settings.kafka_sasl_mechanism or "",
                    "sasl.username": settings.kafka_sasl_username or "",
                    "sasl.password": settings.kafka_sasl_password or "",
                })
            
            admin = AdminClient(config)
            metadata = admin.list_topics(timeout=10)
            topics = list(metadata.topics.keys())
        else:
            if not check_required_package("aiokafka", "pip install aiokafka"):
                return
            
            from core.messaging.kafka import KafkaAdmin
            
            admin = KafkaAdmin()
            await admin.connect()
            topics = await admin.list_topics()
            await admin.close()
        
        if not topics:
            print(info("No topics found."))
        else:
            # Filter internal topics
            user_topics = [t for t in sorted(topics) if not t.startswith("_")]
            internal_topics = [t for t in sorted(topics) if t.startswith("_")]
            
            if user_topics:
                print()
                for topic in user_topics:
                    print(f"  {topic}")
            
            if internal_topics:
                print()
                print(info("Internal topics:"))
                for topic in internal_topics:
                    print(f"  {topic}")
    
    asyncio.run(list_topics())
    return 0


def cmd_topics_create(args: argparse.Namespace) -> int:
    """Create a Kafka topic."""
    # Check Kafka connection first
    if not check_kafka_connection():
        return 1
    
    print()
    print(bold(f"Creating Topic: {args.name}"))
    print("=" * 50)
    
    async def create_topic():
        from core.messaging.kafka import KafkaAdmin
        
        admin = KafkaAdmin()
        await admin.connect()
        
        created = await admin.create_topic(
            name=args.name,
            partitions=args.partitions,
            replication_factor=args.replication,
        )
        
        if created:
            print(success(f"Topic '{args.name}' created successfully."))
            print(info(f"  Partitions: {args.partitions}"))
            print(info(f"  Replication: {args.replication}"))
        else:
            print(warning(f"Topic '{args.name}' already exists."))
        
        await admin.close()
    
    asyncio.run(create_topic())
    return 0


def cmd_topics_delete(args: argparse.Namespace) -> int:
    """Delete a Kafka topic."""
    # Check Kafka connection first
    if not check_kafka_connection():
        return 1
    
    if not args.yes:
        print()
        print(warning(f"This will delete topic '{args.name}' and all its data."))
        confirm = input("Are you sure? (y/N): ")
        if confirm.lower() != "y":
            print(info("Aborted."))
            return 0
    
    print()
    print(bold(f"Deleting Topic: {args.name}"))
    
    async def delete_topic():
        from core.messaging.kafka import KafkaAdmin
        
        admin = KafkaAdmin()
        await admin.connect()
        
        deleted = await admin.delete_topic(args.name)
        
        if deleted:
            print(success(f"Topic '{args.name}' deleted."))
        else:
            print(warning(f"Topic '{args.name}' not found."))
        
        await admin.close()
    
    asyncio.run(delete_topic())
    return 0


def cmd_collectstatic(args: argparse.Namespace) -> int:
    """Collect static assets for admin panel."""
    print()
    print(bold("Collecting Static Assets"))
    print("=" * 50)
    
    from core.admin.collectstatic import collectstatic
    
    output_dir = args.output if hasattr(args, "output") else None
    no_hash = args.no_hash if hasattr(args, "no_hash") else False
    verbose_flag = args.verbose if hasattr(args, "verbose") else False
    
    result = collectstatic(
        output_dir=output_dir,
        no_hash=no_hash,
        verbose=verbose_flag,
    )
    
    print()
    print(f"  Output: {info(result['output_dir'])}")
    print(f"  Files copied: {success(str(result['files_copied']))}")
    
    if result["conflicts"]:
        print(f"  Conflicts: {warning(str(len(result['conflicts'])))}")
        for conflict in result["conflicts"]:
            print(f"    {warning('⚠')} {conflict}")
    
    print(f"  Manifest: {info(result['manifest_path'])}")
    print()
    print(success("Static assets collected successfully!"))
    
    return 0


def cmd_createsuperuser(args: argparse.Namespace) -> int:
    """Create a superuser account interactively or via flags."""

    config = load_config()

    if not check_database_connection(config["database_url"]):
        return 1

    print()
    print(bold("Create Superuser"))
    print("=" * 50)

    # ── Resolve User model ──────────────────────────────────────────────
    try:
        from core.auth.models import get_user_model
        User = get_user_model()
    except RuntimeError:
        try:
            app_module = config.get("app_module")
            if app_module:
                import importlib
                importlib.import_module(app_module)

            from core.auth.models import get_user_model
            User = get_user_model()
        except Exception as exc:
            print(error(f"Could not resolve User model: {exc}"))
            return 1

    username_field = getattr(User, "USERNAME_FIELD", "email")

    # ── CLI field governance ───────────────────────────────────────────
    cli_required: list[str] = []
    cli_base_fields: set[str] = set()

    if hasattr(User, "cli_required_fields"):
        cli_required = User.cli_required_fields()
        cli_base_fields = User.cli_base_fields()

    # ── Non-interactive mode (--noinput) ────────────────────────────────
    noinput = getattr(args, "noinput", False)

    email_value = getattr(args, "email", None) or getattr(args, username_field, None)
    password_value = getattr(args, "password", None)

    if noinput:
        if not email_value:
            print(error(f"--{username_field} is required when using --noinput"))
            return 1
        if not password_value:
            print(error("--password is required when using --noinput"))
            return 1
    else:
        if not email_value:
            while True:
                email_value = input(f"  {username_field.capitalize()}: ").strip()
                if email_value:
                    break
                print(warning(f"  {username_field.capitalize()} cannot be empty."))

        if not password_value:
            while True:
                password_value = getpass.getpass("  Password: ")
                if len(password_value) < 8:
                    print(warning("  Password must be at least 8 characters."))
                    continue

                confirm = getpass.getpass("  Password (confirm): ")
                if password_value != confirm:
                    print(warning("  Passwords do not match."))
                    continue
                break

    # ── Collect required base fields only ──────────────────────────────
    extra_fields: dict[str, Any] = {}

    for field_name in cli_required:
        if field_name not in cli_base_fields:
            # Campo customizado do projeto → fora do escopo do CLI
            continue

        if field_name == username_field:
            continue  # já coletado

        val = getattr(args, field_name, None)

        if not val and not noinput:
            val = input(f"  {field_name.replace('_', ' ').capitalize()}: ").strip()

        if not val:
            print(error(f"{field_name} is required."))
            return 1

        extra_fields[field_name] = val

    # ── Create superuser ────────────────────────────────────────────────
    async def create():
        from core.models import init_database, get_session

        await init_database(config["database_url"])
        session = get_session()

        async with await session as db:
            existing = await User.get_by_email(email_value, db)
            if existing:
                print(warning(f"User '{email_value}' already exists."))

                if noinput:
                    return 1

                overwrite = input("Overwrite and grant superuser? [y/N]: ").lower()
                if overwrite != "y":
                    print(info("Aborted."))
                    return 0

                existing.is_staff = True
                existing.is_superuser = True
                existing.is_active = True
                existing.set_password(password_value)
                await db.commit()
                print(success("Superuser updated."))
                return 0

            await User.create_superuser(
                email=email_value,
                password=password_value,
                db=db,
                **extra_fields,
            )
            await db.commit()

        return 0

    result = asyncio.run(create())

    if result == 0:
        print(success(f"Superuser '{email_value}' ready."))

    return result


def cmd_deploy(args: argparse.Namespace) -> int:
    """Generate deployment files."""
    print()
    print(bold("Generating Deployment Files"))
    print("=" * 50)
    
    output_dir = Path(args.output or ".")
    target = args.target
    
    from core.deployment import generate_docker, generate_pm2, generate_kubernetes
    
    if target in ("docker", "all"):
        generate_docker(output_dir)
        print(success("  Generated: docker-compose.yml"))
        print(success("  Generated: Dockerfile"))
    
    if target in ("pm2", "all"):
        generate_pm2(output_dir)
        print(success("  Generated: ecosystem.config.js"))
    
    if target in ("k8s", "all"):
        generate_kubernetes(output_dir)
        print(success("  Generated: k8s/"))
    
    print()
    print(success("Deployment files generated successfully!"))
    
    if target == "docker" or target == "all":
        print()
        print(info("To start with Docker:"))
        print("  # Set your GitHub token for private repos")
        print("  export GITHUB_TOKEN=ghp_your_token_here")
        print("  docker compose up -d")
    
    if target == "pm2" or target == "all":
        print()
        print(info("To start with PM2:"))
        print("  pm2 start ecosystem.config.js")
    
    if target == "k8s" or target == "all":
        print()
        print(info("To deploy to Kubernetes:"))
        print("  kubectl apply -f k8s/")
    
    return 0


def _discover_and_import_tasks() -> list[str]:
    """
    Auto-discover and import task modules.
    
    Searches for:
    1. Modules defined in core.toml tasks_module
    2. Common patterns: tasks.py, */tasks.py, src/*/tasks.py
    3. App main module (to trigger imports)
    
    Returns:
        List of imported module names
    """
    imported = []
    cwd = os.getcwd()
    
    # Add current directory to path
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    os.environ["PYTHONPATH"] = cwd
    
    config = load_config()
    
    # 1. Try tasks_module from config
    tasks_module = config.get("tasks_module")
    if tasks_module:
        try:
            importlib.import_module(tasks_module)
            imported.append(tasks_module)
        except ImportError as e:
            print(warning(f"Could not import tasks_module '{tasks_module}': {e}"))
    
    # 2. Try app main module (may import tasks)
    app_module = config.get("app_module", "src.main")
    try:
        importlib.import_module(app_module)
        imported.append(app_module)
    except ImportError:
        pass
    
    # 3. Auto-discover tasks.py files
    patterns = [
        "tasks.py",
        "*/tasks.py",
        "src/tasks.py",
        "src/*/tasks.py",
        "src/**/tasks.py",
        "app/tasks.py",
        "app/*/tasks.py",
        "src/apps/*/tasks.py",
    ]
    
    for pattern in patterns:
        for path in Path(cwd).glob(pattern):
            if path.is_file():
                # Convert path to module name
                relative = path.relative_to(cwd)
                module_name = str(relative).replace("/", ".").replace("\\", ".").replace(".py", "")
                
                if module_name not in imported:
                    try:
                        importlib.import_module(module_name)
                        imported.append(module_name)
                    except ImportError:
                        pass
                    except Exception as e:
                        print(warning(f"Error importing {module_name}: {e}"))
    
    # 4. Try common module names
    common_modules = [
        "tasks",
        "src.tasks",
        "app.tasks",
        "src.background.tasks",
        "src.apps.tasks",
    ]
    
    for module_name in common_modules:
        if module_name not in imported:
            try:
                importlib.import_module(module_name)
                imported.append(module_name)
            except ImportError:
                pass
    
    return imported


def cmd_tasks(args: argparse.Namespace) -> int:
    """List registered tasks."""
    print()
    print(bold("Registered Tasks"))
    print("=" * 50)
    
    # Auto-discover and import tasks
    imported = _discover_and_import_tasks()
    
    from core.tasks.registry import list_tasks
    
    tasks = list_tasks()
    
    if not tasks:
        print(info("No tasks registered."))
        print()
        print("Tasks are auto-discovered from:")
        print("  - tasks_module in core.toml")
        print("  - tasks.py files in project")
        print("  - src/*/tasks.py patterns")
        print()
        print("Example task definition:")
        print()
        print("  # src/tasks.py")
        print("  from core.tasks import task, periodic_task")
        print()
        print("  @task(queue='emails')")
        print("  async def send_email(to, subject, body):")
        print("      ...")
        print()
        print("  @periodic_task(cron='0 0 * * *')")
        print("  async def daily_cleanup():")
        print("      ...")
        print()
        if imported:
            print(info(f"Modules searched: {', '.join(imported)}"))
        return 0
    
    # Group by type
    regular_tasks = [t for t in tasks if t["type"] == "task"]
    periodic_tasks = [t for t in tasks if t["type"] == "periodic"]
    
    if regular_tasks:
        print()
        print(bold("Background Tasks:"))
        for task in regular_tasks:
            print(f"  {task['name']}")
            print(f"    Queue: {task['queue']}, Retry: {task['retry']}, Timeout: {task['timeout']}s")
    
    if periodic_tasks:
        print()
        print(bold("Periodic Tasks:"))
        for task in periodic_tasks:
            schedule = task.get("cron") or f"every {task.get('interval')}s"
            status = "enabled" if task.get("enabled") else "disabled"
            print(f"  {task['name']} ({status})")
            print(f"    Schedule: {schedule}, Queue: {task['queue']}")
            if task.get("last_run"):
                print(f"    Last run: {task['last_run']}")
            if task.get("next_run"):
                print(f"    Next run: {task['next_run']}")
    
    print()
    if imported:
        print(info(f"Discovered from: {', '.join(imported)}"))
    return 0


def cmd_collectpermissions(args: argparse.Namespace) -> int:
    """
    Auto-generate CRUD permissions for all registered models.
    
    Scans all models (same discovery as makemigrations) and creates
    the 4 standard permissions for each:
    - {app_label}.view_{model_name}
    - {app_label}.add_{model_name}
    - {app_label}.change_{model_name}
    - {app_label}.delete_{model_name}
    
    Idempotent: only creates permissions that don't already exist.
    """
    import asyncio

    config = load_config()

    root = _get_project_root()
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    if not check_database_connection(config["database_url"]):
        return 1

    print()
    print(bold("Collect Permissions"))
    print("=" * 50)

    # ── Discover all models ──
    models_module = config.get("models_module")
    if not models_module or models_module == "app.models":
        models = discover_models(models_module=None)
    else:
        models = discover_models(models_module=models_module)

    if not models:
        print(warning("No models found. Nothing to do."))
        return 0

    # ── Derive app_label and model_name ──
    ACTIONS = ("view", "add", "change", "delete")
    ACTION_LABELS = {
        "view": "Can view",
        "add": "Can add",
        "change": "Can change",
        "delete": "Can delete",
    }

    def resolve_app_label(model: type) -> str:
        """Resolve app_label from model's module (same logic as ModelAdmin)."""
        module = model.__module__
        parts = module.split(".")
        if len(parts) >= 2:
            return parts[-2]
        return parts[0]

    permissions_to_create: list[tuple[str, str]] = []  # (codename, name)

    # Skip abstract models and models without __table__
    concrete_models = [m for m in models if hasattr(m, "__table__") and not getattr(m, "__abstract__", False)]

    print(info(f"Found {len(concrete_models)} model(s) from {len(set(resolve_app_label(m) for m in concrete_models))} app(s)"))
    print()

    for model in concrete_models:
        app_label = resolve_app_label(model)
        model_name = model.__name__.lower()
        for action in ACTIONS:
            codename = f"{app_label}.{action}_{model_name}"
            display_name = f"{ACTION_LABELS[action]} {model.__name__}"
            permissions_to_create.append((codename, display_name))

    print(info(f"Generating {len(permissions_to_create)} permission(s)..."))
    print()

    # ── Create in database ──
    created_count = 0
    existed_count = 0

    async def run():
        nonlocal created_count, existed_count
        from core.models import init_database, get_session
        from core.auth.models import Permission
        from sqlalchemy import select

        await init_database(config["database_url"])
        session = get_session()

        async with await session as db:
            # Fetch all existing codenames in one query
            stmt = select(Permission.codename)
            result = await db.execute(stmt)
            existing_codenames = {row[0] for row in result}

            for codename, display_name in permissions_to_create:
                if codename in existing_codenames:
                    existed_count += 1
                    print(f"  {success('✓')} {codename} {info('(already exists)')}")
                else:
                    perm = Permission(
                        codename=codename,
                        name=display_name,
                    )
                    db.add(perm)
                    created_count += 1
                    print(f"  {success('✓')} {codename} {success('(created)')}")

            await db.commit()

    asyncio.run(run())

    print()
    print(success(f"Done! Created {created_count} permission(s) ({existed_count} already existed)"))
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
    
    # init (also aliased as startproject)
    init_parser = subparsers.add_parser(
        "init",
        help="Initialize a new project (interactive wizard)",
        description="Create a new project. Without arguments, opens interactive wizard with keyboard navigation."
    )
    init_parser.add_argument("name", nargs="?", help="Project name (omit for interactive wizard)")
    init_parser.add_argument("--python", "-p", help="Python version (default: select from installed)")
    init_parser.add_argument("--no-venv", action="store_true", help="Skip virtual environment setup")
    init_parser.add_argument("--template", "-t", help="Template: minimal, default, kafka, tenant, workers")
    init_parser.add_argument("--minimal", action="store_true", help="Shortcut for --template minimal")
    init_parser.set_defaults(func=cmd_init)
    
    # startproject (alias for init - Django-style command)
    startproject_parser = subparsers.add_parser(
        "startproject",
        help="Create a new project (alias for init)",
        description="Create a new project. Without arguments, opens interactive wizard with keyboard navigation."
    )
    startproject_parser.add_argument("name", nargs="?", help="Project name (omit for interactive wizard)")
    startproject_parser.add_argument("--python", "-p", help="Python version (default: select from installed)")
    startproject_parser.add_argument("--no-venv", action="store_true", help="Skip virtual environment setup")
    startproject_parser.add_argument("--template", "-t", help="Template: minimal, default, kafka, tenant, workers")
    startproject_parser.add_argument("--minimal", action="store_true", help="Shortcut for --template minimal")
    startproject_parser.set_defaults(func=cmd_init)
    
    # templates (list available templates)
    templates_parser = subparsers.add_parser("templates", help="List available project templates")
    templates_parser.set_defaults(func=cmd_templates)
    
    # makemigrations
    make_parser = subparsers.add_parser("makemigrations", help="Generate migration files")
    make_parser.add_argument("-n", "--name", help="Migration name")
    make_parser.add_argument("--empty", action="store_true", help="Create empty migration")
    make_parser.add_argument("--dry-run", action="store_true", help="Show what would be generated")
    make_parser.add_argument("--rescan", action="store_true", help="Rescan project for models (ignore cache)")
    make_parser.set_defaults(func=cmd_makemigrations)
    
    # migrate
    migrate_parser = subparsers.add_parser("migrate", help="Apply migrations")
    migrate_parser.add_argument("-t", "--target", help="Target migration name")
    migrate_parser.add_argument("--fake", action="store_true", help="Mark as applied without running")
    migrate_parser.add_argument("--dry-run", action="store_true", help="Show what would be applied")
    migrate_parser.add_argument("--no-check", action="store_true", help="Skip pre-migration analysis (not recommended)")
    migrate_parser.add_argument("-y", "--yes", action="store_true", help="Auto-confirm warnings (non-interactive)")
    migrate_parser.set_defaults(func=cmd_migrate)
    
    # showmigrations
    show_parser = subparsers.add_parser("showmigrations", help="Show migration status")
    show_parser.set_defaults(func=cmd_showmigrations)
    
    # check
    check_parser = subparsers.add_parser("check", help="Analyze pending migrations for potential issues")
    check_parser.add_argument("-v", "--verbose", action="store_true", help="Show all warnings")
    check_parser.set_defaults(func=cmd_check)
    
    # rollback
    rollback_parser = subparsers.add_parser("rollback", help="Rollback migrations")
    rollback_parser.add_argument("-t", "--target", help="Target migration (exclusive)")
    rollback_parser.add_argument("--fake", action="store_true", help="Unmark without running")
    rollback_parser.add_argument("--dry-run", action="store_true", help="Show what would be rolled back")
    rollback_parser.set_defaults(func=cmd_rollback)
    
    # dbinfo
    dbinfo_parser = subparsers.add_parser("dbinfo", help="Show database driver info and capabilities")
    dbinfo_parser.set_defaults(func=cmd_dbinfo)
    
    # run
    run_parser = subparsers.add_parser("run", help="Run development server")
    run_parser.add_argument("--host", help="Host to bind (default: 0.0.0.0)")
    run_parser.add_argument("-p", "--port", type=int, help="Port to bind (default: 8000)")
    run_parser.add_argument("--app", help="App module (default: src.main)")
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
    
    # startapp (alias for createapp - Django-style command)
    startapp_parser = subparsers.add_parser("startapp", help="Create a new app (alias for createapp)")
    startapp_parser.add_argument("name", help="App name")
    startapp_parser.set_defaults(func=cmd_createapp)
    
    # reset_db
    resetdb_parser = subparsers.add_parser(
        "reset_db",
        help="Reset database completely (DANGEROUS - destroys all data)"
    )
    resetdb_parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Skip confirmation prompt"
    )
    resetdb_parser.set_defaults(func=cmd_reset_db)
    
    # version (também como subcomando)
    version_parser = subparsers.add_parser("version", help="Show version")
    version_parser.set_defaults(func=cmd_version)
    
    # ============================================================
    # Enterprise Commands (Messaging & Tasks)
    # ============================================================
    
    # worker
    worker_parser = subparsers.add_parser(
        "worker",
        help="Start background task worker"
    )
    worker_parser.add_argument(
        "-q", "--queue",
        action="append",
        dest="queues",
        help="Queue(s) to consume from (can be repeated)"
    )
    worker_parser.add_argument(
        "-c", "--concurrency",
        type=int,
        help="Number of concurrent tasks (default: 4)"
    )
    worker_parser.set_defaults(func=cmd_worker)
    
    # scheduler
    scheduler_parser = subparsers.add_parser(
        "scheduler",
        help="Start periodic task scheduler"
    )
    scheduler_parser.set_defaults(func=cmd_scheduler)
    
    # consumer
    consumer_parser = subparsers.add_parser(
        "consumer",
        help="Start event consumer"
    )
    consumer_parser.add_argument(
        "-g", "--group",
        required=True,
        help="Consumer group ID"
    )
    consumer_parser.add_argument(
        "-t", "--topic",
        action="append",
        dest="topics",
        help="Topic(s) to subscribe to (can be repeated)"
    )
    consumer_parser.set_defaults(func=cmd_consumer)
    
    # runworker (message workers)
    runworker_parser = subparsers.add_parser(
        "runworker",
        help="Run a message worker"
    )
    runworker_parser.add_argument(
        "name",
        help="Worker name (or 'all' to run all workers)"
    )
    runworker_parser.set_defaults(func=cmd_runworker)
    
    # workers (list workers)
    workers_parser = subparsers.add_parser(
        "workers",
        help="List registered message workers"
    )
    workers_parser.set_defaults(func=cmd_workers_list)
    
    # topics
    topics_parser = subparsers.add_parser(
        "topics",
        help="Manage Kafka topics"
    )
    topics_subparsers = topics_parser.add_subparsers(dest="topics_command")
    
    topics_list = topics_subparsers.add_parser("list", help="List all topics")
    topics_list.set_defaults(func=cmd_topics_list)
    
    topics_create = topics_subparsers.add_parser("create", help="Create a topic")
    topics_create.add_argument("name", help="Topic name")
    topics_create.add_argument("-p", "--partitions", type=int, default=1, help="Number of partitions")
    topics_create.add_argument("-r", "--replication", type=int, default=1, help="Replication factor")
    topics_create.set_defaults(func=cmd_topics_create)
    
    topics_delete = topics_subparsers.add_parser("delete", help="Delete a topic")
    topics_delete.add_argument("name", help="Topic name")
    topics_delete.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    topics_delete.set_defaults(func=cmd_topics_delete)
    
    # deploy
    deploy_parser = subparsers.add_parser(
        "deploy",
        help="Generate deployment files"
    )
    deploy_parser.add_argument(
        "target",
        choices=["docker", "pm2", "k8s", "all"],
        help="Deployment target"
    )
    deploy_parser.add_argument(
        "-o", "--output",
        help="Output directory (default: current directory)"
    )
    deploy_parser.set_defaults(func=cmd_deploy)
    
    # tasks
    tasks_parser = subparsers.add_parser(
        "tasks",
        help="List registered tasks"
    )
    tasks_parser.set_defaults(func=cmd_tasks)
    
    # createsuperuser
    superuser_parser = subparsers.add_parser(
        "createsuperuser",
        help="Create a superuser account for the admin panel"
    )
    superuser_parser.add_argument(
        "--email",
        help="Email for the superuser (non-interactive)"
    )
    superuser_parser.add_argument(
        "--password",
        help="Password for the superuser (non-interactive)"
    )
    superuser_parser.add_argument(
        "--noinput",
        action="store_true",
        help="Non-interactive mode (requires --email and --password)"
    )
    superuser_parser.set_defaults(func=cmd_createsuperuser)
    
    # collectstatic
    collectstatic_parser = subparsers.add_parser(
        "collectstatic",
        help="Collect static assets for admin panel (CSS, JS, images)"
    )
    collectstatic_parser.add_argument(
        "-o", "--output",
        help="Output directory (default: ./static/core-admin)"
    )
    collectstatic_parser.add_argument(
        "--no-hash",
        action="store_true",
        help="Disable cache busting hash in filenames"
    )
    collectstatic_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show each file as it is copied"
    )
    collectstatic_parser.set_defaults(func=cmd_collectstatic)
    
    # collectpermissions
    collectperms_parser = subparsers.add_parser(
        "collectpermissions",
        help="Auto-generate CRUD permissions (view, add, change, delete) for all models",
    )
    collectperms_parser.set_defaults(func=cmd_collectpermissions)
    
    # test
    test_parser = subparsers.add_parser(
        "test",
        help="Run tests with auto-discovery and isolated environment"
    )
    test_parser.add_argument(
        "path",
        nargs="?",
        default="tests",
        help="Test path or file (default: tests)"
    )
    test_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output"
    )
    test_parser.add_argument(
        "-k", "--keyword",
        help="Only run tests matching keyword expression"
    )
    test_parser.add_argument(
        "-x", "--exitfirst",
        action="store_true",
        help="Exit on first failure"
    )
    test_parser.add_argument(
        "--cov",
        nargs="?",
        const=".",
        help="Enable coverage (optionally specify source)"
    )
    test_parser.add_argument(
        "--cov-report",
        choices=["term", "html", "xml", "json"],
        default="term",
        help="Coverage report format"
    )
    test_parser.add_argument(
        "-m", "--marker",
        help="Only run tests with this marker (e.g., 'unit', 'integration')"
    )
    test_parser.add_argument(
        "--no-header",
        action="store_true",
        help="Disable pytest header"
    )
    test_parser.set_defaults(func=cmd_test)
    
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
