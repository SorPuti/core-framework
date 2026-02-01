"""
Sistema de Permissões simples e extensível.

Características:
- Interface clara e explícita
- Composição de permissões
- Async por padrão
- Integração com FastAPI Depends
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TYPE_CHECKING

from fastapi import HTTPException, Request, status

if TYPE_CHECKING:
    from core.views import APIView


class Permission(ABC):
    """
    Classe base para permissões.
    
    Implemente o método has_permission para criar permissões customizadas.
    
    Exemplo:
        class IsAdmin(Permission):
            async def has_permission(
                self,
                request: Request,
                view: APIView | None = None,
            ) -> bool:
                user = getattr(request.state, "user", None)
                return user is not None and user.is_admin
    """
    
    # Mensagem de erro padrão
    message: str = "Permission denied"
    status_code: int = status.HTTP_403_FORBIDDEN
    
    @abstractmethod
    async def has_permission(
        self,
        request: Request,
        view: "APIView | None" = None,
    ) -> bool:
        """
        Verifica se a requisição tem permissão.
        
        Args:
            request: Requisição FastAPI
            view: View que está sendo acessada (opcional)
            
        Returns:
            True se permitido, False caso contrário
        """
        ...
    
    async def has_object_permission(
        self,
        request: Request,
        view: "APIView | None" = None,
        obj: Any = None,
    ) -> bool:
        """
        Verifica permissão para um objeto específico.
        
        Por padrão, retorna True. Sobrescreva para implementar
        permissões a nível de objeto.
        
        Args:
            request: Requisição FastAPI
            view: View que está sendo acessada
            obj: Objeto sendo acessado
            
        Returns:
            True se permitido, False caso contrário
        """
        return True
    
    def __and__(self, other: "Permission") -> "AndPermission":
        """Combina permissões com AND."""
        return AndPermission(self, other)
    
    def __or__(self, other: "Permission") -> "OrPermission":
        """Combina permissões com OR."""
        return OrPermission(self, other)
    
    def __invert__(self) -> "NotPermission":
        """Inverte a permissão."""
        return NotPermission(self)


class AndPermission(Permission):
    """Combina duas permissões com AND."""
    
    def __init__(self, perm1: Permission, perm2: Permission) -> None:
        self.perm1 = perm1
        self.perm2 = perm2
        self.message = f"{perm1.message} and {perm2.message}"
    
    async def has_permission(
        self,
        request: Request,
        view: "APIView | None" = None,
    ) -> bool:
        return (
            await self.perm1.has_permission(request, view)
            and await self.perm2.has_permission(request, view)
        )
    
    async def has_object_permission(
        self,
        request: Request,
        view: "APIView | None" = None,
        obj: Any = None,
    ) -> bool:
        return (
            await self.perm1.has_object_permission(request, view, obj)
            and await self.perm2.has_object_permission(request, view, obj)
        )


class OrPermission(Permission):
    """Combina duas permissões com OR."""
    
    def __init__(self, perm1: Permission, perm2: Permission) -> None:
        self.perm1 = perm1
        self.perm2 = perm2
        self.message = f"{perm1.message} or {perm2.message}"
    
    async def has_permission(
        self,
        request: Request,
        view: "APIView | None" = None,
    ) -> bool:
        return (
            await self.perm1.has_permission(request, view)
            or await self.perm2.has_permission(request, view)
        )
    
    async def has_object_permission(
        self,
        request: Request,
        view: "APIView | None" = None,
        obj: Any = None,
    ) -> bool:
        return (
            await self.perm1.has_object_permission(request, view, obj)
            or await self.perm2.has_object_permission(request, view, obj)
        )


class NotPermission(Permission):
    """Inverte uma permissão."""
    
    def __init__(self, perm: Permission) -> None:
        self.perm = perm
        self.message = f"Not {perm.message}"
    
    async def has_permission(
        self,
        request: Request,
        view: "APIView | None" = None,
    ) -> bool:
        return not await self.perm.has_permission(request, view)
    
    async def has_object_permission(
        self,
        request: Request,
        view: "APIView | None" = None,
        obj: Any = None,
    ) -> bool:
        return not await self.perm.has_object_permission(request, view, obj)


# Permissões built-in
class AllowAny(Permission):
    """Permite qualquer acesso."""
    
    message = "Access allowed"
    
    async def has_permission(
        self,
        request: Request,
        view: "APIView | None" = None,
    ) -> bool:
        return True


class DenyAll(Permission):
    """Nega qualquer acesso."""
    
    message = "Access denied"
    
    async def has_permission(
        self,
        request: Request,
        view: "APIView | None" = None,
    ) -> bool:
        return False


class IsAuthenticated(Permission):
    """Requer usuário autenticado."""
    
    message = "Authentication required"
    status_code = status.HTTP_401_UNAUTHORIZED
    
    async def has_permission(
        self,
        request: Request,
        view: "APIView | None" = None,
    ) -> bool:
        user = getattr(request.state, "user", None)
        return user is not None


class IsAuthenticatedOrReadOnly(Permission):
    """
    Permite leitura para todos, escrita apenas para autenticados.
    """
    
    message = "Authentication required for write operations"
    status_code = status.HTTP_401_UNAUTHORIZED
    
    SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
    
    async def has_permission(
        self,
        request: Request,
        view: "APIView | None" = None,
    ) -> bool:
        if request.method in self.SAFE_METHODS:
            return True
        
        user = getattr(request.state, "user", None)
        return user is not None


class IsAdmin(Permission):
    """Requer usuário administrador."""
    
    message = "Admin access required"
    
    async def has_permission(
        self,
        request: Request,
        view: "APIView | None" = None,
    ) -> bool:
        user = getattr(request.state, "user", None)
        if user is None:
            return False
        
        # Verifica atributos comuns de admin
        return getattr(user, "is_admin", False) or getattr(user, "is_superuser", False)


class IsOwner(Permission):
    """
    Permite acesso apenas ao dono do objeto.
    
    Requer que o objeto tenha um campo 'user_id' ou 'owner_id'.
    """
    
    message = "You don't have permission to access this object"
    owner_field: str = "user_id"
    
    async def has_permission(
        self,
        request: Request,
        view: "APIView | None" = None,
    ) -> bool:
        # Permissão geral sempre True, verificação é feita por objeto
        return True
    
    async def has_object_permission(
        self,
        request: Request,
        view: "APIView | None" = None,
        obj: Any = None,
    ) -> bool:
        if obj is None:
            return True
        
        user = getattr(request.state, "user", None)
        if user is None:
            return False
        
        # Tenta diferentes campos de owner
        owner_id = getattr(obj, self.owner_field, None)
        if owner_id is None:
            owner_id = getattr(obj, "owner_id", None)
        
        user_id = getattr(user, "id", None)
        
        return owner_id is not None and owner_id == user_id


class HasRole(Permission):
    """
    Verifica se o usuário tem um role específico.
    
    Exemplo:
        @router.get("/admin", dependencies=[Depends(HasRole("admin").dependency)])
        async def admin_only():
            ...
    """
    
    def __init__(self, *roles: str) -> None:
        self.roles = set(roles)
        self.message = f"Required role: {', '.join(roles)}"
    
    async def has_permission(
        self,
        request: Request,
        view: "APIView | None" = None,
    ) -> bool:
        user = getattr(request.state, "user", None)
        if user is None:
            return False
        
        user_roles = getattr(user, "roles", [])
        if isinstance(user_roles, str):
            user_roles = [user_roles]
        
        return bool(self.roles & set(user_roles))


# Funções utilitárias
async def check_permissions(
    permissions: list[Permission],
    request: Request,
    view: "APIView | None" = None,
    obj: Any = None,
) -> None:
    """
    Verifica uma lista de permissões.
    
    Raises:
        HTTPException: Se alguma permissão falhar
    """
    for permission in permissions:
        if not await permission.has_permission(request, view):
            raise HTTPException(
                status_code=permission.status_code,
                detail=permission.message,
            )
        
        if obj is not None:
            if not await permission.has_object_permission(request, view, obj):
                raise HTTPException(
                    status_code=permission.status_code,
                    detail=permission.message,
                )


def require_permission(permission: Permission):
    """
    Decorator para exigir permissão em uma rota.
    
    Exemplo:
        @router.get("/protected")
        @require_permission(IsAuthenticated())
        async def protected_route(request: Request):
            ...
    """
    async def dependency(request: Request) -> None:
        if not await permission.has_permission(request):
            raise HTTPException(
                status_code=permission.status_code,
                detail=permission.message,
            )
    
    return dependency
