"""
Sistema de Autenticação e Autorização - Estilo Django Moderno.

Fornece:
- AbstractUser: Modelo base para usuários
- Group: Grupos de usuários
- Permission: Permissões por string (app.action)
- Decorators e dependencies para proteção de rotas
- Autenticação JWT integrada
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any, ClassVar, TYPE_CHECKING

from sqlalchemy import String, Boolean, DateTime, Integer, ForeignKey, Table, Column, Text
from sqlalchemy.orm import Mapped, relationship, declared_attr

from core.models import Model, Field

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# =============================================================================
# Tabelas de Associação (Many-to-Many)
# =============================================================================

def _create_user_groups_table(user_tablename: str = "users"):
    """Cria tabela de associação user <-> groups."""
    return Table(
        "auth_user_groups",
        Model.metadata,
        Column("user_id", Integer, ForeignKey(f"{user_tablename}.id", ondelete="CASCADE"), primary_key=True),
        Column("group_id", Integer, ForeignKey("auth_groups.id", ondelete="CASCADE"), primary_key=True),
    )


def _create_user_permissions_table(user_tablename: str = "users"):
    """Cria tabela de associação user <-> permissions."""
    return Table(
        "auth_user_permissions",
        Model.metadata,
        Column("user_id", Integer, ForeignKey(f"{user_tablename}.id", ondelete="CASCADE"), primary_key=True),
        Column("permission_id", Integer, ForeignKey("auth_permissions.id", ondelete="CASCADE"), primary_key=True),
    )


def _create_group_permissions_table():
    """Cria tabela de associação group <-> permissions."""
    return Table(
        "auth_group_permissions",
        Model.metadata,
        Column("group_id", Integer, ForeignKey("auth_groups.id", ondelete="CASCADE"), primary_key=True),
        Column("permission_id", Integer, ForeignKey("auth_permissions.id", ondelete="CASCADE"), primary_key=True),
    )


# =============================================================================
# Models de Autenticação
# =============================================================================

class Permission(Model):
    """
    Permissão por string no formato 'app.action' ou 'resource.action'.
    
    Exemplos:
        - "posts.create"
        - "posts.delete"
        - "users.view"
        - "admin.access"
    """
    
    __tablename__ = "auth_permissions"
    
    id: Mapped[int] = Field.pk()
    codename: Mapped[str] = Field.string(max_length=100, unique=True)
    name: Mapped[str] = Field.string(max_length=255)
    description: Mapped[str | None] = Field.text(nullable=True)
    
    def __repr__(self) -> str:
        return f"<Permission {self.codename}>"
    
    def __str__(self) -> str:
        return self.codename
    
    @classmethod
    async def get_or_create(
        cls,
        codename: str,
        name: str | None = None,
        db: "AsyncSession | None" = None,
    ) -> "Permission":
        """Obtém ou cria uma permissão."""
        if db is None:
            from core.models import get_session
            db = await get_session()
        
        perm = await cls.objects.using(db).filter(codename=codename).first()
        if perm:
            return perm
        
        perm = cls(
            codename=codename,
            name=name or codename.replace(".", " ").replace("_", " ").title(),
        )
        await perm.save(db)
        return perm


class Group(Model):
    """
    Grupo de usuários com permissões compartilhadas.
    
    Exemplo:
        admin_group = Group(name="Administrators")
        await admin_group.permissions.add(delete_permission)
    """
    
    __tablename__ = "auth_groups"
    
    id: Mapped[int] = Field.pk()
    name: Mapped[str] = Field.string(max_length=150, unique=True)
    description: Mapped[str | None] = Field.text(nullable=True)
    
    # Relacionamento com permissões
    permissions: Mapped[list["Permission"]] = relationship(
        "Permission",
        secondary=_create_group_permissions_table(),
        lazy="selectin",
    )
    
    def __repr__(self) -> str:
        return f"<Group {self.name}>"
    
    def __str__(self) -> str:
        return self.name
    
    async def add_permission(self, permission: Permission | str, db: "AsyncSession") -> None:
        """Adiciona uma permissão ao grupo."""
        if isinstance(permission, str):
            permission = await Permission.get_or_create(permission, db=db)
        
        if permission not in self.permissions:
            self.permissions.append(permission)
            await self.save(db)
    
    async def remove_permission(self, permission: Permission | str, db: "AsyncSession") -> None:
        """Remove uma permissão do grupo."""
        if isinstance(permission, str):
            perm = await Permission.objects.using(db).filter(codename=permission).first()
            if perm:
                permission = perm
            else:
                return
        
        if permission in self.permissions:
            self.permissions.remove(permission)
            await self.save(db)
    
    def has_permission(self, codename: str) -> bool:
        """Verifica se o grupo tem uma permissão."""
        return any(p.codename == codename for p in self.permissions)


class AbstractUser(Model):
    """
    Modelo abstrato base para usuários.
    
    Herde desta classe para criar seu modelo de usuário:
    
        class User(AbstractUser):
            __tablename__ = "users"
            
            # Campos adicionais
            phone: Mapped[str | None] = Field.string(max_length=20, nullable=True)
            avatar_url: Mapped[str | None] = Field.string(max_length=500, nullable=True)
    
    Campos incluídos:
        - id: Chave primária
        - email: Email único (usado para login)
        - password_hash: Hash da senha
        - is_active: Se o usuário está ativo
        - is_staff: Se pode acessar área administrativa
        - is_superuser: Se tem todas as permissões
        - date_joined: Data de criação
        - last_login: Último login
        - groups: Grupos do usuário
        - user_permissions: Permissões diretas
    """
    
    __abstract__ = True
    
    # Campos de autenticação
    id: Mapped[int] = Field.pk()
    email: Mapped[str] = Field.string(max_length=255, unique=True, index=True)
    password_hash: Mapped[str] = Field.string(max_length=255)
    
    # Campos de status
    is_active: Mapped[bool] = Field.boolean(default=True)
    is_staff: Mapped[bool] = Field.boolean(default=False)
    is_superuser: Mapped[bool] = Field.boolean(default=False)
    
    # Timestamps
    date_joined: Mapped[datetime] = Field.datetime(auto_now_add=True)
    last_login: Mapped[datetime | None] = Field.datetime(nullable=True)
    
    # Configuração
    USERNAME_FIELD: ClassVar[str] = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.email}>"
    
    def __str__(self) -> str:
        return self.email
    
    # =========================================================================
    # Métodos de Senha
    # =========================================================================
    
    def set_password(self, raw_password: str) -> None:
        """
        Define a senha do usuário (com hash).
        
        Usa PBKDF2 com SHA256 e salt aleatório.
        """
        salt = secrets.token_hex(16)
        hash_value = hashlib.pbkdf2_hmac(
            "sha256",
            raw_password.encode("utf-8"),
            salt.encode("utf-8"),
            100000,
        ).hex()
        self.password_hash = f"pbkdf2_sha256${salt}${hash_value}"
    
    def check_password(self, raw_password: str) -> bool:
        """Verifica se a senha está correta."""
        if not self.password_hash:
            return False
        
        try:
            algorithm, salt, hash_value = self.password_hash.split("$")
            new_hash = hashlib.pbkdf2_hmac(
                "sha256",
                raw_password.encode("utf-8"),
                salt.encode("utf-8"),
                100000,
            ).hex()
            return secrets.compare_digest(hash_value, new_hash)
        except (ValueError, AttributeError):
            return False
    
    @classmethod
    def make_password(cls, raw_password: str) -> str:
        """Gera hash de senha (método de classe)."""
        salt = secrets.token_hex(16)
        hash_value = hashlib.pbkdf2_hmac(
            "sha256",
            raw_password.encode("utf-8"),
            salt.encode("utf-8"),
            100000,
        ).hex()
        return f"pbkdf2_sha256${salt}${hash_value}"
    
    # =========================================================================
    # Métodos de Permissão
    # =========================================================================
    
    def has_perm(self, perm: str) -> bool:
        """
        Verifica se o usuário tem uma permissão específica.
        
        Args:
            perm: Código da permissão (ex: "posts.delete")
            
        Returns:
            True se tem a permissão
        """
        # Superuser tem todas as permissões
        if self.is_superuser and self.is_active:
            return True
        
        if not self.is_active:
            return False
        
        # Verifica permissões diretas
        if hasattr(self, "user_permissions"):
            if any(p.codename == perm for p in self.user_permissions):
                return True
        
        # Verifica permissões via grupos
        if hasattr(self, "groups"):
            for group in self.groups:
                if group.has_permission(perm):
                    return True
        
        return False
    
    def has_perms(self, perms: list[str]) -> bool:
        """Verifica se tem todas as permissões da lista."""
        return all(self.has_perm(perm) for perm in perms)
    
    def has_any_perm(self, perms: list[str]) -> bool:
        """Verifica se tem pelo menos uma das permissões."""
        return any(self.has_perm(perm) for perm in perms)
    
    def get_all_permissions(self) -> set[str]:
        """Retorna todas as permissões do usuário."""
        if self.is_superuser:
            # Retorna string especial indicando todas
            return {"*"}
        
        perms = set()
        
        # Permissões diretas
        if hasattr(self, "user_permissions"):
            perms.update(p.codename for p in self.user_permissions)
        
        # Permissões via grupos
        if hasattr(self, "groups"):
            for group in self.groups:
                perms.update(p.codename for p in group.permissions)
        
        return perms
    
    def get_group_names(self) -> list[str]:
        """Retorna nomes dos grupos do usuário."""
        if hasattr(self, "groups"):
            return [g.name for g in self.groups]
        return []
    
    def is_in_group(self, group_name: str) -> bool:
        """Verifica se está em um grupo específico."""
        return group_name in self.get_group_names()
    
    # =========================================================================
    # Métodos de Autenticação
    # =========================================================================
    
    @classmethod
    async def authenticate(
        cls,
        email: str,
        password: str,
        db: "AsyncSession",
    ) -> "AbstractUser | None":
        """
        Autentica um usuário por email e senha.
        
        Returns:
            Usuário se autenticado, None caso contrário
        """
        user = await cls.objects.using(db).filter(email=email).first()
        
        if user is None:
            return None
        
        if not user.is_active:
            return None
        
        if not user.check_password(password):
            return None
        
        # Atualiza last_login
        user.last_login = datetime.utcnow()
        await user.save(db)
        
        return user
    
    @classmethod
    async def create_user(
        cls,
        email: str,
        password: str,
        db: "AsyncSession",
        **extra_fields,
    ) -> "AbstractUser":
        """
        Cria um novo usuário.
        
        Args:
            email: Email do usuário
            password: Senha em texto plano
            db: Sessão do banco
            **extra_fields: Campos adicionais
            
        Returns:
            Novo usuário criado
        """
        user = cls(email=email.lower(), **extra_fields)
        user.set_password(password)
        await user.save(db)
        return user
    
    @classmethod
    async def create_superuser(
        cls,
        email: str,
        password: str,
        db: "AsyncSession",
        **extra_fields,
    ) -> "AbstractUser":
        """Cria um superusuário."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        
        return await cls.create_user(email, password, db, **extra_fields)


# =============================================================================
# Mixin para adicionar relacionamentos de permissão
# =============================================================================

class PermissionsMixin:
    """
    Mixin que adiciona campos de grupos e permissões ao usuário.
    
    Use junto com AbstractUser:
    
        class User(AbstractUser, PermissionsMixin):
            __tablename__ = "users"
    """
    
    @declared_attr
    def groups(cls) -> Mapped[list["Group"]]:
        """Grupos do usuário."""
        return relationship(
            "Group",
            secondary=_create_user_groups_table(cls.__tablename__),
            lazy="selectin",
        )
    
    @declared_attr
    def user_permissions(cls) -> Mapped[list["Permission"]]:
        """Permissões diretas do usuário."""
        return relationship(
            "Permission",
            secondary=_create_user_permissions_table(cls.__tablename__),
            lazy="selectin",
        )
    
    async def add_to_group(self, group: Group | str, db: "AsyncSession") -> None:
        """Adiciona o usuário a um grupo."""
        if isinstance(group, str):
            grp = await Group.objects.using(db).filter(name=group).first()
            if grp is None:
                grp = Group(name=group)
                await grp.save(db)
            group = grp
        
        if group not in self.groups:
            self.groups.append(group)
            await self.save(db)
    
    async def remove_from_group(self, group: Group | str, db: "AsyncSession") -> None:
        """Remove o usuário de um grupo."""
        if isinstance(group, str):
            grp = await Group.objects.using(db).filter(name=group).first()
            if grp:
                group = grp
            else:
                return
        
        if group in self.groups:
            self.groups.remove(group)
            await self.save(db)
    
    async def add_permission(self, permission: Permission | str, db: "AsyncSession") -> None:
        """Adiciona uma permissão direta ao usuário."""
        if isinstance(permission, str):
            permission = await Permission.get_or_create(permission, db=db)
        
        if permission not in self.user_permissions:
            self.user_permissions.append(permission)
            await self.save(db)
    
    async def remove_permission(self, permission: Permission | str, db: "AsyncSession") -> None:
        """Remove uma permissão direta do usuário."""
        if isinstance(permission, str):
            perm = await Permission.objects.using(db).filter(codename=permission).first()
            if perm:
                permission = perm
            else:
                return
        
        if permission in self.user_permissions:
            self.user_permissions.remove(permission)
            await self.save(db)


# =============================================================================
# Modelo de Usuário Completo (pronto para usar)
# =============================================================================

class User(AbstractUser, PermissionsMixin):
    """
    Modelo de usuário completo com grupos e permissões.
    
    Pronto para usar ou herdar para adicionar campos extras.
    
    Exemplo de uso:
        # Criar usuário
        user = await User.create_user("admin@example.com", "password123", db)
        
        # Criar superusuário
        admin = await User.create_superuser("admin@example.com", "password123", db)
        
        # Verificar permissão
        if user.has_perm("posts.delete"):
            ...
        
        # Adicionar a grupo
        await user.add_to_group("editors", db)
        
        # Autenticar
        user = await User.authenticate("admin@example.com", "password123", db)
    """
    
    __tablename__ = "auth_users"
    
    # Campos adicionais opcionais
    first_name: Mapped[str | None] = Field.string(max_length=150, nullable=True)
    last_name: Mapped[str | None] = Field.string(max_length=150, nullable=True)
    
    @property
    def full_name(self) -> str:
        """Retorna nome completo."""
        parts = [self.first_name, self.last_name]
        return " ".join(p for p in parts if p) or self.email


# =============================================================================
# JWT Token Utilities
# =============================================================================

def create_access_token(
    user_id: int | str,
    secret_key: str,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """
    Cria um token JWT de acesso.
    
    Args:
        user_id: ID do usuário
        secret_key: Chave secreta para assinar
        expires_delta: Tempo de expiração (padrão: 30 minutos)
        extra_claims: Claims adicionais
        
    Returns:
        Token JWT
    """
    import jwt
    
    if expires_delta is None:
        expires_delta = timedelta(minutes=30)
    
    expire = datetime.utcnow() + expires_delta
    
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access",
    }
    
    if extra_claims:
        payload.update(extra_claims)
    
    return jwt.encode(payload, secret_key, algorithm="HS256")


def create_refresh_token(
    user_id: int | str,
    secret_key: str,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Cria um token JWT de refresh.
    
    Args:
        user_id: ID do usuário
        secret_key: Chave secreta
        expires_delta: Tempo de expiração (padrão: 7 dias)
        
    Returns:
        Token JWT
    """
    import jwt
    
    if expires_delta is None:
        expires_delta = timedelta(days=7)
    
    expire = datetime.utcnow() + expires_delta
    
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh",
    }
    
    return jwt.encode(payload, secret_key, algorithm="HS256")


def decode_token(token: str, secret_key: str) -> dict[str, Any]:
    """
    Decodifica um token JWT.
    
    Args:
        token: Token JWT
        secret_key: Chave secreta
        
    Returns:
        Payload do token
        
    Raises:
        jwt.InvalidTokenError: Se token inválido
    """
    import jwt
    
    return jwt.decode(token, secret_key, algorithms=["HS256"])


def verify_token(token: str, secret_key: str, token_type: str = "access") -> dict[str, Any] | None:
    """
    Verifica e decodifica um token JWT.
    
    Args:
        token: Token JWT
        secret_key: Chave secreta
        token_type: Tipo esperado ("access" ou "refresh")
        
    Returns:
        Payload se válido, None caso contrário
    """
    import jwt
    
    try:
        payload = jwt.decode(token, secret_key, algorithms=["HS256"])
        
        if payload.get("type") != token_type:
            return None
        
        return payload
    except jwt.InvalidTokenError:
        return None


# =============================================================================
# Permission Decorators e Dependencies
# =============================================================================

from fastapi import Depends, HTTPException, Request, status
from core.permissions import Permission as PermissionBase


class HasPermission(PermissionBase):
    """
    Verifica se o usuário tem uma permissão específica.
    
    Uso em ViewSet:
        class PostViewSet(ModelViewSet):
            permission_classes_by_action = {
                "destroy": [HasPermission("posts.delete")],
            }
    
    Uso em rota:
        @router.delete("/posts/{id}")
        async def delete_post(
            id: int,
            user: User = Depends(get_current_user),
            _: None = Depends(HasPermission("posts.delete").dependency),
        ):
            ...
    """
    
    def __init__(self, *perms: str, require_all: bool = True) -> None:
        self.perms = perms
        self.require_all = require_all
        self.message = f"Permission required: {', '.join(perms)}"
    
    async def has_permission(
        self,
        request: Request,
        view: Any = None,
    ) -> bool:
        user = getattr(request.state, "user", None)
        
        if user is None:
            return False
        
        if not hasattr(user, "has_perm"):
            return False
        
        if self.require_all:
            return all(user.has_perm(p) for p in self.perms)
        else:
            return any(user.has_perm(p) for p in self.perms)
    
    @property
    def dependency(self):
        """Retorna dependency para uso com Depends()."""
        async def check(request: Request):
            if not await self.has_permission(request):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=self.message,
                )
        return check


class IsInGroup(PermissionBase):
    """
    Verifica se o usuário está em um grupo específico.
    
    Uso:
        @router.get("/admin")
        async def admin_panel(
            user: User = Depends(get_current_user),
            _: None = Depends(IsInGroup("administrators").dependency),
        ):
            ...
    """
    
    def __init__(self, *groups: str, require_all: bool = False) -> None:
        self.groups = groups
        self.require_all = require_all
        self.message = f"Group membership required: {', '.join(groups)}"
    
    async def has_permission(
        self,
        request: Request,
        view: Any = None,
    ) -> bool:
        user = getattr(request.state, "user", None)
        
        if user is None:
            return False
        
        if not hasattr(user, "is_in_group"):
            return False
        
        if self.require_all:
            return all(user.is_in_group(g) for g in self.groups)
        else:
            return any(user.is_in_group(g) for g in self.groups)
    
    @property
    def dependency(self):
        """Retorna dependency para uso com Depends()."""
        async def check(request: Request):
            if not await self.has_permission(request):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=self.message,
                )
        return check


def require_permission(*perms: str, require_all: bool = True):
    """
    Dependency factory para exigir permissões.
    
    Uso:
        @router.delete("/posts/{id}")
        async def delete_post(
            id: int,
            _: None = Depends(require_permission("posts.delete")),
        ):
            ...
    """
    return HasPermission(*perms, require_all=require_all).dependency


def require_group(*groups: str, require_all: bool = False):
    """
    Dependency factory para exigir grupos.
    
    Uso:
        @router.get("/admin")
        async def admin_panel(
            _: None = Depends(require_group("administrators")),
        ):
            ...
    """
    return IsInGroup(*groups, require_all=require_all).dependency


def require_superuser():
    """
    Dependency que exige superusuário.
    
    Uso:
        @router.get("/superadmin")
        async def super_admin(
            _: None = Depends(require_superuser()),
        ):
            ...
    """
    async def check(request: Request):
        user = getattr(request.state, "user", None)
        
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        
        if not getattr(user, "is_superuser", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Superuser access required",
            )
    
    return check


def require_staff():
    """
    Dependency que exige usuário staff.
    
    Uso:
        @router.get("/staff")
        async def staff_area(
            _: None = Depends(require_staff()),
        ):
            ...
    """
    async def check(request: Request):
        user = getattr(request.state, "user", None)
        
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        
        if not getattr(user, "is_staff", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Staff access required",
            )
    
    return check
