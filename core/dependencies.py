"""
Sistema de Dependency Injection centralizado.

Características:
- Integração nativa com FastAPI Depends
- Gerenciamento de sessão de banco de dados
- Autenticação de usuário
- Cache de dependências
- Lifecycle management
"""

from __future__ import annotations

from typing import Any, Annotated, TypeVar, Generic
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import Depends, Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings

T = TypeVar("T")


# Re-export Depends para uso conveniente
__all__ = [
    "Depends",
    "get_db",
    "get_current_user",
    "get_settings_dep",
    "get_optional_user",
    "require_user",
    "DatabaseSession",
    "CurrentUser",
    "OptionalUser",
]


# Security scheme para autenticação Bearer
security = HTTPBearer(auto_error=False)


# Tipo para usuário (será definido pela aplicação)
UserType = TypeVar("UserType")


# Funções de autenticação (devem ser configuradas pela aplicação)
_user_loader: Callable[[str], Any] | None = None
_token_decoder: Callable[[str], dict[str, Any]] | None = None


def configure_auth(
    user_loader: Callable[[str], Any],
    token_decoder: Callable[[str], dict[str, Any]] | None = None,
) -> None:
    """
    Configura as funções de autenticação.
    
    Args:
        user_loader: Função async que carrega usuário por ID
        token_decoder: Função que decodifica o token JWT (opcional)
        
    Exemplo:
        async def load_user(user_id: str) -> User | None:
            return await User.objects.using(session).get_or_none(id=int(user_id))
        
        def decode_token(token: str) -> dict:
            return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        
        configure_auth(load_user, decode_token)
    """
    global _user_loader, _token_decoder
    _user_loader = user_loader
    _token_decoder = token_decoder


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency que fornece uma sessão de banco de dados.
    
    Uso:
        @router.get("/users")
        async def list_users(db: AsyncSession = Depends(get_db)):
            users = await User.objects.using(db).all()
            return users
    
    A sessão é automaticamente fechada após a requisição.
    """
    from core.models import get_session
    
    session = await get_session()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Dependency que retorna o usuário autenticado.
    
    Raises:
        HTTPException 401: Se não autenticado ou token inválido
        
    Uso:
        @router.get("/me")
        async def get_me(user: User = Depends(get_current_user)):
            return user
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if _user_loader is None:
        raise RuntimeError(
            "Auth not configured. Call configure_auth() during app startup."
        )
    
    try:
        # Decodifica o token se configurado
        if _token_decoder is not None:
            payload = _token_decoder(credentials.credentials)
            user_id = payload.get("sub") or payload.get("user_id")
        else:
            # Assume que o token é o próprio user_id
            user_id = credentials.credentials
        
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )
        
        # Carrega o usuário
        user = await _user_loader(user_id)
        
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )
        
        # Armazena no request.state para uso em permissões
        request.state.user = user
        request.state.db = db
        
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
        )


async def get_optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Any | None:
    """
    Dependency que retorna o usuário autenticado ou None.
    
    Não levanta exceção se não autenticado.
    
    Uso:
        @router.get("/posts")
        async def list_posts(user: User | None = Depends(get_optional_user)):
            if user:
                # Mostrar posts privados do usuário
                ...
            # Mostrar posts públicos
            ...
    """
    if credentials is None:
        request.state.user = None
        request.state.db = db
        return None
    
    try:
        return await get_current_user(request, credentials, db)
    except HTTPException:
        request.state.user = None
        return None


def require_user(user: Any = Depends(get_current_user)) -> Any:
    """
    Dependency que garante usuário autenticado.
    
    Alias para get_current_user com nome mais expressivo.
    """
    return user


def get_settings_dep() -> Settings:
    """
    Dependency que retorna as configurações.
    
    Uso:
        @router.get("/config")
        async def get_config(settings: Settings = Depends(get_settings_dep)):
            return {"app_name": settings.app_name}
    """
    return get_settings()


# Type aliases para uso com Annotated
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[Any, Depends(get_current_user)]
OptionalUser = Annotated[Any | None, Depends(get_optional_user)]
AppSettings = Annotated[Settings, Depends(get_settings_dep)]


# Dependency factory para injeção customizada
class DependencyFactory(Generic[T]):
    """
    Factory para criar dependencies customizadas.
    
    Exemplo:
        class UserService:
            def __init__(self, db: AsyncSession):
                self.db = db
            
            async def get_user(self, user_id: int) -> User:
                return await User.objects.using(self.db).get(id=user_id)
        
        user_service_dep = DependencyFactory(UserService)
        
        @router.get("/users/{user_id}")
        async def get_user(
            user_id: int,
            service: UserService = Depends(user_service_dep),
        ):
            return await service.get_user(user_id)
    """
    
    def __init__(self, factory: type[T]) -> None:
        self.factory = factory
    
    async def __call__(self, db: AsyncSession = Depends(get_db)) -> T:
        return self.factory(db)


# Pagination dependency
class PaginationParams:
    """
    Parâmetros de paginação.
    
    Uso:
        @router.get("/users")
        async def list_users(
            pagination: PaginationParams = Depends(),
            db: AsyncSession = Depends(get_db),
        ):
            users = await User.objects.using(db)\\
                .offset(pagination.offset)\\
                .limit(pagination.limit)\\
                .all()
            return users
    """
    
    def __init__(
        self,
        page: int = 1,
        page_size: int = 20,
        max_page_size: int = 100,
    ) -> None:
        self.page = max(1, page)
        self.page_size = min(max(1, page_size), max_page_size)
    
    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size
    
    @property
    def limit(self) -> int:
        return self.page_size


# Sorting dependency
class SortingParams:
    """
    Parâmetros de ordenação.
    
    Uso:
        @router.get("/users")
        async def list_users(
            sorting: SortingParams = Depends(),
            db: AsyncSession = Depends(get_db),
        ):
            users = await User.objects.using(db)\\
                .order_by(*sorting.order_by)\\
                .all()
            return users
    """
    
    def __init__(
        self,
        sort_by: str | None = None,
        sort_order: str = "asc",
        allowed_fields: list[str] | None = None,
    ) -> None:
        self.sort_by = sort_by
        self.sort_order = sort_order.lower()
        self.allowed_fields = allowed_fields or []
    
    @property
    def order_by(self) -> list[str]:
        if not self.sort_by:
            return []
        
        if self.allowed_fields and self.sort_by not in self.allowed_fields:
            return []
        
        prefix = "-" if self.sort_order == "desc" else ""
        return [f"{prefix}{self.sort_by}"]


# Request context dependency
async def get_request_context(request: Request) -> dict[str, Any]:
    """
    Dependency que retorna contexto da requisição.
    
    Útil para logging e auditoria.
    """
    return {
        "method": request.method,
        "url": str(request.url),
        "client_ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
        "user": getattr(request.state, "user", None),
    }


RequestContext = Annotated[dict[str, Any], Depends(get_request_context)]
