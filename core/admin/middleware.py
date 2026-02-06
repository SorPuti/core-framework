"""
AdminSessionMiddleware — Resolve cookie admin_session → request.state.admin_user.

Sem este middleware, _get_admin_user() sempre retorna None e o admin
entra em loop infinito de login.

Fluxo:
1. Intercepta requests para rotas do admin (admin_url_prefix)
2. Lê cookie "admin_session" do request
3. Busca AdminSession no banco (session_key, is_active, nao expirada)
4. Busca User pelo session.user_id
5. Define request.state.admin_user = user
6. Passa request para o proximo handler
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

if TYPE_CHECKING:
    from starlette.types import ASGIApp

logger = logging.getLogger("core.admin")


class AdminSessionMiddleware(BaseHTTPMiddleware):
    """
    Middleware que resolve o cookie admin_session em request.state.admin_user.
    
    Deve ser registrado automaticamente pelo AdminSite.mount().
    Só intercepta rotas sob admin_url_prefix para não impactar performance
    de rotas da API normal.
    """
    
    def __init__(self, app: "ASGIApp", admin_prefix: str = "/admin") -> None:
        super().__init__(app)
        self.admin_prefix = admin_prefix.rstrip("/")
    
    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Resolve sessão admin em cada request para rotas do admin."""
        path = request.url.path
        
        # Só intercepta rotas do admin
        if not path.startswith(self.admin_prefix):
            return await call_next(request)
        
        # Rota de login/logout/static não precisa de resolução
        admin_path = path[len(self.admin_prefix):]
        if admin_path in ("/login", "/logout") or admin_path.startswith("/static"):
            return await call_next(request)
        
        # Lê cookie
        session_key = request.cookies.get("admin_session")
        if not session_key:
            return await call_next(request)
        
        # Resolve sessão → user
        try:
            user = await self._resolve_session(session_key)
            if user is not None:
                request.state.admin_user = user
        except Exception as e:
            logger.debug("Failed to resolve admin session: %s", e)
        
        return await call_next(request)
    
    async def _resolve_session(self, session_key: str) -> Any | None:
        """
        Busca AdminSession no banco e retorna o User associado.
        
        Returns:
            User object ou None se sessão inválida/expirada
        """
        from core.models import get_session
        from core.admin.models import AdminSession
        
        try:
            db = await get_session()
        except RuntimeError:
            # Banco não inicializado (ex: durante startup)
            return None
        
        async with db:
            # Busca sessão ativa
            session = await AdminSession.objects.using(db).filter(
                session_key=session_key,
                is_active=True,
            ).first()
            
            if session is None:
                return None
            
            # Verifica expiração
            from core.datetime import timezone
            if hasattr(session, "expires_at") and session.expires_at:
                now = timezone.now()
                if session.expires_at < now:
                    logger.debug("Admin session expired for user_id=%s", session.user_id)
                    return None
            
            # Busca User
            try:
                from core.auth.models import get_user_model
                User = get_user_model()
            except RuntimeError:
                return None
            
            # user_id é VARCHAR — precisa converter para o tipo da PK do User
            user_id = session.user_id
            user = await User.objects.using(db).filter(id=user_id).first()
            
            if user is None:
                # Tenta com conversão int (user_id pode ser "123" com PK int)
                try:
                    user_id_int = int(user_id)
                    user = await User.objects.using(db).filter(id=user_id_int).first()
                except (ValueError, TypeError):
                    pass
            
            return user
