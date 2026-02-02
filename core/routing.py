"""
Sistema de Roteamento automático inspirado no DRF.

Características:
- Auto-registro de ViewSets
- Geração automática de rotas REST
- Nomes previsíveis
- OpenAPI consistente
- Override manual quando necessário
- Integração nativa com FastAPI
"""

from __future__ import annotations

from typing import Any, ClassVar, TYPE_CHECKING
from collections.abc import Callable
import inspect

from fastapi import APIRouter, Request, Depends, Body
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies import get_db

if TYPE_CHECKING:
    from core.views import ViewSet, APIView


class Router(APIRouter):
    """
    Router estendido com funcionalidades extras.
    
    Compatível com FastAPI APIRouter, mas com métodos adicionais
    para registro de ViewSets.
    
    Exemplo:
        router = Router(prefix="/api/v1", tags=["api"])
        router.register_viewset("/users", UserViewSet)
    """
    
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._viewsets: list[tuple[str, type]] = []
    
    def register_viewset(
        self,
        prefix: str,
        viewset_class: type["ViewSet"],
        basename: str | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """
        Registra um ViewSet com rotas REST automáticas.
        
        Gera as seguintes rotas:
        - GET {prefix}/ -> list
        - POST {prefix}/ -> create
        - GET {prefix}/{id} -> retrieve
        - PUT {prefix}/{id} -> update
        - PATCH {prefix}/{id} -> partial_update
        - DELETE {prefix}/{id} -> destroy
        
        Args:
            prefix: Prefixo da URL (ex: "/users")
            viewset_class: Classe do ViewSet
            basename: Nome base para as rotas (default: nome do model)
            tags: Tags para OpenAPI
        """
        viewset = viewset_class()
        basename = basename or getattr(viewset_class, "model", None).__name__.lower()
        tags = tags or viewset_class.tags or [basename]
        
        lookup_field = viewset_class.lookup_field
        lookup_url_kwarg = viewset_class.lookup_url_kwarg or lookup_field
        
        # Normaliza o prefixo
        prefix = prefix.rstrip("/")
        
        # Rota de lista (GET) e criação (POST)
        @self.get(
            f"{prefix}/",
            tags=tags,
            name=f"{basename}-list",
            summary=f"List {basename}s",
        )
        async def list_route(
            request: Request,
            db: AsyncSession = Depends(get_db),
            page: int = 1,
            page_size: int = viewset_class.page_size,
        ) -> dict[str, Any]:
            vs = viewset_class()
            return await vs.list(request, db, page=page, page_size=page_size)
        
        @self.post(
            f"{prefix}/",
            tags=tags,
            name=f"{basename}-create",
            summary=f"Create {basename}",
            status_code=201,
        )
        async def create_route(
            request: Request,
            data: dict[str, Any] = Body(...),
            db: AsyncSession = Depends(get_db),
        ) -> dict[str, Any]:
            vs = viewset_class()
            return await vs.create(request, db, data)
        
        # Rota de detalhe (GET), atualização (PUT, PATCH) e deleção (DELETE)
        @self.get(
            f"{prefix}/{{{lookup_url_kwarg}}}",
            tags=tags,
            name=f"{basename}-detail",
            summary=f"Get {basename} by {lookup_url_kwarg}",
        )
        async def retrieve_route(
            request: Request,
            db: AsyncSession = Depends(get_db),
            **kwargs: Any,
        ) -> dict[str, Any]:
            vs = viewset_class()
            # Extrai o parâmetro de path
            path_params = request.path_params
            return await vs.retrieve(request, db, **path_params)
        
        @self.put(
            f"{prefix}/{{{lookup_url_kwarg}}}",
            tags=tags,
            name=f"{basename}-update",
            summary=f"Update {basename}",
        )
        async def update_route(
            request: Request,
            data: dict[str, Any] = Body(...),
            db: AsyncSession = Depends(get_db),
        ) -> dict[str, Any]:
            vs = viewset_class()
            path_params = request.path_params
            return await vs.update(request, db, data, **path_params)
        
        @self.patch(
            f"{prefix}/{{{lookup_url_kwarg}}}",
            tags=tags,
            name=f"{basename}-partial-update",
            summary=f"Partial update {basename}",
        )
        async def partial_update_route(
            request: Request,
            data: dict[str, Any] = Body(...),
            db: AsyncSession = Depends(get_db),
        ) -> dict[str, Any]:
            vs = viewset_class()
            path_params = request.path_params
            return await vs.partial_update(request, db, data, **path_params)
        
        @self.delete(
            f"{prefix}/{{{lookup_url_kwarg}}}",
            tags=tags,
            name=f"{basename}-delete",
            summary=f"Delete {basename}",
        )
        async def destroy_route(
            request: Request,
            db: AsyncSession = Depends(get_db),
        ) -> dict[str, Any]:
            vs = viewset_class()
            path_params = request.path_params
            return await vs.destroy(request, db, **path_params)
        
        # Registra actions customizadas
        self._register_custom_actions(prefix, viewset_class, basename, tags, lookup_url_kwarg)
        
        # Guarda referência
        self._viewsets.append((prefix, viewset_class))
    
    def _register_custom_actions(
        self,
        prefix: str,
        viewset_class: type["ViewSet"],
        basename: str,
        tags: list[str],
        lookup_url_kwarg: str,
    ) -> None:
        """Registra actions customizadas decoradas com @action."""
        for name, method in inspect.getmembers(viewset_class, predicate=inspect.isfunction):
            if not getattr(method, "is_action", False):
                continue
            
            action_methods = method.methods
            detail = method.detail
            url_path = method.url_path
            
            if detail:
                path = f"{prefix}/{{{lookup_url_kwarg}}}/{url_path}"
            else:
                path = f"{prefix}/{url_path}"
            
            # Cria endpoint para cada método HTTP
            for http_method in action_methods:
                route_name = f"{basename}-{name}"
                
                # Captura method em closure para evitar late binding
                def make_action_endpoint(action_method: Callable) -> Callable:
                    async def action_endpoint(
                        request: Request,
                        db: AsyncSession = Depends(get_db),
                        data: dict[str, Any] | None = Body(None),
                    ) -> Any:
                        vs = viewset_class()
                        path_params = request.path_params
                        if data is not None:
                            return await action_method(vs, request, db, data=data, **path_params)
                        return await action_method(vs, request, db, **path_params)
                    return action_endpoint
                
                self.add_api_route(
                    path,
                    make_action_endpoint(method),
                    methods=[http_method],
                    tags=tags,
                    name=route_name,
                    summary=f"{name.replace('_', ' ').title()}",
                )
    
    def register_view(
        self,
        path: str,
        view_class: type["APIView"],
        methods: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Registra uma APIView.
        
        Args:
            path: Caminho da rota
            view_class: Classe da view
            methods: Métodos HTTP permitidos
            **kwargs: Argumentos extras para a rota
        """
        view = view_class()
        methods = methods or ["GET", "POST", "PUT", "PATCH", "DELETE"]
        tags = kwargs.pop("tags", view_class.tags or [])
        
        async def endpoint(
            request: Request,
            db: AsyncSession = Depends(get_db),
        ) -> Any:
            method = request.method.lower()
            handler = getattr(view, method, None)
            
            if handler is None:
                from fastapi import HTTPException
                raise HTTPException(status_code=405, detail="Method not allowed")
            
            await view.check_permissions(request, method)
            path_params = request.path_params
            return await handler(request, db=db, **path_params)
        
        self.add_api_route(
            path,
            endpoint,
            methods=methods,
            tags=tags,
            **kwargs,
        )


class AutoRouter:
    """
    Router automático que descobre e registra ViewSets.
    
    Similar ao DefaultRouter do DRF.
    
    Exemplo:
        auto_router = AutoRouter()
        auto_router.register("/users", UserViewSet)
        auto_router.register("/posts", PostViewSet)
        
        app.include_router(auto_router.router)
    """
    
    def __init__(
        self,
        prefix: str = "",
        tags: list[str] | None = None,
    ) -> None:
        self.router = Router(prefix=prefix, tags=tags or [])
        self._registry: list[tuple[str, type, dict[str, Any]]] = []
    
    def register(
        self,
        prefix: str,
        viewset_class: type["ViewSet"],
        basename: str | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """
        Registra um ViewSet.
        
        Args:
            prefix: Prefixo da URL
            viewset_class: Classe do ViewSet
            basename: Nome base para as rotas
            tags: Tags para OpenAPI
        """
        self._registry.append((prefix, viewset_class, {
            "basename": basename,
            "tags": tags,
        }))
        self.router.register_viewset(prefix, viewset_class, basename, tags)
    
    def register_view(
        self,
        path: str,
        view_class: type["APIView"],
        **kwargs: Any,
    ) -> None:
        """Registra uma APIView."""
        self.router.register_view(path, view_class, **kwargs)
    
    def include_router(
        self,
        router: "AutoRouter | Router",
        prefix: str = "",
        tags: list[str] | None = None,
    ) -> None:
        """
        Inclui outro router neste router.
        
        Args:
            router: Router a incluir (AutoRouter ou Router)
            prefix: Prefixo adicional para as rotas
            tags: Tags adicionais para OpenAPI
        """
        # Se for AutoRouter, pega o router interno
        if isinstance(router, AutoRouter):
            inner_router = router.router
        else:
            inner_router = router
        
        # Inclui no router interno
        self.router.include_router(inner_router, prefix=prefix, tags=tags or [])
    
    @property
    def urls(self) -> list[dict[str, Any]]:
        """Retorna lista de URLs registradas."""
        return [
            {
                "path": route.path,
                "name": route.name,
                "methods": route.methods,
            }
            for route in self.router.routes
        ]
    
    def get_api_root_view(self) -> Callable:
        """
        Retorna uma view que lista todas as URLs da API.
        
        Similar ao api_root do DRF.
        """
        registry = self._registry
        
        async def api_root(request: Request) -> dict[str, str]:
            return {
                basename or viewset.__name__.lower(): str(request.url_for(f"{basename or viewset.__name__.lower()}-list"))
                for prefix, viewset, opts in registry
                for basename in [opts.get("basename")]
            }
        
        return api_root


def include_router(
    app_or_router: Any,
    router: Router | AutoRouter,
    prefix: str = "",
    tags: list[str] | None = None,
) -> None:
    """
    Inclui um router em uma aplicação ou outro router.
    
    Função utilitária para simplificar a inclusão de routers.
    
    Args:
        app_or_router: FastAPI app ou APIRouter
        router: Router ou AutoRouter a incluir
        prefix: Prefixo adicional
        tags: Tags adicionais
    """
    actual_router = router.router if isinstance(router, AutoRouter) else router
    app_or_router.include_router(actual_router, prefix=prefix, tags=tags or [])
