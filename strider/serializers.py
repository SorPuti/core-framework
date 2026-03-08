"""
Sistema de Serializers inspirado no DRF, mas baseado em Pydantic.

Características:
- Validação automática via Pydantic
- Separação clara entre Input e Output schemas
- Transformação de dados
- Exclusão de campos
- Validação customizada
- Suporte a campos computados (@computed_field)
- Zero overhead de reflexão
"""

from __future__ import annotations

from typing import Any, ClassVar, Generic, TypeVar, get_type_hints
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, field_validator, model_validator, computed_field
from pydantic.functional_validators import BeforeValidator, AfterValidator

# Type vars para generics
ModelT = TypeVar("ModelT")
InputT = TypeVar("InputT", bound="InputSchema")
OutputT = TypeVar("OutputT", bound="OutputSchema")


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
        extra="forbid",
        from_attributes=True,
    )
    
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
    def dump_for_list(cls, obj: Any) -> dict[str, Any]:
        """
        Serializa um objeto para uso em resposta de listagem.
        Respeita list_include / list_exclude quando definidos no schema.
        Inclui campos computados (@computed_field) automaticamente.
        """
        data = cls.model_validate(obj).model_dump()
        
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


class OutputSchema(BaseModel):
    """
    Schema base para dados de saída (response body).
    
    Use para serializar dados retornados em respostas.
    
    Suporta @computed_field para campos calculados dinamicamente a partir
    de outros campos ou do banco de dados.
    
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
            
            # Campo computado - calculado dinamicamente
            @computed_field
            @property
            def display_name(self) -> str:
                return f"{self.name} <{self.email}>"
            
            # Lista retorna só estes campos (sem list_include/list_exclude = retorna todos)
            list_include = ("id", "name", "email", "display_name", "created_at")
    """
    
    model_config = ConfigDict(
        from_attributes=True,
        validate_default=True,
    )
    
    list_include: ClassVar[set[str] | tuple[str, ...] | None] = None
    list_exclude: ClassVar[set[str] | tuple[str, ...] | None] = None
    
    @classmethod
    def _get_all_fields(cls) -> set[str]:
        """
        Retorna todos os campos disponíveis incluindo campos computados.
        """
        # Campos regulares do schema
        regular_fields = set(cls.model_fields.keys())
        
        # Campos computados (computed_fields) - Pydantic v2 armazena em __computed_fields__
        computed_fields = set(getattr(cls, '__computed_fields__', {}).keys())
        
        return regular_fields | computed_fields
    
    @classmethod
    def dump_for_list(cls, obj: Any) -> dict[str, Any]:
        """
        Serializa um objeto para uso em resposta de listagem.
        Respeita list_include / list_exclude quando definidos no schema.
        Inclui campos computados (@computed_field) automaticamente.
        """
        # Validar o objeto primeiro
        instance = cls.model_validate(obj)
        
        # Usar mode='json' para garantir serialização correta e incluir computed_fields
        # include_computed_fields=True é padrão no Pydantic v2, mas deixamos explícito
        data = instance.model_dump(
            mode='json',
            by_alias=False,
            include=None,
            exclude=None,
        )
        
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


# Exportar computed_field para uso nos schemas
__all__ = [
    "InputSchema",
    "OutputSchema",
    "computed_field",
]
