"""
Sistema de Serializers inspirado no DRF, mas baseado em Pydantic.

Características:
- Validação automática via Pydantic
- Separação clara entre Input e Output schemas
- Transformação de dados
- Exclusão de campos
- Validação customizada
- Zero overhead de reflexão
"""

from __future__ import annotations

from typing import Any, ClassVar, Generic, TypeVar, get_type_hints
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from pydantic.functional_validators import BeforeValidator, AfterValidator

# Type vars para generics
ModelT = TypeVar("ModelT")
InputT = TypeVar("InputT", bound="InputSchema")
OutputT = TypeVar("OutputT", bound="OutputSchema")


class InputSchema(BaseModel):
    """
    Schema base para dados de entrada (request body).
    
    Use para validar e transformar dados recebidos em requisições.
    
    Exemplo:
        class UserCreateInput(InputSchema):
            email: EmailStr
            password: str
            name: str
            
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
        extra="forbid",
        from_attributes=True,
    )


class OutputSchema(BaseModel):
    """
    Schema base para dados de saída (response body).
    
    Use para serializar dados retornados em respostas.
    
    Exemplo:
        class UserOutput(OutputSchema):
            id: int
            email: str
            name: str
            created_at: datetime
            
            # Campos computados
            @computed_field
            @property
            def display_name(self) -> str:
                return f"{self.name} <{self.email}>"
    """
    
    model_config = ConfigDict(
        from_attributes=True,
        validate_default=True,
    )
    
    @classmethod
    def from_orm(cls, obj: Any) -> "OutputSchema":
        """
        Cria uma instância do schema a partir de um objeto ORM.
        
        Equivalente ao .from_orm() do Pydantic v1.
        """
        return cls.model_validate(obj)
    
    @classmethod
    def from_orm_list(cls, objects: Sequence[Any]) -> list["OutputSchema"]:
        """
        Cria uma lista de schemas a partir de objetos ORM.
        """
        return [cls.model_validate(obj) for obj in objects]


class Serializer(Generic[ModelT, InputT, OutputT]):
    """
    Serializer completo que combina Input e Output schemas.
    
    Inspirado no ModelSerializer do DRF, mas sem magia.
    
    Exemplo:
        class UserSerializer(Serializer[User, UserCreateInput, UserOutput]):
            input_schema = UserCreateInput
            output_schema = UserOutput
            
            async def create(self, data: UserCreateInput, session: AsyncSession) -> User:
                user = User(**data.model_dump())
                await user.save(session)
                return user
    """
    
    input_schema: ClassVar[type[InputSchema]]
    output_schema: ClassVar[type[OutputSchema]]
    
    def __init__(self) -> None:
        self._validated_data: dict[str, Any] | None = None
    
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
        validated = self.input_schema.model_validate(data)
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
        return self.output_schema.model_validate(obj)  # type: ignore
    
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


# Schemas utilitários comuns
class PaginatedResponse(BaseModel, Generic[OutputT]):
    """
    Schema para respostas paginadas.
    
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


class ErrorResponse(BaseModel):
    """Schema padrão para respostas de erro."""
    
    detail: str
    code: str | None = None
    errors: list[dict[str, Any]] | None = None


class SuccessResponse(BaseModel):
    """Schema padrão para respostas de sucesso simples."""
    
    message: str
    data: dict[str, Any] | None = None


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
