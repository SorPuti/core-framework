"""
Sistema de Views inspirado no DRF.

Características:
- APIView para views baseadas em classe
- ViewSet para CRUD completo
- ModelViewSet para operações automáticas
- Integração nativa com FastAPI
- Permissões por view/action
- Serialização automática
- Validação de unicidade automática
"""

from __future__ import annotations

from typing import Any, ClassVar, Generic, TypeVar, get_type_hints
from collections.abc import Sequence, Callable, Awaitable

from fastapi import APIRouter, Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import inspect

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
from core.validators import (
    ValidationError,
    UniqueValidationError,
    MultipleValidationErrors,
    UniqueValidator,
    AsyncValidator,
)

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
        ) -> Any:
            method = request.method.lower()
            handler = getattr(view, method, None)
            
            if handler is None:
                raise HTTPException(status_code=405, detail="Method not allowed")
            
            await view.check_permissions(request, method)
            return await handler(request, db=db)
        
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
            
            # Campos únicos para validação automática
            unique_fields = ["email", "username"]
            
            # Validadores customizados assíncronos
            async def validate_email(self, value, db, instance=None):
                # Validação customizada
                if value.endswith("@spam.com"):
                    raise ValidationError("Email domain not allowed", field="email")
                return value
            
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
    
    # Validação de unicidade automática
    # Lista de campos que devem ser únicos
    unique_fields: ClassVar[list[str]] = []
    
    # Validadores assíncronos customizados por campo
    # Formato: {"field_name": [validator1, validator2]}
    field_validators: ClassVar[dict[str, list[AsyncValidator]]] = {}
    
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
        from core.querysets import QuerySet
        return QuerySet(self.model, db)
    
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
        
        # Converte lookup_value para o tipo correto baseado no campo do modelo
        lookup_value = self._convert_lookup_value(lookup_value)
        
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
    
    def _convert_lookup_value(self, value: Any) -> Any:
        """
        Converte o valor de lookup para o tipo correto do campo.
        
        Por padrão, tenta converter para int se o lookup_field for 'id'.
        """
        if self.lookup_field == "id" and isinstance(value, str):
            try:
                return int(value)
            except (ValueError, TypeError):
                pass
        return value
    
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
    
    def get_unique_fields(self) -> list[str]:
        """
        Retorna lista de campos únicos para validação.
        
        Por padrão, detecta automaticamente do model se não definido.
        """
        if self.unique_fields:
            return self.unique_fields
        
        # Detecta automaticamente do model
        unique = []
        if hasattr(self.model, "__table__"):
            for column in self.model.__table__.columns:
                if column.unique and not column.primary_key:
                    unique.append(column.name)
        return unique
    
    async def validate_unique_fields(
        self,
        data: dict[str, Any],
        db: AsyncSession,
        instance: ModelT | None = None,
    ) -> None:
        """
        Valida unicidade dos campos antes de salvar.
        
        Args:
            data: Dados a validar
            db: Sessão do banco
            instance: Instância existente (para updates)
        
        Raises:
            UniqueValidationError: Se campo único já existe
            MultipleValidationErrors: Se múltiplos campos violam unicidade
        """
        errors = []
        unique_fields = self.get_unique_fields()
        
        for field_name in unique_fields:
            if field_name not in data:
                continue
            
            value = data[field_name]
            if value is None:
                continue
            
            # Verifica se já existe
            queryset = self.get_queryset(db).filter(**{field_name: value})
            
            # Exclui o registro atual se for update
            if instance is not None:
                pk = getattr(instance, self.lookup_field, None)
                if pk is not None:
                    queryset = queryset.exclude(**{self.lookup_field: pk})
            
            exists = await queryset.exists()
            
            if exists:
                errors.append(UniqueValidationError(
                    field=field_name,
                    value=value,
                    message=f"A record with this {field_name} already exists.",
                ))
        
        if len(errors) == 1:
            raise errors[0]
        elif len(errors) > 1:
            raise MultipleValidationErrors(errors)
    
    async def validate_field(
        self,
        field_name: str,
        value: Any,
        db: AsyncSession,
        instance: ModelT | None = None,
    ) -> Any:
        """
        Executa validadores customizados para um campo.
        
        Procura por método validate_{field_name} no ViewSet.
        """
        # Método customizado no ViewSet
        method_name = f"validate_{field_name}"
        if hasattr(self, method_name):
            method = getattr(self, method_name)
            result = method(value, db, instance=instance)
            if hasattr(result, "__await__"):
                value = await result
            else:
                value = result
        
        # Validadores registrados
        if field_name in self.field_validators:
            for validator in self.field_validators[field_name]:
                value = await validator(value, db)
        
        return value
    
    async def validate_data(
        self,
        data: dict[str, Any],
        db: AsyncSession,
        instance: ModelT | None = None,
    ) -> dict[str, Any]:
        """
        Executa todas as validações nos dados.
        
        1. Valida unicidade
        2. Executa validadores de campo
        3. Executa validate() geral
        
        Args:
            data: Dados validados pelo Pydantic
            db: Sessão do banco
            instance: Instância existente (para updates)
        
        Returns:
            Dados validados (possivelmente modificados)
        """
        errors = []
        
        # 1. Valida unicidade
        try:
            await self.validate_unique_fields(data, db, instance)
        except (UniqueValidationError, MultipleValidationErrors) as e:
            if isinstance(e, MultipleValidationErrors):
                errors.extend(e.errors)
            else:
                errors.append(e)
        
        # 2. Valida cada campo
        validated_data = {}
        for field_name, value in data.items():
            try:
                validated_data[field_name] = await self.validate_field(
                    field_name, value, db, instance
                )
            except ValidationError as e:
                errors.append(e)
        
        # 3. Validação geral
        try:
            validated_data = await self.validate(validated_data, db, instance)
        except ValidationError as e:
            errors.append(e)
        except MultipleValidationErrors as e:
            errors.extend(e.errors)
        
        if errors:
            if len(errors) == 1:
                raise errors[0]
            raise MultipleValidationErrors(errors)
        
        return validated_data
    
    async def validate(
        self,
        data: dict[str, Any],
        db: AsyncSession,
        instance: ModelT | None = None,
    ) -> dict[str, Any]:
        """
        Hook para validação customizada geral.
        
        Sobrescreva para adicionar validações cross-field.
        
        Exemplo:
            async def validate(self, data, db, instance=None):
                if data.get("start_date") > data.get("end_date"):
                    raise ValidationError(
                        "Start date must be before end date",
                        field="start_date"
                    )
                return data
        """
        return data
    
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
        
        # 1. Valida com Pydantic
        input_schema = self.get_input_schema()
        pydantic_validated = input_schema.model_validate(data)
        data_dict = pydantic_validated.model_dump()
        
        # 2. Valida unicidade e regras de negócio
        validated_data = await self.validate_data(data_dict, db, instance=None)
        
        # 3. Hook antes de criar
        validated_data = await self.perform_create_validation(validated_data, db)
        
        # 4. Cria o objeto
        obj = self.model(**validated_data)
        await obj.save(db)
        
        # 5. Hook após criar
        await self.after_create(obj, db)
        
        output_schema = self.get_output_schema()
        return output_schema.model_validate(obj).model_dump()
    
    async def perform_create_validation(
        self,
        data: dict[str, Any],
        db: AsyncSession,
    ) -> dict[str, Any]:
        """
        Hook para validação adicional antes de criar.
        
        Sobrescreva para adicionar lógica customizada.
        """
        return data
    
    async def after_create(self, obj: ModelT, db: AsyncSession) -> None:
        """
        Hook executado após criar o objeto.
        
        Útil para side effects como enviar emails, criar logs, etc.
        """
        pass
    
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
        
        # 1. Valida com Pydantic
        input_schema = self.get_input_schema()
        
        # Para partial update, mescla com dados existentes
        if partial:
            # Pega dados atuais do objeto
            current_data = {}
            for field in input_schema.model_fields:
                if hasattr(obj, field):
                    current_data[field] = getattr(obj, field)
            # Mescla com novos dados
            merged_data = {**current_data, **data}
            pydantic_validated = input_schema.model_validate(merged_data)
            data_dict = {k: v for k, v in pydantic_validated.model_dump().items() if k in data}
        else:
            pydantic_validated = input_schema.model_validate(data)
            data_dict = pydantic_validated.model_dump()
        
        # 2. Valida unicidade e regras de negócio
        validated_data = await self.validate_data(data_dict, db, instance=obj)
        
        # 3. Hook antes de atualizar
        validated_data = await self.perform_update_validation(validated_data, obj, db)
        
        # 4. Atualiza o objeto
        for field, value in validated_data.items():
            setattr(obj, field, value)
        
        await obj.save(db)
        
        # 5. Hook após atualizar
        await self.after_update(obj, db)
        
        output_schema = self.get_output_schema()
        return output_schema.model_validate(obj).model_dump()
    
    async def perform_update_validation(
        self,
        data: dict[str, Any],
        instance: ModelT,
        db: AsyncSession,
    ) -> dict[str, Any]:
        """
        Hook para validação adicional antes de atualizar.
        
        Sobrescreva para adicionar lógica customizada.
        """
        return data
    
    async def after_update(self, obj: ModelT, db: AsyncSession) -> None:
        """
        Hook executado após atualizar o objeto.
        
        Útil para side effects como invalidar cache, criar logs, etc.
        """
        pass
    
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
