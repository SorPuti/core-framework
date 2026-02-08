"""
Permissões do Admin Panel.

Integra com o sistema de permissões existente do core.
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from fastapi import HTTPException, Request, status

if TYPE_CHECKING:
    from core.views import APIView

logger = logging.getLogger("core.admin")


def _get_admin_user(request: Request) -> Any | None:
    """
    Obtém o usuário autenticado do request.
    
    Verifica múltiplos patterns de autenticação:
    1. request.state.admin_user (session-based admin auth)
    2. request.user (Starlette AuthenticationMiddleware)
    3. request.state.user (legacy)
    """
    # Admin session
    admin_user = getattr(getattr(request, "state", None), "admin_user", None)
    if admin_user is not None:
        return admin_user
    
    # Starlette middleware
    user = getattr(request, "user", None)
    if user is not None:
        if getattr(user, "is_authenticated", False):
            if hasattr(user, "_user"):
                return user._user
            return user
    
    # Legacy
    if hasattr(request, "state"):
        user = getattr(request.state, "user", None)
        if user is not None:
            return user
    
    return None


class IsAdminUser:
    """
    Permissão: requer is_staff=True ou is_superuser=True.
    
    Aplicada a todas as rotas do admin panel.
    """
    message = "Admin access required"
    
    async def __call__(self, request: Request) -> bool:
        user = _get_admin_user(request)
        if user is None:
            return False
        return bool(getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))


async def check_admin_access(request: Request) -> Any:
    """
    FastAPI dependency que verifica acesso ao admin.
    
    Returns:
        O usuário admin se autenticado e autorizado
    
    Raises:
        HTTPException 401/403
    """
    user = _get_admin_user(request)
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    
    is_staff = getattr(user, "is_staff", False)
    is_superuser = getattr(user, "is_superuser", False)
    
    if not (is_staff or is_superuser):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required. User must have is_staff=True or is_superuser=True.",
        )
    
    return user


async def check_model_permission(
    user: Any,
    app_label: str,
    model_name: str,
    action: str,
) -> bool:
    """
    Verifica se o usuário tem permissão para uma ação em um model.
    
    Superusers sempre têm acesso.
    Staff users precisam da permissão específica.
    
    Permissões seguem o formato: {app_label}.{action}_{model_name}
    Ex: users.view_user, users.add_user, users.change_user, users.delete_user
    
    Args:
        user: Usuário autenticado
        app_label: Label do app (ex: "users")
        model_name: Nome do model (ex: "user")
        action: Ação (view, add, change, delete)
    
    Returns:
        True se autorizado
    """
    if getattr(user, "is_superuser", False):
        return True
    
    codename = f"{app_label}.{action}_{model_name}"
    
    # Tenta has_permission (PermissionsMixin)
    if hasattr(user, "has_permission"):
        result = user.has_permission(codename)
        # Pode ser async ou sync
        if hasattr(result, "__await__"):
            return await result
        return result
    
    # Fallback: verifica user_permissions diretamente
    if hasattr(user, "user_permissions"):
        perms = user.user_permissions
        if any(
            getattr(p, "codename", None) == codename
            for p in perms
        ):
            return True
    
    # Fallback: verifica grupos
    if hasattr(user, "groups"):
        for group in user.groups:
            if hasattr(group, "permissions"):
                if any(
                    getattr(p, "codename", None) == codename
                    for p in group.permissions
                ):
                    return True
    
    return False


async def get_user_model_permissions(
    user: Any,
    app_label: str,
    model_name: str,
) -> dict[str, bool]:
    """
    Retorna dict com todas as permissões do usuário para um model.
    
    Usado para renderizar UI do admin (esconder/mostrar botões).
    
    Returns:
        {"view": True, "add": False, "change": True, "delete": False}
    """
    actions = ("view", "add", "change", "delete")
    result = {}
    
    for action in actions:
        result[action] = await check_model_permission(user, app_label, model_name, action)
    
    return result
