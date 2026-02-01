"""
Implementações de backends de permissão.

Backends disponíveis:
- DefaultPermissionBackend: Permissões via modelo (grupos + permissões diretas)
- ObjectPermissionBackend: Permissões por objeto específico

Uso:
    from core.auth import get_permission_backend, register_permission_backend
    
    # Verificar permissão
    backend = get_permission_backend()
    has_perm = await backend.has_permission(user, "posts.delete")
    
    # Permissão por objeto
    has_perm = await backend.has_permission(user, "posts.edit", obj=post)
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from core.auth.base import (
    PermissionBackend,
    register_permission_backend,
)

if TYPE_CHECKING:
    pass


class DefaultPermissionBackend(PermissionBackend):
    """
    Backend de permissões padrão.
    
    Verifica permissões via:
    1. is_superuser (tem todas)
    2. user_permissions (permissões diretas)
    3. groups -> permissions (permissões via grupos)
    
    Uso:
        backend = get_permission_backend()
        
        # Verificar permissão
        if await backend.has_permission(user, "posts.delete"):
            ...
    """
    
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
            permission: Código da permissão (ex: "posts.delete")
            obj: Ignorado neste backend
            
        Returns:
            True se tem permissão
        """
        if user is None:
            return False
        
        # Verifica se está ativo
        if hasattr(user, "is_active") and not user.is_active:
            return False
        
        # Superuser tem todas as permissões
        if hasattr(user, "is_superuser") and user.is_superuser:
            return True
        
        # Usa método do modelo se disponível
        if hasattr(user, "has_perm"):
            return user.has_perm(permission)
        
        # Fallback: verifica manualmente
        return await self._check_permission(user, permission)
    
    async def _check_permission(self, user: Any, permission: str) -> bool:
        """Verifica permissão manualmente."""
        # Permissões diretas
        if hasattr(user, "user_permissions"):
            for perm in user.user_permissions:
                codename = getattr(perm, "codename", str(perm))
                if codename == permission:
                    return True
        
        # Permissões via grupos
        if hasattr(user, "groups"):
            for group in user.groups:
                if hasattr(group, "permissions"):
                    for perm in group.permissions:
                        codename = getattr(perm, "codename", str(perm))
                        if codename == permission:
                            return True
        
        return False
    
    async def get_all_permissions(self, user: Any) -> set[str]:
        """Retorna todas as permissões do usuário."""
        if user is None:
            return set()
        
        # Usa método do modelo se disponível
        if hasattr(user, "get_all_permissions"):
            result = user.get_all_permissions()
            if isinstance(result, set):
                return result
        
        # Fallback: coleta manualmente
        perms = set()
        
        if hasattr(user, "user_permissions"):
            for perm in user.user_permissions:
                codename = getattr(perm, "codename", str(perm))
                perms.add(codename)
        
        if hasattr(user, "groups"):
            for group in user.groups:
                if hasattr(group, "permissions"):
                    for perm in group.permissions:
                        codename = getattr(perm, "codename", str(perm))
                        perms.add(codename)
        
        return perms
    
    async def get_group_permissions(self, user: Any) -> set[str]:
        """Retorna permissões via grupos."""
        if user is None:
            return set()
        
        perms = set()
        
        if hasattr(user, "groups"):
            for group in user.groups:
                if hasattr(group, "permissions"):
                    for perm in group.permissions:
                        codename = getattr(perm, "codename", str(perm))
                        perms.add(codename)
        
        return perms


class ObjectPermissionBackend(PermissionBackend):
    """
    Backend de permissões por objeto.
    
    Verifica permissões específicas para um objeto:
    - Dono do objeto (owner_id == user.id)
    - Permissões customizadas por objeto
    
    Uso:
        backend = ObjectPermissionBackend(owner_field="user_id")
        
        # Verificar se é dono
        if await backend.has_permission(user, "posts.edit", obj=post):
            ...
    """
    
    def __init__(
        self,
        owner_field: str = "user_id",
        fallback_backend: str | None = "default",
    ) -> None:
        self.owner_field = owner_field
        self.fallback_backend = fallback_backend
    
    async def has_permission(
        self,
        user: Any,
        permission: str,
        obj: Any = None,
    ) -> bool:
        """
        Verifica permissão para um objeto específico.
        
        Args:
            user: Usuário
            permission: Código da permissão
            obj: Objeto a verificar
            
        Returns:
            True se tem permissão
        """
        if user is None:
            return False
        
        # Verifica se está ativo
        if hasattr(user, "is_active") and not user.is_active:
            return False
        
        # Superuser tem todas as permissões
        if hasattr(user, "is_superuser") and user.is_superuser:
            return True
        
        # Se não tem objeto, usa fallback
        if obj is None:
            return await self._fallback_check(user, permission)
        
        # Verifica se é dono
        if self._is_owner(user, obj):
            return True
        
        # Verifica permissões customizadas do objeto
        if await self._check_object_permission(user, permission, obj):
            return True
        
        # Fallback para permissões gerais
        return await self._fallback_check(user, permission)
    
    def _is_owner(self, user: Any, obj: Any) -> bool:
        """Verifica se usuário é dono do objeto."""
        user_id = getattr(user, "id", None)
        if user_id is None:
            return False
        
        # Tenta diferentes campos de owner
        owner_id = getattr(obj, self.owner_field, None)
        if owner_id is None:
            owner_id = getattr(obj, "owner_id", None)
        if owner_id is None:
            owner_id = getattr(obj, "created_by_id", None)
        
        return owner_id is not None and owner_id == user_id
    
    async def _check_object_permission(
        self,
        user: Any,
        permission: str,
        obj: Any,
    ) -> bool:
        """
        Verifica permissões customizadas do objeto.
        
        Sobrescreva para implementar lógica customizada.
        """
        # Se o objeto tem método de verificação, usa ele
        if hasattr(obj, "has_permission"):
            return obj.has_permission(user, permission)
        
        if hasattr(obj, "can_access"):
            return obj.can_access(user, permission)
        
        return False
    
    async def _fallback_check(self, user: Any, permission: str) -> bool:
        """Usa backend de fallback para verificação."""
        if self.fallback_backend is None:
            return False
        
        from core.auth.base import get_permission_backend
        
        try:
            backend = get_permission_backend(self.fallback_backend)
            return await backend.has_permission(user, permission)
        except KeyError:
            return False
    
    async def get_all_permissions(self, user: Any) -> set[str]:
        """Delega para fallback backend."""
        if self.fallback_backend is None:
            return set()
        
        from core.auth.base import get_permission_backend
        
        try:
            backend = get_permission_backend(self.fallback_backend)
            return await backend.get_all_permissions(user)
        except KeyError:
            return set()


class RoleBasedPermissionBackend(PermissionBackend):
    """
    Backend de permissões baseado em roles (RBAC).
    
    Define permissões por role em vez de individualmente:
    
        backend = RoleBasedPermissionBackend({
            "admin": ["*"],  # Todas as permissões
            "editor": ["posts.create", "posts.edit", "posts.delete"],
            "viewer": ["posts.view"],
        })
    
    Uso:
        # Usuário com role "editor"
        user.role = "editor"
        
        await backend.has_permission(user, "posts.edit")  # True
        await backend.has_permission(user, "users.delete")  # False
    """
    
    def __init__(
        self,
        role_permissions: dict[str, list[str]] | None = None,
        role_field: str = "role",
        roles_field: str = "roles",
    ) -> None:
        self.role_permissions = role_permissions or {}
        self.role_field = role_field
        self.roles_field = roles_field
    
    def define_role(self, role: str, permissions: list[str]) -> None:
        """Define permissões para um role."""
        self.role_permissions[role] = permissions
    
    def get_user_roles(self, user: Any) -> list[str]:
        """Obtém roles do usuário."""
        roles = []
        
        # Campo único
        role = getattr(user, self.role_field, None)
        if role:
            roles.append(role)
        
        # Campo múltiplo
        user_roles = getattr(user, self.roles_field, None)
        if user_roles:
            if isinstance(user_roles, str):
                roles.append(user_roles)
            else:
                roles.extend(user_roles)
        
        # Via grupos
        if hasattr(user, "groups"):
            for group in user.groups:
                name = getattr(group, "name", str(group))
                roles.append(name)
        
        return roles
    
    async def has_permission(
        self,
        user: Any,
        permission: str,
        obj: Any = None,
    ) -> bool:
        """Verifica permissão baseada em roles."""
        if user is None:
            return False
        
        if hasattr(user, "is_active") and not user.is_active:
            return False
        
        if hasattr(user, "is_superuser") and user.is_superuser:
            return True
        
        roles = self.get_user_roles(user)
        
        for role in roles:
            role_perms = self.role_permissions.get(role, [])
            
            # Wildcard - todas as permissões
            if "*" in role_perms:
                return True
            
            # Permissão específica
            if permission in role_perms:
                return True
            
            # Wildcard parcial (ex: "posts.*")
            for perm in role_perms:
                if perm.endswith(".*"):
                    prefix = perm[:-2]
                    if permission.startswith(prefix + "."):
                        return True
        
        return False
    
    async def get_all_permissions(self, user: Any) -> set[str]:
        """Retorna todas as permissões dos roles do usuário."""
        if user is None:
            return set()
        
        perms = set()
        roles = self.get_user_roles(user)
        
        for role in roles:
            role_perms = self.role_permissions.get(role, [])
            perms.update(role_perms)
        
        return perms


# =============================================================================
# Registro dos backends padrão
# =============================================================================

def _register_default_permission_backends() -> None:
    """Registra os backends de permissão padrão."""
    register_permission_backend("default", DefaultPermissionBackend())
    register_permission_backend("object", ObjectPermissionBackend())
    register_permission_backend("rbac", RoleBasedPermissionBackend())


# Registra ao importar
_register_default_permission_backends()
