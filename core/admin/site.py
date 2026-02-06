"""
AdminSite — Registry central do admin panel.

Gerencia o registro de models, discovery de admin.py, e montagem de rotas.
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from core.admin.exceptions import (
    AdminConfigurationError,
    AdminRegistrationError,
    AdminErrorCollector,
)
from core.admin.options import ModelAdmin

if TYPE_CHECKING:
    from fastapi import FastAPI
    from core.config import Settings

logger = logging.getLogger("core.admin")


class AdminSite:
    """
    Registry central do admin panel.
    
    Gerencia:
    - Registro de models e suas configurações ModelAdmin
    - Discovery automático de admin.py
    - Montagem de rotas no FastAPI
    - Coleção de erros para exibição profissional
    
    Exemplo:
        site = AdminSite()
        site.register(User, UserAdmin)
        site.autodiscover()
        site.mount(app, settings)
    """
    
    def __init__(self, name: str = "admin") -> None:
        self.name = name
        self._registry: dict[type, ModelAdmin] = {}
        self._app: FastAPI | None = None
        self._settings: "Settings | None" = None
        self.errors = AdminErrorCollector()
        self._is_mounted = False
    
    _SENTINEL = object()
    
    def register(
        self,
        model: type,
        admin_class: type[ModelAdmin] | None = _SENTINEL,
    ) -> type[ModelAdmin] | Any:
        """
        Registra um model no admin.
        
        Pode ser usado como decorator ou como função:
        
            # Como decorator
            @admin.register(User)
            class UserAdmin(ModelAdmin):
                list_display = ("id", "email")
            
            # Como função (registro com defaults)
            admin.register(PaymentLog)
            
            # Como função (com admin class explícita)
            admin.register(Order, OrderAdmin)
        
        Args:
            model: Model SQLAlchemy a registrar
            admin_class: Classe ModelAdmin customizada (opcional)
        
        Raises:
            AdminRegistrationError: Se configuração inválida
        """
        if admin_class is self._SENTINEL:
            # Chamado com 1 argumento: admin.register(Model)
            # Retorna decorator para suportar @admin.register(Model)
            # MAS também registra com defaults se usado como chamada direta
            
            def decorator(cls: type) -> type:
                if isinstance(cls, type) and issubclass(cls, ModelAdmin):
                    self._do_register(model, cls)
                    return cls
                # Se cls não é ModelAdmin, registra model com defaults
                self._do_register(model, None)
                return cls
            
            # Para suportar admin.register(Model) sem decorator,
            # registra com defaults imediatamente
            self._do_register(model, None)
            
            # Retorna decorator que re-registra se usado como @decorator
            def override_decorator(cls: type[ModelAdmin]) -> type[ModelAdmin]:
                self._do_register(model, cls)  # Sobrescreve o registro default
                return cls
            
            return override_decorator
        
        if admin_class is None:
            self._do_register(model, None)
            return model
        
        self._do_register(model, admin_class)
        return admin_class
    
    def _do_register(
        self,
        model: type,
        admin_class: type[ModelAdmin] | None,
    ) -> None:
        """Executa o registro efetivo."""
        model_name = model.__name__
        
        # Se já registrado, sobrescreve (último vence — usuário sobrescreve core)
        if model in self._registry:
            logger.debug(
                "Model %s re-registered in admin (overriding previous registration)",
                model_name,
            )
        
        # Instancia o ModelAdmin
        if admin_class is None:
            admin_instance = ModelAdmin()
        elif isinstance(admin_class, type) and issubclass(admin_class, ModelAdmin):
            admin_instance = admin_class()
        elif isinstance(admin_class, ModelAdmin):
            admin_instance = admin_class
        else:
            self.errors.add(
                code="invalid_admin_class",
                title=f"Admin class inválido para {model_name}",
                detail=f"{admin_class} não é subclasse de ModelAdmin",
                hint="Use uma classe que herde de ModelAdmin",
                model=model_name,
                level="error",
            )
            return
        
        # Bind ao model e valida
        try:
            admin_instance.bind(model)
        except AdminRegistrationError as e:
            logger.warning(
                "AdminRegistrationError for %s: %s", model_name, e,
            )
            self.errors.add_registration_error(model_name, e)
            return
        except Exception as e:
            logger.warning(
                "Unexpected error binding %s to admin: %s", model_name, e,
            )
            self.errors.add(
                code="bind_error",
                title=f"Erro ao vincular {model_name}",
                detail=f"{type(e).__name__}: {e}",
                hint="Verifique se o model tem __tablename__ e colunas definidas",
                model=model_name,
                level="error",
            )
            return
        
        self._registry[model] = admin_instance
        logger.debug("Registered %s in admin", model_name)
    
    def unregister(self, model: type) -> None:
        """
        Remove um model do admin.
        
        Útil para ocultar models core:
            admin.unregister(Permission)
        """
        if model in self._registry:
            del self._registry[model]
            logger.debug("Unregistered %s from admin", model.__name__)
    
    def is_registered(self, model: type) -> bool:
        """Verifica se um model está registrado."""
        return model in self._registry
    
    def get_admin_for_model(self, model: type) -> ModelAdmin | None:
        """Retorna o ModelAdmin de um model."""
        return self._registry.get(model)
    
    def get_registry(self) -> dict[type, ModelAdmin]:
        """Retorna cópia do registry."""
        return dict(self._registry)
    
    def get_model_by_name(self, app_label: str, model_name: str) -> tuple[type, ModelAdmin] | None:
        """Busca model por app_label e model_name."""
        for model, admin_instance in self._registry.items():
            if admin_instance._app_label == app_label and admin_instance._model_name == model_name:
                return (model, admin_instance)
        return None
    
    def get_app_list(self) -> list[dict[str, Any]]:
        """
        Retorna lista de apps com seus models para o menu lateral.
        Agrupado por app_label.
        """
        apps: dict[str, list[dict[str, Any]]] = {}
        
        for model, admin_instance in self._registry.items():
            app_label = admin_instance._app_label
            if app_label not in apps:
                apps[app_label] = []
            
            apps[app_label].append({
                "model_name": admin_instance._model_name,
                "display_name": admin_instance.display_name,
                "display_name_plural": admin_instance.display_name_plural,
                "icon": admin_instance.icon,
                "permissions": admin_instance.permissions,
                "has_errors": bool(self.errors.get_errors_for_model(model.__name__)),
            })
        
        return [
            {
                "app_label": label,
                "models": sorted(models, key=lambda m: m["display_name"] or ""),
            }
            for label, models in sorted(apps.items())
        ]
    
    def autodiscover(self) -> None:
        """
        Importa admin.py de todos os apps e registra models core.
        
        Ordem:
        1. Registra models core (User via get_user_model(), Group, Permission)
        2. Descobre e importa admin.py dos apps do usuário
        3. Usuário sobrescreve core (último registro vence)
        """
        # 1. Registra defaults do core
        from core.admin.defaults import register_core_models
        register_core_models(self)
        
        # 2. Descobre admin.py dos apps
        from core.admin.discovery import discover_admin_modules
        discover_admin_modules(self)
    
    def mount(self, app: "FastAPI", settings: "Settings") -> None:
        """
        Monta o admin router no FastAPI app.
        
        Usa settings.admin_url_prefix para o prefixo da rota.
        """
        self._app = app
        self._settings = settings
        
        prefix = getattr(settings, "admin_url_prefix", "/admin").rstrip("/")
        
        from core.admin.router import create_admin_router
        router = create_admin_router(self, settings)
        
        app.include_router(router, prefix=prefix)
        
        # Serve static files em debug mode
        debug = getattr(settings, "debug", False)
        if debug:
            self._mount_static(app, prefix)
        
        self._is_mounted = True
        
        # Log de status
        model_count = len(self._registry)
        error_count = self.errors.error_count
        warning_count = self.errors.warning_count
        
        logger.info(
            "Admin panel mounted at %s (%d models, %d errors, %d warnings)",
            prefix, model_count, error_count, warning_count,
        )
        
        if error_count > 0:
            logger.warning(
                "Admin has %d registration errors. Check %s/dashboard/ for details.",
                error_count, prefix,
            )
    
    def _mount_static(self, app: "FastAPI", prefix: str) -> None:
        """Monta StaticFiles para servir assets em dev mode."""
        import importlib.resources
        from pathlib import Path
        from starlette.staticfiles import StaticFiles
        
        # Resolve o diretório de static files do core admin
        static_dir = Path(__file__).parent / "static" / "core-admin"
        
        if static_dir.is_dir():
            app.mount(
                f"{prefix}/static",
                StaticFiles(directory=str(static_dir)),
                name="core-admin-static",
            )
            logger.debug("Admin static files mounted at %s/static", prefix)
    
    @property
    def url_prefix(self) -> str:
        """Retorna o prefixo de URL do admin."""
        if self._settings:
            return getattr(self._settings, "admin_url_prefix", "/admin").rstrip("/")
        return "/admin"
