"""
Sistema de Views inspirado no DRF.

Características:
- APIView para views baseadas em classe
- ViewSet para CRUD completo
- ModelViewSet para operações automáticas
- Integração nativa com FastAPI
- Permissões por view/action
- Serialização automática
"""

from __future__ import annotations

from typing import Any, ClassVar, Generic, TypeVar, get_type_hints
from collections.abc import Sequence

from fastapi import APIRouter, Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies import get_db, DatabaseSession
from core.permissions import Permission, AllowAny, check_permissions
from core.serializers import (
    InputSchema,
    OutputSchema,
    Serializer,
    ModelSerializer,
    PaginatedResponse,
)
from core.querysets import DoesNotExist

# Type vars
ModelT = TypeVar("ModelT")
InputT = TypeVar("InputT", bound=InputSchema)
OutputT = TypeVar("OutputT", bound=OutputSchema)


class APIView:
    """
    View baseada em classe, similar ao DRF APIView.
    
    Define handlers para métodos HTTP (get, post, put, patch, delete).
    
    Exemplo:
        class UserDetailView(APIView):
            permission_classes = [IsAuthenticated]
            
            async def get(self, request: Request, user_id: int, db: AsyncSession) -> dict:
                user = await User.objects.using(db).get(id=user_id)
                return UserOutput.model_validate(user).model_dump()
            
            async def delete(self, request: Request, user_id: int, db: AsyncSession) -> dict:
                user = await User.objects.using(db).get(id=user_id)
                await user.delete(db)
                return {"message": "User deleted"}
    """
    
    # Permissões aplicadas a todos os métodos
    permission_classes: ClassVar[list[type[Permission]]] = [AllowAny]
    
    # Permissões por método HTTP
    permission_classes_by_method: ClassVar[dict[str, list[type[Permission]]]] = {}
    
    # Tags para OpenAPI
    tags: ClassVar[list[str]] = []
    
    def get_permissions(self, method: str) -> list[Permission]:
        """Retorna instâncias de permissões para o método."""
        perm_classes = self.permission_classes_by_method.get(
            method.upper(),
            self.permission_classes,
        )
        return [perm() for perm in perm_classes]
    
    async def check_permissions(self, request: Request, method: str) -> None:
        """Verifica permissões antes de executar o handler."""
        permissions = self.get_permissions(method)
        await check_permissions(permissions, request, self)
    
    async def check_object_permissions(
        self,
        request: Request,
        obj: Any,
        method: str,
    ) -> None:
        """Verifica permissões para um objeto específico."""
        permissions = self.get_permissions(method)
        await check_permissions(permissions, request, self, obj)
    
    # Métodos HTTP (sobrescreva conforme necessário)
    async def get(self, request: Request, **kwargs: Any) -> Any:
        raise HTTPException(status_code=405, detail="Method not allowed")
    
    async def post(self, request: Request, **kwargs: Any) -> Any:
        raise HTTPException(status_code=405, detail="Method not allowed")
    
    async def put(self, request: Request, **kwargs: Any) -> Any:
        raise HTTPException(status_code=405, detail="Method not allowed")
    
    async def patch(self, request: Request, **kwargs: Any) -> Any:
        raise HTTPException(status_code=405, detail="Method not allowed")
    
    async def delete(self, request: Request, **kwargs: Any) -> Any:
        raise HTTPException(status_code=405, detail="Method not allowed")
    
    @classmethod
    def as_route(
        cls,
        path: str,
        methods: list[str] | None = None,
        **route_kwargs: Any,
    ) -> tuple[str, Any, dict[str, Any]]:
        """
        Converte a view em uma rota FastAPI.
        
        Retorna tupla (path, endpoint, kwargs) para registro no router.
        """
        view = cls()
        methods = methods or ["GET", "POST", "PUT", "PATCH", "DELETE"]
        
        async def endpoint(
            request: Request,
            db: AsyncSession = Depends(get_db),
            **kwargs: Any,
        ) -> Any:
            method = request.method.lower()
            handler = getattr(view, method, None)
            
            if handler is None:
                raise HTTPException(status_code=405, detail="Method not allowed")
            
            await view.check_permissions(request, method)
            return await handler(request, db=db, **kwargs)
        
        return path, endpoint, {"methods": methods, "tags": cls.tags, **route_kwargs}


class ViewSet(Generic[ModelT, InputT, OutputT]):
    """
    ViewSet para operações CRUD.
    
    Define actions: list, retrieve, create, update, partial_update, destroy.
    
    Exemplo:
        class UserViewSet(ViewSet[User, UserInput, UserOutput]):
            model = User
            serializer_class = UserSerializer
            permission_classes = [IsAuthenticated]
            
            # Customizar queryset
            def get_queryset(self, db: AsyncSession):
                return User.objects.using(db).filter(is_active=True)
    """
    
    # Model e serializer
    model: ClassVar[type]
    serializer_class: ClassVar[type[Serializer]] | None = None
    input_schema: ClassVar[type[InputSchema]] | None = None
    output_schema: ClassVar[type[OutputSchema]] | None = None
    
    # Permissões
    permission_classes: ClassVar[list[type[Permission]]] = [AllowAny]
    permission_classes_by_action: ClassVar[dict[str, list[type[Permission]]]] = {}
    
    # Configurações
    lookup_field: ClassVar[str] = "id"
    lookup_url_kwarg: ClassVar[str | None] = None
    
    # Paginação
    page_size: ClassVar[int] = 20
    max_page_size: ClassVar[int] = 100
    
    # Tags para OpenAPI
    tags: ClassVar[list[str]] = []
    
    def __init__(self) -> None:
        self.action: str | None = None
        self.request: Request | None = None
        self.kwargs: dict[str, Any] = {}
    
    def get_permissions(self, action: str) -> list[Permission]:
        """Retorna instâncias de permissões para a action."""
        perm_classes = self.permission_classes_by_action.get(
            action,
            self.permission_classes,
        )
        return [perm() for perm in perm_classes]
    
    async def check_permissions(self, request: Request, action: str) -> None:
        """Verifica permissões antes de executar a action."""
        permissions = self.get_permissions(action)
        await check_permissions(permissions, request, self)
    
    async def check_object_permissions(
        self,
        request: Request,
        obj: Any,
        action: str,
    ) -> None:
        """Verifica permissões para um objeto específico."""
        permissions = self.get_permissions(action)
        await check_permissions(permissions, request, self, obj)
    
    def get_queryset(self, db: AsyncSession):
        """
        Retorna o queryset base.
        
        Sobrescreva para customizar filtros.
        """
        return self.model.objects.using(db)
    
    async def get_object(self, db: AsyncSession, **kwargs: Any) -> ModelT:
        """
        Retorna um objeto específico.
        
        Raises:
            HTTPException 404: Se não encontrado
        """
        lookup_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = kwargs.get(lookup_kwarg)
        
        if lookup_value is None:
            raise HTTPException(
                status_code=400,
                detail=f"Missing lookup parameter: {lookup_kwarg}",
            )
        
        try:
            obj = await self.get_queryset(db).filter(
                **{self.lookup_field: lookup_value}
            ).get()
            return obj
        except DoesNotExist:
            raise HTTPException(
                status_code=404,
                detail=f"{self.model.__name__} not found",
            )
    
    def get_serializer(self) -> Serializer:
        """Retorna instância do serializer."""
        if self.serializer_class:
            return self.serializer_class()
        raise NotImplementedError("Define serializer_class or override get_serializer")
    
    def get_input_schema(self) -> type[InputSchema]:
        """Retorna o schema de input."""
        if self.input_schema:
            return self.input_schema
        if self.serializer_class:
            return self.serializer_class.input_schema
        raise NotImplementedError("Define input_schema or serializer_class")
    
    def get_output_schema(self) -> type[OutputSchema]:
        """Retorna o schema de output."""
        if self.output_schema:
            return self.output_schema
        if self.serializer_class:
            return self.serializer_class.output_schema
        raise NotImplementedError("Define output_schema or serializer_class")
    
    # Actions CRUD
    async def list(
        self,
        request: Request,
        db: AsyncSession,
        page: int = 1,
        page_size: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Lista todos os objetos com paginação."""
        await self.check_permissions(request, "list")
        
        page_size = min(page_size or self.page_size, self.max_page_size)
        offset = (page - 1) * page_size
        
        queryset = self.get_queryset(db)
        total = await queryset.count()
        objects = await queryset.offset(offset).limit(page_size).all()
        
        output_schema = self.get_output_schema()
        items = [output_schema.model_validate(obj).model_dump() for obj in objects]
        
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size if page_size > 0 else 0,
        }
    
    async def retrieve(
        self,
        request: Request,
        db: AsyncSession,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Retorna um objeto específico."""
        await self.check_permissions(request, "retrieve")
        
        obj = await self.get_object(db, **kwargs)
        await self.check_object_permissions(request, obj, "retrieve")
        
        output_schema = self.get_output_schema()
        return output_schema.model_validate(obj).model_dump()
    
    async def create(
        self,
        request: Request,
        db: AsyncSession,
        data: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Cria um novo objeto."""
        await self.check_permissions(request, "create")
        
        input_schema = self.get_input_schema()
        validated_data = input_schema.model_validate(data)
        
        obj = self.model(**validated_data.model_dump())
        await obj.save(db)
        
        output_schema = self.get_output_schema()
        return output_schema.model_validate(obj).model_dump()
    
    async def update(
        self,
        request: Request,
        db: AsyncSession,
        data: dict[str, Any],
        partial: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Atualiza um objeto existente."""
        await self.check_permissions(request, "update")
        
        obj = await self.get_object(db, **kwargs)
        await self.check_object_permissions(request, obj, "update")
        
        input_schema = self.get_input_schema()
        validated_data = input_schema.model_validate(data)
        
        update_data = validated_data.model_dump(exclude_unset=partial)
        for field, value in update_data.items():
            setattr(obj, field, value)
        
        await obj.save(db)
        
        output_schema = self.get_output_schema()
        return output_schema.model_validate(obj).model_dump()
    
    async def partial_update(
        self,
        request: Request,
        db: AsyncSession,
        data: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Atualização parcial (PATCH)."""
        return await self.update(request, db, data, partial=True, **kwargs)
    
    async def destroy(
        self,
        request: Request,
        db: AsyncSession,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Deleta um objeto."""
        await self.check_permissions(request, "destroy")
        
        obj = await self.get_object(db, **kwargs)
        await self.check_object_permissions(request, obj, "destroy")
        
        await obj.delete(db)
        
        return {"message": f"{self.model.__name__} deleted successfully"}


class ModelViewSet(ViewSet[ModelT, InputT, OutputT]):
    """
    ViewSet completo para um Model.
    
    Fornece todas as operações CRUD automaticamente.
    
    Exemplo:
        class UserViewSet(ModelViewSet[User, UserInput, UserOutput]):
            model = User
            input_schema = UserInput
            output_schema = UserOutput
            permission_classes = [IsAuthenticated]
            
            # Customizar actions específicas
            permission_classes_by_action = {
                "destroy": [IsAdmin],
            }
    """
    pass


class ReadOnlyModelViewSet(ViewSet[ModelT, InputT, OutputT]):
    """
    ViewSet apenas para leitura (list e retrieve).
    
    Exemplo:
        class PublicUserViewSet(ReadOnlyModelViewSet[User, UserInput, UserOutput]):
            model = User
            output_schema = UserOutput
    """
    
    async def create(self, *args: Any, **kwargs: Any) -> Any:
        raise HTTPException(status_code=405, detail="Method not allowed")
    
    async def update(self, *args: Any, **kwargs: Any) -> Any:
        raise HTTPException(status_code=405, detail="Method not allowed")
    
    async def partial_update(self, *args: Any, **kwargs: Any) -> Any:
        raise HTTPException(status_code=405, detail="Method not allowed")
    
    async def destroy(self, *args: Any, **kwargs: Any) -> Any:
        raise HTTPException(status_code=405, detail="Method not allowed")


# Decorator para actions customizadas
def action(
    methods: list[str] | None = None,
    detail: bool = False,
    url_path: str | None = None,
    url_name: str | None = None,
    permission_classes: list[type[Permission]] | None = None,
    **kwargs: Any,
):
    """
    Decorator para definir actions customizadas em ViewSets.
    
    Exemplo:
        class UserViewSet(ModelViewSet):
            model = User
            
            @action(methods=["POST"], detail=True)
            async def activate(self, request: Request, db: AsyncSession, **kwargs):
                user = await self.get_object(db, **kwargs)
                user.is_active = True
                await user.save(db)
                return {"message": "User activated"}
    """
    def decorator(func):
        func.is_action = True
        func.methods = methods or ["GET"]
        func.detail = detail
        func.url_path = url_path or func.__name__
        func.url_name = url_name or func.__name__
        func.permission_classes = permission_classes
        func.kwargs = kwargs
        return func
    return decorator
