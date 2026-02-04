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

# Registry for viewsets pending validation
_pending_viewsets: set[type] = set()


def validate_pending_viewsets(*, strict: bool | None = None) -> list[str]:
    """
    Validate all pending viewsets.
    
    Called automatically during application startup.
    
    Args:
        strict: Override strict mode. If None, uses each viewset's setting.
    
    Returns:
        List of all validation issues found
    """
    import logging
    logger = logging.getLogger("core.views")
    
    if not _pending_viewsets:
        return []
    
    logger.debug(f"Validating {len(_pending_viewsets)} viewsets...")
    
    all_issues: list[str] = []
    
    for viewset_cls in list(_pending_viewsets):
        try:
            vs_strict = strict if strict is not None else viewset_cls.strict_validation
            
            # Temporarily set strict mode
            original_strict = viewset_cls.strict_validation
            viewset_cls.strict_validation = vs_strict
            
            issues = viewset_cls._validate_schemas()
            all_issues.extend(issues)
            
            # Restore
            viewset_cls.strict_validation = original_strict
            
        except Exception as e:
            all_issues.append(f"{viewset_cls.__name__}: {e}")
    
    _pending_viewsets.clear()
    
    if all_issues:
        logger.warning(f"ViewSet validation found {len(all_issues)} issues")
    else:
        logger.debug("ViewSet validation passed")
    
    return all_issues


# =============================================================================
# Decorator para actions customizadas
# =============================================================================

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


# =============================================================================
# Views
# =============================================================================

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
    
    # Schema/Model Validation
    # Se True, valida schemas contra model no startup (falha em DEBUG)
    strict_validation: ClassVar[bool] = True
    # Cache de validação
    _schema_validated: ClassVar[bool] = False
    
    def __init_subclass__(cls, **kwargs: Any) -> None:
        """
        Called when a ViewSet subclass is created.
        
        Registers the viewset for startup validation.
        """
        super().__init_subclass__(**kwargs)
        cls._schema_validated = False
        # Register for lazy validation
        _pending_viewsets.add(cls)
    
    @classmethod
    def _validate_schemas(cls) -> list[str]:
        """
        Validate schemas against model.
        
        Called automatically on application startup or first request.
        
        Returns:
            List of validation issues found
        
        Raises:
            SchemaModelMismatchError: If strict_validation=True and critical issues
        """
        if cls._schema_validated:
            return []
        
        model = getattr(cls, "model", None)
        if not model:
            cls._schema_validated = True
            return []
        
        try:
            from core.validation import SchemaModelValidator
            
            issues = SchemaModelValidator.validate_viewset(
                cls,
                strict=cls.strict_validation,
            )
            
            cls._schema_validated = True
            return issues
        except Exception as e:
            import logging
            logging.getLogger("core.views").warning(
                f"Could not validate {cls.__name__}: {e}"
            )
            cls._schema_validated = True
            return []
    
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
        
        Detecta automaticamente o tipo do campo no modelo e converte
        o valor de string (vindo da URL) para o tipo apropriado.
        
        Tipos suportados:
        - Integer (int, Integer, BigInteger, SmallInteger)
        - UUID (uuid.UUID, UUID)
        - String (str, String, Text) - sem conversão
        
        Raises:
            HTTPException 400: Se o valor não puder ser convertido
        """
        import uuid
        from sqlalchemy import Integer, BigInteger, SmallInteger, String, Text
        from sqlalchemy.dialects.postgresql import UUID as PG_UUID
        
        # Se não for string, retorna como está
        if not isinstance(value, str):
            return value
        
        # Tenta obter o tipo do campo do modelo
        field_type = self._get_lookup_field_type()
        
        if field_type is None:
            # Fallback: tenta int se for campo 'id'
            if self.lookup_field == "id":
                try:
                    return int(value)
                except (ValueError, TypeError):
                    self._raise_invalid_lookup_error(value, "integer")
            return value
        
        # Converte baseado no tipo do campo
        type_name = type(field_type).__name__
        
        # Tipos inteiros
        if isinstance(field_type, (Integer, BigInteger, SmallInteger)) or type_name in ('Integer', 'BigInteger', 'SmallInteger'):
            try:
                return int(value)
            except (ValueError, TypeError):
                self._raise_invalid_lookup_error(value, "integer")
        
        # UUID
        if type_name in ('UUID', 'GUID') or isinstance(field_type, PG_UUID):
            try:
                return uuid.UUID(value)
            except (ValueError, TypeError):
                self._raise_invalid_lookup_error(value, "UUID")
        
        # String - sem conversão necessária
        if isinstance(field_type, (String, Text)) or type_name in ('String', 'Text', 'VARCHAR'):
            return value
        
        # Tipo desconhecido - retorna como está
        return value
    
    def _get_lookup_field_type(self) -> Any:
        """
        Obtém o tipo SQLAlchemy do campo de lookup.
        
        Returns:
            Tipo do campo ou None se não encontrado
        """
        try:
            # Obtém a coluna do modelo
            mapper = inspect(self.model)
            if self.lookup_field in mapper.columns:
                column = mapper.columns[self.lookup_field]
                return column.type
        except Exception:
            pass
        return None
    
    def _raise_invalid_lookup_error(self, value: Any, expected_type: str) -> None:
        """
        Levanta erro padronizado para valor de lookup inválido.
        
        Returns 422 Validation Error (not 500 Internal Server Error).
        
        Args:
            value: Valor recebido
            expected_type: Tipo esperado (para mensagem de erro)
        """
        raise HTTPException(
            status_code=422,
            detail={
                "error": "validation_error",
                "message": f"Invalid {self.lookup_field} format. Expected {expected_type}.",
                "errors": [
                    {
                        "loc": ["path", self.lookup_field],
                        "msg": f"Invalid {expected_type} format",
                        "type": f"{expected_type.lower()}_parsing",
                        "input": str(value),
                    }
                ],
                "field": self.lookup_field,
                "value": str(value),
                "expected_type": expected_type,
            }
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


# =============================================================================
# Presets de ViewSet
# =============================================================================

class CreateModelViewSet(ViewSet[ModelT, InputT, OutputT]):
    """
    ViewSet apenas para criação.
    
    Exemplo:
        class ContactFormViewSet(CreateModelViewSet):
            model = ContactMessage
            input_schema = ContactInput
            output_schema = ContactOutput
    """
    
    async def list(self, *args: Any, **kwargs: Any) -> Any:
        raise HTTPException(status_code=405, detail="Method not allowed")
    
    async def retrieve(self, *args: Any, **kwargs: Any) -> Any:
        raise HTTPException(status_code=405, detail="Method not allowed")
    
    async def update(self, *args: Any, **kwargs: Any) -> Any:
        raise HTTPException(status_code=405, detail="Method not allowed")
    
    async def partial_update(self, *args: Any, **kwargs: Any) -> Any:
        raise HTTPException(status_code=405, detail="Method not allowed")
    
    async def destroy(self, *args: Any, **kwargs: Any) -> Any:
        raise HTTPException(status_code=405, detail="Method not allowed")


class ListModelViewSet(ViewSet[ModelT, InputT, OutputT]):
    """
    ViewSet apenas para listagem.
    
    Exemplo:
        class PublicCategoryViewSet(ListModelViewSet):
            model = Category
            output_schema = CategoryOutput
    """
    
    async def create(self, *args: Any, **kwargs: Any) -> Any:
        raise HTTPException(status_code=405, detail="Method not allowed")
    
    async def retrieve(self, *args: Any, **kwargs: Any) -> Any:
        raise HTTPException(status_code=405, detail="Method not allowed")
    
    async def update(self, *args: Any, **kwargs: Any) -> Any:
        raise HTTPException(status_code=405, detail="Method not allowed")
    
    async def partial_update(self, *args: Any, **kwargs: Any) -> Any:
        raise HTTPException(status_code=405, detail="Method not allowed")
    
    async def destroy(self, *args: Any, **kwargs: Any) -> Any:
        raise HTTPException(status_code=405, detail="Method not allowed")


class ListCreateModelViewSet(ViewSet[ModelT, InputT, OutputT]):
    """
    ViewSet para listagem e criação.
    
    Exemplo:
        class CommentViewSet(ListCreateModelViewSet):
            model = Comment
            input_schema = CommentInput
            output_schema = CommentOutput
    """
    
    async def retrieve(self, *args: Any, **kwargs: Any) -> Any:
        raise HTTPException(status_code=405, detail="Method not allowed")
    
    async def update(self, *args: Any, **kwargs: Any) -> Any:
        raise HTTPException(status_code=405, detail="Method not allowed")
    
    async def partial_update(self, *args: Any, **kwargs: Any) -> Any:
        raise HTTPException(status_code=405, detail="Method not allowed")
    
    async def destroy(self, *args: Any, **kwargs: Any) -> Any:
        raise HTTPException(status_code=405, detail="Method not allowed")


class RetrieveUpdateModelViewSet(ViewSet[ModelT, InputT, OutputT]):
    """
    ViewSet para recuperar e atualizar (sem delete).
    
    Exemplo:
        class ProfileViewSet(RetrieveUpdateModelViewSet):
            model = Profile
            input_schema = ProfileInput
            output_schema = ProfileOutput
    """
    
    async def list(self, *args: Any, **kwargs: Any) -> Any:
        raise HTTPException(status_code=405, detail="Method not allowed")
    
    async def create(self, *args: Any, **kwargs: Any) -> Any:
        raise HTTPException(status_code=405, detail="Method not allowed")
    
    async def destroy(self, *args: Any, **kwargs: Any) -> Any:
        raise HTTPException(status_code=405, detail="Method not allowed")


class RetrieveDestroyModelViewSet(ViewSet[ModelT, InputT, OutputT]):
    """
    ViewSet para recuperar e deletar.
    
    Exemplo:
        class NotificationViewSet(RetrieveDestroyModelViewSet):
            model = Notification
            output_schema = NotificationOutput
    """
    
    async def list(self, *args: Any, **kwargs: Any) -> Any:
        raise HTTPException(status_code=405, detail="Method not allowed")
    
    async def create(self, *args: Any, **kwargs: Any) -> Any:
        raise HTTPException(status_code=405, detail="Method not allowed")
    
    async def update(self, *args: Any, **kwargs: Any) -> Any:
        raise HTTPException(status_code=405, detail="Method not allowed")
    
    async def partial_update(self, *args: Any, **kwargs: Any) -> Any:
        raise HTTPException(status_code=405, detail="Method not allowed")


class RetrieveUpdateDestroyModelViewSet(ViewSet[ModelT, InputT, OutputT]):
    """
    ViewSet para operações em item individual (sem list/create).
    
    Exemplo:
        class SettingsViewSet(RetrieveUpdateDestroyModelViewSet):
            model = UserSettings
            input_schema = SettingsInput
            output_schema = SettingsOutput
    """
    
    async def list(self, *args: Any, **kwargs: Any) -> Any:
        raise HTTPException(status_code=405, detail="Method not allowed")
    
    async def create(self, *args: Any, **kwargs: Any) -> Any:
        raise HTTPException(status_code=405, detail="Method not allowed")


class SearchModelViewSet(ModelViewSet[ModelT, InputT, OutputT]):
    """
    ModelViewSet com busca integrada.
    
    Atributos:
        search_fields: Campos para busca textual
        filter_fields: Campos para filtros exatos
        ordering_fields: Campos permitidos para ordenação
        default_ordering: Ordenação padrão
    
    Exemplo:
        class ProductViewSet(SearchModelViewSet):
            model = Product
            input_schema = ProductInput
            output_schema = ProductOutput
            search_fields = ["name", "description"]
            filter_fields = ["category_id", "is_active"]
            ordering_fields = ["name", "price", "created_at"]
            default_ordering = ["-created_at"]
    """
    
    search_fields: list[str] = []
    filter_fields: list[str] = []
    ordering_fields: list[str] = []
    default_ordering: list[str] = ["-id"]
    search_param: str = "q"
    
    async def list(
        self,
        request: Request,
        db: AsyncSession,
        page: int = 1,
        page_size: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Lista com busca, filtros e ordenação."""
        await self.check_permissions(request, "list")
        
        page_size = min(page_size or self.page_size, self.max_page_size)
        offset = (page - 1) * page_size
        
        queryset = self.get_queryset(db)
        
        # Aplicar busca textual
        search_query = request.query_params.get(self.search_param)
        if search_query and self.search_fields:
            queryset = self._apply_search(queryset, search_query)
        
        # Aplicar filtros
        queryset = self._apply_filters(queryset, request.query_params)
        
        # Aplicar ordenação
        ordering = request.query_params.get("ordering")
        queryset = self._apply_ordering(queryset, ordering)
        
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
    
    def _apply_search(self, queryset: Any, search_query: str) -> Any:
        """Aplica busca textual nos campos configurados."""
        from sqlalchemy import or_
        
        if not self.search_fields:
            return queryset
        
        conditions = []
        for field in self.search_fields:
            if hasattr(self.model, field):
                column = getattr(self.model, field)
                conditions.append(column.ilike(f"%{search_query}%"))
        
        if conditions:
            return queryset.filter(or_(*conditions))
        return queryset
    
    def _apply_filters(self, queryset: Any, params: Any) -> Any:
        """Aplica filtros exatos nos campos configurados."""
        for field in self.filter_fields:
            value = params.get(field)
            if value is not None:
                queryset = queryset.filter(**{field: value})
        return queryset
    
    def _apply_ordering(self, queryset: Any, ordering: str | None) -> Any:
        """Aplica ordenação."""
        if ordering:
            fields = ordering.split(",")
        else:
            fields = self.default_ordering
        
        for field in fields:
            desc = field.startswith("-")
            field_name = field.lstrip("-")
            
            if field_name not in self.ordering_fields and self.ordering_fields:
                continue
            
            if hasattr(self.model, field_name):
                column = getattr(self.model, field_name)
                if desc:
                    queryset = queryset.order_by(column.desc())
                else:
                    queryset = queryset.order_by(column.asc())
        
        return queryset


class BulkModelViewSet(ModelViewSet[ModelT, InputT, OutputT]):
    """
    ModelViewSet com operações em lote.
    
    Endpoints adicionais:
        POST /bulk-create - Criar múltiplos
        PATCH /bulk-update - Atualizar múltiplos
        DELETE /bulk-delete - Deletar múltiplos
    
    Exemplo:
        class ProductViewSet(BulkModelViewSet):
            model = Product
            input_schema = ProductInput
            output_schema = ProductOutput
            bulk_max_items = 100
    """
    
    bulk_max_items: int = 100
    
    @action(methods=["POST"], detail=False, url_path="bulk-create")
    async def bulk_create(
        self,
        request: Request,
        db: AsyncSession,
        data: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Cria múltiplos objetos de uma vez."""
        await self.check_permissions(request, "create")
        
        if not data:
            raise HTTPException(status_code=400, detail="No data provided")
        
        if len(data) > self.bulk_max_items:
            raise HTTPException(
                status_code=400,
                detail=f"Maximum {self.bulk_max_items} items allowed"
            )
        
        input_schema = self.get_input_schema()
        output_schema = self.get_output_schema()
        created = []
        errors = []
        
        for i, item_data in enumerate(data):
            try:
                validated = input_schema.model_validate(item_data)
                data_dict = validated.model_dump()
                validated_data = await self.validate_data(data_dict, db, instance=None)
                
                obj = self.model(**validated_data)
                await obj.save(db)
                created.append(output_schema.model_validate(obj).model_dump())
            except Exception as e:
                errors.append({"index": i, "error": str(e)})
        
        return {
            "created": created,
            "created_count": len(created),
            "errors": errors,
            "error_count": len(errors),
        }
    
    @action(methods=["PATCH"], detail=False, url_path="bulk-update")
    async def bulk_update(
        self,
        request: Request,
        db: AsyncSession,
        data: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Atualiza múltiplos objetos."""
        await self.check_permissions(request, "update")
        
        if not data:
            raise HTTPException(status_code=400, detail="No data provided")
        
        if len(data) > self.bulk_max_items:
            raise HTTPException(
                status_code=400,
                detail=f"Maximum {self.bulk_max_items} items allowed"
            )
        
        output_schema = self.get_output_schema()
        updated = []
        errors = []
        
        for i, item_data in enumerate(data):
            try:
                item_id = item_data.get(self.lookup_field)
                if not item_id:
                    errors.append({"index": i, "error": f"Missing {self.lookup_field}"})
                    continue
                
                obj = await self.get_object(db, **{self.lookup_field: item_id})
                
                update_data = {k: v for k, v in item_data.items() if k != self.lookup_field}
                for field, value in update_data.items():
                    if hasattr(obj, field):
                        setattr(obj, field, value)
                
                await obj.save(db)
                updated.append(output_schema.model_validate(obj).model_dump())
            except HTTPException as e:
                errors.append({"index": i, "error": e.detail})
            except Exception as e:
                errors.append({"index": i, "error": str(e)})
        
        return {
            "updated": updated,
            "updated_count": len(updated),
            "errors": errors,
            "error_count": len(errors),
        }
    
    @action(methods=["DELETE"], detail=False, url_path="bulk-delete")
    async def bulk_delete(
        self,
        request: Request,
        db: AsyncSession,
        data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Deleta múltiplos objetos por IDs."""
        await self.check_permissions(request, "destroy")
        
        if not data or "ids" not in data:
            raise HTTPException(status_code=400, detail="No ids provided")
        
        ids = data["ids"]
        if len(ids) > self.bulk_max_items:
            raise HTTPException(
                status_code=400,
                detail=f"Maximum {self.bulk_max_items} items allowed"
            )
        
        deleted = []
        errors = []
        
        for item_id in ids:
            try:
                obj = await self.get_object(db, **{self.lookup_field: item_id})
                await obj.delete(db)
                deleted.append(item_id)
            except HTTPException as e:
                errors.append({"id": item_id, "error": e.detail})
            except Exception as e:
                errors.append({"id": item_id, "error": str(e)})
        
        return {
            "deleted": deleted,
            "deleted_count": len(deleted),
            "errors": errors,
            "error_count": len(errors),
        }
