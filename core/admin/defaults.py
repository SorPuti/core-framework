"""
Registro automático de models core no admin.

Models core que sempre sobem no admin:
- User (via get_user_model() — NUNCA import direto)
- Group
- Permission
- AuditLog
- AdminSession

O usuário pode sobrescrever (admin.unregister / re-register).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.admin.options import ModelAdmin
from core.admin.exceptions import AdminConfigurationError

if TYPE_CHECKING:
    from core.admin.site import AdminSite

logger = logging.getLogger("core.admin")


# =========================================================================
# Admin configs para models core
# =========================================================================

class UserAdmin(ModelAdmin):
    """Admin config para o modelo User (resolvido via get_user_model)."""
    display_name = "User"
    display_name_plural = "Users"
    icon = "users"
    list_display = ("id", "email", "is_active", "is_staff", "is_superuser", "date_joined")
    search_fields = ("email",)
    list_filter = ("is_active", "is_staff", "is_superuser")
    ordering = ("-id",)
    readonly_fields = ("id", "date_joined", "last_login", "password_hash")
    exclude = ("password_hash",)


class GroupAdmin(ModelAdmin):
    """Admin config para Groups."""
    display_name = "Group"
    display_name_plural = "Groups"
    icon = "shield"
    list_display = ("id", "name", "description")
    search_fields = ("name",)
    ordering = ("name",)


class PermissionAdmin(ModelAdmin):
    """Admin config para Permissions."""
    display_name = "Permission"
    display_name_plural = "Permissions"
    icon = "key"
    list_display = ("id", "codename", "name", "description")
    search_fields = ("codename", "name")
    ordering = ("codename",)


class AuditLogAdmin(ModelAdmin):
    """Admin config para AuditLog (somente leitura)."""
    display_name = "Audit Log"
    display_name_plural = "Audit Logs"
    icon = "scroll-text"
    list_display = ("id", "user_email", "action", "model_name", "object_id", "timestamp")
    search_fields = ("user_email", "model_name", "object_id")
    list_filter = ("action", "model_name")
    ordering = ("-timestamp",)
    permissions = ("view",)  # Somente visualização
    readonly_fields = (
        "id", "user_id", "user_email", "action", "app_label",
        "model_name", "object_id", "object_repr", "changes",
        "ip_address", "user_agent", "timestamp",
    )


class AdminSessionAdmin(ModelAdmin):
    """Admin config para AdminSessions."""
    display_name = "Admin Session"
    display_name_plural = "Admin Sessions"
    icon = "monitor"
    list_display = ("id", "user_id", "ip_address", "created_at", "expires_at", "is_active")
    list_filter = ("is_active",)
    ordering = ("-created_at",)
    permissions = ("view", "delete")  # Ver e revogar sessões


# =========================================================================
# Função de registro
# =========================================================================

def register_core_models(site: "AdminSite") -> None:
    """
    Registra models core no admin.
    
    Chamado durante autodiscover(), ANTES dos admin.py do usuário.
    O usuário pode sobrescrever qualquer registro.
    
    REGRA: User via get_user_model(), NUNCA import direto.
    """
    # -- User (via get_user_model) --
    try:
        from core.auth.models import get_user_model
        User = get_user_model()
        
        # Adapta campos do UserAdmin ao modelo real
        user_admin = UserAdmin()
        # Verifica quais campos existem no modelo custom
        if hasattr(User, "__table__"):
            columns = [col.name for col in User.__table__.columns]
            # Filtra list_display para campos que existem
            user_admin.list_display = tuple(
                f for f in UserAdmin.list_display if f in columns
            ) or ("id",)
            user_admin.search_fields = tuple(
                f for f in UserAdmin.search_fields if f in columns
            )
            user_admin.list_filter = tuple(
                f for f in UserAdmin.list_filter if f in columns
            )
            user_admin.readonly_fields = tuple(
                f for f in UserAdmin.readonly_fields if f in columns
            )
            user_admin.exclude = tuple(
                f for f in UserAdmin.exclude if f in columns
            )
        
        site.register(User, type(user_admin))
        logger.debug("Registered User model (%s) in admin", User.__name__)
        
    except RuntimeError as e:
        # get_user_model() falhou — user model não configurado
        logger.warning(
            "Could not register User in admin: %s. "
            "Call configure_auth(user_model=YourUser) before app startup.",
            e,
        )
        site.errors.add(
            code="user_model_not_configured",
            title="User model não configurado",
            detail=str(e),
            hint="Chame configure_auth(user_model=YourUser) antes do startup da app.",
            model="User",
            level="warning",
        )
    except Exception as e:
        logger.warning("Could not register User in admin: %s", e)
        site.errors.add(
            code="user_model_error",
            title="Erro ao registrar User",
            detail=f"{type(e).__name__}: {e}",
            hint="Verifique se o modelo de usuário está corretamente definido.",
            model="User",
            level="warning",
        )
    
    # -- Group --
    try:
        from core.auth.models import Group
        site.register(Group, GroupAdmin)
    except Exception as e:
        logger.warning("Could not register Group in admin: %s", e)
        site.errors.add(
            code="model_registration_error",
            title="Erro ao registrar Group",
            detail=f"{type(e).__name__}: {e}",
            model="Group",
            level="warning",
        )
    
    # -- Permission --
    try:
        from core.auth.models import Permission
        site.register(Permission, PermissionAdmin)
    except Exception as e:
        logger.warning("Could not register Permission in admin: %s", e)
        site.errors.add(
            code="model_registration_error",
            title="Erro ao registrar Permission",
            detail=f"{type(e).__name__}: {e}",
            model="Permission",
            level="warning",
        )
    
    # -- AuditLog --
    try:
        from core.admin.models import AuditLog
        site.register(AuditLog, AuditLogAdmin)
    except Exception as e:
        logger.warning("Could not register AuditLog in admin: %s", e)
    
    # -- AdminSession --
    try:
        from core.admin.models import AdminSession
        site.register(AdminSession, AdminSessionAdmin)
    except Exception as e:
        logger.warning("Could not register AdminSession in admin: %s", e)
