"""
Implementações de backends de autenticação.

Backends disponíveis:
- ModelBackend: Autenticação via modelo de usuário (padrão)
- TokenAuthBackend: Autenticação via token Bearer

Uso:
    from core.auth import get_auth_backend, register_auth_backend
    
    # Usar backend padrão
    backend = get_auth_backend()
    user = await backend.authenticate(email="...", password="...")
    
    # Registrar backend customizado
    class MyBackend(AuthBackend):
        async def authenticate(self, request, **credentials):
            ...
    
    register_auth_backend("my_backend", MyBackend())
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from core.auth.base import (
    AuthBackend,
    CredentialsError,
    UserInactive,
    register_auth_backend,
    get_auth_config,
    get_password_hasher,
    get_token_backend,
)
from core.datetime import timezone

if TYPE_CHECKING:
    from fastapi import Request
    from sqlalchemy.ext.asyncio import AsyncSession


class ModelBackend(AuthBackend):
    """
    Backend de autenticação via modelo de usuário.
    
    Autentica usando email/username + senha contra um modelo SQLAlchemy.
    
    Configuração:
        configure_auth(
            user_model=User,
            username_field="email",  # ou "username"
        )
    
    Uso:
        backend = get_auth_backend("model")
        user = await backend.authenticate(
            email="user@example.com",
            password="password123",
            db=session,
        )
    """
    
    def __init__(
        self,
        user_model: type | None = None,
        username_field: str | None = None,
    ) -> None:
        self._user_model = user_model
        self._username_field = username_field
    
    @property
    def user_model(self) -> type:
        """Obtém modelo de usuário da config se não definido."""
        if self._user_model:
            return self._user_model
        
        config = get_auth_config()
        if config.user_model:
            return config.user_model
        
        # Fallback para User padrão
        from core.auth.models import User
        return User
    
    @property
    def username_field(self) -> str:
        """Obtém campo de username da config se não definido."""
        if self._username_field:
            return self._username_field
        return get_auth_config().username_field
    
    async def authenticate(
        self,
        request: "Request | None" = None,
        **credentials: Any,
    ) -> Any | None:
        """
        Autentica usuário por credenciais.
        
        Args:
            request: Request FastAPI (opcional)
            **credentials: Deve incluir username/email e password
            
        Returns:
            Usuário autenticado ou None
        """
        # Obtém credenciais
        username = credentials.get(self.username_field) or credentials.get("username")
        password = credentials.get("password")
        db = credentials.get("db")
        
        if not username or not password:
            return None
        
        if db is None:
            from core.models import get_session
            db = await get_session()
        
        # Busca usuário
        user_model = self.user_model
        user = await user_model.objects.using(db).filter(
            **{self.username_field: username}
        ).first()
        
        if user is None:
            return None
        
        # Verifica se está ativo
        if hasattr(user, "is_active") and not user.is_active:
            return None
        
        # Verifica senha
        if not self._check_password(user, password):
            return None
        
        # Atualiza last_login
        if hasattr(user, "last_login"):
            user.last_login = timezone.now()
            await user.save(db)
        
        return user
    
    def _check_password(self, user: Any, password: str) -> bool:
        """Verifica senha do usuário."""
        # Se o modelo tem método check_password, usa ele
        if hasattr(user, "check_password"):
            return user.check_password(password)
        
        # Senão, usa o hasher configurado
        if not hasattr(user, "password_hash"):
            return False
        
        hasher = get_password_hasher()
        return hasher.verify(password, user.password_hash)
    
    async def get_user(self, user_id: Any, db: "AsyncSession") -> Any | None:
        """Obtém usuário por ID."""
        user_model = self.user_model
        return await user_model.objects.using(db).filter(id=user_id).first()
    
    async def login(self, request: "Request", user: Any) -> None:
        """Executa ações pós-login."""
        # Armazena usuário no request.state
        request.state.user = user
    
    async def logout(self, request: "Request", user: Any) -> None:
        """Executa ações de logout."""
        # Remove usuário do request.state
        if hasattr(request.state, "user"):
            request.state.user = None


class TokenAuthBackend(AuthBackend):
    """
    Backend de autenticação via token Bearer.
    
    Extrai token do header Authorization e valida.
    
    Uso:
        backend = get_auth_backend("token")
        user = await backend.authenticate(request=request, db=session)
    """
    
    def __init__(
        self,
        user_model: type | None = None,
        header_name: str = "Authorization",
        scheme: str = "Bearer",
    ) -> None:
        self._user_model = user_model
        self.header_name = header_name
        self.scheme = scheme
    
    @property
    def user_model(self) -> type:
        """Obtém modelo de usuário da config se não definido."""
        if self._user_model:
            return self._user_model
        
        config = get_auth_config()
        if config.user_model:
            return config.user_model
        
        from core.auth.models import User
        return User
    
    async def authenticate(
        self,
        request: "Request | None" = None,
        **credentials: Any,
    ) -> Any | None:
        """
        Autentica via token Bearer.
        
        Args:
            request: Request FastAPI
            **credentials: Pode incluir "token" diretamente
            
        Returns:
            Usuário autenticado ou None
        """
        # Obtém token
        token = credentials.get("token")
        
        if token is None and request is not None:
            token = self._extract_token(request)
        
        if not token:
            return None
        
        # Valida token
        token_backend = get_token_backend()
        payload = token_backend.verify_token(token, token_type="access")
        
        if payload is None:
            return None
        
        # Obtém user_id do payload
        user_id = payload.get("sub") or payload.get("user_id")
        if not user_id:
            return None
        
        # Busca usuário
        db = credentials.get("db")
        if db is None:
            from core.models import get_session
            db = await get_session()
        
        user = await self.get_user(user_id, db)
        
        if user is None:
            return None
        
        # Verifica se está ativo
        if hasattr(user, "is_active") and not user.is_active:
            return None
        
        return user
    
    def _extract_token(self, request: "Request") -> str | None:
        """Extrai token do header Authorization."""
        auth_header = request.headers.get(self.header_name)
        
        if not auth_header:
            return None
        
        parts = auth_header.split()
        
        if len(parts) != 2:
            return None
        
        scheme, token = parts
        
        if scheme.lower() != self.scheme.lower():
            return None
        
        return token
    
    async def get_user(self, user_id: Any, db: "AsyncSession") -> Any | None:
        """Obtém usuário por ID."""
        user_model = self.user_model
        
        # Tenta converter para int se necessário
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            pass
        
        return await user_model.objects.using(db).filter(id=user_id).first()


class MultiBackend(AuthBackend):
    """
    Backend que tenta múltiplos backends em sequência.
    
    Útil para suportar múltiplos métodos de autenticação:
    
        backend = MultiBackend(["token", "model"])
        
        # Tenta token primeiro, depois model
        user = await backend.authenticate(request=request, db=db)
    """
    
    def __init__(self, backends: list[str] | None = None) -> None:
        self.backend_names = backends or ["token", "model"]
    
    async def authenticate(
        self,
        request: "Request | None" = None,
        **credentials: Any,
    ) -> Any | None:
        """Tenta autenticar com cada backend em ordem."""
        from core.auth.base import get_auth_backend
        
        for name in self.backend_names:
            try:
                backend = get_auth_backend(name)
                user = await backend.authenticate(request=request, **credentials)
                if user is not None:
                    return user
            except KeyError:
                continue
        
        return None
    
    async def get_user(self, user_id: Any, db: "AsyncSession") -> Any | None:
        """Usa o primeiro backend disponível."""
        from core.auth.base import get_auth_backend
        
        for name in self.backend_names:
            try:
                backend = get_auth_backend(name)
                user = await backend.get_user(user_id, db)
                if user is not None:
                    return user
            except KeyError:
                continue
        
        return None


# =============================================================================
# Registro dos backends padrão
# =============================================================================

def _register_default_auth_backends() -> None:
    """Registra os backends de autenticação padrão."""
    register_auth_backend("model", ModelBackend())
    register_auth_backend("token", TokenAuthBackend())
    register_auth_backend("multi", MultiBackend())


# Registra ao importar
_register_default_auth_backends()
