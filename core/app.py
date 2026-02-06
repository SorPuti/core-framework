"""
Bootstrap do Framework - Aplicação principal.

Boot Sequence (ordem garantida):
1. Settings loaded (frozen, validado)
2. Logging configured
3. Database engine initialized
4. Models metadata ready (tables registered)
5. Auth configured (se middleware "auth" habilitado)
6. Middleware applied
7. Routes registered
8. Health checks registered (se habilitado)
9. Startup callbacks executed

Características:
- Configuração centralizada via Settings
- Lifecycle management (startup/shutdown)
- Middleware integrado (Django-style)
- CORS configurável
- Documentação automática
- Health checks built-in (/healthz, /readyz)
- Auto-configuração de features enterprise:
  - Multi-tenancy
  - Read/Write replicas
  - Soft delete
"""

from __future__ import annotations

import logging
from typing import Any
from collections.abc import Callable, Sequence
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.config import Settings, get_settings
from core.models import init_database, create_tables, close_database
from core.routing import Router, AutoRouter, include_router

app_logger = logging.getLogger("core.app")


class CoreApp:
    """
    Aplicação principal do framework.
    
    Encapsula FastAPI com configurações e lifecycle management.
    
    Exemplo básico:
        app = CoreApp(
            title="My API",
            settings=MySettings(),
        )
        
        # Registra routers
        app.include_router(user_router, prefix="/users")
        
        # Obtém a aplicação FastAPI
        fastapi_app = app.app
    
    Exemplo com middlewares Django-style:
        app = CoreApp(
            title="My API",
            middleware=[
                "core.middleware.TimingMiddleware",
                "core.auth.AuthenticationMiddleware",
                ("core.middleware.LoggingMiddleware", {"log_headers": True}),
            ],
        )
    
    Shortcuts disponíveis:
        - "auth": AuthenticationMiddleware
        - "timing": TimingMiddleware
        - "request_id": RequestIDMiddleware
        - "logging": LoggingMiddleware
        - "security_headers": SecurityHeadersMiddleware
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
        middleware: list[str | type | tuple] | None = None,
        exception_handlers: dict[type, Callable] | None = None,
        auto_create_tables: bool | None = None,
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
            middlewares: Lista de middlewares formato antigo (classe, kwargs)
            middleware: Lista de middlewares formato Django-style (strings/classes)
            exception_handlers: Handlers de exceção customizados
            auto_create_tables: Se True, cria tabelas no startup (default: Settings.auto_create_tables)
            **fastapi_kwargs: Argumentos extras para FastAPI
        
        Middleware format (novo, Django-style):
            middleware=[
                "core.auth.AuthenticationMiddleware",  # String path
                "auth",  # Shortcut
                MyMiddleware,  # Classe direta
                ("logging", {"log_body": True}),  # Com kwargs
            ]
        """
        # ── Step 1: Settings (loaded, validated) ──
        self.settings = settings or get_settings()
        self._on_startup = on_startup or []
        self._on_shutdown = on_shutdown or []
        
        # auto_create_tables: parâmetro explícito > settings > default (False)
        if auto_create_tables is not None:
            self._auto_create_tables = auto_create_tables
        else:
            self._auto_create_tables = getattr(self.settings, "auto_create_tables", False)
        
        # Store settings on app.state for dependency injection
        # Evita chamadas get_settings() em hot paths
        
        # ── Step 2: Create FastAPI app ──
        self.app = FastAPI(
            title=title or self.settings.app_name,
            description=description,
            version=version,
            docs_url=self.settings.docs_url,
            redoc_url=self.settings.redoc_url,
            openapi_url=self.settings.openapi_url,
            lifespan=self._lifespan,
            **fastapi_kwargs,
        )
        
        # Store settings on app.state for request-level access
        self.app.state.settings = self.settings
        
        # ── Step 3: CORS ──
        self._setup_cors()
        
        # ── Step 4: Tenancy middleware ──
        if self.settings.tenancy_enabled:
            self._setup_tenancy_middleware()
        
        # ── Step 5: Django-style middleware ──
        middleware_list = middleware or getattr(self.settings, "middleware", None)
        if middleware_list:
            self._setup_django_style_middleware(middleware_list)
        
        # ── Step 6: Legacy middleware format ──
        if middlewares:
            for middleware_class, middleware_kwargs in middlewares:
                self.app.add_middleware(middleware_class, **middleware_kwargs)
        
        # ── Step 7: Exception handlers ──
        self._setup_exception_handlers(exception_handlers)
        
        # ── Step 8: Routers ──
        if routers:
            for router in routers:
                self.include_router(router)
        
        # ── Step 8.5: Admin Panel ──
        self._admin_site = None
        if getattr(self.settings, "admin_enabled", True):
            self._setup_admin()
        
        # ── Step 9: Health checks ──
        if getattr(self.settings, "health_check_enabled", True):
            self._setup_health_checks()
    
    @asynccontextmanager
    async def _lifespan(self, app: FastAPI):
        """Gerencia o ciclo de vida da aplicação."""
        # Startup
        await self._startup()
        
        yield
        
        # Shutdown
        await self._shutdown()
    
    async def _startup(self) -> None:
        """
        Executa tarefas de startup na ordem garantida.
        
        Boot sequence:
        1. Schema validation (fail-fast)
        2. Database initialization
        3. Table creation (if configured)
        4. Tenancy setup
        5. User startup callbacks
        """
        app_logger.info(
            "Starting %s (environment=%s, debug=%s)",
            self.settings.app_name,
            self.settings.environment,
            self.settings.debug,
        )
        
        # ── Step 1: Schema/Model validation (before DB for fail-fast) ──
        if getattr(self.settings, "strict_validation", self.settings.debug):
            await self._validate_schemas()
        
        # ── Step 2: Database initialization ──
        if self.settings.has_read_replica:
            from core.database import init_replicas
            
            await init_replicas(
                write_url=self.settings.database_url,
                read_url=self.settings.database_read_url,
                echo=self.settings.database_echo,
                pool_size=self.settings.database_pool_size,
                max_overflow=self.settings.database_max_overflow,
                pool_recycle=self.settings.database_pool_recycle,
            )
        else:
            await init_database(
                database_url=self.settings.database_url,
                echo=self.settings.database_echo,
                pool_size=self.settings.database_pool_size,
                max_overflow=self.settings.database_max_overflow,
            )
        
        # ── Step 3: Table creation ──
        if self._auto_create_tables:
            await create_tables()
        
        # ── Step 4: Tenancy ──
        if self.settings.tenancy_enabled:
            from core.tenancy import set_tenant_field
            set_tenant_field(self.settings.tenancy_field)
        
        # ── Step 5: User callbacks ──
        for callback in self._on_startup:
            result = callback()
            if hasattr(result, "__await__"):
                await result
        
        app_logger.info("Application started successfully")
    
    async def _validate_schemas(self) -> None:
        """
        Validate all ViewSet schemas against their models.
        
        Called during startup if strict_validation is enabled.
        In DEBUG mode, raises SchemaModelMismatchError on critical issues.
        In production, logs errors but continues.
        """
        import logging
        logger = logging.getLogger("core.app")
        
        try:
            from core.views import validate_pending_viewsets
            from core.validation import SchemaModelMismatchError
            
            logger.info("Running schema/model validations...")
            
            # In debug mode, fail fast on critical issues
            strict = self.settings.debug
            
            try:
                issues = validate_pending_viewsets(strict=strict)
                
                if issues:
                    logger.warning(
                        f"Schema validation completed with {len(issues)} issues"
                    )
                else:
                    logger.info("Schema validation passed")
                    
            except SchemaModelMismatchError as e:
                if self.settings.debug:
                    logger.error(f"Schema validation failed: {e}")
                    raise RuntimeError(
                        f"Schema validation errors (set DEBUG=False to skip):\n{e}"
                    ) from e
                else:
                    logger.error(f"Schema validation errors (ignored): {e}")
                    
        except ImportError:
            logger.debug("Validation module not available, skipping")
        except Exception as e:
            logger.warning(f"Could not validate schemas: {e}")
    
    async def _shutdown(self) -> None:
        """Executa tarefas de shutdown."""
        # Executa callbacks customizados
        for callback in self._on_shutdown:
            result = callback()
            if hasattr(result, "__await__"):
                await result
        
        # Flush and close messaging producers
        try:
            from core.messaging.registry import stop_all_producers
            await stop_all_producers()
        except Exception:
            pass  # Messaging may not be configured
        
        # Fecha conexões
        if self.settings.has_read_replica:
            from core.database import close_replicas
            await close_replicas()
        else:
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
    
    def _setup_tenancy_middleware(self) -> None:
        """Configura middleware de multi-tenancy."""
        from core.tenancy import TenantMiddleware
        
        self.app.add_middleware(
            TenantMiddleware,
            user_tenant_attr=self.settings.tenancy_user_attribute,
            tenant_field=self.settings.tenancy_field,
            require_tenant=self.settings.tenancy_require,
        )
    
    def _setup_django_style_middleware(
        self,
        middleware_list: list[str | type | tuple],
    ) -> None:
        """
        Configura middlewares no estilo Django.
        
        Args:
            middleware_list: Lista de middlewares
                - String: path do middleware (ex: "core.auth.AuthenticationMiddleware")
                - String shortcut: nome curto (ex: "auth", "timing")
                - Classe: classe do middleware diretamente
                - Tuple: (middleware, kwargs) para passar configurações
        
        Example:
            middleware_list = [
                "core.middleware.TimingMiddleware",
                "auth",  # shortcut para AuthenticationMiddleware
                MyCustomMiddleware,
                ("logging", {"log_body": True}),
            ]
        """
        from core.middleware import configure_middleware, apply_middlewares
        
        # Configura no registry global
        configure_middleware(middleware_list, clear_existing=True)
        
        # Aplica ao app
        apply_middlewares(self.app)
    
    def _setup_exception_handlers(
        self,
        custom_handlers: dict[type, Callable] | None = None,
    ) -> None:
        """Configura handlers de exceção."""
        from pydantic import ValidationError
        from sqlalchemy.exc import IntegrityError, DataError, OperationalError
        from core.validators import (
            ValidationError as CoreValidationError,
            MultipleValidationErrors,
            UniqueValidationError,
        )
        
        # Handler para erros de validação Pydantic
        @self.app.exception_handler(ValidationError)
        async def pydantic_validation_handler(
            request: Request,
            exc: ValidationError,
        ) -> JSONResponse:
            # Converte erros para formato JSON serializável
            errors = []
            for error in exc.errors():
                err = {
                    "loc": list(error.get("loc", [])),
                    "msg": str(error.get("msg", "")),
                    "type": error.get("type", ""),
                }
                # Inclui input apenas se for serializável
                if "input" in error:
                    try:
                        import json
                        json.dumps(error["input"])
                        err["input"] = error["input"]
                    except (TypeError, ValueError):
                        err["input"] = str(error["input"])
                errors.append(err)
            
            return JSONResponse(
                status_code=422,
                content={
                    "detail": "Validation error",
                    "code": "validation_error",
                    "errors": errors,
                },
            )
        
        # Handler para erros de validação do Core
        @self.app.exception_handler(CoreValidationError)
        async def core_validation_handler(
            request: Request,
            exc: CoreValidationError,
        ) -> JSONResponse:
            return JSONResponse(
                status_code=422,
                content={
                    "detail": exc.message,
                    "code": exc.code,
                    "field": exc.field,
                    "errors": [exc.to_dict()],
                },
            )
        
        # Handler para múltiplos erros de validação
        @self.app.exception_handler(MultipleValidationErrors)
        async def multiple_validation_handler(
            request: Request,
            exc: MultipleValidationErrors,
        ) -> JSONResponse:
            return JSONResponse(
                status_code=422,
                content=exc.to_dict(),
            )
        
        # Handler para erros de unicidade
        @self.app.exception_handler(UniqueValidationError)
        async def unique_validation_handler(
            request: Request,
            exc: UniqueValidationError,
        ) -> JSONResponse:
            return JSONResponse(
                status_code=409,  # Conflict
                content={
                    "detail": exc.message,
                    "code": "unique_constraint",
                    "field": exc.field,
                    "value": exc.value,
                },
            )
        
        # Handler para IntegrityError do SQLAlchemy (UNIQUE, FK, etc.)
        @self.app.exception_handler(IntegrityError)
        async def integrity_error_handler(
            request: Request,
            exc: IntegrityError,
        ) -> JSONResponse:
            error_msg = str(exc.orig) if exc.orig else str(exc)
            
            # Detecta tipo de erro
            if "UNIQUE constraint failed" in error_msg:
                # Extrai nome do campo
                field_match = error_msg.split("UNIQUE constraint failed:")[-1].strip()
                field_name = field_match.split(".")[-1] if "." in field_match else field_match
                
                return JSONResponse(
                    status_code=409,
                    content={
                        "detail": f"A record with this {field_name} already exists.",
                        "code": "unique_constraint",
                        "field": field_name,
                    },
                )
            
            elif "FOREIGN KEY constraint failed" in error_msg:
                return JSONResponse(
                    status_code=400,
                    content={
                        "detail": "Referenced record does not exist.",
                        "code": "foreign_key_constraint",
                    },
                )
            
            elif "NOT NULL constraint failed" in error_msg:
                field_match = error_msg.split("NOT NULL constraint failed:")[-1].strip()
                field_name = field_match.split(".")[-1] if "." in field_match else field_match
                
                return JSONResponse(
                    status_code=422,
                    content={
                        "detail": f"Field '{field_name}' is required.",
                        "code": "required_field",
                        "field": field_name,
                    },
                )
            
            elif "duplicate key" in error_msg.lower():
                # PostgreSQL
                return JSONResponse(
                    status_code=409,
                    content={
                        "detail": "A record with this value already exists.",
                        "code": "unique_constraint",
                    },
                )
            
            # Erro genérico de integridade
            if self.settings.debug:
                return JSONResponse(
                    status_code=400,
                    content={
                        "detail": "Database integrity error.",
                        "code": "integrity_error",
                        "debug_info": error_msg,
                    },
                )
            return JSONResponse(
                status_code=400,
                content={
                    "detail": "Database integrity error. Please check your data.",
                    "code": "integrity_error",
                },
            )
        
        # Handler para DataError (dados inválidos para o tipo da coluna)
        @self.app.exception_handler(DataError)
        async def data_error_handler(
            request: Request,
            exc: DataError,
        ) -> JSONResponse:
            return JSONResponse(
                status_code=422,
                content={
                    "detail": "Invalid data format for database field.",
                    "code": "data_error",
                },
            )
        
        # Handler para OperationalError (conexão, timeout, etc.)
        @self.app.exception_handler(OperationalError)
        async def operational_error_handler(
            request: Request,
            exc: OperationalError,
        ) -> JSONResponse:
            if self.settings.debug:
                return JSONResponse(
                    status_code=503,
                    content={
                        "detail": "Database operation failed.",
                        "code": "database_error",
                        "debug_info": str(exc),
                    },
                )
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "Service temporarily unavailable. Please try again.",
                    "code": "service_unavailable",
                },
            )
        
        # Handler padrão para exceções não tratadas
        @self.app.exception_handler(Exception)
        async def generic_exception_handler(
            request: Request,
            exc: Exception,
        ) -> JSONResponse:
            # NUNCA expor traceback em produção, mesmo se debug=True acidental
            if self.settings.debug and not self.settings.is_production:
                import traceback
                return JSONResponse(
                    status_code=500,
                    content={
                        "detail": str(exc),
                        "code": "internal_error",
                        "type": type(exc).__name__,
                        "traceback": traceback.format_exc(),
                    },
                )
            # Log the error server-side, return generic message to client
            app_logger.exception("Unhandled exception: %s", exc)
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal server error",
                    "code": "internal_error",
                },
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
    
    def add_api_route(
        self,
        path: str,
        endpoint: Callable,
        methods: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Add an API route directly.
        
        Useful for adding routes from APIView classes.
        
        Example:
            app.add_api_route("/health", HealthView.as_route("/health")[1], methods=["GET"])
        """
        self.app.add_api_route(path, endpoint, methods=methods, **kwargs)
    
    def _setup_admin(self) -> None:
        """
        Configura o Admin Panel.
        
        Boot sequence do admin:
        1. Instancia AdminSite com settings
        2. Executa autodiscover (registra core models + scan admin.py)
        3. Monta router sob settings.admin_url_prefix
        4. Em debug, serve static files diretamente
        
        Erros de configuração são logados profissionalmente:
        - AdminConfigurationError: fatal, impede mount
        - AdminRegistrationError: por model, não bloqueia outros
        """
        try:
            from core.admin import default_site
            
            self._admin_site = default_site
            self._admin_site.autodiscover()
            self._admin_site.mount(self.app, self.settings)
            
            prefix = getattr(self.settings, "admin_url_prefix", "/admin")
            app_logger.info("Admin panel enabled at %s", prefix)
            
        except Exception as e:
            app_logger.error(
                "Failed to setup admin panel: %s: %s. "
                "Admin will be unavailable. Fix the error and restart.",
                type(e).__name__, e,
            )
            self._admin_site = None
    
    def _setup_health_checks(self) -> None:
        """
        Registra endpoints de health check.
        
        - /healthz: Liveness probe (app está rodando?)
        - /readyz: Readiness probe (app está pronta para receber requests?)
        """
        @self.app.get("/healthz", tags=["health"], include_in_schema=False)
        async def healthz():
            """Liveness probe — returns 200 if the app is running."""
            return {"status": "alive"}
        
        @self.app.get("/readyz", tags=["health"], include_in_schema=False)
        async def readyz():
            """Readiness probe — checks database and messaging connectivity."""
            checks: dict[str, str] = {}
            all_ok = True
            
            # Database check
            try:
                from core.models import get_session
                session = await get_session()
                try:
                    from sqlalchemy import text
                    await session.execute(text("SELECT 1"))
                    checks["database"] = "ok"
                finally:
                    await session.close()
            except Exception as e:
                checks["database"] = f"error: {type(e).__name__}"
                all_ok = False
            
            # Kafka check (only if enabled)
            if getattr(self.settings, "kafka_enabled", False):
                try:
                    from core.messaging.registry import get_broker
                    broker = get_broker()
                    checks["kafka"] = "configured"
                except Exception as e:
                    checks["kafka"] = f"error: {type(e).__name__}"
                    all_ok = False
            
            status_code = 200 if all_ok else 503
            return JSONResponse(
                status_code=status_code,
                content={"status": "ready" if all_ok else "not_ready", "checks": checks},
            )
    
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
