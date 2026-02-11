"""
AdminSessionMiddleware — Resolve cookie admin_session → request.state.admin_user.

Fluxo:
1. Intercepta requests para rotas do admin (admin_url_prefix)
2. Lê cookie "admin_session" do request
3. Busca AdminSession no banco (session_key, is_active, não expirada)
4. Busca User pelo session.user_id
5. Define request.state.admin_user = user
"""

from __future__ import annotations

import logging
import traceback
from typing import Any, TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

if TYPE_CHECKING:
    from starlette.types import ASGIApp

logger = logging.getLogger("core.admin")


class AdminSessionMiddleware(BaseHTTPMiddleware):
    """
    Middleware que resolve o cookie admin_session em request.state.admin_user.
    
    Registrado automaticamente pelo AdminSite.mount().
    Só intercepta rotas sob admin_url_prefix.
    
    IMPORTANTE: Este middleware SEMPRE retorna um Response, mesmo em caso de erro.
    Isso evita o erro "RuntimeError: No response returned" do Starlette.
    """
    
    def __init__(self, app: "ASGIApp", admin_prefix: str = "/admin") -> None:
        super().__init__(app)
        self.admin_prefix = admin_prefix.rstrip("/")
    
    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Resolve sessão admin em cada request para rotas do admin."""
        path = request.url.path
        
        # Só intercepta rotas do admin
        if not path.startswith(self.admin_prefix):
            try:
                return await call_next(request)
            except Exception as exc:
                # Não deveria acontecer, mas garante resposta
                logger.exception(f"Unhandled error in non-admin route: {path}")
                return self._error_response(exc, path)
        
        # Rotas públicas não precisam de resolução
        admin_path = path[len(self.admin_prefix):]
        if admin_path in ("/login", "/logout") or admin_path.startswith("/static"):
            try:
                return await call_next(request)
            except Exception as exc:
                logger.exception(f"Unhandled error in public admin route: {path}")
                return self._error_response(exc, path)
        
        # Lê cookie e resolve sessão
        try:
            session_key = request.cookies.get("admin_session")
            if session_key:
                user = await self._resolve_session(session_key)
                if user is not None:
                    request.state.admin_user = user
        except Exception as exc:
            # Erro ao resolver sessão não deve bloquear o request
            logger.warning(f"Error resolving admin session: {exc}")
        
        # Chama o próximo handler com tratamento de erro robusto
        try:
            response = await call_next(request)
            return response
        except Exception as exc:
            logger.exception(f"Unhandled error in admin route: {path}")
            return self._error_response(exc, path)
    
    def _error_response(self, exc: Exception, path: str) -> JSONResponse:
        """
        Gera uma resposta de erro JSON garantida.
        
        NUNCA deixa o middleware sem retornar um Response.
        """
        error_type = type(exc).__name__
        error_message = str(exc)
        
        # Log detalhado para debug
        tb = traceback.format_exc()
        logger.error(f"Admin middleware error response for {path}:\n{tb}")
        
        return JSONResponse(
            status_code=500,
            content={
                "detail": error_message or "Internal server error",
                "code": "internal_error",
                "type": error_type,
                "path": path,
                "traceback": tb,
            },
        )
    
    async def _resolve_session(self, session_key: str) -> Any | None:
        """Busca AdminSession no banco e retorna o User associado."""
        from core.models import get_session
        from core.admin.models import AdminSession
        
        try:
            db = await get_session()
        except RuntimeError:
            return None
        
        async with db:
            # Busca sessão ativa
            session = await AdminSession.objects.using(db).filter(
                session_key=session_key,
                is_active=True,
            ).first()
            
            if session is None:
                return None
            
            # Verifica expiração (usa is_past para comparação segura naive/aware)
            from core.datetime import timezone
            if hasattr(session, "expires_at") and session.expires_at:
                if timezone.is_past(session.expires_at):
                    return None
            
            # Busca User
            try:
                from core.auth.models import get_user_model
                User = get_user_model()
            except RuntimeError:
                return None
            
            # Converte user_id (VARCHAR) para o tipo correto do User.id
            from core.auth.base import coerce_user_id
            user_id: Any = session.user_id
            user_id = coerce_user_id(User, user_id)
            if user_id is None:
                return None
            
            return await User.objects.using(db).filter(id=user_id).first()
