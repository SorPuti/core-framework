"""
Sistema de Middleware Plugável - Django-style.
"""
from __future__ import annotations

import importlib
import time
import uuid
import warnings
from abc import ABC
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send, Message
import logging

logger = logging.getLogger("core.middleware")

if TYPE_CHECKING:
    from collections.abc import Callable, Awaitable, MutableSequence
    from fastapi import FastAPI


# =============================================================================
# Pure ASGI Middleware Base (RECOMMENDED — zero overhead)
# =============================================================================

class ASGIMiddleware:
    """
    Base para middlewares Pure ASGI — sem overhead de BaseHTTPMiddleware.
    
    Vantagens sobre BaseMiddleware:
    - Não consome body da request em memória
    - Compatível com StreamingResponse
    - Compatível com BackgroundTask
    - ~10x menos overhead por request
    
    Herde desta classe e implemente os hooks que precisar:
    
    - before_request(scope, request): Antes de processar a request
    - after_response(scope, request, status_code, response_headers): Após enviar response
    - on_error(scope, request, exc): Quando ocorre exceção
    
    Exemplo:
        class TimingMiddleware(ASGIMiddleware):
            async def before_request(self, scope, request):
                scope["state"]["start_time"] = time.perf_counter()
            
            async def after_response(self, scope, request, status_code, response_headers):
                start = scope["state"].get("start_time")
                if start:
                    duration = time.perf_counter() - start
                    response_headers.append(
                        (b"x-response-time", f"{duration:.4f}s".encode())
                    )
    """
    
    # Nome legível do middleware (para logs e debug)
    name: str = "ASGIMiddleware"
    
    # Ordem de execução (menor = executa primeiro)
    order: int = 100
    
    # Paths para ignorar
    exclude_paths: list[str] = []
    
    # Paths para incluir (se vazio, inclui todos)
    include_paths: list[str] = []
    
    def __init__(self, app: ASGIApp, **kwargs: Any) -> None:
        self.app = app
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        
        if scope["type"] == "websocket":
            await self.app(scope, receive, send)
            return
        
        # Check path filtering
        path = scope.get("path", "")
        if not self._should_process(path):
            await self.app(scope, receive, send)
            return
        
        # Ensure scope has state dict
        if "state" not in scope:
            scope["state"] = {}
        
        request = Request(scope, receive, send)
        
        # Before request hook
        try:
            result = await self.before_request(scope, request)
            if isinstance(result, Response):
                await result(scope, receive, send)
                return
        except Exception as exc:
            error_response = await self.on_error(scope, request, exc)
            if error_response is not None:
                await error_response(scope, receive, send)
                return
            raise
        
        # Wrap send to capture response headers for after_response
        status_code = 200
        response_headers: list[tuple[bytes, bytes]] = []
        response_started = False
        
        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, response_headers, response_started
            
            if message["type"] == "http.response.start":
                status_code = message.get("status", 200)
                response_headers = list(message.get("headers", []))
                
                # Call after_response hook (can modify headers)
                try:
                    await self.after_response(scope, request, status_code, response_headers)
                except Exception:
                    pass  # Don't break response on after_response errors
                
                message = {
                    "type": "http.response.start",
                    "status": status_code,
                    "headers": response_headers,
                }
                response_started = True
            
            await send(message)
        
        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            if not response_started:
                error_response = await self.on_error(scope, request, exc)
                if error_response is not None:
                    await error_response(scope, receive, send)
                    return
            raise
    
    def _should_process(self, path: str) -> bool:
        """Verifica se deve processar esta path."""
        if self.include_paths:
            return any(path.startswith(p) for p in self.include_paths)
        if self.exclude_paths:
            return not any(path.startswith(p) for p in self.exclude_paths)
        return True
    
    async def before_request(self, scope: Scope, request: Request) -> Response | None:
        """Hook executado antes da request. Retorne Response para short-circuit."""
        pass
    
    async def after_response(
        self,
        scope: Scope,
        request: Request,
        status_code: int,
        response_headers: list[tuple[bytes, bytes]],
    ) -> None:
        """Hook executado após a response (pode modificar headers in-place)."""
        pass
    
    async def on_error(self, scope: Scope, request: Request, exc: Exception) -> Response | None:
        """Hook executado quando ocorre exceção. Retorne Response ou None para re-raise."""
        return None


# =============================================================================
# Legacy Base Middleware Class (BaseHTTPMiddleware wrapper — DEPRECATED)
# =============================================================================

class BaseMiddleware(BaseHTTPMiddleware):
    """
    Classe base legada para middlewares (usa BaseHTTPMiddleware internamente).
    
    DEPRECATED: Prefira ASGIMiddleware para novos middlewares.
    BaseHTTPMiddleware consome o body inteiro da request em memória
    e é incompatível com StreamingResponse e BackgroundTask.
    
    Herde desta classe e implemente os métodos que precisar:
    
    - before_request(request): Executado antes da view
    - after_request(request, response): Executado depois da view
    - on_error(request, exc): Executado quando ocorre exceção
    """
    
    name: str = "BaseMiddleware"
    order: int = 100
    exclude_paths: list[str] = []
    include_paths: list[str] = []
    
    def __init__(
        self,
        app: "Callable[[Request], Awaitable[Response]]",
        **kwargs: Any,
    ) -> None:
        super().__init__(app)
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    async def dispatch(
        self,
        request: Request,
        call_next: "Callable[[Request], Awaitable[Response]]",
    ) -> Response:
        if not self._should_process(request.url.path):
            try:
                return await call_next(request)
            except Exception as exc:
                return self._fallback_error_response(request, exc)
        
        try:
            result = await self.before_request(request)
            if isinstance(result, Response):
                return result
            
            response = await call_next(request)
            response = await self.after_request(request, response)
            return response
            
        except Exception as exc:
            error_response = await self.on_error(request, exc)
            if error_response is not None:
                return error_response
            # Fallback: SEMPRE retorna uma resposta, nunca deixa vazar
            return self._fallback_error_response(request, exc)
    
    def _fallback_error_response(self, request: Request, exc: Exception) -> Response:
        """Resposta de erro garantida quando on_error não trata."""
        from starlette.responses import JSONResponse
        import traceback
        
        logger.exception(f"Unhandled error in {self.name}: {exc}")
        
        return JSONResponse(
            status_code=500,
            content={
                "detail": str(exc) or "Internal server error",
                "type": type(exc).__name__,
                "middleware": self.name,
                "path": str(request.url.path),
            },
        )
    
    def _should_process(self, path: str) -> bool:
        if self.include_paths:
            return any(path.startswith(p) for p in self.include_paths)
        if self.exclude_paths:
            return not any(path.startswith(p) for p in self.exclude_paths)
        return True
    
    async def before_request(self, request: Request) -> Response | None:
        pass
    
    async def after_request(self, request: Request, response: Response) -> Response:
        return response
    
    async def on_error(self, request: Request, exc: Exception) -> Response | None:
        return None


# =============================================================================
# Middleware Registry
# =============================================================================

@dataclass
class MiddlewareConfig:
    """Configuração de um middleware."""
    middleware: str | type
    kwargs: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
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
    
    # Pre-built (this module)
    "timing": "core.middleware.TimingMiddleware",
    "request_id": "core.middleware.RequestIDMiddleware",
    "logging": "core.middleware.LoggingMiddleware",
    "maintenance": "core.middleware.MaintenanceModeMiddleware",
    "security_headers": "core.middleware.SecurityHeadersMiddleware",
    "rate_limit": "core.middleware.RateLimitMiddleware",
    "content_length_limit": "core.middleware.ContentLengthLimitMiddleware",
}


def _resolve_middleware_class(middleware: str | type) -> type:
    """Resolve middleware string para classe."""
    if isinstance(middleware, type):
        return middleware
    
    if middleware in _builtin_middlewares:
        middleware = _builtin_middlewares[middleware]
    
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
    """Registra um middleware no registry global."""
    config = MiddlewareConfig(
        middleware=middleware,
        kwargs=kwargs or {},
        enabled=enabled,
        name=name,
    )
    _middleware_registry.append(config)


def unregister_middleware(name_or_class: str | type) -> bool:
    """Remove um middleware do registry."""
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
    """Configura middlewares de forma declarativa, estilo Django."""
    if clear_existing:
        clear_middleware_registry()
    
    for item in middlewares:
        if isinstance(item, tuple):
            middleware, kwargs = item
            register_middleware(middleware, kwargs)
        else:
            register_middleware(item)


def apply_middlewares(app: "FastAPI") -> "FastAPI":
    """Aplica todos os middlewares registrados ao app."""
    configs = get_registered_middlewares()
    
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
    """Retorna informações sobre a stack de middlewares."""
    info = []
    
    if hasattr(app, "app"):
        app = app.app
    
    current = getattr(app, "middleware_stack", None)
    
    while current is not None:
        middleware_info = {
            "class": type(current).__name__,
            "module": type(current).__module__,
        }
        
        if hasattr(current, "name"):
            middleware_info["name"] = current.name
        if hasattr(current, "order"):
            middleware_info["order"] = current.order
        if hasattr(current, "exclude_paths"):
            middleware_info["exclude_paths"] = current.exclude_paths
        
        info.append(middleware_info)
        current = getattr(current, "app", None)
        
        if not hasattr(current, "middleware_stack") and not isinstance(current, (BaseHTTPMiddleware, ASGIMiddleware)):
            if current is not None:
                info.append({
                    "class": type(current).__name__,
                    "module": type(current).__module__,
                    "is_app": True,
                })
            break
    
    return info


def print_middleware_stack(app: Any) -> None:
    """Imprime a stack de middlewares formatada."""
    info = get_middleware_stack_info(app)
    
    print("\nMiddleware Stack:")
    print("=" * 50)
    
    for i, mw in enumerate(info):
        is_app = mw.get("is_app", False)
        prefix = "   -> " if is_app else f"   {i+1}. "
        name = mw.get("name", mw["class"])
        
        if is_app:
            print(f"{prefix}[APP] {name}")
        else:
            print(f"{prefix}{name}")
            if "exclude_paths" in mw and mw["exclude_paths"]:
                print(f"        exclude: {mw['exclude_paths']}")
    
    print("=" * 50)


# =============================================================================
# Pre-built Middleware Classes (Pure ASGI)
# =============================================================================

class TimingMiddleware(ASGIMiddleware):
    """
    Middleware que mede tempo de resposta.
    Adiciona header X-Response-Time com duração em segundos.
    """
    
    name = "TimingMiddleware"
    order = 10
    
    async def before_request(self, scope: Scope, request: Request) -> None:
        scope["state"]["_timing_start"] = time.perf_counter()
    
    async def after_response(
        self,
        scope: Scope,
        request: Request,
        status_code: int,
        response_headers: list[tuple[bytes, bytes]],
    ) -> None:
        start = scope["state"].get("_timing_start")
        if start is not None:
            duration = time.perf_counter() - start
            response_headers.append(
                (b"x-response-time", f"{duration:.4f}s".encode())
            )


class RequestIDMiddleware(ASGIMiddleware):
    """
    Middleware que adiciona ID único a cada request.
    Útil para tracing e logs.
    """
    
    name = "RequestIDMiddleware"
    order = 5
    header_name: str = "X-Request-ID"
    
    async def before_request(self, scope: Scope, request: Request) -> None:
        request_id = request.headers.get(self.header_name)
        if not request_id:
            request_id = str(uuid.uuid4())
        scope["state"]["request_id"] = request_id
        # Also set on request.state for backward compat
        request.state.request_id = request_id
    
    async def after_response(
        self,
        scope: Scope,
        request: Request,
        status_code: int,
        response_headers: list[tuple[bytes, bytes]],
    ) -> None:
        request_id = scope["state"].get("request_id")
        if request_id:
            header_name_bytes = self.header_name.lower().encode()
            response_headers.append((header_name_bytes, request_id.encode()))


class LoggingMiddleware(ASGIMiddleware):
    """
    Middleware que loga requests.
    """
    
    name = "LoggingMiddleware"
    order = 20
    log_body: bool = False
    log_headers: bool = False
    logger_name: str = "core.requests"
    
    async def before_request(self, scope: Scope, request: Request) -> None:
        import logging
        scope["state"]["_log_start"] = time.perf_counter()
        
        logger = logging.getLogger(self.logger_name)
        msg = f"-> {request.method} {request.url.path}"
        if request.query_params:
            msg += f"?{request.query_params}"
        logger.info(msg)
        
        if self.log_headers:
            logger.debug(f"  Headers: {dict(request.headers)}")
    
    async def after_response(
        self,
        scope: Scope,
        request: Request,
        status_code: int,
        response_headers: list[tuple[bytes, bytes]],
    ) -> None:
        import logging
        logger = logging.getLogger(self.logger_name)
        
        start = scope["state"].get("_log_start")
        duration = ""
        if start:
            duration = f" [{time.perf_counter() - start:.3f}s]"
        
        logger.info(f"<- {status_code}{duration}")
    
    async def on_error(self, scope: Scope, request: Request, exc: Exception) -> None:
        import logging
        logger = logging.getLogger(self.logger_name)
        logger.error(f"Error: {type(exc).__name__}: {exc}")
        return None


class MaintenanceModeMiddleware(ASGIMiddleware):
    """
    Middleware para modo de manutenção.
    Retorna 503 para todas as requests quando ativado.
    """
    
    name = "MaintenanceModeMiddleware"
    order = 1
    maintenance_enabled: bool = False
    message: str = "Service temporarily unavailable for maintenance"
    allowed_ips: list[str] = []
    allowed_paths: list[str] = ["/health", "/healthz", "/readyz"]
    
    async def before_request(self, scope: Scope, request: Request) -> Response | None:
        if not self.maintenance_enabled:
            return None
        
        if any(request.url.path.startswith(p) for p in self.allowed_paths):
            return None
        
        client_ip = request.client.host if request.client else None
        if client_ip in self.allowed_ips:
            return None
        
        from starlette.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={
                "detail": self.message,
                "code": "maintenance_mode",
            },
        )


class SecurityHeadersMiddleware(ASGIMiddleware):
    """
    Middleware que adiciona headers de segurança (OWASP).
    Suporta CSP (Content-Security-Policy) e HSTS configuráveis via Settings.
    """
    
    name = "SecurityHeadersMiddleware"
    order = 15
    
    # Default security headers (best practice)
    headers: dict[str, str] = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    }
    
    enable_hsts: bool = False
    hsts_max_age: int = 31536000  # 1 ano
    content_security_policy: str | None = None  # CSP header value; None = não envia
    
    def __init__(self, app: ASGIApp, **kwargs: Any) -> None:
        super().__init__(app, **kwargs)
        if "content_security_policy" not in kwargs or "enable_hsts" not in kwargs:
            try:
                from core.config import get_settings
                s = get_settings()
                if "content_security_policy" not in kwargs:
                    self.content_security_policy = getattr(s, "security_csp", None) or self.content_security_policy
                if "enable_hsts" not in kwargs:
                    self.enable_hsts = getattr(s, "security_headers_hsts", self.enable_hsts)
            except Exception:
                pass
    
    async def after_response(
        self,
        scope: Scope,
        request: Request,
        status_code: int,
        response_headers: list[tuple[bytes, bytes]],
    ) -> None:
        for header, value in self.headers.items():
            response_headers.append((header.lower().encode(), value.encode()))
        
        if self.content_security_policy:
            response_headers.append(
                (b"content-security-policy", self.content_security_policy.encode())
            )
        
        if self.enable_hsts and scope.get("scheme") == "https":
            response_headers.append(
                (b"strict-transport-security", f"max-age={self.hsts_max_age}".encode())
            )


class RateLimitMiddleware(ASGIMiddleware):
    """
    Rate limiting por IP (in-memory). Retorna 429 quando exceder o limite.
    Configurável via kwargs ou Settings (rate_limit_requests, rate_limit_window_seconds).
    """
    
    name = "RateLimitMiddleware"
    order = 2  # cedo na stack
    
    requests_per_window: int = 100
    window_seconds: int = 60
    exclude_paths: list[str] = ["/healthz", "/readyz", "/docs", "/redoc", "/openapi.json"]
    
    def __init__(self, app: ASGIApp, **kwargs: Any) -> None:
        super().__init__(app, **kwargs)
        try:
            from core.config import get_settings
            s = get_settings()
            self.requests_per_window = getattr(s, "rate_limit_requests", self.requests_per_window)
            self.window_seconds = getattr(s, "rate_limit_window_seconds", self.window_seconds)
            self.exclude_paths = getattr(s, "rate_limit_exclude_paths", self.exclude_paths) or self.exclude_paths
        except Exception:
            pass
        self._store: dict[str, list[float]] = {}
        import threading
        self._lock = threading.Lock()
    
    def _get_client_key(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host or "unknown"
        return "unknown"
    
    def _is_over_limit(self, key: str) -> bool:
        now = time.time()
        cutoff = now - self.window_seconds
        with self._lock:
            if key not in self._store:
                self._store[key] = []
            times = self._store[key]
            times[:] = [t for t in times if t > cutoff]
            if len(times) >= self.requests_per_window:
                return True
            times.append(now)
        return False
    
    async def before_request(self, scope: Scope, request: Request) -> Response | None:
        if not self._should_process(request.url.path):
            return None
        if self._is_over_limit(self._get_client_key(request)):
            from starlette.responses import JSONResponse
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too Many Requests",
                    "code": "rate_limit_exceeded",
                    "retry_after": self.window_seconds,
                },
                headers=[(b"retry-after", str(self.window_seconds).encode())],
            )
        return None


class ContentLengthLimitMiddleware(ASGIMiddleware):
    """
    Rejeita requests com Content-Length acima do limite (413 Payload Too Large).
    Usa max_request_size dos Settings quando não passado por kwargs.
    """
    
    name = "ContentLengthLimitMiddleware"
    order = 3
    
    max_bytes: int = 10 * 1024 * 1024  # 10MB
    
    def __init__(self, app: ASGIApp, **kwargs: Any) -> None:
        super().__init__(app, **kwargs)
        if "max_bytes" not in kwargs:
            try:
                from core.config import get_settings
                self.max_bytes = getattr(get_settings(), "max_request_size", self.max_bytes)
            except Exception:
                pass
    
    async def before_request(self, scope: Scope, request: Request) -> Response | None:
        if not self._should_process(request.url.path):
            return None
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self.max_bytes:
                    from starlette.responses import JSONResponse
                    return JSONResponse(
                        status_code=413,
                        content={
                            "detail": "Request body too large",
                            "code": "payload_too_large",
                            "max_bytes": self.max_bytes,
                        },
                    )
            except ValueError:
                pass
        return None


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Pure ASGI base (recommended)
    "ASGIMiddleware",
    
    # Legacy base (deprecated)
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
    
    # Pre-built middlewares (Pure ASGI)
    "TimingMiddleware",
    "RequestIDMiddleware",
    "LoggingMiddleware",
    "MaintenanceModeMiddleware",
    "SecurityHeadersMiddleware",
    "RateLimitMiddleware",
    "ContentLengthLimitMiddleware",
]
