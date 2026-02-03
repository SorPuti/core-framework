"""
Modelos de autenticação.

Modelos disponíveis:
- AbstractUser: Modelo base abstrato para usuários
- PermissionsMixin: Mixin para adicionar grupos e permissões
- User: Modelo de usuário completo (pronto para usar)
- Group: Grupos de usuários
- Permission: Permissões por string

Uso:
    # Usar modelo pronto
    from core.auth import User
    
    user = await User.create_user("email@example.com", "password", db)
    
    # Ou criar modelo customizado
    from core.auth import AbstractUser, PermissionsMixin
    
    class MyUser(AbstractUser, PermissionsMixin):
        __tablename__ = "users"
        
        # Seus campos
        phone: Mapped[str | None] = Field.string(max_length=20, nullable=True)
"""

from __future__ import annotations

from typing import Any, ClassVar, TYPE_CHECKING

from sqlalchemy import Table, Column, Integer, ForeignKey, inspect
from sqlalchemy.orm import Mapped, relationship, declared_attr
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from core.models import Model, Field
from core.auth.base import get_password_hasher, get_auth_config
from core.datetime import timezone, DateTime

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# =============================================================================
# Tabelas de Associação (Many-to-Many)
# =============================================================================

# Cache de tabelas criadas para evitar duplicação
_association_tables: dict[str, Table] = {}


def _get_pk_column_type(model_class: type) -> type:
    """
    Detecta o tipo da coluna PK de um modelo.
    
    Suporta:
    - Integer (int)
    - BigInteger (int com bigint=True)
    - UUID (uuid.UUID)
    - String (str)
    
    Returns:
        SQLAlchemy column type class
    """
    from sqlalchemy import Integer, BigInteger, String
    from sqlalchemy.dialects.postgresql import UUID as PG_UUID
    import uuid
    
    # Tenta obter do __annotations__ ou columns
    if hasattr(model_class, "__table__"):
        # Modelo já mapeado - pega direto da tabela
        pk_columns = [c for c in model_class.__table__.columns if c.primary_key]
        if pk_columns:
            return type(pk_columns[0].type)
    
    # Tenta via annotations
    annotations = getattr(model_class, "__annotations__", {})
    
    if "id" in annotations:
        ann = annotations["id"]
        ann_str = str(ann)
        
        # Detecta UUID
        if "UUID" in ann_str or "uuid" in ann_str:
            return PG_UUID
        
        # Detecta int
        if "int" in ann_str.lower():
            return Integer
        
        # Detecta str
        if "str" in ann_str.lower():
            return String
    
    # Default: Integer
    return Integer


def _create_user_fk_column(user_tablename: str, user_model: type | None = None):
    """
    Cria coluna FK para user_id detectando automaticamente o tipo.
    
    Args:
        user_tablename: Nome da tabela do usuário
        user_model: Classe do modelo (opcional, para detecção de tipo)
    
    Returns:
        SQLAlchemy Column
    """
    from sqlalchemy import Integer, BigInteger, String
    from sqlalchemy.dialects.postgresql import UUID as PG_UUID
    
    # Tenta detectar o tipo do modelo
    col_type = Integer  # Default
    
    if user_model is not None:
        detected = _get_pk_column_type(user_model)
        if detected == PG_UUID:
            col_type = PG_UUID(as_uuid=True)
        elif detected == BigInteger:
            col_type = BigInteger
        elif detected == String:
            col_type = String(36)  # UUID como string
        else:
            col_type = Integer
    
    return Column(
        "user_id",
        col_type,
        ForeignKey(f"{user_tablename}.id", ondelete="CASCADE"),
        primary_key=True,
    )


def get_user_groups_table(user_tablename: str = "auth_users", user_model: type | None = None) -> Table:
    """
    Obtém ou cria tabela de associação user <-> groups.
    
    Detecta automaticamente o tipo do ID do usuário (INTEGER, UUID, etc).
    
    Args:
        user_tablename: Nome da tabela do usuário
        user_model: Classe do modelo User (para detecção de tipo)
    """
    key = f"user_groups_{user_tablename}"
    
    if key not in _association_tables:
        _association_tables[key] = Table(
            f"{user_tablename}_groups",
            Model.metadata,
            _create_user_fk_column(user_tablename, user_model),
            Column("group_id", Integer, ForeignKey("auth_groups.id", ondelete="CASCADE"), primary_key=True),
            extend_existing=True,
        )
    
    return _association_tables[key]


def get_user_permissions_table(user_tablename: str = "auth_users", user_model: type | None = None) -> Table:
    """
    Obtém ou cria tabela de associação user <-> permissions.
    
    Detecta automaticamente o tipo do ID do usuário (INTEGER, UUID, etc).
    
    Args:
        user_tablename: Nome da tabela do usuário
        user_model: Classe do modelo User (para detecção de tipo)
    """
    key = f"user_permissions_{user_tablename}"
    
    if key not in _association_tables:
        _association_tables[key] = Table(
            f"{user_tablename}_permissions",
            Model.metadata,
            _create_user_fk_column(user_tablename, user_model),
            Column("permission_id", Integer, ForeignKey("auth_permissions.id", ondelete="CASCADE"), primary_key=True),
            extend_existing=True,
        )
    
    return _association_tables[key]


def get_group_permissions_table() -> Table:
    """Obtém ou cria tabela de associação group <-> permissions."""
    key = "group_permissions"
    
    if key not in _association_tables:
        _association_tables[key] = Table(
            "auth_group_permissions",
            Model.metadata,
            Column("group_id", Integer, ForeignKey("auth_groups.id", ondelete="CASCADE"), primary_key=True),
            Column("permission_id", Integer, ForeignKey("auth_permissions.id", ondelete="CASCADE"), primary_key=True),
            extend_existing=True,
        )
    
    return _association_tables[key]


# =============================================================================
# Permission Model
# =============================================================================

class Permission(Model):
    """
    Permissão por string no formato 'app.action' ou 'resource.action'.
    
    Exemplos de codenames:
        - "posts.create"
        - "posts.delete"
        - "users.view"
        - "admin.access"
    
    Uso:
        # Criar permissão
        perm = Permission(codename="posts.delete", name="Can delete posts")
        await perm.save(db)
        
        # Ou usar get_or_create
        perm = await Permission.get_or_create("posts.delete", db=db)
    """
    
    __tablename__ = "auth_permissions"
    
    id: Mapped[int] = Field.pk()
    codename: Mapped[str] = Field.string(max_length=100, unique=True, index=True)
    name: Mapped[str] = Field.string(max_length=255)
    description: Mapped[str | None] = Field.text(nullable=True)
    
    def __repr__(self) -> str:
        return f"<Permission {self.codename}>"
    
    def __str__(self) -> str:
        return self.codename
    
    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Permission):
            return self.codename == other.codename
        if isinstance(other, str):
            return self.codename == other
        return False
    
    def __hash__(self) -> int:
        return hash(self.codename)
    
    @classmethod
    async def get_or_create(
        cls,
        codename: str,
        name: str | None = None,
        description: str | None = None,
        db: "AsyncSession | None" = None,
    ) -> "Permission":
        """
        Obtém ou cria uma permissão.
        
        Args:
            codename: Código da permissão (ex: "posts.delete")
            name: Nome legível (gerado automaticamente se None)
            description: Descrição opcional
            db: Sessão do banco
            
        Returns:
            Permissão existente ou nova
        """
        if db is None:
            from core.models import get_session
            db = await get_session()
        
        perm = await cls.objects.using(db).filter(codename=codename).first()
        if perm:
            return perm
        
        # Gera nome a partir do codename
        if name is None:
            name = codename.replace(".", " ").replace("_", " ").title()
        
        perm = cls(codename=codename, name=name, description=description)
        await perm.save(db)
        return perm
    
    @classmethod
    async def bulk_create(
        cls,
        codenames: list[str],
        db: "AsyncSession | None" = None,
    ) -> list["Permission"]:
        """
        Cria múltiplas permissões de uma vez.
        
        Args:
            codenames: Lista de códigos de permissão
            db: Sessão do banco
            
        Returns:
            Lista de permissões criadas/existentes
        """
        if db is None:
            from core.models import get_session
            db = await get_session()
        
        permissions = []
        for codename in codenames:
            perm = await cls.get_or_create(codename, db=db)
            permissions.append(perm)
        
        return permissions


# =============================================================================
# Group Model
# =============================================================================

class Group(Model):
    """
    Grupo de usuários com permissões compartilhadas.
    
    Uso:
        # Criar grupo
        admin_group = Group(name="Administrators")
        await admin_group.save(db)
        
        # Adicionar permissão
        await admin_group.add_permission("users.delete", db)
        
        # Verificar permissão
        if admin_group.has_permission("users.delete"):
            ...
    """
    
    __tablename__ = "auth_groups"
    
    id: Mapped[int] = Field.pk()
    name: Mapped[str] = Field.string(max_length=150, unique=True, index=True)
    description: Mapped[str | None] = Field.text(nullable=True)
    
    # Relacionamento com permissões
    permissions: Mapped[list["Permission"]] = relationship(
        "Permission",
        secondary=get_group_permissions_table(),
        lazy="selectin",
    )
    
    def __repr__(self) -> str:
        return f"<Group {self.name}>"
    
    def __str__(self) -> str:
        return self.name
    
    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Group):
            return self.name == other.name
        if isinstance(other, str):
            return self.name == other
        return False
    
    def __hash__(self) -> int:
        return hash(self.name)
    
    def has_permission(self, codename: str) -> bool:
        """Verifica se o grupo tem uma permissão."""
        return any(p.codename == codename for p in self.permissions)
    
    async def add_permission(
        self,
        permission: Permission | str,
        db: "AsyncSession",
    ) -> None:
        """Adiciona uma permissão ao grupo."""
        if isinstance(permission, str):
            permission = await Permission.get_or_create(permission, db=db)
        
        if permission not in self.permissions:
            self.permissions.append(permission)
            await self.save(db)
    
    async def remove_permission(
        self,
        permission: Permission | str,
        db: "AsyncSession",
    ) -> None:
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
    
    async def set_permissions(
        self,
        permissions: list[Permission | str],
        db: "AsyncSession",
    ) -> None:
        """Define as permissões do grupo (substitui existentes)."""
        self.permissions.clear()
        
        for perm in permissions:
            if isinstance(perm, str):
                perm = await Permission.get_or_create(perm, db=db)
            self.permissions.append(perm)
        
        await self.save(db)
    
    @classmethod
    async def get_or_create(
        cls,
        name: str,
        description: str | None = None,
        db: "AsyncSession | None" = None,
    ) -> "Group":
        """Obtém ou cria um grupo."""
        if db is None:
            from core.models import get_session
            db = await get_session()
        
        group = await cls.objects.using(db).filter(name=name).first()
        if group:
            return group
        
        group = cls(name=name, description=description)
        await group.save(db)
        return group


# =============================================================================
# AbstractUser Model
# =============================================================================

class AbstractUser(Model):
    """
    Modelo abstrato base para usuários.
    
    Herde desta classe para criar seu modelo de usuário customizado:
    
        class User(AbstractUser, PermissionsMixin):
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
    date_joined: Mapped[DateTime] = Field.datetime(auto_now_add=True)
    last_login: Mapped[DateTime | None] = Field.datetime(nullable=True)
    
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
        
        Usa o hasher configurado (padrão: PBKDF2).
        """
        hasher = get_password_hasher()
        self.password_hash = hasher.hash(raw_password)
    
    def check_password(self, raw_password: str) -> bool:
        """Verifica se a senha está correta."""
        if not self.password_hash:
            return False
        
        hasher = get_password_hasher()
        
        # Detecta algoritmo do hash armazenado
        algorithm = hasher.get_algorithm_from_hash(self.password_hash)
        if algorithm:
            try:
                from core.auth.base import get_password_hasher as get_hasher
                specific_hasher = get_hasher(algorithm)
                return specific_hasher.verify(raw_password, self.password_hash)
            except KeyError:
                pass
        
        return hasher.verify(raw_password, self.password_hash)
    
    def password_needs_rehash(self) -> bool:
        """Verifica se a senha precisa ser recalculada."""
        if not self.password_hash:
            return False
        
        hasher = get_password_hasher()
        return hasher.needs_rehash(self.password_hash)
    
    @classmethod
    def make_password(cls, raw_password: str) -> str:
        """Gera hash de senha (método de classe)."""
        hasher = get_password_hasher()
        return hasher.hash(raw_password)
    
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
            return {"*"}
        
        perms = set()
        
        if hasattr(self, "user_permissions"):
            perms.update(p.codename for p in self.user_permissions)
        
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
        user = await cls.objects.using(db).filter(email=email.lower()).first()
        
        if user is None:
            return None
        
        if not user.is_active:
            return None
        
        if not user.check_password(password):
            return None
        
        # Atualiza last_login
        user.last_login = timezone.now()
        
        # Rehash se necessário
        if user.password_needs_rehash():
            user.set_password(password)
        
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
    
    @classmethod
    async def get_by_email(
        cls,
        email: str,
        db: "AsyncSession",
    ) -> "AbstractUser | None":
        """Obtém usuário por email."""
        return await cls.objects.using(db).filter(email=email.lower()).first()


# =============================================================================
# PermissionsMixin
# =============================================================================

class PermissionsMixin:
    """
    Mixin que adiciona campos de grupos e permissões ao usuário.
    
    Use junto com AbstractUser:
    
        class User(AbstractUser, PermissionsMixin):
            __tablename__ = "users"
    
    Suporta automaticamente diferentes tipos de ID:
        - INTEGER (padrão)
        - UUID
        - BigInteger
        - String
    
    Adiciona:
        - groups: Relacionamento com grupos
        - user_permissions: Permissões diretas
        - Métodos para gerenciar grupos e permissões
    
    Example com UUID:
        import uuid
        from core import Field
        
        class User(AbstractUser, PermissionsMixin):
            __tablename__ = "users"
            
            id: Mapped[uuid.UUID] = Field.pk(type="uuid")
            # PermissionsMixin detecta automaticamente UUID
    """
    
    @declared_attr
    def groups(cls) -> Mapped[list["Group"]]:
        """Grupos do usuário."""
        return relationship(
            "Group",
            secondary=get_user_groups_table(cls.__tablename__, cls),
            lazy="selectin",
        )
    
    @declared_attr
    def user_permissions(cls) -> Mapped[list["Permission"]]:
        """Permissões diretas do usuário."""
        return relationship(
            "Permission",
            secondary=get_user_permissions_table(cls.__tablename__, cls),
            lazy="selectin",
        )
    
    async def add_to_group(
        self,
        group: Group | str,
        db: "AsyncSession",
    ) -> None:
        """Adiciona o usuário a um grupo."""
        if isinstance(group, str):
            group = await Group.get_or_create(group, db=db)
        
        if group not in self.groups:
            self.groups.append(group)
            await self.save(db)
    
    async def remove_from_group(
        self,
        group: Group | str,
        db: "AsyncSession",
    ) -> None:
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
    
    async def set_groups(
        self,
        groups: list[Group | str],
        db: "AsyncSession",
    ) -> None:
        """Define os grupos do usuário (substitui existentes)."""
        self.groups.clear()
        
        for group in groups:
            if isinstance(group, str):
                group = await Group.get_or_create(group, db=db)
            self.groups.append(group)
        
        await self.save(db)
    
    async def add_permission(
        self,
        permission: Permission | str,
        db: "AsyncSession",
    ) -> None:
        """Adiciona uma permissão direta ao usuário."""
        if isinstance(permission, str):
            permission = await Permission.get_or_create(permission, db=db)
        
        if permission not in self.user_permissions:
            self.user_permissions.append(permission)
            await self.save(db)
    
    async def remove_permission(
        self,
        permission: Permission | str,
        db: "AsyncSession",
    ) -> None:
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
    
    async def set_permissions(
        self,
        permissions: list[Permission | str],
        db: "AsyncSession",
    ) -> None:
        """Define as permissões diretas do usuário (substitui existentes)."""
        self.user_permissions.clear()
        
        for perm in permissions:
            if isinstance(perm, str):
                perm = await Permission.get_or_create(perm, db=db)
            self.user_permissions.append(perm)
        
        await self.save(db)


# =============================================================================
# User Model Helper
# =============================================================================

def get_user_model() -> type[AbstractUser]:
    """
    Retorna o modelo de usuário configurado no projeto.
    
    O modelo é obtido de:
    1. AuthConfig.user_model (se configurado via configure_auth)
    2. Settings.user_model (se definido no settings do projeto)
    
    Raises:
        RuntimeError: Se nenhum user_model foi configurado
    
    Example:
        from core.auth import get_user_model
        
        User = get_user_model()
        user = await User.create_user("email@example.com", "password", db)
    
    Note:
        O projeto DEVE definir seu próprio User:
        
            from core.auth import AbstractUser, PermissionsMixin
            
            class User(AbstractUser, PermissionsMixin):
                __tablename__ = "users"
                # seus campos
        
        E configurar via:
        
            from core.auth import configure_auth
            configure_auth(user_model=User)
        
        Ou via settings:
        
            class Settings(CoreSettings):
                user_model: str = "myapp.models.User"
    """
    from core.auth.base import get_auth_config
    
    config = get_auth_config()
    
    if config.user_model is not None:
        return config.user_model
    
    # Tenta obter do settings
    try:
        from core.config import get_settings
        settings = get_settings()
        if hasattr(settings, "user_model") and settings.user_model:
            # Se for string, importa dinamicamente
            if isinstance(settings.user_model, str):
                import importlib
                module_path, class_name = settings.user_model.rsplit(".", 1)
                module = importlib.import_module(module_path)
                return getattr(module, class_name)
            return settings.user_model
    except Exception:
        pass
    
    raise RuntimeError(
        "No user_model configured. You must:\n"
        "1. Create your own User class inheriting from AbstractUser\n"
        "2. Configure it via configure_auth(user_model=User)\n"
        "   or set user_model in your Settings class\n\n"
        "Example:\n"
        "    from core.auth import AbstractUser, PermissionsMixin\n"
        "    \n"
        "    class User(AbstractUser, PermissionsMixin):\n"
        "        __tablename__ = 'users'\n"
        "        # your fields\n"
        "    \n"
        "    configure_auth(user_model=User)"
    )
