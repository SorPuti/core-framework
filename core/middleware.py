"""
Sistema de Middleware Plugável - Django-style.

Permite configurar middlewares de forma declarativa, similar ao MIDDLEWARE do Django.

Uso:
    # Em settings ou core.toml
    MIDDLEWARE = [
        "core.auth.AuthenticationMiddleware",
        "core.tenancy.TenantMiddleware",
        "myapp.middleware.CustomMiddleware",
    ]
    
    # Ou via configuração
    from core.middleware import configure_middleware
    
    configure_middleware([
        "core.auth.AuthenticationMiddleware",
        ("myapp.middleware.RateLimitMiddleware", {"requests_per_minute": 60}),
    ])

O framework carrega e aplica os middlewares na ordem especificada.

Criando middlewares customizados:
    from core.middleware import BaseMiddleware
    
    class MyMiddleware(BaseMiddleware):
        async def before_request(self, request):
            # Executado antes da view
            request.state.custom_data = "hello"
        
        async def after_request(self, request, response):
            # Executado depois da view
            response.headers["X-Custom"] = "value"
            return response
"""

from __future__ import annotations

import importlib
import warnings
from abc import ABC
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

if TYPE_CHECKING:
    from collections.abc import Callable, Awaitable
    from fastapi import FastAPI


# =============================================================================
# Base Middleware Class
# =============================================================================

class BaseMiddleware(BaseHTTPMiddleware):
    """
    Classe base para criar middlewares de forma simplificada.
    
    Herde desta classe e implemente os métodos que precisar:
    
    - before_request(request): Executado antes da view
    - after_request(request, response): Executado depois da view
    - on_error(request, exc): Executado quando ocorre exceção
    
    Exemplo:
        from core.middleware import BaseMiddleware
        
        class TimingMiddleware(BaseMiddleware):
            '''Mede tempo de execução das requests.'''
            
            async def before_request(self, request):
                import time
                request.state.start_time = time.time()
            
            async def after_request(self, request, response):
                import time
                duration = time.time() - request.state.start_time
                response.headers["X-Response-Time"] = f"{duration:.3f}s"
                return response
        
        class AuthMiddleware(BaseMiddleware):
            '''Autentica usuários.'''
            
            def __init__(self, app, user_model=None):
                super().__init__(app)
                self.user_model = user_model
            
            async def before_request(self, request):
                request.state.user = await self.authenticate(request)
    """
    
    # Nome legível do middleware (para logs e debug)
    name: str = "BaseMiddleware"
    
    # Ordem de execução (menor = executa primeiro)
    # Middlewares com mesma ordem executam na ordem de registro
    order: int = 100
    
    # Paths para ignorar (não executar middleware)
    exclude_paths: list[str] = []
    
    # Paths para incluir (executar apenas nesses)
    # Se vazio, executa em todos (exceto exclude_paths)
    include_paths: list[str] = []
    
    def __init__(
        self,
        app: "Callable[[Request], Awaitable[Response]]",
        **kwargs: Any,
    ) -> None:
        """
        Inicializa o middleware.
        
        Args:
            app: Próximo app/middleware na cadeia
            **kwargs: Configurações customizadas
        """
        super().__init__(app)
        
        # Aplica kwargs como atributos
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    async def dispatch(
        self,
        request: Request,
        call_next: "Callable[[Request], Awaitable[Response]]",
    ) -> Response:
        """
        Processa a request através do middleware.
        
        Não sobrescreva este método diretamente.
        Use before_request, after_request e on_error.
        """
        # Verifica se deve processar esta request
        if not self._should_process(request.url.path):
            return await call_next(request)
        
        try:
            # Before request hook
            result = await self.before_request(request)
            
            # Se before_request retornar Response, use-a diretamente
            if isinstance(result, Response):
                return result
            
            # Chama próximo middleware/view
            response = await call_next(request)
            
            # After request hook
            response = await self.after_request(request, response)
            
            return response
            
        except Exception as exc:
            # Error hook
            error_response = await self.on_error(request, exc)
            if error_response is not None:
                return error_response
            raise
    
    def _should_process(self, path: str) -> bool:
        """Verifica se deve processar esta path."""
        # Se include_paths definido, só processa esses
        if self.include_paths:
            return any(path.startswith(p) for p in self.include_paths)
        
        # Verifica exclude_paths
        if self.exclude_paths:
            return not any(path.startswith(p) for p in self.exclude_paths)
        
        return True
    
    async def before_request(self, request: Request) -> Response | None:
        """
        Hook executado antes da view.
        
        Args:
            request: Request objeto
            
        Returns:
            None para continuar, ou Response para retornar diretamente
        """
        pass
    
    async def after_request(self, request: Request, response: Response) -> Response:
        """
        Hook executado depois da view.
        
        Args:
            request: Request objeto
            response: Response da view
            
        Returns:
            Response (pode ser modificada)
        """
        return response
    
    async def on_error(self, request: Request, exc: Exception) -> Response | None:
        """
        Hook executado quando ocorre exceção.
        
        Args:
            request: Request objeto
            exc: Exceção que ocorreu
            
        Returns:
            Response para retornar, ou None para re-raise
        """
        return None


# =============================================================================
# Middleware Registry
# =============================================================================

@dataclass
class MiddlewareConfig:
    """Configuração de um middleware."""
    
    # Classe ou path string do middleware
    middleware: str | type
    
    # Kwargs para passar ao middleware
    kwargs: dict[str, Any] = field(default_factory=dict)
    
    # Se está habilitado
    enabled: bool = True
    
    # Nome para identificação (auto-gerado se None)
    name: str | None = None
    
    def __post_init__(self):
        if self.name is None:
            if isinstance(self.middleware, str):
                self.name = self.middleware.split(".")[-1]
            else:
                self.name = self.middleware.__name__


# Registry global de middlewares configurados
_middleware_registry: list[MiddlewareConfig] = []

# Middlewares built-in disponíveis (atalhos)
_builtin_middlewares: dict[str, str] = {
    # Auth
    "auth": "core.auth.middleware.AuthenticationMiddleware",
    "authentication": "core.auth.middleware.AuthenticationMiddleware",
    "optional_auth": "core.auth.middleware.OptionalAuthenticationMiddleware",
    
    # Tenancy
    "tenant": "core.tenancy.TenantMiddleware",
    "tenancy": "core.tenancy.TenantMiddleware",
    
    # Common
    "cors": "starlette.middleware.cors.CORSMiddleware",
    "gzip": "starlette.middleware.gzip.GZipMiddleware",
    "https_redirect": "starlette.middleware.httpsredirect.HTTPSRedirectMiddleware",
    "trusted_host": "starlette.middleware.trustedhost.TrustedHostMiddleware",
}


def _resolve_middleware_class(middleware: str | type) -> type:
    """
    Resolve middleware string para classe.
    
    Args:
        middleware: String path ou classe direta
        
    Returns:
        Classe do middleware
        
    Raises:
        ImportError: Se não encontrar
    """
    if isinstance(middleware, type):
        return middleware
    
    # Verifica se é atalho built-in
    if middleware in _builtin_middlewares:
        middleware = _builtin_middlewares[middleware]
    
    # Importa dinamicamente
    try:
        module_path, class_name = middleware.rsplit(".", 1)
        module = importlib.import_module(module_path)
        return getattr(module, class_name)
    except (ValueError, ImportError, AttributeError) as e:
        raise ImportError(
            f"Could not import middleware '{middleware}'. "
            f"Make sure the module and class exist. Error: {e}"
        )


def register_middleware(
    middleware: str | type,
    kwargs: dict[str, Any] | None = None,
    enabled: bool = True,
    name: str | None = None,
) -> None:
    """
    Registra um middleware no registry global.
    
    Args:
        middleware: Classe ou path string do middleware
        kwargs: Argumentos para o middleware
        enabled: Se está habilitado
        name: Nome opcional
        
    Example:
        register_middleware("core.auth.AuthenticationMiddleware")
        register_middleware(MyMiddleware, {"option": "value"})
    """
    config = MiddlewareConfig(
        middleware=middleware,
        kwargs=kwargs or {},
        enabled=enabled,
        name=name,
    )
    _middleware_registry.append(config)


def unregister_middleware(name_or_class: str | type) -> bool:
    """
    Remove um middleware do registry.
    
    Args:
        name_or_class: Nome ou classe do middleware
        
    Returns:
        True se removido, False se não encontrado
    """
    global _middleware_registry
    
    for i, config in enumerate(_middleware_registry):
        if config.name == name_or_class or config.middleware == name_or_class:
            _middleware_registry.pop(i)
            return True
    
    return False


def get_registered_middlewares() -> list[MiddlewareConfig]:
    """Retorna lista de middlewares registrados."""
    return _middleware_registry.copy()


def clear_middleware_registry() -> None:
    """Limpa o registry de middlewares."""
    global _middleware_registry
    _middleware_registry = []


# =============================================================================
# Configuration Functions
# =============================================================================

def configure_middleware(
    middlewares: list[str | type | tuple[str | type, dict[str, Any]]],
    clear_existing: bool = True,
) -> None:
    """
    Configura middlewares de forma declarativa, estilo Django.
    
    Args:
        middlewares: Lista de middlewares para registrar
        clear_existing: Se True, limpa registry antes
        
    Example:
        configure_middleware([
            # String path
            "core.auth.AuthenticationMiddleware",
            
            # Com kwargs
            ("myapp.RateLimitMiddleware", {"requests_per_minute": 60}),
            
            # Classe direta
            MyCustomMiddleware,
            
            # Built-in shortcut
            "auth",  # = core.auth.AuthenticationMiddleware
            
            # Built-in com kwargs
            ("gzip", {"minimum_size": 500}),
        ])
    """
    if clear_existing:
        clear_middleware_registry()
    
    for item in middlewares:
        if isinstance(item, tuple):
            middleware, kwargs = item
            register_middleware(middleware, kwargs)
        else:
            register_middleware(item)


def apply_middlewares(app: "FastAPI") -> "FastAPI":
    """
    Aplica todos os middlewares registrados ao app.
    
    Args:
        app: FastAPI app
        
    Returns:
        App com middlewares aplicados
    """
    # Ordena por prioridade (se BaseMiddleware)
    configs = get_registered_middlewares()
    
    # Aplica em ordem reversa (primeiro registrado = mais externo)
    for config in reversed(configs):
        if not config.enabled:
            continue
        
        try:
            middleware_class = _resolve_middleware_class(config.middleware)
            app.add_middleware(middleware_class, **config.kwargs)
        except ImportError as e:
            warnings.warn(f"Failed to load middleware: {e}", RuntimeWarning)
    
    return app


# =============================================================================
# Middleware Stack Info (Debug/Introspection)
# =============================================================================

def get_middleware_stack_info(app: Any) -> list[dict[str, Any]]:
    """
    Retorna informações sobre a stack de middlewares.
    
    Útil para debug e introspection.
    
    Args:
        app: FastAPI ou CoreApp
        
    Returns:
        Lista com info de cada middleware
    """
    info = []
    
    # Obtém FastAPI app se CoreApp
    if hasattr(app, "app"):
        app = app.app
    
    # Percorre middleware stack
    current = getattr(app, "middleware_stack", None)
    
    while current is not None:
        middleware_info = {
            "class": type(current).__name__,
            "module": type(current).__module__,
        }
        
        # Tenta obter atributos úteis
        if hasattr(current, "name"):
            middleware_info["name"] = current.name
        if hasattr(current, "order"):
            middleware_info["order"] = current.order
        if hasattr(current, "exclude_paths"):
            middleware_info["exclude_paths"] = current.exclude_paths
        
        info.append(middleware_info)
        
        # Próximo na stack
        current = getattr(current, "app", None)
        
        # Para quando chegar ao app final
        if not hasattr(current, "middleware_stack") and not isinstance(current, BaseHTTPMiddleware):
            if current is not None:
                info.append({
                    "class": type(current).__name__,
                    "module": type(current).__module__,
                    "is_app": True,
                })
            break
    
    return info


def print_middleware_stack(app: Any) -> None:
    """
    Imprime a stack de middlewares formatada.
    
    Args:
        app: FastAPI ou CoreApp
    """
    info = get_middleware_stack_info(app)
    
    print("\n📦 Middleware Stack:")
    print("=" * 50)
    
    for i, mw in enumerate(info):
        is_app = mw.get("is_app", False)
        prefix = "   └─ " if is_app else f"   {i+1}. "
        name = mw.get("name", mw["class"])
        
        if is_app:
            print(f"{prefix}[APP] {name}")
        else:
            print(f"{prefix}{name}")
            if "exclude_paths" in mw and mw["exclude_paths"]:
                print(f"        exclude: {mw['exclude_paths']}")
    
    print("=" * 50)


# =============================================================================
# Pre-built Middleware Classes
# =============================================================================

class TimingMiddleware(BaseMiddleware):
    """
    Middleware que mede tempo de resposta.
    
    Adiciona header X-Response-Time com duração em segundos.
    
    Usage:
        configure_middleware([
            "core.middleware.TimingMiddleware",
        ])
    """
    
    name = "TimingMiddleware"
    order = 10  # Executa cedo para medir tempo total
    
    async def before_request(self, request: Request) -> None:
        import time
        request.state._timing_start = time.perf_counter()
    
    async def after_request(self, request: Request, response: Response) -> Response:
        import time
        start = getattr(request.state, "_timing_start", None)
        if start is not None:
            duration = time.perf_counter() - start
            response.headers["X-Response-Time"] = f"{duration:.4f}s"
        return response


class RequestIDMiddleware(BaseMiddleware):
    """
    Middleware que adiciona ID único a cada request.
    
    Útil para tracing e logs.
    
    Usage:
        configure_middleware([
            "core.middleware.RequestIDMiddleware",
        ])
    """
    
    name = "RequestIDMiddleware"
    order = 5  # Executa muito cedo
    
    # Nome do header para ID
    header_name: str = "X-Request-ID"
    
    async def before_request(self, request: Request) -> None:
        import uuid
        
        # Usa ID do header se fornecido, senão gera novo
        request_id = request.headers.get(self.header_name)
        if not request_id:
            request_id = str(uuid.uuid4())
        
        request.state.request_id = request_id
    
    async def after_request(self, request: Request, response: Response) -> Response:
        request_id = getattr(request.state, "request_id", None)
        if request_id:
            response.headers[self.header_name] = request_id
        return response


class LoggingMiddleware(BaseMiddleware):
    """
    Middleware que loga requests.
    
    Usage:
        configure_middleware([
            ("core.middleware.LoggingMiddleware", {"log_body": False}),
        ])
    """
    
    name = "LoggingMiddleware"
    order = 20
    
    # Se deve logar body da request
    log_body: bool = False
    
    # Se deve logar headers
    log_headers: bool = False
    
    # Logger name
    logger_name: str = "core.requests"
    
    async def before_request(self, request: Request) -> None:
        import logging
        import time
        
        request.state._log_start = time.perf_counter()
        
        logger = logging.getLogger(self.logger_name)
        
        msg = f"→ {request.method} {request.url.path}"
        if request.query_params:
            msg += f"?{request.query_params}"
        
        logger.info(msg)
        
        if self.log_headers:
            logger.debug(f"  Headers: {dict(request.headers)}")
    
    async def after_request(self, request: Request, response: Response) -> Response:
        import logging
        import time
        
        logger = logging.getLogger(self.logger_name)
        
        start = getattr(request.state, "_log_start", None)
        duration = ""
        if start:
            duration = f" [{time.perf_counter() - start:.3f}s]"
        
        logger.info(f"← {response.status_code}{duration}")
        
        return response
    
    async def on_error(self, request: Request, exc: Exception) -> None:
        import logging
        
        logger = logging.getLogger(self.logger_name)
        logger.error(f"✗ Error: {type(exc).__name__}: {exc}")
        
        return None  # Re-raise


class MaintenanceModeMiddleware(BaseMiddleware):
    """
    Middleware para modo de manutenção.
    
    Retorna 503 para todas as requests quando ativado.
    
    Usage:
        configure_middleware([
            ("core.middleware.MaintenanceModeMiddleware", {
                "enabled": False,  # Ative quando precisar
                "message": "Site em manutenção",
                "allowed_ips": ["127.0.0.1"],
            }),
        ])
    """
    
    name = "MaintenanceModeMiddleware"
    order = 1  # Executa primeiro
    
    # Se modo manutenção está ativo
    maintenance_enabled: bool = False
    
    # Mensagem de manutenção
    message: str = "Service temporarily unavailable for maintenance"
    
    # IPs permitidos mesmo em manutenção
    allowed_ips: list[str] = []
    
    # Paths permitidos mesmo em manutenção (ex: /health)
    allowed_paths: list[str] = ["/health", "/healthz"]
    
    async def before_request(self, request: Request) -> Response | None:
        if not self.maintenance_enabled:
            return None
        
        # Verifica paths permitidos
        if any(request.url.path.startswith(p) for p in self.allowed_paths):
            return None
        
        # Verifica IPs permitidos
        client_ip = request.client.host if request.client else None
        if client_ip in self.allowed_ips:
            return None
        
        # Retorna 503
        from starlette.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={
                "detail": self.message,
                "code": "maintenance_mode",
            },
        )


class SecurityHeadersMiddleware(BaseMiddleware):
    """
    Middleware que adiciona headers de segurança.
    
    Usage:
        configure_middleware([
            "core.middleware.SecurityHeadersMiddleware",
        ])
    """
    
    name = "SecurityHeadersMiddleware"
    order = 15
    
    # Headers a adicionar
    headers: dict[str, str] = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
    }
    
    # Se deve adicionar HSTS (apenas para HTTPS)
    enable_hsts: bool = False
    hsts_max_age: int = 31536000  # 1 ano
    
    async def after_request(self, request: Request, response: Response) -> Response:
        for header, value in self.headers.items():
            response.headers[header] = value
        
        # HSTS apenas para HTTPS
        if self.enable_hsts and request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = f"max-age={self.hsts_max_age}"
        
        return response


# =============================================================================
# Built-in middleware shortcuts - update registry
# =============================================================================

_builtin_middlewares.update({
    # Pre-built middlewares from this module
    "timing": "core.middleware.TimingMiddleware",
    "request_id": "core.middleware.RequestIDMiddleware",
    "logging": "core.middleware.LoggingMiddleware",
    "maintenance": "core.middleware.MaintenanceModeMiddleware",
    "security_headers": "core.middleware.SecurityHeadersMiddleware",
    # Auth middlewares (ensure they're registered even if initial dict failed)
    "auth": "core.auth.middleware.AuthenticationMiddleware",
    "authentication": "core.auth.middleware.AuthenticationMiddleware",
    "optional_auth": "core.auth.middleware.OptionalAuthenticationMiddleware",
})


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Base class
    "BaseMiddleware",
    
    # Configuration
    "MiddlewareConfig",
    "configure_middleware",
    "register_middleware",
    "unregister_middleware",
    "get_registered_middlewares",
    "clear_middleware_registry",
    "apply_middlewares",
    
    # Debug
    "get_middleware_stack_info",
    "print_middleware_stack",
    
    # Pre-built middlewares
    "TimingMiddleware",
    "RequestIDMiddleware",
    "LoggingMiddleware",
    "MaintenanceModeMiddleware",
    "SecurityHeadersMiddleware",
]
