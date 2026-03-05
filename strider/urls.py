"""
Sistema de URLs estilo Django com auto-discovery automático.

Este módulo implementa um sistema de roteamento similar ao Django,
onde cada app pode definir seu próprio urls.py com urlpatterns.

O auto-discovery carrega automaticamente todos os urls.py das apps
listadas em settings.installed_apps.

Usage:
    # src/apps/users/urls.py
    from strider.urls import path
    from .views import UserViewSet
    
    urlpatterns = [
        path("users", UserViewSet),
    ]
    
    # src/main.py
    from strider import StrideApp
    app = StrideApp()  # Auto-discovery carrega tudo
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, TYPE_CHECKING
from collections.abc import Callable

if TYPE_CHECKING:
    from strider.views import ViewSet, APIView
    from strider.routing import Router, AutoRouter

logger = logging.getLogger("strider.urls")


class URLPattern:
    """
    Representa um padrão de URL.
    
    Similar ao django.urls.path().
    
    Attributes:
        route: Caminho da URL (ex: "users", "auth/login")
        view: ViewSet, APIView ou callable a ser registrado
        name: Nome opcional para a rota
        kwargs: Argumentos adicionais para o registro
    """
    
    def __init__(
        self,
        route: str,
        view: type | Callable,
        name: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.route = route
        self.view = view
        self.name = name
        self.kwargs = kwargs
    
    def __repr__(self) -> str:
        return f"URLPattern(route='{self.route}', view={self.view.__name__})"


class URLInclude:
    """
    Representa uma inclusão de sub-rotas.
    
    Similar ao django.urls.include().
    
    Attributes:
        module: Módulo de URLs a incluir (ex: "app.urls" ou "auth.urls")
        namespace: Namespace opcional para as rotas
    """
    
    def __init__(
        self,
        module: str,
        namespace: str | None = None,
    ) -> None:
        self.module = module
        self.namespace = namespace
    
    def __repr__(self) -> str:
        return f"URLInclude(module='{self.module}')"


def path(
    route: str,
    view: type | Callable | URLInclude,
    name: str | None = None,
    **kwargs: Any,
) -> URLPattern:
    """
    Define um padrão de URL.
    
    Similar ao django.urls.path().
    
    Args:
        route: Caminho da URL (ex: "users", "auth/login")
        view: ViewSet, APIView, callable ou URLInclude
        name: Nome opcional para a rota
        **kwargs: Argumentos adicionais
    
    Returns:
        URLPattern configurado
    
    Examples:
        path("users", UserViewSet)
        path("login", LoginView.as_view())
        path("api/", include("otherapp.urls"))
    """
    if isinstance(view, URLInclude):
        # Para includes, retornamos um padrão especial
        return URLPattern(route, view, name, **kwargs)
    
    return URLPattern(route, view, name, **kwargs)


def include(module: str, namespace: str | None = None) -> URLInclude:
    """
    Inclui rotas de outro módulo.
    
    Similar ao django.urls.include().
    
    Args:
        module: Módulo de URLs (ex: "auth.urls", "api.v1.urls")
        namespace: Namespace opcional
    
    Returns:
        URLInclude configurado
    
    Examples:
        path("api/v1/", include("myapp.urls"))
        path("admin/", include("admin.site.urls"))
    """
    return URLInclude(module, namespace)


def _load_url_module(module_path: str) -> list[URLPattern] | None:
    """
    Carrega um módulo de URLs e retorna os urlpatterns.
    
    Args:
        module_path: Caminho do módulo (ex: "src.apps.users.urls")
    
    Returns:
        Lista de URLPattern ou None se não encontrar
    """
    try:
        module = importlib.import_module(module_path)
    except ImportError:
        # Módulo não existe - silenciosamente ignora
        return None
    
    # Busca urlpatterns no módulo
    patterns = getattr(module, "urlpatterns", None)
    if patterns is None:
        logger.debug(f"Module {module_path} has no urlpatterns")
        return None
    
    if not isinstance(patterns, list):
        logger.warning(f"urlpatterns in {module_path} is not a list")
        return None
    
    return patterns


def _resolve_app_module(app_name: str, sub_module: str = "urls") -> str | None:
    """
    Resolve o caminho completo de um módulo de app.
    
    Aceita nomes curtos (ex: 'users') e tenta encontrar em locais padrão:
    1. Tenta como caminho absoluto primeiro (ex: 'src.apps.users')
    2. Tenta em src.apps.{app_name}
    3. Tenta em apps.{app_name}
    
    Args:
        app_name: Nome curto ou caminho completo do app
        sub_module: Submódulo a carregar (ex: 'urls', 'models', 'admin')
    
    Returns:
        Caminho completo do módulo ou None se não encontrado
    """
    import importlib
    
    # Se já tem ponto, tenta como caminho absoluto primeiro
    if "." in app_name:
        full_path = f"{app_name}.{sub_module}"
        try:
            if importlib.util.find_spec(full_path.replace(".", "/").rsplit("/", 1)[0]):
                return full_path
        except (ImportError, ModuleNotFoundError):
            pass
    
    # Tenta locais padrão
    search_paths = [
        f"src.apps.{app_name}.{sub_module}",
        f"apps.{app_name}.{sub_module}",
        f"src.{app_name}.{sub_module}",
    ]
    
    for path in search_paths:
        try:
            # Tenta importar para verificar se existe
            if importlib.util.find_spec(path.replace(".", "/").rsplit("/", 1)[0]):
                return path
        except (ImportError, ModuleNotFoundError, ValueError):
            continue
    
    # Fallback: retorna como estava se não conseguiu resolver
    return f"{app_name}.{sub_module}" if "." not in app_name else f"{app_name}.{sub_module}"


def autodiscover(settings: Any) -> "AutoRouter":
    """
    Descobre e carrega automaticamente todos os urls.py das apps.
    
    Esta função é chamada automaticamente pelo StrideApp.
    
    Se settings.root_urlconf estiver definido, carrega URLs deste módulo
    (similar ao Django ROOT_URLCONF). Caso contrário, faz auto-discovery
    de todas as apps em installed_apps.
    
    Aceita app names curtos (ex: 'users') ou caminhos completos (ex: 'src.apps.users').
    
    Args:
        settings: Instância de Settings com installed_apps ou root_urlconf
    
    Returns:
        AutoRouter configurado com todas as rotas
    
    Examples:
        from strider.config import get_settings
        from strider.urls import autodiscover
        
        settings = get_settings()
        router = autodiscover(settings)
        
        # Configuração simples:
        # installed_apps = ["users", "items"]  # Auto-resolvido para src.apps.{name}
        # ou
        # installed_apps = ["src.apps.users", "myapp.custom"]  # Caminhos completos
    """
    from strider.routing import AutoRouter
    
    url_prefix: str = getattr(settings, "url_prefix", "/api/v1")
    root_urlconf: str | None = getattr(settings, "root_urlconf", None)
    
    # Cria o router principal
    router = AutoRouter(prefix=url_prefix)
    
    # Se root_urlconf definido, carrega de lá (modo Django-like)
    if root_urlconf:
        logger.info(f"Loading URLs from root_urlconf: {root_urlconf}")
        patterns = _load_url_module(root_urlconf)
        
        if patterns is None:
            logger.warning(f"No urlpatterns found in {root_urlconf}")
            return router
        
        logger.info(f"Loaded {len(patterns)} URL patterns from {root_urlconf}")
        
        for pattern in patterns:
            if not isinstance(pattern, URLPattern):
                logger.warning(f"Invalid pattern in {root_urlconf}: {pattern}")
                continue
            
            _register_pattern(router, pattern, root_urlconf)
        
        return router
    
    # Modo auto-discovery: carrega de cada app em installed_apps
    installed_apps: list[str] = getattr(settings, "installed_apps", [])
    
    if not installed_apps:
        logger.warning("No installed_apps configured, skipping URL autodiscovery")
        return router
    
    logger.info(f"Starting URL autodiscovery for {len(installed_apps)} apps")
    
    discovered_count = 0
    
    for app_name in installed_apps:
        # Resolve o caminho completo do app (aceita nomes curtos ou completos)
        url_module = _resolve_app_module(app_name, "urls")
        
        if url_module is None:
            logger.debug(f"Could not resolve app: {app_name}")
            continue
        
        patterns = _load_url_module(url_module)
        
        if patterns is None:
            logger.debug(f"No urls.py found for app: {app_name} (tried: {url_module})")
            continue
        
        logger.info(f"Discovered {len(patterns)} URL patterns from {app_name}")
        
        # Registra cada padrão no router
        for pattern in patterns:
            if not isinstance(pattern, URLPattern):
                logger.warning(f"Invalid pattern in {url_module}: {pattern}")
                continue
            
            _register_pattern(router, pattern, app_name)
            discovered_count += 1
    
    logger.info(f"URL autodiscovery complete: {discovered_count} patterns registered")
    return router


def _register_pattern(
    router: "AutoRouter",
    pattern: URLPattern,
    app_path: str,
    prefix: str = "",
) -> None:
    """
    Registra um padrão de URL no router.
    
    Args:
        router: AutoRouter a registrar
        pattern: URLPattern a registrar
        app_path: Caminho da app (para logging)
        prefix: Prefixo adicional para a rota
    """
    from strider.views import ViewSet, APIView
    
    route = f"{prefix}{pattern.route}".strip("/")
    view = pattern.view
    
    # Se for um include, processa recursivamente
    if isinstance(view, URLInclude):
        included_patterns = _load_url_module(view.module)
        if included_patterns:
            for included in included_patterns:
                if isinstance(included, URLPattern):
                    _register_pattern(router, included, app_path, f"{route}/")
        return
    
    # Determina o tipo de view e registra adequadamente
    if isinstance(view, type):
        if issubclass(view, ViewSet):
            # ViewSet - usa register()
            basename = pattern.kwargs.get("basename") or view.__name__.lower().replace("viewset", "")
            tags = pattern.kwargs.get("tags")
            router.register(
                prefix=route,
                viewset_class=view,
                basename=basename,
                tags=tags,
            )
            logger.debug(f"Registered ViewSet {view.__name__} at /{route}")
            
        elif issubclass(view, APIView):
            # APIView - usa register_view()
            router.register_view(
                path=route,
                view_class=view,
                name=pattern.name,
                **{k: v for k, v in pattern.kwargs.items() if k not in ("basename", "tags")},
            )
            logger.debug(f"Registered APIView {view.__name__} at /{route}")
            
        else:
            # Outras classes - tenta registrar como View
            logger.warning(f"Unknown view type {view.__name__} in {app_path}, skipping")
            
    elif callable(view):
        # Callable direto (função ou método)
        # Adiciona como endpoint simples no router interno
        methods = pattern.kwargs.get("methods", ["GET"])
        router.router.add_api_route(
            path=route,
            endpoint=view,
            methods=methods,
            name=pattern.name,
            **{k: v for k, v in pattern.kwargs.items() if k not in ("methods", "basename", "tags")},
        )
        logger.debug(f"Registered callable at /{route}")
    
    else:
        logger.warning(f"Invalid view type for route /{route}: {type(view)}")


# Variável global para cache do router descoberto
_discovered_router: "AutoRouter | None" = None


def get_discovered_router(settings: Any | None = None) -> "AutoRouter":
    """
    Retorna o router descoberto, ou descobre se ainda não foi feito.
    
    Args:
        settings: Instância de Settings (opcional, usa get_settings() se não fornecido)
    
    Returns:
        AutoRouter com todas as rotas descobertas
    """
    global _discovered_router
    
    if _discovered_router is not None:
        return _discovered_router
    
    if settings is None:
        from strider.config import get_settings
        settings = get_settings()
    
    _discovered_router = autodiscover(settings)
    return _discovered_router


def clear_cache() -> None:
    """
    Limpa o cache do router descoberto.
    
    Útil para testes ou quando as configurações mudam.
    """
    global _discovered_router
    _discovered_router = None
    logger.debug("URL discovery cache cleared")
