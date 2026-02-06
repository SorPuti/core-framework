"""
Sistema de Roteamento automático inspirado no DRF.

Características:
- Auto-registro de ViewSets
- Geração automática de rotas REST
- Nomes previsíveis
- OpenAPI consistente com schemas tipados para request/response
- Exportação rica para Postman (campos pré-configurados)
- Override manual quando necessário
- Integração nativa com FastAPI
"""

from __future__ import annotations

from typing import Any, ClassVar, Optional, TYPE_CHECKING
from collections.abc import Callable
import inspect

from fastapi import APIRouter, Request, Depends, Body
from pydantic import BaseModel, create_model
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies import get_db, get_optional_user
from core.serializers import (
    InputSchema,
    OutputSchema,
    PaginatedResponse,
    ErrorResponse,
    SuccessResponse,
    DeleteResponse,
    ValidationErrorResponse,
    NotFoundResponse,
    ConflictResponse,
)

if TYPE_CHECKING:
    from core.views import ViewSet, APIView


# =============================================================================
# Helpers para OpenAPI / Schema resolution
# =============================================================================

# Cache para modelos parciais (PATCH)
_partial_model_cache: dict[type, type] = {}


def _make_partial_model(schema: type[BaseModel]) -> type[BaseModel]:
    """
    Cria um modelo Pydantic com todos os campos opcionais.
    
    Usado para endpoints PATCH onde apenas alguns campos são enviados.
    O resultado é cacheado por classe de schema.
    
    Args:
        schema: Modelo Pydantic original com campos obrigatórios
    
    Returns:
        Novo modelo com todos os campos Optional e default None
    """
    if schema in _partial_model_cache:
        return _partial_model_cache[schema]
    
    fields = {}
    for field_name, field_info in schema.model_fields.items():
        annotation = field_info.annotation
        if annotation is not None:
            fields[field_name] = (Optional[annotation], None)
        else:
            fields[field_name] = (Optional[Any], None)
    
    partial_model = create_model(
        f"Partial{schema.__name__}",
        **fields,
    )
    
    _partial_model_cache[schema] = partial_model
    return partial_model


def _resolve_schemas(
    viewset_class: type,
) -> tuple[type[InputSchema] | None, type[OutputSchema] | None]:
    """
    Resolve input e output schemas a partir de uma classe ViewSet.
    
    Verifica atributos de classe primeiro, depois serializer_class.
    
    Returns:
        Tupla de (input_schema, output_schema), None para cada se não encontrado
    """
    input_schema = getattr(viewset_class, "input_schema", None)
    output_schema = getattr(viewset_class, "output_schema", None)
    
    serializer_class = getattr(viewset_class, "serializer_class", None)
    
    if not input_schema and serializer_class:
        input_schema = getattr(serializer_class, "input_schema", None)
    if not output_schema and serializer_class:
        output_schema = getattr(serializer_class, "output_schema", None)
    
    return input_schema, output_schema


def _build_error_responses(
    include_404: bool = False,
    include_409: bool = False,
    include_422: bool = True,
) -> dict[int, dict[str, Any]]:
    """
    Constrói respostas de erro comuns para documentação OpenAPI.
    
    Args:
        include_404: Incluir resposta 404 Not Found
        include_409: Incluir resposta 409 Conflict
        include_422: Incluir resposta 422 Validation Error
    
    Returns:
        Dict de status_code → schema para OpenAPI responses
    """
    responses: dict[int, dict[str, Any]] = {}
    
    if include_422:
        responses[422] = {
            "description": "Erro de validação nos dados enviados",
            "model": ValidationErrorResponse,
        }
    
    if include_404:
        responses[404] = {
            "description": "Recurso não encontrado",
            "model": NotFoundResponse,
        }
    
    if include_409:
        responses[409] = {
            "description": "Conflito - registro com valor duplicado",
            "model": ConflictResponse,
        }
    
    return responses


# =============================================================================
# Router
# =============================================================================

class Router(APIRouter):
    """
    Router estendido com funcionalidades extras.
    
    Compatível com FastAPI APIRouter, mas com métodos adicionais
    para registro de ViewSets com documentação OpenAPI rica.
    
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
        include_crud: bool | None = None,
    ) -> None:
        """
        Registra um ViewSet com rotas REST automáticas e OpenAPI tipado.
        
        Gera documentação OpenAPI completa com:
        - Request body schemas (campos de entrada tipados)
        - Response schemas (campos de saída tipados)
        - Modelo parcial automático para PATCH
        - Respostas de erro documentadas (422, 404, 409)
        
        Para ViewSet com model: cria rotas CRUD + actions customizadas.
        Para ViewSet sem model: cria apenas actions customizadas.
        
        Args:
            prefix: Prefixo da URL (ex: "/users")
            viewset_class: Classe do ViewSet
            basename: Nome base para as rotas (default: nome do model)
            tags: Tags para OpenAPI
            include_crud: Forçar criação de rotas CRUD (default: auto-detecta por model)
        """
        viewset = viewset_class()
        
        # Detecta se tem model (para decidir sobre CRUD routes)
        has_model = hasattr(viewset_class, "model") and viewset_class.model is not None
        
        # Auto-detecta include_crud baseado em model, ou usa valor explícito
        if include_crud is None:
            include_crud = has_model
        
        # Infer basename from model or class name
        if basename is None:
            model = getattr(viewset_class, "model", None)
            if model is not None:
                basename = getattr(model, "__tablename__", None) or model.__name__.lower()
            else:
                class_name = viewset_class.__name__
                basename = class_name.lower().replace("viewset", "").replace("view", "") or "api"
        
        tags = tags or viewset_class.tags or [basename]
        
        lookup_field = viewset_class.lookup_field
        lookup_url_kwarg = viewset_class.lookup_url_kwarg or lookup_field
        
        # Normaliza o prefixo
        prefix = prefix.rstrip("/")
        
        # Se não tem model e não forçou CRUD, registra apenas actions customizadas
        if not include_crud:
            self._register_custom_actions(
                prefix, viewset_class, basename, tags, lookup_url_kwarg,
                detail_filter=None  # Registra todas as actions
            )
            return
        
        # ==================================================================
        # Resolve schemas para documentação OpenAPI tipada
        # ==================================================================
        input_schema, output_schema = _resolve_schemas(viewset_class)
        partial_input_schema = _make_partial_model(input_schema) if input_schema else None
        
        # Response models
        list_response_model = PaginatedResponse[output_schema] if output_schema else None
        detail_response_model = output_schema
        
        # Nome do model para descrições
        model_cls = getattr(viewset_class, "model", None)
        model_label = model_cls.__name__ if model_cls else basename.title()
        
        # ==================================================================
        # 1. LIST (GET) - Lista paginada
        # ==================================================================
        async def list_route(
            request, db=Depends(get_db), _user=Depends(get_optional_user),
            page=1, page_size=viewset_class.page_size,
        ):
            vs = viewset_class()
            return await vs.list(request, db, page=page, page_size=page_size)
        
        # Annotations programáticas (bypass de __future__.annotations)
        list_route.__annotations__ = {
            "request": Request,
            "db": AsyncSession,
            "_user": Any,
            "page": int,
            "page_size": int,
        }
        
        self.add_api_route(
            f"{prefix}/",
            list_route,
            methods=["GET"],
            tags=tags,
            name=f"{basename}-list",
            summary=f"List {basename}s",
            description=(
                f"Retorna lista paginada de **{model_label}**.\n\n"
                f"Suporta paginação via query params `page` e `page_size`.\n"
                f"O `page_size` máximo é {viewset_class.max_page_size}."
            ),
            response_model=list_response_model,
            responses=_build_error_responses(include_422=False),
        )
        
        # ==================================================================
        # 2. CREATE (POST) - Criação com schema tipado
        # ==================================================================
        async def create_route(
            request, data=Body(...), db=Depends(get_db),
            _user=Depends(get_optional_user),
        ):
            vs = viewset_class()
            # Converte Pydantic model → dict para manter compatibilidade com ViewSet
            data_dict = data.model_dump() if hasattr(data, "model_dump") else data
            return await vs.create(request, db, data_dict)
        
        create_route.__annotations__ = {
            "request": Request,
            "data": input_schema if input_schema else dict[str, Any],
            "db": AsyncSession,
            "_user": Any,
        }
        
        self.add_api_route(
            f"{prefix}/",
            create_route,
            methods=["POST"],
            tags=tags,
            name=f"{basename}-create",
            summary=f"Create {basename}",
            description=f"Cria um novo **{model_label}**.",
            status_code=201,
            response_model=detail_response_model,
            responses=_build_error_responses(include_422=True, include_409=True),
        )
        
        # ==================================================================
        # 3. Actions detail=False (ANTES das rotas {id} para evitar conflitos)
        #    Ex: /users/me deve ser registrada antes de /users/{id}
        # ==================================================================
        self._register_custom_actions(
            prefix, viewset_class, basename, tags, lookup_url_kwarg,
            detail_filter=False  # Só registra detail=False
        )
        
        # ==================================================================
        # 4. RETRIEVE (GET detail) - Detalhes com response tipado
        # ==================================================================
        async def retrieve_route(
            request, db=Depends(get_db), _user=Depends(get_optional_user),
        ):
            vs = viewset_class()
            path_params = request.path_params
            return await vs.retrieve(request, db, **path_params)
        
        retrieve_route.__annotations__ = {
            "request": Request,
            "db": AsyncSession,
            "_user": Any,
        }
        
        self.add_api_route(
            f"{prefix}/{{{lookup_url_kwarg}}}",
            retrieve_route,
            methods=["GET"],
            tags=tags,
            name=f"{basename}-detail",
            summary=f"Get {basename} by {lookup_url_kwarg}",
            description=f"Retorna detalhes de um **{model_label}** específico pelo `{lookup_url_kwarg}`.",
            response_model=detail_response_model,
            responses=_build_error_responses(include_404=True, include_422=False),
        )
        
        # ==================================================================
        # 5. UPDATE (PUT) - Atualização completa com schema tipado
        # ==================================================================
        async def update_route(
            request, data=Body(...), db=Depends(get_db),
            _user=Depends(get_optional_user),
        ):
            vs = viewset_class()
            data_dict = data.model_dump() if hasattr(data, "model_dump") else data
            path_params = request.path_params
            return await vs.update(request, db, data_dict, **path_params)
        
        update_route.__annotations__ = {
            "request": Request,
            "data": input_schema if input_schema else dict[str, Any],
            "db": AsyncSession,
            "_user": Any,
        }
        
        self.add_api_route(
            f"{prefix}/{{{lookup_url_kwarg}}}",
            update_route,
            methods=["PUT"],
            tags=tags,
            name=f"{basename}-update",
            summary=f"Update {basename}",
            description=(
                f"Atualiza completamente um **{model_label}** existente.\n\n"
                f"Todos os campos obrigatórios devem ser enviados."
            ),
            response_model=detail_response_model,
            responses=_build_error_responses(
                include_404=True, include_409=True, include_422=True,
            ),
        )
        
        # ==================================================================
        # 6. PARTIAL UPDATE (PATCH) - Atualização parcial com modelo parcial
        # ==================================================================
        async def partial_update_route(
            request, data=Body(...), db=Depends(get_db),
            _user=Depends(get_optional_user),
        ):
            vs = viewset_class()
            # exclude_unset=True garante que só campos enviados sejam atualizados
            if hasattr(data, "model_dump"):
                data_dict = data.model_dump(exclude_unset=True)
            else:
                data_dict = data
            path_params = request.path_params
            return await vs.partial_update(request, db, data_dict, **path_params)
        
        partial_update_route.__annotations__ = {
            "request": Request,
            "data": partial_input_schema if partial_input_schema else dict[str, Any],
            "db": AsyncSession,
            "_user": Any,
        }
        
        self.add_api_route(
            f"{prefix}/{{{lookup_url_kwarg}}}",
            partial_update_route,
            methods=["PATCH"],
            tags=tags,
            name=f"{basename}-partial-update",
            summary=f"Partial update {basename}",
            description=(
                f"Atualiza parcialmente um **{model_label}**.\n\n"
                f"Apenas os campos enviados serão atualizados. "
                f"Campos omitidos permanecem inalterados."
            ),
            response_model=detail_response_model,
            responses=_build_error_responses(
                include_404=True, include_409=True, include_422=True,
            ),
        )
        
        # ==================================================================
        # 7. DELETE - Deleção com response tipado
        # ==================================================================
        async def destroy_route(
            request, db=Depends(get_db), _user=Depends(get_optional_user),
        ):
            vs = viewset_class()
            path_params = request.path_params
            return await vs.destroy(request, db, **path_params)
        
        destroy_route.__annotations__ = {
            "request": Request,
            "db": AsyncSession,
            "_user": Any,
        }
        
        self.add_api_route(
            f"{prefix}/{{{lookup_url_kwarg}}}",
            destroy_route,
            methods=["DELETE"],
            tags=tags,
            name=f"{basename}-delete",
            summary=f"Delete {basename}",
            description=f"Remove permanentemente um **{model_label}** pelo `{lookup_url_kwarg}`.",
            response_model=DeleteResponse,
            responses=_build_error_responses(include_404=True, include_422=False),
        )
        
        # ==================================================================
        # 8. Actions detail=True (DEPOIS das rotas {id})
        #    Ex: /users/{id}/activate
        # ==================================================================
        self._register_custom_actions(
            prefix, viewset_class, basename, tags, lookup_url_kwarg,
            detail_filter=True  # Só registra detail=True
        )
        
        # Guarda referência
        self._viewsets.append((prefix, viewset_class))
    
    def _register_custom_actions(
        self,
        prefix: str,
        viewset_class: type["ViewSet"],
        basename: str,
        tags: list[str],
        lookup_url_kwarg: str,
        detail_filter: bool | None = None,
    ) -> None:
        """
        Registra actions customizadas decoradas com @action.
        
        Suporta schemas tipados para request/response via parâmetros
        do decorator @action(input_schema=..., output_schema=...).
        
        Args:
            prefix: Prefixo da URL
            viewset_class: Classe do ViewSet
            basename: Nome base para as rotas
            tags: Tags para OpenAPI
            lookup_url_kwarg: Nome do parâmetro de URL para lookup
            detail_filter: Se especificado, filtra actions por detail:
                          - True: só registra actions com detail=True
                          - False: só registra actions com detail=False
                          - None: registra todas as actions
        """
        for name, method in inspect.getmembers(viewset_class, predicate=inspect.isfunction):
            if not getattr(method, "is_action", False):
                continue
            
            action_methods = method.methods
            detail = method.detail
            url_path = method.url_path
            
            # Filtra por detail se especificado
            if detail_filter is not None and detail != detail_filter:
                continue
            
            if detail:
                path = f"{prefix}/{{{lookup_url_kwarg}}}/{url_path}"
            else:
                path = f"{prefix}/{url_path}"
            
            # Resolve schemas da action (se definidos no decorator @action)
            action_input_schema = getattr(method, "action_input_schema", None)
            action_output_schema = getattr(method, "action_output_schema", None)
            
            # Cria endpoint para cada método HTTP
            for http_method in action_methods:
                route_name = f"{basename}-{name}"
                
                # Get action-specific permission_classes
                action_permission_classes = getattr(method, "permission_classes", None)
                
                # Determina se o método HTTP suporta body
                method_has_body = http_method.upper() in ("POST", "PUT", "PATCH")
                
                # Captura method em closure para evitar late binding
                def make_action_endpoint(
                    action_method: Callable,
                    perm_classes: list | None = None,
                    a_input_schema: type | None = None,
                    with_body: bool = True,
                ) -> Callable:
                    if with_body:
                        # Endpoint COM body (POST, PUT, PATCH)
                        async def action_endpoint(
                            request,
                            db=Depends(get_db),
                            _user=Depends(get_optional_user),
                            data=Body(None),
                        ):
                            vs = viewset_class()
                            
                            if perm_classes:
                                from core.permissions import check_permissions
                                perms = [p() if isinstance(p, type) else p for p in perm_classes]
                                await check_permissions(perms, request, vs)
                            
                            path_params = request.path_params
                            if data is not None:
                                data_dict = data.model_dump() if hasattr(data, "model_dump") else data
                                return await action_method(vs, request, db, data=data_dict, **path_params)
                            return await action_method(vs, request, db, **path_params)
                        
                        # Typed annotations para OpenAPI
                        if a_input_schema:
                            data_type = Optional[a_input_schema]
                        else:
                            data_type = Optional[dict[str, Any]]
                        
                        action_endpoint.__annotations__ = {
                            "request": Request,
                            "db": AsyncSession,
                            "_user": Any,
                            "data": data_type,
                        }
                    else:
                        # Endpoint SEM body (GET, DELETE) - limpo no OpenAPI
                        async def action_endpoint(
                            request,
                            db=Depends(get_db),
                            _user=Depends(get_optional_user),
                        ):
                            vs = viewset_class()
                            
                            if perm_classes:
                                from core.permissions import check_permissions
                                perms = [p() if isinstance(p, type) else p for p in perm_classes]
                                await check_permissions(perms, request, vs)
                            
                            path_params = request.path_params
                            return await action_method(vs, request, db, **path_params)
                        
                        action_endpoint.__annotations__ = {
                            "request": Request,
                            "db": AsyncSession,
                            "_user": Any,
                        }
                    
                    return action_endpoint
                
                self.add_api_route(
                    path,
                    make_action_endpoint(
                        method, action_permission_classes,
                        action_input_schema, with_body=method_has_body,
                    ),
                    methods=[http_method],
                    tags=tags,
                    name=route_name,
                    summary=f"{name.replace('_', ' ').title()}",
                    response_model=action_output_schema,
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
            _user: Any = Depends(get_optional_user),
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
