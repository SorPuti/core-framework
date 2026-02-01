"""
Bootstrap do Framework - Aplicação principal.

Características:
- Configuração centralizada
- Lifecycle management (startup/shutdown)
- Middleware integrado
- CORS configurável
- Documentação automática
"""

from __future__ import annotations

from typing import Any
from collections.abc import Callable, Sequence
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.config import Settings, get_settings
from core.models import init_database, create_tables, close_database
from core.routing import Router, AutoRouter, include_router


class CoreApp:
    """
    Aplicação principal do framework.
    
    Encapsula FastAPI com configurações e lifecycle management.
    
    Exemplo:
        app = CoreApp(
            title="My API",
            settings=MySettings(),
        )
        
        # Registra routers
        app.include_router(user_router, prefix="/users")
        
        # Obtém a aplicação FastAPI
        fastapi_app = app.app
    """
    
    def __init__(
        self,
        title: str | None = None,
        description: str = "",
        version: str = "1.0.0",
        settings: Settings | None = None,
        routers: list[Router | AutoRouter] | None = None,
        on_startup: list[Callable] | None = None,
        on_shutdown: list[Callable] | None = None,
        middlewares: list[tuple[type, dict[str, Any]]] | None = None,
        exception_handlers: dict[type, Callable] | None = None,
        auto_create_tables: bool = True,
        **fastapi_kwargs: Any,
    ) -> None:
        """
        Inicializa a aplicação.
        
        Args:
            title: Título da API
            description: Descrição da API
            version: Versão da API
            settings: Configurações (usa padrão se não fornecido)
            routers: Lista de routers a incluir
            on_startup: Callbacks de startup
            on_shutdown: Callbacks de shutdown
            middlewares: Lista de middlewares (classe, kwargs)
            exception_handlers: Handlers de exceção customizados
            auto_create_tables: Se True, cria tabelas automaticamente
            **fastapi_kwargs: Argumentos extras para FastAPI
        """
        self.settings = settings or get_settings()
        self._on_startup = on_startup or []
        self._on_shutdown = on_shutdown or []
        self._auto_create_tables = auto_create_tables
        
        # Cria a aplicação FastAPI
        self.app = FastAPI(
            title=title or self.settings.app_name,
            description=description,
            version=version,
            docs_url=self.settings.docs_url,
            redoc_url=self.settings.redoc_url,
            lifespan=self._lifespan,
            **fastapi_kwargs,
        )
        
        # Configura CORS
        self._setup_cors()
        
        # Adiciona middlewares customizados
        if middlewares:
            for middleware_class, middleware_kwargs in middlewares:
                self.app.add_middleware(middleware_class, **middleware_kwargs)
        
        # Adiciona exception handlers
        self._setup_exception_handlers(exception_handlers)
        
        # Inclui routers
        if routers:
            for router in routers:
                self.include_router(router)
    
    @asynccontextmanager
    async def _lifespan(self, app: FastAPI):
        """Gerencia o ciclo de vida da aplicação."""
        # Startup
        await self._startup()
        
        yield
        
        # Shutdown
        await self._shutdown()
    
    async def _startup(self) -> None:
        """Executa tarefas de startup."""
        # Inicializa o banco de dados
        await init_database(
            database_url=self.settings.database_url,
            echo=self.settings.database_echo,
            pool_size=self.settings.database_pool_size,
            max_overflow=self.settings.database_max_overflow,
        )
        
        # Cria tabelas se configurado
        if self._auto_create_tables:
            await create_tables()
        
        # Executa callbacks customizados
        for callback in self._on_startup:
            result = callback()
            if hasattr(result, "__await__"):
                await result
    
    async def _shutdown(self) -> None:
        """Executa tarefas de shutdown."""
        # Executa callbacks customizados
        for callback in self._on_shutdown:
            result = callback()
            if hasattr(result, "__await__"):
                await result
        
        # Fecha conexão com o banco
        await close_database()
    
    def _setup_cors(self) -> None:
        """Configura CORS."""
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=self.settings.cors_origins,
            allow_credentials=self.settings.cors_allow_credentials,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    def _setup_exception_handlers(
        self,
        custom_handlers: dict[type, Callable] | None = None,
    ) -> None:
        """Configura handlers de exceção."""
        from pydantic import ValidationError
        
        # Handler para erros de validação Pydantic
        @self.app.exception_handler(ValidationError)
        async def validation_exception_handler(
            request: Request,
            exc: ValidationError,
        ) -> JSONResponse:
            return JSONResponse(
                status_code=422,
                content={
                    "detail": "Validation error",
                    "errors": exc.errors(),
                },
            )
        
        # Handler padrão para exceções não tratadas
        @self.app.exception_handler(Exception)
        async def generic_exception_handler(
            request: Request,
            exc: Exception,
        ) -> JSONResponse:
            if self.settings.debug:
                return JSONResponse(
                    status_code=500,
                    content={
                        "detail": str(exc),
                        "type": type(exc).__name__,
                    },
                )
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"},
            )
        
        # Handlers customizados
        if custom_handlers:
            for exc_class, handler in custom_handlers.items():
                self.app.add_exception_handler(exc_class, handler)
    
    def include_router(
        self,
        router: Router | AutoRouter,
        prefix: str = "",
        tags: list[str] | None = None,
    ) -> None:
        """
        Inclui um router na aplicação.
        
        Args:
            router: Router ou AutoRouter
            prefix: Prefixo adicional
            tags: Tags para OpenAPI
        """
        include_router(self.app, router, prefix=prefix, tags=tags)
    
    def on_startup(self, func: Callable) -> Callable:
        """
        Decorator para registrar callback de startup.
        
        Exemplo:
            @app.on_startup
            async def setup_cache():
                await cache.connect()
        """
        self._on_startup.append(func)
        return func
    
    def on_shutdown(self, func: Callable) -> Callable:
        """
        Decorator para registrar callback de shutdown.
        
        Exemplo:
            @app.on_shutdown
            async def cleanup():
                await cache.disconnect()
        """
        self._on_shutdown.append(func)
        return func
    
    def get(self, path: str, **kwargs: Any) -> Callable:
        """Decorator para rota GET."""
        return self.app.get(path, **kwargs)
    
    def post(self, path: str, **kwargs: Any) -> Callable:
        """Decorator para rota POST."""
        return self.app.post(path, **kwargs)
    
    def put(self, path: str, **kwargs: Any) -> Callable:
        """Decorator para rota PUT."""
        return self.app.put(path, **kwargs)
    
    def patch(self, path: str, **kwargs: Any) -> Callable:
        """Decorator para rota PATCH."""
        return self.app.patch(path, **kwargs)
    
    def delete(self, path: str, **kwargs: Any) -> Callable:
        """Decorator para rota DELETE."""
        return self.app.delete(path, **kwargs)
    
    async def __call__(self, scope, receive, send):
        """
        Torna CoreApp callable como ASGI app.
        
        Permite usar diretamente com uvicorn:
            uvicorn main:app --reload
        
        Onde app é uma instância de CoreApp.
        """
        await self.app(scope, receive, send)


def create_app(
    title: str = "Core Framework API",
    settings: Settings | None = None,
    **kwargs: Any,
) -> CoreApp:
    """
    Factory function para criar aplicação.
    
    Exemplo:
        app = create_app(
            title="My API",
            description="API description",
        )
    """
    return CoreApp(title=title, settings=settings, **kwargs)
