"""
Decorators e dependencies para proteção de rotas.

Uso:
    from core.auth import require_permission, require_group, login_required
    
    # Via dependency
    @router.delete("/posts/{id}")
    async def delete_post(
        id: int,
        _: None = Depends(require_permission("posts.delete")),
    ):
        ...
    
    # Via classe de permissão
    class PostViewSet(ModelViewSet):
        permission_classes = [HasPermission("posts.view")]
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from fastapi import Depends, HTTPException, Request, status

from core.permissions import Permission as PermissionBase

if TYPE_CHECKING:
    pass


def _get_user(request: Request) -> Any | None:
    """
    Get authenticated user from request.
    
    Internal helper to avoid circular imports.
    Checks both Starlette and legacy patterns.
    """
    # Pattern 1: request.user (Starlette AuthenticationMiddleware)
    user = getattr(request, "user", None)
    if user is not None:
        if getattr(user, "is_authenticated", False):
            if hasattr(user, "_user"):
                return user._user
            return user
    
    # Pattern 2: request.state.user (legacy)
    if hasattr(request, "state"):
        return getattr(request.state, "user", None)
    
    return None


# =============================================================================
# Classes de Permissão (para uso em ViewSets)
# =============================================================================

class HasPermission(PermissionBase):
    """
    Verifica se o usuário tem uma permissão específica.
    
    Uso em ViewSet:
        class PostViewSet(ModelViewSet):
            permission_classes = [HasPermission("posts.view")]
            
            permission_classes_by_action = {
                "destroy": [HasPermission("posts.delete")],
                "create": [HasPermission("posts.create")],
            }
    
    Uso em rota:
        @router.delete("/posts/{id}")
        async def delete_post(
            id: int,
            _: None = Depends(HasPermission("posts.delete").dependency),
        ):
            ...
    """
    
    def __init__(self, *perms: str, require_all: bool = True) -> None:
        """
        Args:
            *perms: Permissões a verificar
            require_all: Se True, exige todas; se False, exige pelo menos uma
        """
        self.perms = perms
        self.require_all = require_all
        self.message = f"Permission required: {', '.join(perms)}"
    
    async def has_permission(
        self,
        request: Request,
        view: Any = None,
    ) -> bool:
        user = _get_user(request)
        
        if user is None:
            return False
        
        if not hasattr(user, "has_perm"):
            # Fallback: usa backend de permissão
            from core.auth.base import get_permission_backend
            backend = get_permission_backend()
            
            if self.require_all:
                for perm in self.perms:
                    if not await backend.has_permission(user, perm):
                        return False
                return True
            else:
                for perm in self.perms:
                    if await backend.has_permission(user, perm):
                        return True
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
            _: None = Depends(IsInGroup("administrators").dependency),
        ):
            ...
    """
    
    def __init__(self, *groups: str, require_all: bool = False) -> None:
        """
        Args:
            *groups: Grupos a verificar
            require_all: Se True, exige todos; se False, exige pelo menos um
        """
        self.groups = groups
        self.require_all = require_all
        self.message = f"Group membership required: {', '.join(groups)}"
    
    async def has_permission(
        self,
        request: Request,
        view: Any = None,
    ) -> bool:
        user = _get_user(request)
        
        if user is None:
            return False
        
        if not hasattr(user, "is_in_group"):
            # Fallback: verifica grupos diretamente
            if not hasattr(user, "groups"):
                return False
            
            user_groups = {g.name for g in user.groups}
            
            if self.require_all:
                return all(g in user_groups for g in self.groups)
            else:
                return any(g in user_groups for g in self.groups)
        
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


class IsSuperuser(PermissionBase):
    """Verifica se o usuário é superusuário."""
    
    message = "Superuser access required"
    
    async def has_permission(
        self,
        request: Request,
        view: Any = None,
    ) -> bool:
        user = _get_user(request)
        
        if user is None:
            return False
        
        return getattr(user, "is_superuser", False)
    
    @property
    def dependency(self):
        async def check(request: Request):
            if not await self.has_permission(request):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=self.message,
                )
        return check


class IsStaff(PermissionBase):
    """Verifica se o usuário é staff."""
    
    message = "Staff access required"
    
    async def has_permission(
        self,
        request: Request,
        view: Any = None,
    ) -> bool:
        user = _get_user(request)
        
        if user is None:
            return False
        
        return getattr(user, "is_staff", False)
    
    @property
    def dependency(self):
        async def check(request: Request):
            if not await self.has_permission(request):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=self.message,
                )
        return check


class IsActive(PermissionBase):
    """Verifica se o usuário está ativo."""
    
    message = "Account is inactive"
    
    async def has_permission(
        self,
        request: Request,
        view: Any = None,
    ) -> bool:
        user = _get_user(request)
        
        if user is None:
            return False
        
        return getattr(user, "is_active", True)
    
    @property
    def dependency(self):
        async def check(request: Request):
            if not await self.has_permission(request):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=self.message,
                )
        return check


# =============================================================================
# Dependency Factories
# =============================================================================

def require_permission(*perms: str, require_all: bool = True):
    """
    Dependency factory para exigir permissões.
    
    Args:
        *perms: Permissões a verificar
        require_all: Se True, exige todas; se False, exige pelo menos uma
    
    Uso:
        @router.delete("/posts/{id}")
        async def delete_post(
            id: int,
            _: None = Depends(require_permission("posts.delete")),
        ):
            ...
        
        # Múltiplas permissões (todas necessárias)
        @router.post("/admin/users")
        async def create_admin_user(
            _: None = Depends(require_permission("users.create", "admin.access")),
        ):
            ...
        
        # Qualquer uma das permissões
        @router.get("/content")
        async def view_content(
            _: None = Depends(require_permission("content.view", "admin.access", require_all=False)),
        ):
            ...
    """
    return HasPermission(*perms, require_all=require_all).dependency


def require_group(*groups: str, require_all: bool = False):
    """
    Dependency factory para exigir grupos.
    
    Args:
        *groups: Grupos a verificar
        require_all: Se True, exige todos; se False, exige pelo menos um
    
    Uso:
        @router.get("/admin")
        async def admin_panel(
            _: None = Depends(require_group("administrators")),
        ):
            ...
        
        # Múltiplos grupos (qualquer um)
        @router.get("/staff")
        async def staff_area(
            _: None = Depends(require_group("administrators", "moderators")),
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
    return IsSuperuser().dependency


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
    return IsStaff().dependency


def require_active():
    """
    Dependency que exige usuário ativo.
    
    Uso:
        @router.get("/profile")
        async def profile(
            _: None = Depends(require_active()),
        ):
            ...
    """
    return IsActive().dependency


def login_required():
    """
    Dependency que exige usuário autenticado.
    
    Alias mais expressivo para IsAuthenticated.
    
    Uso:
        @router.get("/me")
        async def get_me(
            _: None = Depends(login_required()),
        ):
            ...
    """
    async def check(request: Request):
        user = _get_user(request)
        
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    return check


# =============================================================================
# Combinadores de Permissão
# =============================================================================

def require_any(*dependencies):
    """
    Exige que pelo menos uma das dependencies passe.
    
    Uso:
        @router.get("/content")
        async def view_content(
            _: None = Depends(require_any(
                require_permission("content.view"),
                require_superuser(),
            )),
        ):
            ...
    """
    async def check(request: Request):
        errors = []
        
        for dep in dependencies:
            try:
                await dep(request)
                return  # Uma passou, ok
            except HTTPException as e:
                errors.append(e.detail)
        
        # Nenhuma passou
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"None of the required permissions were met: {'; '.join(errors)}",
        )
    
    return check


def require_all(*dependencies):
    """
    Exige que todas as dependencies passem.
    
    Uso:
        @router.delete("/admin/users/{id}")
        async def delete_user(
            id: int,
            _: None = Depends(require_all(
                require_permission("users.delete"),
                require_staff(),
            )),
        ):
            ...
    """
    async def check(request: Request):
        for dep in dependencies:
            await dep(request)  # Levanta exceção se falhar
    
    return check
