"""
Core Admin Panel — Centro nervoso operacional do framework.

Admin panel nativo, gerado automaticamente a partir dos models,
com extensão via admin.py no projeto do usuário.

Uso:
    # apps/users/admin.py
    from core.admin import admin, ModelAdmin
    
    @admin.register(User)
    class UserAdmin(ModelAdmin):
        list_display = ("id", "email", "is_active")
        search_fields = ("email",)
        ordering = ("-created_at",)

API pública:
    - admin: Proxy para AdminSite.default_site (registrar models)
    - ModelAdmin: Classe base para configuração de models
    - InlineModelAdmin: Configuração inline de models relacionados (Fase 2)
    - AdminSite: Registry central (uso avançado — múltiplos sites)
"""

from core.admin.site import AdminSite
from core.admin.options import ModelAdmin, InlineModelAdmin
from core.admin.exceptions import (
    AdminConfigurationError,
    AdminRegistrationError,
    AdminRuntimeError,
)
from core.admin.middleware import AdminSessionMiddleware

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


def action(description: str = ""):
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
        return func
    return decorator


__all__ = [
    "AdminSite",
    "ModelAdmin",
    "InlineModelAdmin",
    "AdminConfigurationError",
    "AdminRegistrationError",
    "AdminRuntimeError",
    "default_site",
    "admin",
    "register",
    "unregister",
    "action",
    "AdminSessionMiddleware",
    # Models internos
    "AuditLog",
    "AdminSession",
    "TaskExecution",
    "PeriodicTaskSchedule",
    "WorkerHeartbeat",
]
