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

ViewSets:
    - UserViewSet: User CRUD operations
    - AuthViewSet: Authentication (login, register, refresh, me)
"""

from src.apps.users.routes import users_router, auth_router

__all__ = ["users_router", "auth_router"]
''',
        f"{project_name}/src/apps/users/models.py": '''"""
User model extending AbstractUser.

This module defines the custom User model with additional fields
while inheriting all authentication features from AbstractUser.

Inherited fields from AbstractUser:
    - id: Primary key
    - email: Unique email (used for login)
    - password_hash: Hashed password
    - is_active: Whether user can login
    - is_staff: Whether user can access admin
    - is_superuser: Whether user has all permissions
    - date_joined: Account creation timestamp
    - last_login: Last login timestamp

Inherited from PermissionsMixin:
    - groups: Many-to-many relationship with Group
    - user_permissions: Direct permissions

Available methods:
    - set_password(raw_password): Hash and set password
    - check_password(raw_password): Verify password
    - has_perm(permission): Check single permission
    - has_perms(permissions): Check multiple permissions
    - authenticate(email, password, db): Class method to authenticate
    - create_user(email, password, db): Class method to create user
    - create_superuser(email, password, db): Class method to create admin
"""

from sqlalchemy.orm import Mapped

from core import Field
from core.auth import AbstractUser, PermissionsMixin


class User(AbstractUser, PermissionsMixin):
    """
    Custom User model with additional profile fields.
    
    Extends AbstractUser for authentication and PermissionsMixin
    for groups and permissions support.
    
    Example usage:
        # Create user
        user = await User.create_user("user@example.com", "password123", db)
        
        # Create superuser
        admin = await User.create_superuser("admin@example.com", "password123", db)
        
        # Authenticate
        user = await User.authenticate("user@example.com", "password123", db)
        
        # Check permissions
        if user.has_perm("posts.delete"):
            ...
        
        # Add to group
        await user.add_to_group("editors", db)
    """
    
    __tablename__ = "users"
    
    # Additional profile fields
    first_name: Mapped[str | None] = Field.string(max_length=100, nullable=True)
    last_name: Mapped[str | None] = Field.string(max_length=100, nullable=True)
    phone: Mapped[str | None] = Field.string(max_length=20, nullable=True)
    avatar_url: Mapped[str | None] = Field.string(max_length=500, nullable=True)
    
    @property
    def full_name(self) -> str:
        """Return user's full name or email if not set."""
        parts = [self.first_name, self.last_name]
        return " ".join(p for p in parts if p) or self.email
    
    @property
    def short_name(self) -> str:
        """Return first name or email username."""
        return self.first_name or self.email.split("@")[0]
''',
        f"{project_name}/src/apps/users/schemas.py": '''"""
User schemas for request/response validation.

Defines Pydantic schemas for:
    - User registration (UserRegisterInput)
    - User login (LoginInput)
    - User profile output (UserOutput)
    - Token response (TokenResponse)
"""

from pydantic import EmailStr, field_validator

from core import InputSchema, OutputSchema
from core.datetime import DateTime


class UserRegisterInput(InputSchema):
    """
    Schema for user registration.
    
    Validates:
        - Email format
        - Password strength (min 8 chars, uppercase, lowercase, digit)
    """
    
    email: EmailStr
    password: str
    first_name: str | None = None
    last_name: str | None = None
    
    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password strength."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class LoginInput(InputSchema):
    """Schema for user login."""
    
    email: EmailStr
    password: str


class UserOutput(OutputSchema):
    """
    Schema for user response.
    
    Excludes sensitive data like password_hash.
    """
    
    id: int
    email: str
    first_name: str | None
    last_name: str | None
    phone: str | None
    avatar_url: str | None
    is_active: bool
    is_staff: bool
    date_joined: DateTime
    last_login: DateTime | None


class TokenResponse(OutputSchema):
    """
    Schema for authentication token response.
    
    Contains JWT access and refresh tokens.
    """
    
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshTokenInput(InputSchema):
    """Schema for refreshing access token."""
    
    refresh_token: str


class UserUpdateInput(InputSchema):
    """
    Schema for updating user profile.
    
    All fields are optional for partial updates.
    """
    
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    avatar_url: str | None = None


class ChangePasswordInput(InputSchema):
    """
    Schema for changing password.
    
    Requires current password for security.
    """
    
    current_password: str
    new_password: str
    
    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password strength."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v
''',
        f"{project_name}/src/apps/users/views.py": '''"""
User views using DRF-style ViewSets.

All endpoints are defined using ViewSets and @action decorators.
No direct FastAPI decorators needed - pure DRF pattern.

ViewSets:
    - UserViewSet: User CRUD operations
    - AuthViewSet: Authentication (login, register, refresh, me)
"""

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from core import ModelViewSet, action
from core.permissions import AllowAny, IsAuthenticated
from core.auth import (
    create_access_token,
    create_refresh_token,
    verify_token,
    login_required,
)

from src.apps.users.models import User
from src.apps.users.schemas import (
    UserRegisterInput,
    UserUpdateInput,
    UserOutput,
    LoginInput,
    TokenResponse,
    RefreshTokenInput,
    ChangePasswordInput,
)
from src.api.config import settings


class UserViewSet(ModelViewSet):
    """
    ViewSet for user management (CRUD).
    
    Endpoints (auto-generated):
        GET    /users/              - List all users
        POST   /users/              - Create user (admin)
        GET    /users/{id}/         - Get user details
        PUT    /users/{id}/         - Update user
        PATCH  /users/{id}/         - Partial update
        DELETE /users/{id}/         - Delete user
    
    Custom actions:
        POST   /users/{id}/activate/    - Activate user
        POST   /users/{id}/deactivate/  - Deactivate user
    """
    
    model = User
    input_schema = UserRegisterInput
    output_schema = UserOutput
    tags = ["Users"]
    
    # Permissions per action
    permission_classes = [IsAuthenticated]
    permission_classes_by_action = {
        "list": [IsAuthenticated],
        "retrieve": [IsAuthenticated],
        "create": [IsAuthenticated],  # Admin only in production
        "update": [IsAuthenticated],
        "partial_update": [IsAuthenticated],
        "destroy": [IsAuthenticated],
    }
    
    # Unique field validation
    unique_fields = ["email"]
    
    async def perform_create_validation(self, data: dict, db: AsyncSession) -> dict:
        """Hash password before creating user."""
        if "password" in data:
            password = data.pop("password")
            data["password_hash"] = User.make_password(password)
        return data
    
    @action(methods=["POST"], detail=True, permission_classes=[IsAuthenticated])
    async def activate(self, request: Request, db: AsyncSession, **kwargs):
        """Activate a user account."""
        user = await self.get_object(db, **kwargs)
        user.is_active = True
        await user.save(db)
        return {"message": f"User {user.email} activated", "is_active": True}
    
    @action(methods=["POST"], detail=True, permission_classes=[IsAuthenticated])
    async def deactivate(self, request: Request, db: AsyncSession, **kwargs):
        """Deactivate a user account."""
        user = await self.get_object(db, **kwargs)
        user.is_active = False
        await user.save(db)
        return {"message": f"User {user.email} deactivated", "is_active": False}


class AuthViewSet(ModelViewSet):
    """
    ViewSet for authentication operations.
    
    All authentication endpoints in one ViewSet using @action.
    No FastAPI decorators needed - pure DRF pattern.
    
    Endpoints:
        POST /auth/register/  - Register new user
        POST /auth/login/     - Login and get tokens
        POST /auth/refresh/   - Refresh access token
        GET  /auth/me/        - Get current user profile
        POST /auth/password/  - Change password
    """
    
    model = User
    input_schema = UserRegisterInput
    output_schema = UserOutput
    tags = ["Authentication"]
    
    # Default: no permissions (public endpoints)
    permission_classes = [AllowAny]
    
    # Disable default CRUD actions (we only use custom actions)
    async def list(self, *args, **kwargs):
        raise HTTPException(status_code=404, detail="Not found")
    
    async def retrieve(self, *args, **kwargs):
        raise HTTPException(status_code=404, detail="Not found")
    
    async def create(self, *args, **kwargs):
        raise HTTPException(status_code=404, detail="Not found")
    
    async def update(self, *args, **kwargs):
        raise HTTPException(status_code=404, detail="Not found")
    
    async def destroy(self, *args, **kwargs):
        raise HTTPException(status_code=404, detail="Not found")
    
    @action(methods=["POST"], detail=False, permission_classes=[AllowAny])
    async def register(self, request: Request, db: AsyncSession, **kwargs):
        """
        Register a new user account.
        
        Request body:
            - email: User email (unique)
            - password: Strong password (min 8 chars, upper, lower, digit)
            - first_name: Optional first name
            - last_name: Optional last name
        
        Returns:
            Created user data (without password)
        """
        # Parse request body
        body = await request.json()
        data = UserRegisterInput.model_validate(body)
        
        # Check if email exists
        existing = await User.get_by_email(data.email, db)
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Create user
        user = await User.create_user(
            email=data.email,
            password=data.password,
            db=db,
            first_name=data.first_name,
            last_name=data.last_name,
        )
        
        return UserOutput.model_validate(user).model_dump()
    
    @action(methods=["POST"], detail=False, permission_classes=[AllowAny])
    async def login(self, request: Request, db: AsyncSession, **kwargs):
        """
        Authenticate and get access tokens.
        
        Request body:
            - email: User email
            - password: User password
        
        Returns:
            - access_token: JWT access token
            - refresh_token: JWT refresh token
            - token_type: "bearer"
            - expires_in: Token expiration in seconds
        """
        body = await request.json()
        data = LoginInput.model_validate(body)
        
        # Authenticate
        user = await User.authenticate(data.email, data.password, db)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        # Generate tokens
        access_token = create_access_token({"sub": str(user.id), "email": user.email})
        refresh_token = create_refresh_token({"sub": str(user.id)})
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.auth_access_token_expire_minutes * 60,
        ).model_dump()
    
    @action(methods=["POST"], detail=False, permission_classes=[AllowAny])
    async def refresh(self, request: Request, db: AsyncSession, **kwargs):
        """
        Refresh access token using refresh token.
        
        Request body:
            - refresh_token: Valid refresh token
        
        Returns:
            New access and refresh tokens
        """
        body = await request.json()
        data = RefreshTokenInput.model_validate(body)
        
        # Verify refresh token
        payload = verify_token(data.refresh_token, token_type="refresh")
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
        
        # Generate new tokens
        access_token = create_access_token({"sub": payload["sub"]})
        refresh_token = create_refresh_token({"sub": payload["sub"]})
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.auth_access_token_expire_minutes * 60,
        ).model_dump()
    
    @action(methods=["GET"], detail=False, permission_classes=[IsAuthenticated])
    async def me(self, request: Request, db: AsyncSession, **kwargs):
        """
        Get current authenticated user profile.
        
        Requires: Authorization header with Bearer token
        
        Returns:
            Current user data
        """
        # Get user from token
        user = await login_required(request, db)
        return UserOutput.model_validate(user).model_dump()
    
    @action(methods=["POST"], detail=False, permission_classes=[IsAuthenticated])
    async def password(self, request: Request, db: AsyncSession, **kwargs):
        """
        Change current user password.
        
        Requires: Authorization header with Bearer token
        
        Request body:
            - current_password: Current password
            - new_password: New strong password
        
        Returns:
            Success message
        """
        body = await request.json()
        data = ChangePasswordInput.model_validate(body)
        
        # Get current user
        user = await login_required(request, db)
        
        # Verify current password
        if not user.check_password(data.current_password):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        
        # Update password
        user.set_password(data.new_password)
        await user.save(db)
        
        return {"message": "Password changed successfully"}
''',
        f"{project_name}/src/apps/users/services.py": '''"""
User business logic services.

Separates complex business logic from views for better
testability and reusability.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from src.apps.users.models import User


class UserService:
    """
    Service class for user-related business logic.
    
    Example usage:
        service = UserService(db)
        active_users = await service.get_active_users()
        admins = await service.get_staff_users()
    """
    
    def __init__(self, db: "AsyncSession"):
        self.db = db
    
    async def get_active_users(self) -> list["User"]:
        """Get all active users."""
        from src.apps.users.models import User
        return await User.objects.using(self.db).filter(is_active=True).all()
    
    async def get_staff_users(self) -> list["User"]:
        """Get all staff users."""
        from src.apps.users.models import User
        return await User.objects.using(self.db).filter(is_staff=True).all()
    
    async def get_superusers(self) -> list["User"]:
        """Get all superusers."""
        from src.apps.users.models import User
        return await User.objects.using(self.db).filter(is_superuser=True).all()
    
    async def deactivate_user(self, user_id: int) -> "User | None":
        """Deactivate a user account."""
        from src.apps.users.models import User
        user = await User.objects.using(self.db).get_or_none(id=user_id)
        if user:
            user.is_active = False
            await user.save(self.db)
        return user
    
    async def activate_user(self, user_id: int) -> "User | None":
        """Activate a user account."""
        from src.apps.users.models import User
        user = await User.objects.using(self.db).get_or_none(id=user_id)
        if user:
            user.is_active = True
            await user.save(self.db)
        return user
''',
        f"{project_name}/src/apps/users/routes.py": '''"""
User routes configuration.

All routes are defined using ViewSets - no FastAPI decorators needed.
This is the DRF-style pattern for clean, maintainable code.

Routes (auto-generated from ViewSets):
    Users (CRUD):
        GET    /users/              - List all users
        POST   /users/              - Create user
        GET    /users/{id}/         - Get user by ID
        PUT    /users/{id}/         - Update user
        PATCH  /users/{id}/         - Partial update
        DELETE /users/{id}/         - Delete user
        POST   /users/{id}/activate/    - Activate user
        POST   /users/{id}/deactivate/  - Deactivate user
    
    Authentication:
        POST   /auth/register/  - Register new user
        POST   /auth/login/     - Login and get tokens
        POST   /auth/refresh/   - Refresh access token
        GET    /auth/me/        - Get current user
        POST   /auth/password/  - Change password
"""

from core import AutoRouter
from src.apps.users.views import UserViewSet, AuthViewSet


# User management routes (CRUD + custom actions)
users_router = AutoRouter(prefix="/users", tags=["Users"])
users_router.register("", UserViewSet, basename="user")

# Authentication routes (all via @action)
auth_router = AutoRouter(prefix="/auth", tags=["Authentication"])
auth_router.register("", AuthViewSet, basename="auth")
''',
        f"{project_name}/src/apps/users/tests/__init__.py": '"""Tests for users app."""\n',
        f"{project_name}/src/apps/users/tests/test_users.py": '''"""
User app tests.

Tests for user registration, authentication, and profile management.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_users(client: AsyncClient):
    """Test listing users endpoint."""
    response = await client.get("/api/v1/users/")
    assert response.status_code in [200, 401]  # 401 if auth required


@pytest.mark.asyncio
async def test_register_user(client: AsyncClient):
    """Test user registration."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "newuser@example.com",
            "password": "SecurePass123",
            "first_name": "Test",
            "last_name": "User",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newuser@example.com"
    assert "password" not in data
    assert "password_hash" not in data


@pytest.mark.asyncio
async def test_register_weak_password(client: AsyncClient):
    """Test registration with weak password fails."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "weak@example.com",
            "password": "weak",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login(client: AsyncClient):
    """Test user login."""
    # First register
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "login@example.com",
            "password": "SecurePass123",
        },
    )
    
    # Then login
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "login@example.com",
            "password": "SecurePass123",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient):
    """Test login with invalid credentials fails."""
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "nonexistent@example.com",
            "password": "WrongPass123",
        },
    )
    assert response.status_code == 401
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
Configuracoes da aplicacao.

Todas as configuracoes sao carregadas de variaveis de ambiente
ou do arquivo .env.

Variaveis de ambiente sao mapeadas automaticamente:
    SECRET_KEY -> settings.secret_key
    DATABASE_URL -> settings.database_url
    DEBUG -> settings.debug
"""

from typing import Literal
from pydantic import Field as PydanticField
from core import Settings


class AppSettings(Settings):
    """
    Configuracoes da aplicacao.
    
    Todas as configuracoes abaixo podem ser sobrescritas via variaveis
    de ambiente ou arquivo .env.
    
    Para adicionar configuracoes customizadas, basta definir novos campos:
    
        stripe_api_key: str = ""
        sendgrid_api_key: str = ""
        
    E definir no .env:
    
        STRIPE_API_KEY=sk_test_xxx
        SENDGRID_API_KEY=SG.xxx
    """
    
    # =========================================================================
    # APPLICATION
    # =========================================================================
    
    app_name: str = PydanticField(
        default="My App",
        description="Nome da aplicacao (exibido na documentacao)",
    )
    app_version: str = PydanticField(
        default="0.1.0",
        description="Versao da aplicacao",
    )
    environment: Literal["development", "staging", "production", "testing"] = PydanticField(
        default="development",
        description="Ambiente de execucao (development, staging, production, testing)",
    )
    debug: bool = PydanticField(
        default=False,
        description="Modo debug - NUNCA use True em producao",
    )
    secret_key: str = PydanticField(
        default="change-me-in-production",
        description="Chave secreta para criptografia e tokens JWT",
    )
    
    # =========================================================================
    # DATABASE
    # =========================================================================
    
    database_url: str = PydanticField(
        default="sqlite+aiosqlite:///./app.db",
        description="URL de conexao do banco (async). Exemplos: "
                    "sqlite+aiosqlite:///./app.db, "
                    "postgresql+asyncpg://user:pass@localhost/db, "
                    "mysql+aiomysql://user:pass@localhost/db",
    )
    database_echo: bool = PydanticField(
        default=False,
        description="Habilita logging de SQL (util para debug)",
    )
    database_pool_size: int = PydanticField(
        default=5,
        description="Tamanho do pool de conexoes",
    )
    database_max_overflow: int = PydanticField(
        default=10,
        description="Conexoes extras alem do pool",
    )
    database_pool_timeout: int = PydanticField(
        default=30,
        description="Timeout em segundos para obter conexao do pool",
    )
    database_pool_recycle: int = PydanticField(
        default=3600,
        description="Tempo em segundos para reciclar conexoes",
    )
    
    # =========================================================================
    # API
    # =========================================================================
    
    api_prefix: str = PydanticField(
        default="/api/v1",
        description="Prefixo das rotas da API",
    )
    docs_url: str | None = PydanticField(
        default="/docs",
        description="URL da documentacao Swagger (None para desabilitar)",
    )
    redoc_url: str | None = PydanticField(
        default="/redoc",
        description="URL da documentacao ReDoc (None para desabilitar)",
    )
    openapi_url: str | None = PydanticField(
        default="/openapi.json",
        description="URL do schema OpenAPI (None para desabilitar)",
    )
    
    # =========================================================================
    # CORS
    # =========================================================================
    
    cors_origins: list[str] = PydanticField(
        default=["*"],
        description="Origens permitidas para CORS. Use ['*'] para permitir todas",
    )
    cors_allow_credentials: bool = PydanticField(
        default=True,
        description="Permitir credenciais (cookies, auth headers) em CORS",
    )
    cors_allow_methods: list[str] = PydanticField(
        default=["*"],
        description="Metodos HTTP permitidos em CORS",
    )
    cors_allow_headers: list[str] = PydanticField(
        default=["*"],
        description="Headers permitidos em CORS",
    )
    
    # =========================================================================
    # AUTHENTICATION
    # =========================================================================
    
    auth_secret_key: str | None = PydanticField(
        default=None,
        description="Chave secreta para tokens (usa secret_key se None)",
    )
    auth_algorithm: str = PydanticField(
        default="HS256",
        description="Algoritmo JWT (HS256, HS384, HS512, RS256, etc.)",
    )
    auth_access_token_expire_minutes: int = PydanticField(
        default=30,
        description="Tempo de expiracao do access token em minutos",
    )
    auth_refresh_token_expire_days: int = PydanticField(
        default=7,
        description="Tempo de expiracao do refresh token em dias",
    )
    auth_password_hasher: str = PydanticField(
        default="pbkdf2_sha256",
        description="Algoritmo de hash de senha: pbkdf2_sha256, argon2, bcrypt, scrypt",
    )
    
    # =========================================================================
    # DATETIME / TIMEZONE
    # =========================================================================
    
    timezone: str = PydanticField(
        default="UTC",
        description="Timezone padrao da aplicacao (sempre use UTC)",
    )
    use_tz: bool = PydanticField(
        default=True,
        description="Usar datetimes aware (com timezone). Recomendado: True",
    )
    datetime_format: str = PydanticField(
        default="%Y-%m-%dT%H:%M:%S%z",
        description="Formato padrao de datetime (ISO 8601)",
    )
    date_format: str = PydanticField(
        default="%Y-%m-%d",
        description="Formato padrao de data",
    )
    time_format: str = PydanticField(
        default="%H:%M:%S",
        description="Formato padrao de hora",
    )
    
    # =========================================================================
    # SERVER
    # =========================================================================
    
    host: str = PydanticField(
        default="0.0.0.0",
        description="Host do servidor",
    )
    port: int = PydanticField(
        default=8000,
        description="Porta do servidor",
    )
    workers: int = PydanticField(
        default=1,
        description="Numero de workers (use 1 em desenvolvimento)",
    )
    reload: bool = PydanticField(
        default=True,
        description="Auto-reload em desenvolvimento",
    )
    
    # =========================================================================
    # PERFORMANCE
    # =========================================================================
    
    request_timeout: int = PydanticField(
        default=30,
        description="Timeout de requisicoes em segundos",
    )
    max_request_size: int = PydanticField(
        default=10 * 1024 * 1024,  # 10MB
        description="Tamanho maximo de requisicao em bytes",
    )
    
    # =========================================================================
    # LOGGING
    # =========================================================================
    
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = PydanticField(
        default="INFO",
        description="Nivel de log",
    )
    log_format: str = PydanticField(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Formato de log",
    )
    log_json: bool = PydanticField(
        default=False,
        description="Usar formato JSON para logs (recomendado em producao)",
    )
    
    # =========================================================================
    # CUSTOM SETTINGS
    # Adicione suas configuracoes customizadas abaixo
    # =========================================================================
    
    # stripe_api_key: str = ""
    # sendgrid_api_key: str = ""
    # redis_url: str = "redis://localhost:6379"
    # aws_access_key_id: str = ""
    # aws_secret_access_key: str = ""
    # aws_s3_bucket: str = ""


# Instancia global de configuracoes
settings = AppSettings()
''',
        
        # Main entry point
        f"{project_name}/src/main.py": '''"""
Main Application Entry Point.

Pure DRF-style application - no direct FastAPI decorators needed.
All routes are defined via ViewSets and AutoRouter.

Features:
    - JWT Authentication (login, register, token refresh)
    - User management with AbstractUser
    - Automatic API documentation at /docs
    - CORS configuration
    - DateTime configured for UTC

Routes:
    /api/v1/users/     - User CRUD (UserViewSet)
    /api/v1/auth/      - Authentication (AuthViewSet)
"""

from core import CoreApp, AutoRouter, APIView
from core.datetime import configure_datetime
from core.auth import configure_auth
from core.permissions import AllowAny

from src.api.config import settings
from src.apps.users.routes import users_router, auth_router


# Configure DateTime to use UTC globally
configure_datetime(
    default_timezone=settings.timezone,
    use_aware_datetimes=settings.use_tz,
)

# Configure authentication system
configure_auth(
    secret_key=settings.secret_key,
    access_token_expire_minutes=settings.auth_access_token_expire_minutes,
    refresh_token_expire_days=settings.auth_refresh_token_expire_days,
    password_hasher=settings.auth_password_hasher,
)


# Health check view using APIView (DRF-style)
class HealthView(APIView):
    """Health check endpoint for monitoring."""
    
    permission_classes = [AllowAny]
    tags = ["Health"]
    
    async def get(self, request, **kwargs):
        """
        Health check endpoint.
        
        Use for load balancer health checks and monitoring.
        """
        return {
            "status": "healthy",
            "version": settings.app_version,
            "environment": settings.environment,
        }


class RootView(APIView):
    """Root endpoint with API information."""
    
    permission_classes = [AllowAny]
    tags = ["Root"]
    
    async def get(self, request, **kwargs):
        """
        Root endpoint.
        
        Returns API information and documentation links.
        """
        return {
            "message": f"Welcome to {settings.app_name}",
            "version": settings.app_version,
            "environment": settings.environment,
            "docs": settings.docs_url,
            "redoc": settings.redoc_url,
        }


# Main API router
api_router = AutoRouter(prefix=settings.api_prefix)

# Include app routers (ViewSets)
api_router.include_router(users_router)  # /api/v1/users/
api_router.include_router(auth_router)   # /api/v1/auth/

# Root router for health and info
root_router = AutoRouter(prefix="", tags=["System"])

# Create application
app = CoreApp(
    title=settings.app_name,
    description="API built with Core Framework - Django-inspired, FastAPI-powered. "
                "All endpoints use DRF-style ViewSets for clean, maintainable code.",
    version=settings.app_version,
    debug=settings.debug,
    routers=[api_router, root_router],
)

# Register root views (DRF-style)
app.add_api_route("/", RootView.as_route("/")[1], methods=["GET"], tags=["System"])
app.add_api_route("/health", HealthView.as_route("/health")[1], methods=["GET"], tags=["System"])
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


def cmd_topics_list(args: argparse.Namespace) -> int:
    """List Kafka topics."""
    print()
    print(bold("Kafka Topics"))
    print("=" * 50)
    
    async def list_topics():
        from core.messaging.kafka import KafkaAdmin
        
        admin = KafkaAdmin()
        await admin.connect()
        
        topics = await admin.list_topics()
        
        if not topics:
            print(info("No topics found."))
        else:
            for topic in sorted(topics):
                print(f"  - {topic}")
        
        await admin.close()
    
    try:
        asyncio.run(list_topics())
    except Exception as e:
        print(error(f"Error: {e}"))
        return 1
    
    return 0


def cmd_topics_create(args: argparse.Namespace) -> int:
    """Create a Kafka topic."""
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
    
    try:
        asyncio.run(create_topic())
    except Exception as e:
        print(error(f"Error: {e}"))
        return 1
    
    return 0


def cmd_topics_delete(args: argparse.Namespace) -> int:
    """Delete a Kafka topic."""
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
    
    try:
        asyncio.run(delete_topic())
    except Exception as e:
        print(error(f"Error: {e}"))
        return 1
    
    return 0


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
        print("  docker-compose up -d")
    
    if target == "pm2" or target == "all":
        print()
        print(info("To start with PM2:"))
        print("  pm2 start ecosystem.config.js")
    
    if target == "k8s" or target == "all":
        print()
        print(info("To deploy to Kubernetes:"))
        print("  kubectl apply -f k8s/")
    
    return 0


def cmd_tasks(args: argparse.Namespace) -> int:
    """List registered tasks."""
    print()
    print(bold("Registered Tasks"))
    print("=" * 50)
    
    # Add current directory to path
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    
    # Import app to register tasks
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
    except Exception:
        pass
    
    from core.tasks.registry import list_tasks
    
    tasks = list_tasks()
    
    if not tasks:
        print(info("No tasks registered."))
        print()
        print(info("To register tasks, use @task or @periodic_task decorators:"))
        print()
        print("  from core.tasks import task, periodic_task")
        print()
        print("  @task(queue='emails')")
        print("  async def send_email(to, subject, body):")
        print("      ...")
        print()
        print("  @periodic_task(cron='0 0 * * *')")
        print("  async def daily_cleanup():")
        print("      ...")
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
