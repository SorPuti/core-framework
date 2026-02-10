"""
Typing helpers para autocomplete de ModelAdmin no PyCharm.

Este módulo fornece uma função auxiliar para criar classes ModelAdmin
com autocomplete de campos do model.

Uso:
    from core.admin import ModelAdmin, model_fields
    from apps.domains.models import Domain
    
    # Obtém campos do model como Literal para autocomplete
    DomainFields = model_fields(Domain)
    
    @admin.register(Domain)
    class DomainAdmin(ModelAdmin[Domain]):
        # PyCharm sugere campos válidos
        list_display: tuple[DomainFields, ...] = ("id", "domain", "is_verified")

Alternativa mais simples (sem model_fields):
    Para projetos que preferem simplicidade, use TYPE_CHECKING:
    
    from typing import TYPE_CHECKING
    
    if TYPE_CHECKING:
        from apps.domains.models import Domain
    
    @admin.register(Domain)
    class DomainAdmin(ModelAdmin["Domain"]):
        list_display = ("id", "domain", "is_verified")
"""

from typing import TYPE_CHECKING, Any, TypeVar, get_type_hints

if TYPE_CHECKING:
    from typing import Literal

    # Placeholder - em runtime isso não é usado
    def model_fields(model: type) -> type:
        """
        Retorna um tipo Literal com os nomes dos campos do model.
        
        Uso:
            DomainFields = model_fields(Domain)
            list_display: tuple[DomainFields, ...] = ("id", "domain")
        
        Nota: Esta função é para análise estática apenas.
        Em runtime, retorna str.
        """
        ...


def model_fields(model: type) -> type:
    """
    Retorna um tipo para campos do model.
    
    Em runtime, retorna str (qualquer string é aceita).
    Para análise estática, use com anotação de tipo explícita.
    
    Exemplo:
        from core.admin import model_fields
        
        # Define campos válidos manualmente para autocomplete
        DomainField = Literal["id", "domain", "is_verified", "created_at"]
        
        class DomainAdmin(ModelAdmin[Domain]):
            list_display: tuple[DomainField, ...] = ("id", "domain")
    """
    return str


def get_model_field_names(model: type) -> list[str]:
    """
    Retorna lista de nomes de campos de um model SQLAlchemy.
    
    Útil para gerar Literal types dinamicamente ou para validação.
    
    Exemplo:
        >>> from apps.domains.models import Domain
        >>> fields = get_model_field_names(Domain)
        >>> print(fields)
        ['id', 'domain', 'is_verified', 'created_at', ...]
    """
    try:
        return [col.name for col in model.__table__.columns]
    except AttributeError:
        return []


__all__ = [
    "model_fields",
    "get_model_field_names",
]
