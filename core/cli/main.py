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


def cmd_init(args: argparse.Namespace) -> int:
    """Inicializa um novo projeto com uv."""
    import subprocess
    
    project_name = args.name or "myproject"
    python_version = args.python or "3.12"
    skip_venv = args.no_venv
    
    print(bold(f"\n🚀 Core Framework - Project Initialization\n"))
    print(info(f"Creating project: {project_name}"))
    
    # Verifica/instala uv
    if not skip_venv:
        if not check_uv_installed():
            print(warning("uv not found."))
            if not install_uv():
                print(warning("Continuing without uv..."))
                skip_venv = True
    
    # Cria estrutura de diretórios
    # Nova estrutura escalável:
    # project/
    # ├── src/
    # │   ├── apps/           # Apps modulares
    # │   │   └── users/      # App de exemplo
    # │   ├── core/           # Configurações centrais
    # │   └── main.py         # Entry point
    # ├── migrations/
    # ├── tests/
    # └── settings.py         # Configurações do projeto
    
    print(info("\nCreating project structure..."))
    dirs = [
        project_name,
        f"{project_name}/src",
        f"{project_name}/src/apps",
        f"{project_name}/src/apps/users",
        f"{project_name}/src/apps/users/tests",
        f"{project_name}/src/api",
        f"{project_name}/migrations",
        f"{project_name}/tests",
    ]
    
    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)
        print(f"  📁 {d}/")
    
    # Cria arquivos
    print(info("\nCreating files..."))
    files = {
        # Source package
        f"{project_name}/src/__init__.py": '"""Source package."""\n',
        
        # Apps package
        f"{project_name}/src/apps/__init__.py": '"""Apps package - módulos da aplicação."""\n',
        
        # Users app
        f"{project_name}/src/apps/users/__init__.py": '''"""
Users App.

Authentication and user management module using Core Framework's
built-in AbstractUser, permissions, and JWT authentication.
"""

from src.apps.users.routes import router

__all__ = ["router"]
''',
        f"{project_name}/src/apps/users/models.py": '''"""
User Model - Extends AbstractUser with custom fields.

Inherited from AbstractUser:
    - id, email, password_hash
    - is_active, is_staff, is_superuser
    - date_joined, last_login
    
Methods:
    - User.create_user(email, password, db)
    - User.authenticate(email, password, db)
    - user.check_password(password)
    - user.has_perm("posts.delete")
"""

from sqlalchemy.orm import Mapped
from core import Field
from core.auth import AbstractUser, PermissionsMixin


class User(AbstractUser, PermissionsMixin):
    """Custom User with profile fields."""
    
    __tablename__ = "users"
    
    first_name: Mapped[str | None] = Field.string(max_length=100, nullable=True)
    last_name: Mapped[str | None] = Field.string(max_length=100, nullable=True)
    
    @property
    def full_name(self) -> str:
        return f"{self.first_name or ''} {self.last_name or ''}".strip() or self.email
''',
        f"{project_name}/src/apps/users/schemas.py": '''"""
User Schemas - Pydantic models for validation and serialization.
"""

from pydantic import EmailStr, field_validator
from core import InputSchema, OutputSchema
from core.validators import PasswordValidator


class UserInput(InputSchema):
    """Input schema for user creation."""
    email: EmailStr
    password: str
    first_name: str = ""
    last_name: str = ""
    
    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        PasswordValidator(min_length=8, require_uppercase=True, require_digit=True).validate(v)
        return v


class UserOutput(OutputSchema):
    """Output schema for user data."""
    id: int
    email: str
    first_name: str | None
    last_name: str | None
    is_active: bool
    is_staff: bool


class UserUpdateInput(InputSchema):
    """Input schema for user updates."""
    first_name: str | None = None
    last_name: str | None = None


class LoginInput(InputSchema):
    """Input schema for login."""
    email: EmailStr
    password: str


class TokenOutput(OutputSchema):
    """Output schema for JWT tokens."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshInput(InputSchema):
    """Input schema for token refresh."""
    refresh_token: str
''',
        f"{project_name}/src/apps/users/views.py": '''"""
User ViewSets - DRF-style class-based views.

All business logic is handled by ViewSets with automatic:
- CRUD operations
- Validation
- Serialization
- Permissions
"""

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core import ModelViewSet, ViewSet
from core.permissions import AllowAny, IsAuthenticated
from core.auth import create_access_token, create_refresh_token, verify_token

from src.apps.users.models import User
from src.apps.users.schemas import (
    UserInput, UserOutput, UserUpdateInput,
    LoginInput, TokenOutput, RefreshInput,
)
from src.api.config import settings


class UserViewSet(ModelViewSet):
    """
    User CRUD ViewSet.
    
    Endpoints (auto-generated):
        GET    /users/       - List users
        POST   /users/       - Create user
        GET    /users/{id}   - Get user
        PUT    /users/{id}   - Update user
        DELETE /users/{id}   - Delete user
    """
    model = User
    input_schema = UserInput
    output_schema = UserOutput
    update_schema = UserUpdateInput
    permission_classes = [AllowAny]
    unique_fields = ["email"]
    
    async def perform_create_validation(self, data: dict, db: AsyncSession) -> dict:
        """Hash password before saving."""
        data["password_hash"] = User.make_password(data.pop("password"))
        return data


class AuthViewSet(ViewSet):
    """
    Authentication ViewSet.
    
    Custom actions for auth flow:
        POST /auth/register  - Create account
        POST /auth/login     - Get tokens
        POST /auth/refresh   - Refresh tokens
    """
    permission_classes = [AllowAny]
    
    async def register(self, db: AsyncSession, data: UserInput) -> UserOutput:
        """Register new user."""
        existing = await User.get_by_email(data.email, db)
        if existing:
            raise HTTPException(400, "Email already registered")
        
        user = await User.create_user(
            email=data.email,
            password=data.password,
            db=db,
            first_name=data.first_name,
            last_name=data.last_name,
        )
        return UserOutput.model_validate(user)
    
    async def login(self, db: AsyncSession, data: LoginInput) -> TokenOutput:
        """Authenticate and return tokens."""
        user = await User.authenticate(data.email, data.password, db)
        if not user:
            raise HTTPException(401, "Invalid credentials")
        
        return TokenOutput(
            access_token=create_access_token({"sub": str(user.id), "email": user.email}),
            refresh_token=create_refresh_token({"sub": str(user.id)}),
            expires_in=settings.auth_access_token_expire_minutes * 60,
        )
    
    async def refresh(self, data: RefreshInput) -> TokenOutput:
        """Refresh access token."""
        payload = verify_token(data.refresh_token, token_type="refresh")
        if not payload:
            raise HTTPException(401, "Invalid refresh token")
        
        return TokenOutput(
            access_token=create_access_token({"sub": payload["sub"]}),
            refresh_token=create_refresh_token({"sub": payload["sub"]}),
            expires_in=settings.auth_access_token_expire_minutes * 60,
        )
    
    async def me(self, user: User) -> UserOutput:
        """Get current user profile."""
        return UserOutput.model_validate(user)
''',
        f"{project_name}/src/apps/users/services.py": '''"""
User Services - Business logic layer.

Services encapsulate complex business logic separate from views.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from src.apps.users.models import User


class UserService:
    """Business logic for user operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_active_users(self) -> list[User]:
        return await User.objects.using(self.db).filter(is_active=True).all()
    
    async def get_staff_users(self) -> list[User]:
        return await User.objects.using(self.db).filter(is_staff=True).all()
    
    async def deactivate(self, user_id: int) -> User | None:
        user = await User.objects.using(self.db).get_or_none(id=user_id)
        if user:
            user.is_active = False
            await user.save(self.db)
        return user
''',
        f"{project_name}/src/apps/users/routes.py": '''"""
User Routes - URL configuration using AutoRouter.

All routes are auto-generated from ViewSets.
No need to touch FastAPI directly.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core import AutoRouter
from core.dependencies import get_db
from core.auth import login_required

from src.apps.users.views import UserViewSet, AuthViewSet
from src.apps.users.schemas import UserInput, UserOutput, LoginInput, TokenOutput, RefreshInput


# =============================================================================
# USER ROUTES - Auto-generated CRUD
# =============================================================================

router = AutoRouter(prefix="/users", tags=["Users"])
router.register("", UserViewSet)


# =============================================================================
# AUTH ROUTES - Custom actions from AuthViewSet
# =============================================================================

auth_router = AutoRouter(prefix="/auth", tags=["Auth"])
auth = AuthViewSet()


@auth_router.post("/register", response_model=UserOutput, status_code=201)
async def register(data: UserInput, db: AsyncSession = Depends(get_db)):
    """Create new account."""
    return await auth.register(db, data)


@auth_router.post("/login", response_model=TokenOutput)
async def login(data: LoginInput, db: AsyncSession = Depends(get_db)):
    """Get access tokens."""
    return await auth.login(db, data)


@auth_router.post("/refresh", response_model=TokenOutput)
async def refresh(data: RefreshInput):
    """Refresh access token."""
    return await auth.refresh(data)


@auth_router.get("/me", response_model=UserOutput)
async def me(user = Depends(login_required())):
    """Get current user."""
    return await auth.me(user)
''',
        f"{project_name}/src/apps/users/tests/__init__.py": '"""User tests."""\n',
        f"{project_name}/src/apps/users/tests/test_users.py": '''"""
User Tests - API endpoint tests.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register(client: AsyncClient):
    """Test user registration."""
    r = await client.post("/api/v1/auth/register", json={
        "email": "test@example.com",
        "password": "SecurePass1",
    })
    assert r.status_code == 201
    assert r.json()["email"] == "test@example.com"
    assert "password" not in r.json()


@pytest.mark.asyncio
async def test_login(client: AsyncClient):
    """Test login flow."""
    # Register
    await client.post("/api/v1/auth/register", json={
        "email": "login@example.com",
        "password": "SecurePass1",
    })
    # Login
    r = await client.post("/api/v1/auth/login", json={
        "email": "login@example.com",
        "password": "SecurePass1",
    })
    assert r.status_code == 200
    assert "access_token" in r.json()


@pytest.mark.asyncio
async def test_me_requires_auth(client: AsyncClient):
    """Test /me requires authentication."""
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401
''',
        
        # API config package
        f"{project_name}/src/api/__init__.py": '''"""
API configuration package.

Configuracoes centrais da aplicacao.
"""

from src.api.config import settings

__all__ = ["settings"]
''',
        f"{project_name}/src/api/config.py": '''"""
Application Settings - All config from environment variables.

Usage:
    from src.api.config import settings
    
    print(settings.secret_key)
    print(settings.database_url)
"""

from core import Settings


class AppSettings(Settings):
    """
    Application settings loaded from .env file.
    
    All fields can be overridden via environment variables:
        SECRET_KEY=xxx -> settings.secret_key
        DATABASE_URL=xxx -> settings.database_url
    """
    
    # App
    app_name: str = "My App"
    app_version: str = "0.1.0"
    debug: bool = False
    secret_key: str = "change-me-in-production"
    
    # Database
    database_url: str = "sqlite+aiosqlite:///./app.db"
    
    # API
    api_prefix: str = "/api/v1"
    
    # Auth
    auth_access_token_expire_minutes: int = 30
    auth_refresh_token_expire_days: int = 7
    
    # Timezone
    timezone: str = "UTC"


settings = AppSettings()
''',
        
        # Main entry point
        f"{project_name}/src/main.py": '''"""
Application Entry Point.

Core Framework handles everything:
- Routing from ViewSets
- Authentication with JWT
- Validation with Pydantic
- Database with SQLAlchemy
"""

from core import CoreApp, AutoRouter
from core.datetime import configure_datetime
from core.auth import configure_auth

from src.api.config import settings
from src.apps.users.routes import router as users_router, auth_router


# Configure framework
configure_datetime(default_timezone=settings.timezone)
configure_auth(
    secret_key=settings.secret_key,
    access_token_expire_minutes=settings.auth_access_token_expire_minutes,
    refresh_token_expire_days=settings.auth_refresh_token_expire_days,
)

# API Router
api = AutoRouter(prefix=settings.api_prefix)
api.include_router(users_router)
api.include_router(auth_router)

# Application
app = CoreApp(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    routers=[api],
)


@app.get("/health")
async def health():
    """Health check for load balancers."""
    return {"status": "ok"}
''',
        
        # Root files
        f"{project_name}/migrations/__init__.py": '"""Migrations package."""\n',
        f"{project_name}/tests/__init__.py": '"""Tests package."""\n',
        f"{project_name}/tests/conftest.py": '''"""
Configuração de testes.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from src.main import app


@pytest_asyncio.fixture
async def client():
    """Cliente HTTP para testes."""
    async with AsyncClient(
        transport=ASGITransport(app=app.app),
        base_url="http://test",
    ) as client:
        yield client
''',
        f"{project_name}/.env": f'''# Environment variables
# Copie para .env.local para desenvolvimento

# Application
APP_NAME="{project_name}"
APP_VERSION="0.1.0"
ENVIRONMENT="development"
DEBUG=true
SECRET_KEY="change-me-in-production-{project_name}"

# Database
DATABASE_URL="sqlite+aiosqlite:///./app.db"

# Timezone
TIMEZONE="UTC"
USE_TZ=true
''',
        f"{project_name}/.env.example": '''# Environment variables example
# Copy to .env and fill in the values

# Application
APP_NAME="My App"
APP_VERSION="0.1.0"
ENVIRONMENT="development"  # development, staging, production
DEBUG=false
SECRET_KEY="your-secret-key-here"

# Database
DATABASE_URL="sqlite+aiosqlite:///./app.db"
# DATABASE_URL="postgresql+asyncpg://user:pass@localhost/dbname"

# Timezone
TIMEZONE="UTC"
USE_TZ=true

# Auth (optional)
# AUTH_ACCESS_TOKEN_EXPIRE_MINUTES=30
# AUTH_REFRESH_TOKEN_EXPIRE_DAYS=7
''',
        f"{project_name}/core.toml": '''# Core Framework Configuration

[core]
database_url = "sqlite+aiosqlite:///./app.db"
migrations_dir = "./migrations"
app_label = "main"
models_module = "src.apps.users.models"
app_module = "src.main"
host = "0.0.0.0"
port = 8000
''',
        f"{project_name}/pyproject.toml": f'''[project]
name = "{project_name}"
version = "0.1.0"
description = "Project created with Core Framework"
requires-python = ">={python_version}"
dependencies = [
    "core-framework @ git+https://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@github.com/SorPuti/core-framework.git",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.23.0",
    "httpx>=0.26.0",
    "ruff>=0.1.0",
]

[tool.core]
database_url = "sqlite+aiosqlite:///./app.db"
migrations_dir = "./migrations"
app_label = "main"
models_module = "src.apps.users.models"
app_module = "src.main"

[tool.ruff]
target-version = "py312"
line-length = 100
select = ["E", "W", "F", "I", "B", "C4", "UP"]
ignore = ["E501", "B008"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests", "src"]
''',
        f"{project_name}/.python-version": f"{python_version}\n",
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

# uv
uv.lock

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
        f"{project_name}/README.md": f'''# {project_name}

Projeto criado com [Core Framework](https://github.com/SorPuti/core-framework).

## Setup

```bash
# Ativar ambiente virtual
source .venv/bin/activate

# Configurar variáveis de ambiente
cp .env.example .env
# Edite .env com suas configurações

# Criar migrações
core makemigrations --name initial

# Aplicar migrações
core migrate

# Executar servidor
core run
```

## Estrutura

```
{project_name}/
├── src/
│   ├── apps/              # Apps modulares
│   │   └── users/         # App de usuários (exemplo)
│   │       ├── models.py
│   │       ├── schemas.py
│   │       ├── views.py
│   │       ├── services.py
│   │       ├── routes.py
│   │       └── tests/
│   ├── api/               # Configuracoes centrais
│   │   └── config.py      # Settings da aplicacao
│   └── main.py            # Entry point
├── migrations/            # Arquivos de migração
├── tests/                 # Testes globais
├── .env                   # Variáveis de ambiente
├── core.toml              # Config do Core Framework
└── pyproject.toml         # Config do projeto
```

## Criando novos apps

```bash
# Cria um novo app modular
core createapp products

# Estrutura criada:
# src/apps/products/
# ├── models.py
# ├── schemas.py
# ├── views.py
# ├── services.py
# ├── routes.py
# └── tests/
```

Depois, registre o router no `src/main.py`:

```python
from src.apps.products import router as products_router

api_router.include_router(products_router)
```

## Comandos úteis

```bash
core run              # Servidor de desenvolvimento
core makemigrations   # Gerar migrações
core migrate          # Aplicar migrações
core shell            # Shell interativo
core routes           # Listar rotas
core createapp <name> # Criar novo app
core check            # Verificar migrações
```

## Configuração

Todas as configurações são carregadas de variáveis de ambiente.
Edite `.env` ou defina variáveis no sistema:

```bash
# Aplicação
APP_NAME="{project_name}"
DEBUG=true
SECRET_KEY="sua-chave-secreta"

# Banco de dados
DATABASE_URL="sqlite+aiosqlite:///./app.db"

# Timezone (sempre UTC por padrão)
TIMEZONE="UTC"
```

Adicione configuracoes customizadas em `src/api/config.py`.
''',
    }
    
    for filepath, content in files.items():
        Path(filepath).write_text(content)
        print(f"  📄 {filepath}")
    
    # Configura ambiente virtual com uv
    if not skip_venv:
        print(info("\nSetting up virtual environment with uv..."))
        
        project_path = Path(project_name).absolute()
        
        try:
            # Inicializa projeto uv
            subprocess.run(
                ["uv", "venv", "--python", python_version],
                cwd=project_path,
                check=True,
                capture_output=True,
            )
            print(success("  ✓ Virtual environment created (.venv)"))
            
            # Instala dependências
            print(info("  Installing dependencies..."))
            subprocess.run(
                ["uv", "sync"],
                cwd=project_path,
                check=True,
                capture_output=True,
            )
            print(success("  ✓ Dependencies installed"))
            
        except subprocess.CalledProcessError as e:
            print(warning(f"  Warning: {e}"))
            print(info("  You can manually run: cd {project_name} && uv sync"))
        except FileNotFoundError:
            print(warning("  uv not found in PATH after installation"))
            print(info("  Please restart your terminal and run: cd {project_name} && uv sync"))
    
    # Mensagem final
    print()
    print(success("=" * 50))
    print(success(f"✓ Project '{project_name}' created successfully!"))
    print(success("=" * 50))
    print()
    
    # Instruções
    print(bold("Next steps:\n"))
    print(f"  {info('1.')} cd {project_name}")
    
    if not skip_venv:
        print(f"  {info('2.')} source .venv/bin/activate")
        print(f"  {info('3.')} core makemigrations --name initial")
        print(f"  {info('4.')} core migrate")
        print(f"  {info('5.')} core run")
    else:
        print(f"  {info('2.')} uv sync  # ou pip install -e .")
        print(f"  {info('3.')} source .venv/bin/activate")
        print(f"  {info('4.')} core makemigrations --name initial")
        print(f"  {info('5.')} core migrate")
        print(f"  {info('6.')} core run")
    
    print()
    print(f"  Then open: {bold('http://localhost:8000/docs')}")
    print()
    
    # Gera script de ativação
    activate_script = f"{project_name}/activate.sh"
    Path(activate_script).write_text(f'''#!/bin/bash
# Ativa o ambiente virtual do projeto {project_name}
cd "$(dirname "$0")"
source .venv/bin/activate
echo "✓ Virtual environment activated for {project_name}"
echo "  Run 'core run' to start the server"
''')
    os.chmod(activate_script, 0o755)
    
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


def cmd_check(args: argparse.Namespace) -> int:
    """Analisa migrações pendentes sem aplicar."""
    config = load_config()
    
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
                migration = engine._load_migration(file_path)
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
                
                # Drop all tables
                for table in tables:
                    print(f"  Dropping: {table}")
                    try:
                        await conn.execute(text(f'DROP TABLE IF EXISTS "{table}"'))
                    except Exception as e:
                        print(warning(f"    Warning: {e}"))
                
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
    init_parser = subparsers.add_parser("init", help="Initialize a new project with uv")
    init_parser.add_argument("name", nargs="?", help="Project name (default: myproject)")
    init_parser.add_argument("--python", "-p", default="3.12", help="Python version (default: 3.12)")
    init_parser.add_argument("--no-venv", action="store_true", help="Skip virtual environment setup")
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
