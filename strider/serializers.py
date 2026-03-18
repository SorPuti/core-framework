"""
Sistema de Serializers inspirado no DRF, mas baseado em Pydantic.

Características:
- Validação automática via Pydantic
- Separação clara entre Input e Output schemas
- Transformação de dados
- Exclusão de campos
- Validação customizada
- Suporte a campos computados (@computed_field)
- Suporte a campos computados com acesso ao ORM (@computed_orm_field)
- Zero overhead de reflexão
"""

from __future__ import annotations

from typing import Any, ClassVar, Generic, TypeVar, get_type_hints, Callable, Optional
from collections.abc import Sequence
from functools import wraps

from pydantic import BaseModel, ConfigDict, create_model, field_validator, model_validator, computed_field
from pydantic.functional_validators import BeforeValidator, AfterValidator

# Type vars para generics
ModelT = TypeVar("ModelT")
InputT = TypeVar("InputT", bound="InputSchema")
OutputT = TypeVar("OutputT", bound="OutputSchema")

# Mapa tipo SQLAlchemy -> tipo Python (para schemas gerados a partir do model)
_SA_TYPE_MAP: dict[str, type] = {
    "INTEGER": int, "BIGINT": int, "SMALLINT": int,
    "VARCHAR": str, "STRING": str, "TEXT": str, "CHAR": str,
    "BOOLEAN": bool, "FLOAT": float, "NUMERIC": float, "DECIMAL": float,
    "JSON": dict, "JSONB": dict,
}


def _py_type_for_column(col: Any) -> type:
    """Retorna tipo Python para uma coluna SQLAlchemy."""
    type_str = str(col.type).upper()
    for key, py_type in _SA_TYPE_MAP.items():
        if key in type_str:
            return py_type
    if "UUID" in type_str:
        from uuid import UUID
        return UUID
    if "DATETIME" in type_str or "TIMESTAMP" in type_str or "DATE" in type_str:
        from datetime import datetime
        return datetime
    return str


def build_schemas_from_model(
    model: type,
    fields: list[str] | None = None,
    read_only_fields: list[str] | None = None,
) -> tuple[type[InputSchema] | None, type[OutputSchema]]:
    """
    Gera InputSchema e OutputSchema a partir do model e listas de campos.
    Único ponto de definição: não é necessário criar classes InputSchema/OutputSchema separadas.

    Args:
        model: Classe do model SQLAlchemy
        fields: Nomes dos campos a expor. Se None, usa todas as colunas do model.
        read_only_fields: Campos só na saída (ex.: id, created_at). Não entram no input.

    Returns:
        (input_schema_class ou None, output_schema_class). input_schema é None quando
        não há campos graváveis (todos read_only ou só PK).
    """
    read_only = set(read_only_fields or [])
    table = getattr(model, "__table__", None)
    if table is None:
        raise ValueError(f"Model {getattr(model, '__name__', model)} não possui __table__")

    all_columns = {c.name: c for c in table.columns}
    if fields is not None:
        field_set = set(fields)
        cols = [(name, all_columns[name]) for name in fields if name in all_columns]
        if len(cols) < len(field_set):
            missing = field_set - set(all_columns)
            raise ValueError(f"Campos não encontrados no model {model.__name__}: {missing}")
    else:
        cols = list(all_columns.items())

    name = getattr(model, "__name__", "Model")
    out_fields: dict[str, tuple[Any, Any]] = {}
    in_fields: dict[str, tuple[Any, Any]] = {}

    for col_name, col in cols:
        py_type = _py_type_for_column(col)
        ann = py_type if not col.nullable else Optional[py_type]
        default = None if col.nullable else ...
        out_fields[col_name] = (ann, default)

        if col_name in read_only:
            continue
        if getattr(col, "primary_key", False):
            continue
        autoinc = getattr(col, "autoincrement", False)
        if autoinc is True:  # True = PK auto; "auto" = não aplicável, não pular
            continue
        in_ann = py_type if not col.nullable and col.default is None and col.server_default is None else Optional[py_type]
        in_default = None if (col.nullable or col.default is not None or col.server_default is not None) else ...
        in_fields[col_name] = (in_ann, in_default)

    input_cls: type[InputSchema] | None = None
    if in_fields:
        input_cls = create_model(
            f"{name}Input",
            __base__=InputSchema,
            **in_fields,
        )
    output_cls = create_model(
        f"{name}Output",
        __base__=OutputSchema,
        **out_fields,
    )
    return input_cls, output_cls


class InputSchema(BaseModel):
    """
    Schema base para dados de entrada (request body).
    
    Use para validar e transformar dados recebidos em requisições.
    
    Suporta @computed_field para campos calculados dinamicamente.
    
    Exemplo:
        class UserCreateInput(InputSchema):
            email: EmailStr
            password: str
            name: str
            
            @computed_field
            @property
            def name_upper(self) -> str:
                return self.name.upper()
            
            @field_validator("password")
            @classmethod
            def validate_password(cls, v: str) -> str:
                if len(v) < 8:
                    raise ValueError("Password must be at least 8 characters")
                return v
    """
    
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_default=True,
        extra="ignore",
        from_attributes=True,
    )
    
    # Suporte a filtros de listagem (similar ao DRF)
    list_include: ClassVar[set[str] | tuple[str, ...] | None] = None
    list_exclude: ClassVar[set[str] | tuple[str, ...] | None] = None
    
    @classmethod
    def _get_all_fields(cls) -> set[str]:
        """
        Retorna todos os campos disponíveis incluindo campos computados.
        """
        # Campos regulares do schema
        regular_fields = set(cls.model_fields.keys())
        
        # Campos computados (computed_fields)
        computed_fields = set(getattr(cls, '__computed_fields__', {}).keys())
        
        return regular_fields | computed_fields
    
    @classmethod
    def dump_for_list(cls, obj: Any, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Serializa um objeto para uso em resposta de listagem.
        Respeita list_include / list_exclude quando definidos no schema.
        Inclui campos computados (@computed_field) automaticamente.
        """
        data = cls.model_validate(obj, context=context).model_dump()
        
        list_exclude = getattr(cls, "list_exclude", None)
        list_include = getattr(cls, "list_include", None)
        
        if list_exclude:
            excl = set(list_exclude)
            data = {k: v for k, v in data.items() if k not in excl}
            
        if list_include is not None:
            incl = set(list_include)
            data = {k: v for k, v in data.items() if k in incl}
            
        return data
    
    @classmethod
    def dump_many(cls, objs: Sequence[Any], context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """
        Serializa uma lista de objetos.
        """
        return [cls.dump_for_list(obj, context=context) for obj in objs]


def computed_orm_field(func: Callable[[Any, Any], Any]) -> property:
    """
    Decorator para criar campos computados que precisam acessar o objeto ORM original.
    
    Diferente do @computed_field padrão do Pydantic, este decorator permite que o campo
    computado receba o objeto ORM original como parâmetro, permitindo acessar:
    - Relacionamentos do modelo
    - Métodos do modelo
    - Campos que não estão no schema
    
    Args:
        func: Função que recebe (self, orm_obj) e retorna o valor computado
        
    Example:
        class StrategyOutput(OutputSchema):
            @computed_orm_field
            def user_email(self, orm_obj: Strategy) -> str | None:
                # Acesso ao modelo ORM original!
                return orm_obj.user.email if orm_obj.user else None
            
            @computed_orm_field
            def config_summary(self, orm_obj: Strategy) -> dict[str, Any]:
                # Acesso a dados complexos do modelo
                return {
                    "precisao": orm_obj.config.general.precMin if orm_obj.config else None,
                    "retorno": orm_obj.config.general.retMin if orm_obj.config else None,
                }
    """
    func._is_computed_orm_field = True  # Marca para identificação posterior
    return property(func)


class OutputSchema(BaseModel):
    """
    Schema base para dados de saída (response body).
    
    Use para serializar dados retornados em respostas.
    
    Suporta campos computados de duas formas:
    1. @computed_field - Campos calculados a partir de dados já no schema
    2. @computed_orm_field - Campos calculados com acesso ao objeto ORM original
    
    Opções estilo Django para listagem (evita criar schema separado para list):
        list_include: se definido, apenas esses campos na resposta de list (GET lista).
        list_exclude: se definido, esses campos ficam de fora na listagem.
        Use dump_for_list(obj) para serializar um item da lista.
    
    Exemplo:
        class UserOutput(OutputSchema):
            id: int
            email: str
            name: str
            created_at: datetime
            
            # Campo computado simples (apenas dados do schema)
            @computed_field
            @property
            def display_name(self) -> str:
                return f"{self.name} <{self.email}>"
            
            # Campo computado com acesso ao ORM
            @computed_orm_field
            def tenant_name(self, orm_obj: User) -> str:
                return orm_obj.tenant.name if orm_obj.tenant else ""
            
            # Lista retorna só estes campos
            list_include = ("id", "name", "email", "display_name", "tenant_name", "created_at")
    """
    
    model_config = ConfigDict(
        from_attributes=True,
        validate_default=True,
    )
    
    list_include: ClassVar[set[str] | tuple[str, ...] | None] = None
    list_exclude: ClassVar[set[str] | tuple[str, ...] | None] = None
    
    # Armazena o objeto ORM original durante a serialização
    _orm_obj: Any = None
    
    @classmethod
    def _get_all_fields(cls) -> set[str]:
        """
        Retorna todos os campos disponíveis incluindo campos computados.
        """
        # Campos regulares do schema
        regular_fields = set(cls.model_fields.keys())
        
        # Campos computados do Pydantic (computed_fields)
        computed_fields = set(getattr(cls, '__computed_fields__', {}).keys())
        
        # Campos computados com acesso ao ORM
        orm_computed_fields = set()
        for attr_name in dir(cls):
            attr = getattr(cls, attr_name, None)
            if isinstance(attr, property) and hasattr(attr.fget, '_is_computed_orm_field'):
                orm_computed_fields.add(attr_name)
        
        return regular_fields | computed_fields | orm_computed_fields
    
    def get_orm_obj(self) -> Any:
        """
        Retorna o objeto ORM original usado para criar este schema.
        
        Útil em campos computados que precisam acessar dados fora do schema.
        
        Example:
            @computed_field
            @property
            def user_email(self) -> str | None:
                orm_obj = self.get_orm_obj()
                return orm_obj.user.email if orm_obj and orm_obj.user else None
        """
        return getattr(self, '_orm_obj', None)
    
    @classmethod
    def _process_computed_orm_fields(cls, instance: "OutputSchema", orm_obj: Any) -> dict[str, Any]:
        """
        Processa campos computados que precisam do objeto ORM.
        
        Identifica todos os @computed_orm_field e os chama com o objeto ORM.
        """
        result = {}
        for attr_name in dir(cls):
            attr = getattr(cls, attr_name, None)
            if isinstance(attr, property) and hasattr(attr.fget, '_is_computed_orm_field'):
                # Chama o método property com o objeto ORM
                try:
                    result[attr_name] = attr.fget(instance, orm_obj)
                except Exception as e:
                    # Em caso de erro, retorna None para não quebrar a serialização
                    result[attr_name] = None
        return result
    
    @classmethod
    def dump_for_list(cls, obj: Any) -> dict[str, Any]:
        """
        Serializa um objeto para uso em resposta de listagem.
        Respeita list_include / list_exclude quando definidos no schema.
        Inclui campos computados (@computed_field) automaticamente.
        Inclui campos computados com ORM (@computed_orm_field) automaticamente.
        """
        # Valida o objeto primeiro
        instance = cls.model_validate(obj)
        
        # Armazena referência ao objeto ORM
        instance._orm_obj = obj
        
        # Serializa usando mode='json' para garantir serialização correta
        data = instance.model_dump(
            mode='json',
            by_alias=False,
        )
        
        # Processa campos computados com acesso ao ORM
        orm_fields = cls._process_computed_orm_fields(instance, obj)
        data.update(orm_fields)
        
        list_exclude = getattr(cls, "list_exclude", None)
        list_include = getattr(cls, "list_include", None)
        
        if list_exclude:
            excl = set(list_exclude)
            data = {k: v for k, v in data.items() if k not in excl}
            
        if list_include is not None:
            incl = set(list_include)
            data = {k: v for k, v in data.items() if k in incl}
            
        return data
    
    @classmethod
    def dump_many(cls, objs: Sequence[Any]) -> list[dict[str, Any]]:
        """
        Serializa uma lista de objetos.
        """
        return [cls.dump_for_list(obj) for obj in objs]
    
    def to_dict(self, **kwargs: Any) -> dict[str, Any]:
        """
        Converte a instância para dict incluindo campos computados.
        """
        return self.model_dump(mode='json', **kwargs)
    
    @classmethod
    def from_orm(cls, obj: Any) -> "OutputSchema":
        """
        Cria uma instância do schema a partir de um objeto ORM.
        
        Equivalente ao .from_orm() do Pydantic v1.
        """
        return cls.model_validate(obj)  # type: ignore
    
    @classmethod
    def from_orm_list(cls, objects: Sequence[Any]) -> list["OutputSchema"]:
        """
        Cria uma lista de schemas a partir de objetos ORM.
        """
        return [cls.model_validate(obj) for obj in objects]


class Serializer(Generic[ModelT, InputT, OutputT]):
    """
    Serializer completo que combina Input e Output schemas.
    Ponto único de verdade para contrato de entrada e saída (input_cls / output_cls).
    Inspirado no ModelSerializer do DRF, mas sem magia.

    Exemplo:
        class UserSerializer(Serializer[User, UserCreateInput, UserOutput]):
            input_schema = UserCreateInput
            output_schema = UserOutput
            # input_cls/output_cls são aliases (opcional)
            input_cls = UserCreateInput
            output_cls = UserOutput
    """
    input_schema: ClassVar[type[InputSchema]]
    output_schema: ClassVar[type[OutputSchema]]
    # Aliases para Router/OpenAPI; quando não definidos, usam input_schema/output_schema
    input_cls: ClassVar[type[InputSchema] | None] = None
    output_cls: ClassVar[type[OutputSchema] | None] = None
    
    def __init__(self) -> None:
        self._validated_data: dict[str, Any] | None = None
    
    def _get_input_schema(self) -> type[InputSchema]:
        """Schema de input (input_cls ou input_schema)."""
        return self.input_cls or self.input_schema

    def _get_output_schema(self) -> type[OutputSchema]:
        """Schema de output (output_cls ou output_schema)."""
        return self.output_cls or self.output_schema

    def validate_input(self, data: dict[str, Any]) -> InputT:
        """
        Valida dados de entrada.

        Args:
            data: Dicionário com dados a validar

        Returns:
            Instância do input_schema validada

        Raises:
            ValidationError: Se os dados forem inválidos
        """
        validated = self._get_input_schema().model_validate(data)
        self._validated_data = validated.model_dump()
        return validated  # type: ignore
    
    def serialize(self, obj: ModelT) -> OutputT:
        """
        Serializa um objeto para o output_schema.

        Args:
            obj: Objeto a serializar (geralmente um Model)

        Returns:
            Instância do output_schema
        """
        return self._get_output_schema().model_validate(obj)  # type: ignore
    
    def serialize_many(self, objects: Sequence[ModelT]) -> list[OutputT]:
        """
        Serializa múltiplos objetos.
        
        Args:
            objects: Lista de objetos a serializar
            
        Returns:
            Lista de instâncias do output_schema
        """
        return [self.serialize(obj) for obj in objects]
    
    def to_dict(self, obj: ModelT) -> dict[str, Any]:
        """
        Serializa um objeto para dicionário.

        Args:
            obj: Objeto a serializar

        Returns:
            Dicionário com dados serializados
        """
        return self.serialize(obj).model_dump()

    def to_representation(self, obj: ModelT) -> dict[str, Any]:
        """
        Serializa um objeto para resposta (list/detail).
        Usa dump_for_list do output_schema (list_include/list_exclude, @computed_orm_field).
        Ponto único de serialização para ViewSet.
        """
        return self._get_output_schema().dump_for_list(obj)

    def to_representation_many(
        self, objects: Sequence[ModelT]
    ) -> list[dict[str, Any]]:
        """Serializa múltiplos objetos para resposta (ex.: listagem)."""
        return [self.to_representation(obj) for obj in objects]
    
    def to_dict_many(self, objects: Sequence[ModelT]) -> list[dict[str, Any]]:
        """
        Serializa múltiplos objetos para dicionários.
        
        Args:
            objects: Lista de objetos a serializar
            
        Returns:
            Lista de dicionários
        """
        return [self.to_dict(obj) for obj in objects]


class ModelSerializer(Serializer[ModelT, InputT, OutputT]):
    """
    Serializer com operações CRUD integradas.
    
    Exemplo:
        class UserSerializer(ModelSerializer[User, UserInput, UserOutput]):
            model = User
            input_schema = UserInput
            output_schema = UserOutput
            
            # Campos a excluir na criação
            exclude_on_create = ["id", "created_at"]
            
            # Campos a excluir na atualização
            exclude_on_update = ["id", "email"]
    """
    
    model: ClassVar[type]
    exclude_on_create: ClassVar[list[str]] = []
    exclude_on_update: ClassVar[list[str]] = []
    read_only_fields: ClassVar[list[str]] = []
    
    async def create(self, data: InputT, session: Any) -> ModelT:
        """
        Cria um novo registro.
        
        Args:
            data: Dados validados
            session: Sessão do banco de dados
            
        Returns:
            Instância do model criada
        """
        create_data = data.model_dump(exclude=set(self.exclude_on_create))
        instance = self.model(**create_data)
        await instance.save(session)
        return instance  # type: ignore
    
    async def update(
        self,
        instance: ModelT,
        data: InputT,
        session: Any,
        partial: bool = False,
    ) -> ModelT:
        """
        Atualiza um registro existente.
        
        Args:
            instance: Instância a atualizar
            data: Dados validados
            session: Sessão do banco de dados
            partial: Se True, permite atualização parcial
            
        Returns:
            Instância atualizada
        """
        exclude = set(self.exclude_on_update + self.read_only_fields)
        update_data = data.model_dump(
            exclude=exclude,
            exclude_unset=partial,
        )
        
        for field, value in update_data.items():
            setattr(instance, field, value)
        
        await instance.save(session)  # type: ignore
        return instance


class UnifiedModelSerializer(ModelSerializer[ModelT, InputSchema, OutputSchema]):
    """
    Serializer com contrato centralizado: input e output derivados do model.
    Não é necessário definir InputSchema nem OutputSchema; eles são gerados a partir
    de `fields` e `read_only_fields`.

    Exemplo:
        class PostSerializer(UnifiedModelSerializer):
            model = Post
            fields = ["id", "title", "content", "published", "created_at"]
            read_only_fields = ["id", "created_at"]

        class PostViewSet(ModelViewSet):
            model = Post
            serializer_class = PostSerializer
    """
    model: ClassVar[type]
    fields: ClassVar[list[str]] = []
    read_only_fields: ClassVar[list[str]] = []
    input_schema: ClassVar[type[InputSchema] | None] = None
    output_schema: ClassVar[type[OutputSchema] | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        model = getattr(cls, "model", None)
        fields_list = getattr(cls, "fields", None) or []
        if not model or not fields_list:
            return
        if getattr(cls, "input_schema", None) is not None and getattr(cls, "output_schema", None) is not None:
            return
        try:
            input_cls, output_cls = build_schemas_from_model(
                model,
                fields=fields_list,
                read_only_fields=list(getattr(cls, "read_only_fields", None) or []),
            )
            if input_cls is not None:
                cls.input_schema = input_cls  # type: ignore[assignment]
            cls.output_schema = output_cls  # type: ignore[assignment]
        except Exception:
            pass

    def _get_input_schema(self) -> type[InputSchema]:
        if self.input_schema is None:
            raise RuntimeError(
                f"{self.__class__.__name__}: defina 'fields' e 'model' com pelo menos um campo gravável, "
                "ou atribua 'input_schema' explicitamente."
            )
        return self.input_schema

    def _get_output_schema(self) -> type[OutputSchema]:
        if self.output_schema is None:
            raise RuntimeError(f"{self.__class__.__name__}: defina 'fields' e 'model' ou atribua 'output_schema'.")
        return self.output_schema


# =========================================================================
# Schemas utilitários comuns (herdam de OutputSchema para compatibilidade)
# =========================================================================

class PaginatedResponse(OutputSchema, Generic[OutputT]):
    """
    Schema para respostas paginadas.
    
    Herda de OutputSchema para ser compatível com response_model
    do ViewSet e validação automática de schemas.
    
    Exemplo:
        @router.get("/users", response_model=PaginatedResponse[UserOutput])
        async def list_users(...):
            return PaginatedResponse(
                items=users,
                total=total_count,
                page=page,
                page_size=page_size,
            )
    """
    
    items: list[OutputT]
    total: int
    page: int
    page_size: int
    pages: int | None = None
    
    def model_post_init(self, __context: Any) -> None:
        if self.pages is None and self.page_size > 0:
            self.pages = (self.total + self.page_size - 1) // self.page_size


class ErrorResponse(OutputSchema):
    """Schema padrão para respostas de erro."""
    
    detail: str
    code: str | None = None
    errors: list[dict[str, Any]] | None = None


class ValidationErrorDetail(OutputSchema):
    """Detalhe de um erro de validação individual."""
    
    loc: list[str | int]
    msg: str
    type: str
    input: Any | None = None


class ValidationErrorResponse(OutputSchema):
    """Schema para respostas de erro de validação (422)."""
    
    detail: str = "Validation error"
    code: str = "validation_error"
    errors: list[ValidationErrorDetail]


class NotFoundResponse(OutputSchema):
    """Schema para respostas de recurso não encontrado (404)."""
    
    detail: str


class ConflictResponse(OutputSchema):
    """Schema para respostas de conflito/duplicidade (409)."""
    
    detail: str
    code: str = "unique_constraint"
    field: str | None = None
    value: str | None = None


class SuccessResponse(OutputSchema):
    """Schema padrão para respostas de sucesso simples."""
    
    message: str
    data: dict[str, Any] | None = None


class DeleteResponse(OutputSchema):
    """Schema para resposta de deleção bem-sucedida."""
    
    message: str


# Decorators para validação customizada
def validate_field(field_name: str):
    """
    Decorator para criar validadores de campo.
    
    Exemplo:
        class UserInput(InputSchema):
            email: str
            
            @validate_field("email")
            @classmethod
            def validate_email(cls, v: str) -> str:
                if "@" not in v:
                    raise ValueError("Invalid email")
                return v.lower()
    """
    return field_validator(field_name)


def validate_model(mode: str = "after"):
    """
    Decorator para criar validadores de modelo.
    
    Exemplo:
        class UserInput(InputSchema):
            password: str
            password_confirm: str
            
            @validate_model()
            def passwords_match(self) -> "UserInput":
                if self.password != self.password_confirm:
                    raise ValueError("Passwords don't match")
                return self
    """
    return model_validator(mode=mode)


# Exportar decorators e classes principais
__all__ = [
    "InputSchema",
    "OutputSchema",
    "Serializer",
    "ModelSerializer",
    "UnifiedModelSerializer",
    "build_schemas_from_model",
    "PaginatedResponse",
    "ErrorResponse",
    "ValidationErrorResponse",
    "ValidationErrorDetail",
    "NotFoundResponse",
    "ConflictResponse",
    "SuccessResponse",
    "DeleteResponse",
    "computed_field",
    "computed_orm_field",
    "validate_field",
    "validate_model",
]
