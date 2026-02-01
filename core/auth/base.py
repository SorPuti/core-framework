"""
Interfaces base e registry para o sistema de autenticação plugável.

Todas as classes aqui são abstratas - implemente-as para criar
backends customizados.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Request
    from sqlalchemy.ext.asyncio import AsyncSession


# =============================================================================
# Interfaces Abstratas
# =============================================================================

class PasswordHasher(ABC):
    """
    Interface para hashers de senha.
    
    Implemente para criar seu próprio algoritmo de hash:
    
        class MyHasher(PasswordHasher):
            algorithm = "my_algo"
            
            def hash(self, password: str) -> str:
                return my_hash_function(password)
            
            def verify(self, password: str, hashed: str) -> bool:
                return my_verify_function(password, hashed)
        
        register_password_hasher("my_algo", MyHasher())
    """
    
    algorithm: str = "unknown"
    
    @abstractmethod
    def hash(self, password: str) -> str:
        """
        Gera hash da senha.
        
        Args:
            password: Senha em texto plano
            
        Returns:
            Hash da senha (incluindo salt e metadados)
        """
        ...
    
    @abstractmethod
    def verify(self, password: str, hashed: str) -> bool:
        """
        Verifica se a senha corresponde ao hash.
        
        Args:
            password: Senha em texto plano
            hashed: Hash armazenado
            
        Returns:
            True se a senha está correta
        """
        ...
    
    def needs_rehash(self, hashed: str) -> bool:
        """
        Verifica se o hash precisa ser recalculado.
        
        Útil para migração de algoritmos ou atualização de parâmetros.
        
        Returns:
            True se deve recalcular o hash
        """
        return False
    
    def get_algorithm_from_hash(self, hashed: str) -> str | None:
        """Extrai o algoritmo do hash armazenado."""
        if "$" in hashed:
            return hashed.split("$")[0]
        return None


class TokenBackend(ABC):
    """
    Interface para backends de token.
    
    Implemente para criar seu próprio sistema de tokens:
    
        class MyTokenBackend(TokenBackend):
            def create_token(self, payload, **kwargs):
                return my_encode(payload)
            
            def decode_token(self, token):
                return my_decode(token)
        
        register_token_backend("my_tokens", MyTokenBackend())
    """
    
    @abstractmethod
    def create_token(
        self,
        payload: dict[str, Any],
        token_type: str = "access",
        expires_delta: Any = None,
    ) -> str:
        """
        Cria um token.
        
        Args:
            payload: Dados a incluir no token
            token_type: Tipo do token (access, refresh, etc.)
            expires_delta: Tempo de expiração
            
        Returns:
            Token codificado
        """
        ...
    
    @abstractmethod
    def decode_token(self, token: str) -> dict[str, Any]:
        """
        Decodifica um token.
        
        Args:
            token: Token codificado
            
        Returns:
            Payload do token
            
        Raises:
            TokenError: Se token inválido ou expirado
        """
        ...
    
    @abstractmethod
    def verify_token(self, token: str, token_type: str = "access") -> dict[str, Any] | None:
        """
        Verifica e decodifica um token.
        
        Args:
            token: Token codificado
            token_type: Tipo esperado
            
        Returns:
            Payload se válido, None caso contrário
        """
        ...
    
    def refresh_token(self, refresh_token: str) -> tuple[str, str] | None:
        """
        Gera novos tokens a partir de um refresh token.
        
        Args:
            refresh_token: Token de refresh
            
        Returns:
            Tupla (access_token, refresh_token) ou None se inválido
        """
        return None


class AuthBackend(ABC):
    """
    Interface para backends de autenticação.
    
    Implemente para criar seu próprio sistema de autenticação:
    
        class OAuthBackend(AuthBackend):
            async def authenticate(self, request, **credentials):
                token = credentials.get("token")
                # Valida com provider OAuth
                user_data = await oauth_provider.validate(token)
                return await self.get_or_create_user(user_data)
        
        register_auth_backend("oauth", OAuthBackend())
    """
    
    @abstractmethod
    async def authenticate(
        self,
        request: "Request | None" = None,
        **credentials: Any,
    ) -> Any | None:
        """
        Autentica um usuário.
        
        Args:
            request: Request FastAPI (opcional)
            **credentials: Credenciais (email, password, token, etc.)
            
        Returns:
            Usuário autenticado ou None
        """
        ...
    
    async def get_user(self, user_id: Any, db: "AsyncSession") -> Any | None:
        """
        Obtém usuário por ID.
        
        Args:
            user_id: ID do usuário
            db: Sessão do banco
            
        Returns:
            Usuário ou None
        """
        return None
    
    async def login(self, request: "Request", user: Any) -> None:
        """
        Executa ações pós-login.
        
        Args:
            request: Request FastAPI
            user: Usuário autenticado
        """
        pass
    
    async def logout(self, request: "Request", user: Any) -> None:
        """
        Executa ações de logout.
        
        Args:
            request: Request FastAPI
            user: Usuário fazendo logout
        """
        pass


class PermissionBackend(ABC):
    """
    Interface para backends de permissão.
    
    Implemente para criar seu próprio sistema de permissões:
    
        class RBACBackend(PermissionBackend):
            async def has_permission(self, user, permission, obj=None):
                # Sua lógica RBAC
                return await check_rbac(user, permission, obj)
        
        register_permission_backend("rbac", RBACBackend())
    """
    
    @abstractmethod
    async def has_permission(
        self,
        user: Any,
        permission: str,
        obj: Any = None,
    ) -> bool:
        """
        Verifica se usuário tem permissão.
        
        Args:
            user: Usuário
            permission: Código da permissão
            obj: Objeto específico (para permissões por objeto)
            
        Returns:
            True se tem permissão
        """
        ...
    
    async def get_all_permissions(self, user: Any) -> set[str]:
        """
        Retorna todas as permissões do usuário.
        
        Args:
            user: Usuário
            
        Returns:
            Set de códigos de permissão
        """
        return set()
    
    async def get_group_permissions(self, user: Any) -> set[str]:
        """
        Retorna permissões via grupos.
        
        Args:
            user: Usuário
            
        Returns:
            Set de códigos de permissão
        """
        return set()


# =============================================================================
# Exceções
# =============================================================================

class AuthError(Exception):
    """Erro base de autenticação."""
    pass


class TokenError(AuthError):
    """Erro de token (inválido, expirado, etc.)."""
    pass


class CredentialsError(AuthError):
    """Erro de credenciais inválidas."""
    pass


class PermissionDenied(AuthError):
    """Permissão negada."""
    pass


class UserInactive(AuthError):
    """Usuário inativo."""
    pass


# =============================================================================
# Registry Global
# =============================================================================

_auth_backends: dict[str, AuthBackend] = {}
_password_hashers: dict[str, PasswordHasher] = {}
_token_backends: dict[str, TokenBackend] = {}
_permission_backends: dict[str, PermissionBackend] = {}

_default_auth_backend: str = "model"
_default_password_hasher: str = "pbkdf2_sha256"
_default_token_backend: str = "jwt"
_default_permission_backend: str = "default"


def register_auth_backend(name: str, backend: AuthBackend) -> None:
    """Registra um backend de autenticação."""
    _auth_backends[name] = backend


def register_password_hasher(name: str, hasher: PasswordHasher) -> None:
    """Registra um hasher de senha."""
    _password_hashers[name] = hasher


def register_token_backend(name: str, backend: TokenBackend) -> None:
    """Registra um backend de token."""
    _token_backends[name] = backend


def register_permission_backend(name: str, backend: PermissionBackend) -> None:
    """Registra um backend de permissão."""
    _permission_backends[name] = backend


def get_auth_backend(name: str | None = None) -> AuthBackend:
    """
    Obtém um backend de autenticação.
    
    Args:
        name: Nome do backend (usa padrão se None)
        
    Returns:
        Backend de autenticação
        
    Raises:
        KeyError: Se backend não encontrado
    """
    name = name or _default_auth_backend
    if name not in _auth_backends:
        raise KeyError(f"Auth backend '{name}' not found. Available: {list(_auth_backends.keys())}")
    return _auth_backends[name]


def get_password_hasher(name: str | None = None) -> PasswordHasher:
    """
    Obtém um hasher de senha.
    
    Args:
        name: Nome do hasher (usa padrão se None)
        
    Returns:
        Hasher de senha
        
    Raises:
        KeyError: Se hasher não encontrado
    """
    name = name or _default_password_hasher
    if name not in _password_hashers:
        raise KeyError(f"Password hasher '{name}' not found. Available: {list(_password_hashers.keys())}")
    return _password_hashers[name]


def get_token_backend(name: str | None = None) -> TokenBackend:
    """
    Obtém um backend de token.
    
    Args:
        name: Nome do backend (usa padrão se None)
        
    Returns:
        Backend de token
        
    Raises:
        KeyError: Se backend não encontrado
    """
    name = name or _default_token_backend
    if name not in _token_backends:
        raise KeyError(f"Token backend '{name}' not found. Available: {list(_token_backends.keys())}")
    return _token_backends[name]


def get_permission_backend(name: str | None = None) -> PermissionBackend:
    """
    Obtém um backend de permissão.
    
    Args:
        name: Nome do backend (usa padrão se None)
        
    Returns:
        Backend de permissão
        
    Raises:
        KeyError: Se backend não encontrado
    """
    name = name or _default_permission_backend
    if name not in _permission_backends:
        raise KeyError(f"Permission backend '{name}' not found. Available: {list(_permission_backends.keys())}")
    return _permission_backends[name]


# =============================================================================
# Configuração
# =============================================================================

@dataclass
class AuthConfig:
    """
    Configuração do sistema de autenticação.
    
    Exemplo:
        config = AuthConfig(
            secret_key="your-secret-key",
            access_token_expire_minutes=60,
            password_hasher="argon2",
            auth_backends=["model", "oauth"],
        )
        configure_auth(config)
    """
    
    # Chave secreta para tokens
    secret_key: str = "change-me-in-production"
    
    # Expiração de tokens
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    
    # Backends padrão
    password_hasher: str = "pbkdf2_sha256"
    token_backend: str = "jwt"
    auth_backend: str = "model"
    permission_backend: str = "default"
    
    # Lista de backends de autenticação a tentar (em ordem)
    auth_backends: list[str] = field(default_factory=lambda: ["model"])
    
    # Modelo de usuário (para ModelBackend)
    user_model: type | None = None
    
    # Campo de username (email, username, etc.)
    username_field: str = "email"
    
    # Algoritmo JWT
    jwt_algorithm: str = "HS256"
    
    # Headers de autenticação
    auth_header: str = "Authorization"
    auth_scheme: str = "Bearer"
    
    # Opções de senha
    password_min_length: int = 8
    password_require_uppercase: bool = False
    password_require_lowercase: bool = False
    password_require_digit: bool = False
    password_require_special: bool = False


_auth_config: AuthConfig | None = None


def configure_auth(config: AuthConfig | None = None, **kwargs) -> AuthConfig:
    """
    Configura o sistema de autenticação.
    
    Args:
        config: Objeto AuthConfig ou None para criar com kwargs
        **kwargs: Parâmetros para AuthConfig se config=None
        
    Returns:
        Configuração aplicada
        
    Exemplo:
        # Com objeto
        configure_auth(AuthConfig(secret_key="..."))
        
        # Com kwargs
        configure_auth(secret_key="...", access_token_expire_minutes=60)
    """
    global _auth_config, _default_auth_backend, _default_password_hasher
    global _default_token_backend, _default_permission_backend
    
    if config is None:
        config = AuthConfig(**kwargs)
    
    _auth_config = config
    
    # Atualiza defaults
    _default_auth_backend = config.auth_backend
    _default_password_hasher = config.password_hasher
    _default_token_backend = config.token_backend
    _default_permission_backend = config.permission_backend
    
    return config


def get_auth_config() -> AuthConfig:
    """
    Obtém a configuração atual.
    
    Returns:
        Configuração de autenticação
    """
    global _auth_config
    if _auth_config is None:
        _auth_config = AuthConfig()
    return _auth_config
