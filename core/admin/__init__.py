"""
Core Admin Panel — Centro nervoso operacional do framework.

Admin panel nativo, gerado automaticamente a partir dos models,
com extensão via admin.py no projeto do usuário.

Uso:
    # apps/users/admin.py
    from core.admin import admin, ModelAdmin
    
    @admin.register(User)
    class UserAdmin(ModelAdmin[User]):  # Tipagem genérica para autocomplete
        list_display = ("id", "email", "is_active")
        search_fields = ("email",)
        ordering = ("-created_at",)

API pública:
    - admin: Proxy para AdminSite.default_site (registrar models)
    - ModelAdmin: Classe base para configuração de models (genérica)
    - InlineModelAdmin: Configuração inline de models relacionados (Fase 2)
    - AdminSite: Registry central (uso avançado — múltiplos sites)
    
Tipos para autocomplete:
    - WidgetConfig: TypedDict para configuração de widgets
    - FieldsetConfig: Tipo para fieldsets
    - IconType: Literal com ícones Lucide disponíveis
"""

from core.admin.site import AdminSite
from core.admin.options import ModelAdmin, InlineModelAdmin
from core.admin.exceptions import (
    AdminConfigurationError,
    AdminRegistrationError,
    AdminRuntimeError,
)
from core.admin.middleware import AdminSessionMiddleware
from core.admin.types import (
    WidgetConfig,
    FieldsetConfig,
    FieldsetOptions,
    IconType,
    PermissionType,
    WidgetType,
    ColumnInfo,
    ModelT,
)
from core.admin._typing import (
    model_fields,
    get_model_field_names,
)

# ── Models internos do Admin — importados no module-level para garantir ──
# que são registrados no Base.metadata e visíveis ao sistema de migrações.
from core.admin.models import (  # noqa: F401
    AuditLog,
    AdminSession,
    TaskExecution,
    PeriodicTaskSchedule,
    WorkerHeartbeat,
)

# Singleton default — usado na maioria dos projetos
default_site = AdminSite(name="default")

# Proxy functions para conveniência
register = default_site.register
unregister = default_site.unregister

# Alias para compatibilidade com pattern Django
admin = default_site


def action(
    description: str = "",
    *,
    requires_selection: bool = False,
    confirm: str = "",
    permission: str = "change",
):
    """
    Decorator para custom actions no ModelAdmin.
    
    Exemplo:
        @admin.action(description="Desativar selecionados")
        async def deactivate(self, db, queryset):
            await queryset.update(is_active=False)
    """
    def decorator(func):
        func._admin_action = True
        func.short_description = description or func.__name__.replace("_", " ").title()
        func.requires_selection = requires_selection
        func.confirm_message = confirm
        func.required_permission = permission
        return func
    return decorator


__all__ = [
    # Core classes
    "AdminSite",
    "ModelAdmin",
    "InlineModelAdmin",
    # Exceptions
    "AdminConfigurationError",
    "AdminRegistrationError",
    "AdminRuntimeError",
    # Singleton e helpers
    "default_site",
    "admin",
    "register",
    "unregister",
    "action",
    "AdminSessionMiddleware",
    # Type hints para autocomplete
    "WidgetConfig",
    "FieldsetConfig",
    "FieldsetOptions",
    "IconType",
    "PermissionType",
    "WidgetType",
    "ColumnInfo",
    "ModelT",
    # Helpers para autocomplete de campos
    "model_fields",
    "get_model_field_names",
    # Models internos
    "AuditLog",
    "AdminSession",
    "TaskExecution",
    "PeriodicTaskSchedule",
    "WorkerHeartbeat",
]
