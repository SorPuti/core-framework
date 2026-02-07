"""
AdminRouter — Cria e configura o router do admin panel.

Inclui:
- API endpoints JSON (/api/...)
- Frontend HTML (/dashboard, /login, list views, detail views)
- Static files (em debug mode)
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta
from typing import Any, TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request, Response, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from core.admin.permissions import check_admin_access, _get_admin_user

if TYPE_CHECKING:
    from core.admin.site import AdminSite
    from core.config import Settings

logger = logging.getLogger("core.admin")


def create_admin_router(site: "AdminSite", settings: "Settings") -> APIRouter:
    """
    Cria o router principal do admin panel.
    
    Combina:
    - API endpoints (JSON) sob /api/
    - Frontend endpoints (HTML) na raiz
    """
    router = APIRouter(tags=["admin"])
    
    # ── IMPORTANTE: ordem de registro de routers ──
    # Rotas literais PRIMEIRO, rotas com path params genéricos DEPOIS.
    # FastAPI avalia rotas por ordem de registro — se /api/{app}/{model}
    # vier antes de /api/ops/*, o "ops" é capturado como app_label. (Issue #10, #14)
    
    # 1. Operations Center API (rotas literais: /api/ops/*)
    ops_enabled = getattr(settings, "ops_enabled", True)
    if ops_enabled:
        from core.admin.ops_views import create_ops_api
        ops_router = create_ops_api(site)
        router.include_router(ops_router)
        
        # Initialize log buffer
        from core.admin.log_handler import setup_log_buffer
        setup_log_buffer()
    
    # 2. API views genéricas (rotas com path params: /api/{app_label}/{model_name})
    from core.admin.views import create_api_views
    api_router = create_api_views(site)
    router.include_router(api_router)
    
    # Template rendering
    _templates = _setup_templates(settings)
    
    prefix = getattr(settings, "admin_url_prefix", "/admin").rstrip("/")
    debug = getattr(settings, "debug", False)
    
    # -- Context helpers --
    
    def _base_context(request: Request, **extra: Any) -> dict:
        """Contexto base para todos os templates."""
        from core import __version__ as core_version
        
        # Resolve current page for active sidebar indicator
        current_path = str(request.url.path).rstrip("/")
        
        return {
            "request": request,
            "site_title": getattr(settings, "admin_site_title", "Admin"),
            "site_header": getattr(settings, "admin_site_header", "Core Admin"),
            "admin_prefix": prefix,
            "static_prefix": f"{prefix}/static",
            "apps": site.get_app_list(),
            "errors": site.errors,
            "debug": debug,
            "theme": getattr(settings, "admin_theme", "default"),
            "primary_color": getattr(settings, "admin_primary_color", "#3B82F6"),
            "logo_url": getattr(settings, "admin_logo_url", None),
            "core_version": core_version,
            "current_path": current_path,
            "ops_enabled": ops_enabled,
            **extra,
        }
    
    # =========================================================================
    # Frontend Routes (HTML)
    # =========================================================================
    
    @router.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request) -> Response:
        """Página de login do admin."""
        user = _get_admin_user(request)
        if user and (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)):
            return RedirectResponse(f"{prefix}/", status_code=302)
        
        ctx = _base_context(request, error=request.query_params.get("error"))
        return _templates.TemplateResponse("admin/login.html", ctx)
    
    @router.post("/login")
    async def login_action(
        request: Request,
        response: Response,
        email: str = Form(...),
        password: str = Form(...),
    ) -> Response:
        """Processa login no admin."""
        try:
            from core.auth.models import get_user_model
            User = get_user_model()
        except RuntimeError:
            return RedirectResponse(
                f"{prefix}/login?error=Admin+not+configured",
                status_code=303,
            )
        
        from core.models import get_session
        
        try:
            db = await get_session()
            async with db:
                user = await User.objects.using(db).filter(email=email).first()
                
                if user is None:
                    return RedirectResponse(
                        f"{prefix}/login?error=Invalid+credentials",
                        status_code=303,
                    )
                
                # Verificar senha
                valid = False
                if hasattr(user, "check_password"):
                    valid = user.check_password(password)
                    if hasattr(valid, "__await__"):
                        valid = await valid
                elif hasattr(user, "verify_password"):
                    valid = user.verify_password(password)
                    if hasattr(valid, "__await__"):
                        valid = await valid
                
                if not valid:
                    return RedirectResponse(
                        f"{prefix}/login?error=Invalid+credentials",
                        status_code=303,
                    )
                
                if not (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)):
                    return RedirectResponse(
                        f"{prefix}/login?error=Admin+access+required",
                        status_code=303,
                    )
                
                # Criar sessão
                session_key = secrets.token_urlsafe(48)
                
                try:
                    from core.admin.models import AdminSession
                    from core.datetime import timezone
                    
                    session = AdminSession(
                        session_key=session_key,
                        user_id=str(user.id),
                        ip_address=request.client.host if request.client else None,
                        user_agent=request.headers.get("user-agent", "")[:500],
                        expires_at=timezone.now() + timedelta(hours=24),
                    )
                    await session.save(db)
                    await db.commit()
                except Exception as e:
                    logger.warning("Could not save admin session to DB: %s", e)
                
                response = RedirectResponse(f"{prefix}/", status_code=303)
                
                cookie_secure = getattr(settings, "admin_cookie_secure", None)
                if cookie_secure is None:
                    cookie_secure = request.url.scheme == "https"
                
                response.set_cookie(
                    key="admin_session",
                    value=session_key,
                    httponly=True,
                    samesite="lax",
                    max_age=86400,  # 24 hours
                    secure=cookie_secure,
                )
                return response
                
        except Exception as e:
            logger.error("Login error: %s", e)
            return RedirectResponse(
                f"{prefix}/login?error=Internal+error",
                status_code=303,
            )
    
    @router.get("/logout")
    async def logout(request: Request) -> Response:
        """Logout do admin."""
        response = RedirectResponse(f"{prefix}/login", status_code=302)
        response.delete_cookie("admin_session")
        return response
    
    @router.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request) -> Response:
        """Dashboard principal do admin."""
        user = _get_admin_user(request)
        if not user or not (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)):
            return RedirectResponse(f"{prefix}/login", status_code=302)
        
        ctx = _base_context(request, user=user)
        return _templates.TemplateResponse("admin/dashboard.html", ctx)
    
    # =========================================================================
    # Operations Center Routes (HTML) — BEFORE model routes
    # =========================================================================
    
    if ops_enabled:
        @router.get("/ops/", response_class=HTMLResponse)
        async def ops_dashboard(request: Request) -> Response:
            """Operations Center dashboard."""
            user = _get_admin_user(request)
            if not user or not (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)):
                return RedirectResponse(f"{prefix}/login", status_code=302)
            ctx = _base_context(request, user=user)
            return _templates.TemplateResponse("admin/ops/dashboard.html", ctx)
        
        @router.get("/ops/infrastructure/", response_class=HTMLResponse)
        async def ops_infrastructure(request: Request) -> Response:
            """Infrastructure panel."""
            user = _get_admin_user(request)
            if not user or not (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)):
                return RedirectResponse(f"{prefix}/login", status_code=302)
            ctx = _base_context(request, user=user)
            return _templates.TemplateResponse("admin/ops/infrastructure.html", ctx)
        
        @router.get("/ops/tasks/", response_class=HTMLResponse)
        async def ops_tasks(request: Request) -> Response:
            """Task Manager."""
            user = _get_admin_user(request)
            if not user or not (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)):
                return RedirectResponse(f"{prefix}/login", status_code=302)
            ctx = _base_context(request, user=user)
            return _templates.TemplateResponse("admin/ops/tasks.html", ctx)
        
        @router.get("/ops/workers/", response_class=HTMLResponse)
        async def ops_workers(request: Request) -> Response:
            """Worker Manager."""
            user = _get_admin_user(request)
            if not user or not (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)):
                return RedirectResponse(f"{prefix}/login", status_code=302)
            ctx = _base_context(request, user=user)
            return _templates.TemplateResponse("admin/ops/workers.html", ctx)
        
        @router.get("/ops/logs/", response_class=HTMLResponse)
        async def ops_logs(request: Request) -> Response:
            """Log Viewer with streaming."""
            user = _get_admin_user(request)
            if not user or not (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)):
                return RedirectResponse(f"{prefix}/login", status_code=302)
            ctx = _base_context(request, user=user)
            return _templates.TemplateResponse("admin/ops/logs.html", ctx)
        
        @router.get("/ops/periodic/", response_class=HTMLResponse)
        async def ops_periodic(request: Request) -> Response:
            """Periodic Tasks."""
            user = _get_admin_user(request)
            if not user or not (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)):
                return RedirectResponse(f"{prefix}/login", status_code=302)
            ctx = _base_context(request, user=user)
            return _templates.TemplateResponse("admin/ops/periodic.html", ctx)
    
    # =========================================================================
    # Model Routes (HTML)
    # =========================================================================
    
    @router.get("/{app_label}/{model_name}/", response_class=HTMLResponse)
    async def model_list(
        request: Request,
        app_label: str,
        model_name: str,
    ) -> Response:
        """List view HTML para um model."""
        user = _get_admin_user(request)
        if not user or not (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)):
            return RedirectResponse(f"{prefix}/login", status_code=302)
        
        result = site.get_model_by_name(app_label, model_name)
        if not result:
            raise HTTPException(404, f"Model not found: {app_label}.{model_name}")
        
        model, admin_instance = result
        
        # Verificar erros do model
        model_errors = site.errors.get_errors_for_model(model.__name__)
        
        # Resolve tipo de cada filtro para gerar opcoes corretas no template
        filter_types = {}
        for filter_name in admin_instance.list_filter:
            col = getattr(model, filter_name, None)
            if col is not None:
                try:
                    col_type = str(col.property.columns[0].type).upper()
                    if "BOOL" in col_type:
                        filter_types[filter_name] = "boolean"
                    else:
                        filter_types[filter_name] = "string"
                except Exception:
                    filter_types[filter_name] = "string"
            else:
                filter_types[filter_name] = "string"
        
        import json as _json
        
        ctx = _base_context(
            request,
            user=user,
            app_label=app_label,
            model_name=model_name,
            admin=admin_instance,
            model_errors=model_errors,
            filter_types=filter_types,
            filter_types_json=_json.dumps(filter_types),
        )
        return _templates.TemplateResponse("admin/list.html", ctx)
    
    @router.get("/{app_label}/{model_name}/{pk}/", response_class=HTMLResponse)
    async def model_detail(
        request: Request,
        app_label: str,
        model_name: str,
        pk: str,
    ) -> Response:
        """Detail/edit view HTML para um objeto."""
        user = _get_admin_user(request)
        if not user or not (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)):
            return RedirectResponse(f"{prefix}/login", status_code=302)
        
        result = site.get_model_by_name(app_label, model_name)
        if not result:
            raise HTTPException(404, f"Model not found: {app_label}.{model_name}")
        
        model, admin_instance = result
        
        import json as _json
        fields_json = _json.dumps(admin_instance.get_column_info())
        editable_fields_json = _json.dumps(admin_instance.get_editable_fields())
        
        ctx = _base_context(
            request,
            user=user,
            app_label=app_label,
            model_name=model_name,
            pk=pk,
            admin=admin_instance,
            is_new=(pk == "new"),
            fields_json=fields_json,
            editable_fields_json=editable_fields_json,
        )
        return _templates.TemplateResponse("admin/detail.html", ctx)
    
    return router


def _setup_templates(settings: "Settings") -> Any:
    """Configura Jinja2 templates para o admin."""
    from pathlib import Path
    from starlette.templating import Jinja2Templates
    
    templates_dir = Path(__file__).parent / "templates"
    
    templates = Jinja2Templates(directory=str(templates_dir))
    
    # Adiciona helpers ao ambiente Jinja2
    templates.env.globals["now"] = datetime.utcnow
    
    return templates
