"""
Sistema de Validação Avançado - Estilo DRF.

Fornece validadores reutilizáveis para campos e modelos,
incluindo validação de unicidade no banco de dados.

Características:
- UniqueValidator: Valida unicidade no banco
- UniqueTogetherValidator: Valida unicidade combinada
- Validadores de formato (CPF, CNPJ, telefone, etc.)
- Validadores de range e limites
- Validadores customizáveis
- Mensagens de erro padronizadas
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING, TypeVar, Generic
from collections.abc import Callable, Awaitable

from pydantic import field_validator, model_validator
from pydantic_core import PydanticCustomError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from core.models import Model

T = TypeVar("T")


# =============================================================================
# Exceções de Validação
# =============================================================================

class ValidationError(Exception):
    """Exceção base para erros de validação."""
    
    def __init__(
        self,
        message: str,
        code: str = "invalid",
        field: str | None = None,
        params: dict[str, Any] | None = None,
    ):
        self.message = message
        self.code = code
        self.field = field
        self.params = params or {}
        super().__init__(message)
    
    def to_dict(self) -> dict[str, Any]:
        """Converte para dicionário."""
        result = {
            "message": self.message,
            "code": self.code,
        }
        if self.field:
            result["field"] = self.field
        if self.params:
            result["params"] = self.params
        return result


class UniqueValidationError(ValidationError):
    """Erro de validação de unicidade."""
    
    def __init__(
        self,
        field: str,
        value: Any,
        message: str | None = None,
    ):
        self.value = value
        super().__init__(
            message=message or f"'{field}' with value '{value}' already exists.",
            code="unique",
            field=field,
            params={"value": value},
        )


class MultipleValidationErrors(Exception):
    """Múltiplos erros de validação."""
    
    def __init__(self, errors: list[ValidationError]):
        self.errors = errors
        messages = [e.message for e in errors]
        super().__init__(f"Multiple validation errors: {messages}")
    
    def to_dict(self) -> dict[str, Any]:
        """Converte para dicionário."""
        return {
            "detail": "Validation failed",
            "code": "validation_error",
            "errors": [e.to_dict() for e in self.errors],
        }


# =============================================================================
# Validadores Base
# =============================================================================

class Validator(ABC):
    """Classe base para validadores."""
    
    message: str = "Invalid value."
    code: str = "invalid"
    
    @abstractmethod
    def __call__(self, value: Any, **context: Any) -> Any:
        """Valida o valor."""
        ...
    
    def fail(
        self,
        field: str | None = None,
        message: str | None = None,
        **params: Any,
    ) -> None:
        """Levanta erro de validação."""
        raise ValidationError(
            message=message or self.message.format(**params),
            code=self.code,
            field=field,
            params=params,
        )


class AsyncValidator(ABC):
    """Classe base para validadores assíncronos."""
    
    message: str = "Invalid value."
    code: str = "invalid"
    
    @abstractmethod
    async def __call__(
        self,
        value: Any,
        session: "AsyncSession",
        **context: Any,
    ) -> Any:
        """Valida o valor de forma assíncrona."""
        ...
    
    def fail(
        self,
        field: str | None = None,
        message: str | None = None,
        **params: Any,
    ) -> None:
        """Levanta erro de validação."""
        raise ValidationError(
            message=message or self.message.format(**params),
            code=self.code,
            field=field,
            params=params,
        )


# =============================================================================
# Validadores de Unicidade (Banco de Dados)
# =============================================================================

@dataclass
class UniqueValidator(AsyncValidator):
    """
    Valida que um valor é único no banco de dados.
    
    Exemplo:
        class UserInput(InputSchema):
            email: str
            
            # No ViewSet
            async def validate_unique(self, data, db):
                validator = UniqueValidator(
                    model=User,
                    field="email",
                    message="Este email já está em uso."
                )
                await validator(data.email, db)
    """
    
    model: type["Model"]
    field_name: str
    message: str = "This {field_name} already exists."
    code: str = "unique"
    lookup: str = "exact"  # exact, iexact, contains, etc.
    exclude_pk: int | None = None  # Exclui registro atual (para updates)
    
    async def __call__(
        self,
        value: Any,
        session: "AsyncSession",
        **context: Any,
    ) -> Any:
        """Verifica se o valor já existe no banco."""
        if value is None:
            return value
        
        # Monta o filtro
        filter_kwargs = {self.field_name: value}
        
        # Busca no banco
        queryset = self.model.objects.using(session).filter(**filter_kwargs)
        
        # Exclui o registro atual se for update
        if self.exclude_pk is not None:
            queryset = queryset.exclude(id=self.exclude_pk)
        
        exists = await queryset.exists()
        
        if exists:
            raise UniqueValidationError(
                field=self.field_name,
                value=value,
                message=self.message.format(
                    field_name=self.field_name,
                    value=value,
                ),
            )
        
        return value


@dataclass
class UniqueTogetherValidator(AsyncValidator):
    """
    Valida que uma combinação de campos é única.
    
    Exemplo:
        validator = UniqueTogetherValidator(
            model=OrderItem,
            fields=["order_id", "product_id"],
            message="Este produto já está no pedido."
        )
    """
    
    model: type["Model"]
    fields: list[str]
    message: str = "This combination already exists."
    code: str = "unique_together"
    exclude_pk: int | None = None
    
    async def __call__(
        self,
        data: dict[str, Any],
        session: "AsyncSession",
        **context: Any,
    ) -> dict[str, Any]:
        """Verifica se a combinação já existe."""
        # Monta o filtro com todos os campos
        filter_kwargs = {
            field: data.get(field)
            for field in self.fields
            if data.get(field) is not None
        }
        
        if len(filter_kwargs) != len(self.fields):
            # Nem todos os campos estão presentes
            return data
        
        queryset = self.model.objects.using(session).filter(**filter_kwargs)
        
        if self.exclude_pk is not None:
            queryset = queryset.exclude(id=self.exclude_pk)
        
        exists = await queryset.exists()
        
        if exists:
            raise ValidationError(
                message=self.message,
                code=self.code,
                field=", ".join(self.fields),
                params={"fields": self.fields, "values": filter_kwargs},
            )
        
        return data


@dataclass
class ExistsValidator(AsyncValidator):
    """
    Valida que um registro relacionado existe.
    
    Exemplo:
        validator = ExistsValidator(
            model=Category,
            field="id",
            message="Categoria não encontrada."
        )
        await validator(data.category_id, db)
    """
    
    model: type["Model"]
    field_name: str = "id"
    message: str = "{model_name} not found."
    code: str = "does_not_exist"
    
    async def __call__(
        self,
        value: Any,
        session: "AsyncSession",
        **context: Any,
    ) -> Any:
        """Verifica se o registro existe."""
        if value is None:
            return value
        
        filter_kwargs = {self.field_name: value}
        exists = await self.model.objects.using(session).filter(**filter_kwargs).exists()
        
        if not exists:
            raise ValidationError(
                message=self.message.format(
                    model_name=self.model.__name__,
                    field_name=self.field_name,
                    value=value,
                ),
                code=self.code,
                field=self.field_name,
                params={"value": value},
            )
        
        return value


# =============================================================================
# Validadores de Formato
# =============================================================================

@dataclass
class RegexValidator(Validator):
    """
    Valida usando expressão regular.
    
    Exemplo:
        slug_validator = RegexValidator(
            pattern=r'^[a-z0-9-]+$',
            message="Use apenas letras minúsculas, números e hífens."
        )
    """
    
    pattern: str
    message: str = "Invalid format."
    code: str = "invalid_format"
    flags: int = 0
    inverse_match: bool = False  # Se True, falha quando há match
    
    def __post_init__(self):
        self._regex = re.compile(self.pattern, self.flags)
    
    def __call__(self, value: Any, **context: Any) -> Any:
        if value is None:
            return value
        
        value_str = str(value)
        match = self._regex.search(value_str)
        
        if self.inverse_match:
            if match:
                self.fail(message=self.message)
        else:
            if not match:
                self.fail(message=self.message)
        
        return value


@dataclass
class EmailValidator(Validator):
    """Valida formato de email."""
    
    message: str = "Enter a valid email address."
    code: str = "invalid_email"
    
    # Regex simplificado para email
    _pattern: str = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    def __post_init__(self):
        self._regex = re.compile(self._pattern)
    
    def __call__(self, value: Any, **context: Any) -> Any:
        if value is None:
            return value
        
        if not self._regex.match(str(value)):
            self.fail(message=self.message)
        
        return value


@dataclass
class URLValidator(Validator):
    """Valida formato de URL."""
    
    message: str = "Enter a valid URL."
    code: str = "invalid_url"
    schemes: list[str] = field(default_factory=lambda: ["http", "https"])
    
    def __call__(self, value: Any, **context: Any) -> Any:
        if value is None:
            return value
        
        value_str = str(value)
        
        # Verifica scheme
        has_valid_scheme = any(
            value_str.startswith(f"{scheme}://")
            for scheme in self.schemes
        )
        
        if not has_valid_scheme:
            self.fail(message=self.message)
        
        return value


@dataclass
class SlugValidator(Validator):
    """Valida formato de slug."""
    
    message: str = "Enter a valid slug (letters, numbers, hyphens, underscores)."
    code: str = "invalid_slug"
    allow_unicode: bool = False
    
    def __call__(self, value: Any, **context: Any) -> Any:
        if value is None:
            return value
        
        if self.allow_unicode:
            pattern = r'^[-\w]+$'
        else:
            pattern = r'^[-a-zA-Z0-9_]+$'
        
        if not re.match(pattern, str(value)):
            self.fail(message=self.message)
        
        return value


@dataclass
class PhoneValidator(Validator):
    """Valida formato de telefone brasileiro."""
    
    message: str = "Enter a valid phone number."
    code: str = "invalid_phone"
    
    def __call__(self, value: Any, **context: Any) -> Any:
        if value is None:
            return value
        
        # Remove caracteres não numéricos
        digits = re.sub(r'\D', '', str(value))
        
        # Telefone brasileiro: 10 ou 11 dígitos
        if len(digits) not in (10, 11):
            self.fail(message=self.message)
        
        return value


@dataclass
class CPFValidator(Validator):
    """Valida CPF brasileiro."""
    
    message: str = "Enter a valid CPF."
    code: str = "invalid_cpf"
    
    def __call__(self, value: Any, **context: Any) -> Any:
        if value is None:
            return value
        
        # Remove caracteres não numéricos
        cpf = re.sub(r'\D', '', str(value))
        
        if len(cpf) != 11:
            self.fail(message=self.message)
        
        # Verifica se todos os dígitos são iguais
        if cpf == cpf[0] * 11:
            self.fail(message=self.message)
        
        # Calcula primeiro dígito verificador
        soma = sum(int(cpf[i]) * (10 - i) for i in range(9))
        resto = soma % 11
        digito1 = 0 if resto < 2 else 11 - resto
        
        if int(cpf[9]) != digito1:
            self.fail(message=self.message)
        
        # Calcula segundo dígito verificador
        soma = sum(int(cpf[i]) * (11 - i) for i in range(10))
        resto = soma % 11
        digito2 = 0 if resto < 2 else 11 - resto
        
        if int(cpf[10]) != digito2:
            self.fail(message=self.message)
        
        return value


@dataclass
class CNPJValidator(Validator):
    """Valida CNPJ brasileiro."""
    
    message: str = "Enter a valid CNPJ."
    code: str = "invalid_cnpj"
    
    def __call__(self, value: Any, **context: Any) -> Any:
        if value is None:
            return value
        
        # Remove caracteres não numéricos
        cnpj = re.sub(r'\D', '', str(value))
        
        if len(cnpj) != 14:
            self.fail(message=self.message)
        
        # Verifica se todos os dígitos são iguais
        if cnpj == cnpj[0] * 14:
            self.fail(message=self.message)
        
        # Calcula primeiro dígito verificador
        pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        soma = sum(int(cnpj[i]) * pesos1[i] for i in range(12))
        resto = soma % 11
        digito1 = 0 if resto < 2 else 11 - resto
        
        if int(cnpj[12]) != digito1:
            self.fail(message=self.message)
        
        # Calcula segundo dígito verificador
        pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        soma = sum(int(cnpj[i]) * pesos2[i] for i in range(13))
        resto = soma % 11
        digito2 = 0 if resto < 2 else 11 - resto
        
        if int(cnpj[13]) != digito2:
            self.fail(message=self.message)
        
        return value


# =============================================================================
# Validadores de Range e Limites
# =============================================================================

@dataclass
class MinLengthValidator(Validator):
    """Valida comprimento mínimo."""
    
    min_length: int
    message: str = "Ensure this value has at least {min_length} characters."
    code: str = "min_length"
    
    def __call__(self, value: Any, **context: Any) -> Any:
        if value is None:
            return value
        
        if len(value) < self.min_length:
            self.fail(message=self.message.format(min_length=self.min_length))
        
        return value


@dataclass
class MaxLengthValidator(Validator):
    """Valida comprimento máximo."""
    
    max_length: int
    message: str = "Ensure this value has at most {max_length} characters."
    code: str = "max_length"
    
    def __call__(self, value: Any, **context: Any) -> Any:
        if value is None:
            return value
        
        if len(value) > self.max_length:
            self.fail(message=self.message.format(max_length=self.max_length))
        
        return value


@dataclass
class MinValueValidator(Validator):
    """Valida valor mínimo."""
    
    min_value: int | float
    message: str = "Ensure this value is greater than or equal to {min_value}."
    code: str = "min_value"
    
    def __call__(self, value: Any, **context: Any) -> Any:
        if value is None:
            return value
        
        if value < self.min_value:
            self.fail(message=self.message.format(min_value=self.min_value))
        
        return value


@dataclass
class MaxValueValidator(Validator):
    """Valida valor máximo."""
    
    max_value: int | float
    message: str = "Ensure this value is less than or equal to {max_value}."
    code: str = "max_value"
    
    def __call__(self, value: Any, **context: Any) -> Any:
        if value is None:
            return value
        
        if value > self.max_value:
            self.fail(message=self.message.format(max_value=self.max_value))
        
        return value


@dataclass
class RangeValidator(Validator):
    """Valida que valor está em um range."""
    
    min_value: int | float
    max_value: int | float
    message: str = "Ensure this value is between {min_value} and {max_value}."
    code: str = "out_of_range"
    
    def __call__(self, value: Any, **context: Any) -> Any:
        if value is None:
            return value
        
        if not (self.min_value <= value <= self.max_value):
            self.fail(
                message=self.message.format(
                    min_value=self.min_value,
                    max_value=self.max_value,
                )
            )
        
        return value


@dataclass
class DecimalPlacesValidator(Validator):
    """Valida número de casas decimais."""
    
    max_digits: int | None = None
    decimal_places: int | None = None
    message: str = "Ensure that there are no more than {max_digits} digits in total and {decimal_places} decimal places."
    code: str = "max_decimal_places"
    
    def __call__(self, value: Any, **context: Any) -> Any:
        if value is None:
            return value
        
        from decimal import Decimal, InvalidOperation
        
        try:
            d = Decimal(str(value))
        except InvalidOperation:
            self.fail(message="Enter a valid number.")
        
        sign, digits, exponent = d.as_tuple()
        
        if exponent >= 0:
            # Número inteiro
            total_digits = len(digits) + exponent
            decimal_digits = 0
        else:
            # Número decimal
            total_digits = len(digits)
            decimal_digits = -exponent
        
        if self.max_digits is not None and total_digits > self.max_digits:
            self.fail(
                message=f"Ensure that there are no more than {self.max_digits} digits in total."
            )
        
        if self.decimal_places is not None and decimal_digits > self.decimal_places:
            self.fail(
                message=f"Ensure that there are no more than {self.decimal_places} decimal places."
            )
        
        return value


# =============================================================================
# Validadores de Lista/Escolha
# =============================================================================

@dataclass
class ChoiceValidator(Validator):
    """Valida que valor está em uma lista de escolhas."""
    
    choices: list[Any]
    message: str = "'{value}' is not a valid choice."
    code: str = "invalid_choice"
    
    def __call__(self, value: Any, **context: Any) -> Any:
        if value is None:
            return value
        
        if value not in self.choices:
            self.fail(message=self.message.format(value=value))
        
        return value


@dataclass
class ProhibitedValidator(Validator):
    """Valida que valor NÃO está em uma lista proibida."""
    
    prohibited: list[Any]
    message: str = "'{value}' is not allowed."
    code: str = "prohibited"
    
    def __call__(self, value: Any, **context: Any) -> Any:
        if value is None:
            return value
        
        if value in self.prohibited:
            self.fail(message=self.message.format(value=value))
        
        return value


# =============================================================================
# Validadores de Arquivo
# =============================================================================

@dataclass
class FileExtensionValidator(Validator):
    """Valida extensão de arquivo."""
    
    allowed_extensions: list[str]
    message: str = "File extension '{extension}' is not allowed. Allowed: {allowed}."
    code: str = "invalid_extension"
    
    def __call__(self, value: Any, **context: Any) -> Any:
        if value is None:
            return value
        
        filename = str(value)
        extension = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        
        allowed_lower = [ext.lower().lstrip('.') for ext in self.allowed_extensions]
        
        if extension not in allowed_lower:
            self.fail(
                message=self.message.format(
                    extension=extension,
                    allowed=", ".join(self.allowed_extensions),
                )
            )
        
        return value


@dataclass
class FileSizeValidator(Validator):
    """Valida tamanho de arquivo."""
    
    max_size: int  # Em bytes
    message: str = "File size exceeds maximum allowed ({max_size_mb} MB)."
    code: str = "file_too_large"
    
    def __call__(self, value: Any, **context: Any) -> Any:
        if value is None:
            return value
        
        # Assume que value tem atributo size ou é um número
        size = getattr(value, 'size', value)
        
        if size > self.max_size:
            max_mb = self.max_size / (1024 * 1024)
            self.fail(message=self.message.format(max_size_mb=f"{max_mb:.1f}"))
        
        return value


# =============================================================================
# Validadores de Senha
# =============================================================================

@dataclass
class PasswordValidator(Validator):
    """
    Valida força de senha.
    
    Exemplo:
        validator = PasswordValidator(
            min_length=8,
            require_uppercase=True,
            require_lowercase=True,
            require_digit=True,
            require_special=True,
        )
    """
    
    min_length: int = 8
    max_length: int = 128
    require_uppercase: bool = True
    require_lowercase: bool = True
    require_digit: bool = True
    require_special: bool = False
    special_chars: str = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    message: str = "Password does not meet requirements."
    code: str = "weak_password"
    
    def __call__(self, value: Any, **context: Any) -> Any:
        if value is None:
            return value
        
        password = str(value)
        errors = []
        
        if len(password) < self.min_length:
            errors.append(f"at least {self.min_length} characters")
        
        if len(password) > self.max_length:
            errors.append(f"at most {self.max_length} characters")
        
        if self.require_uppercase and not any(c.isupper() for c in password):
            errors.append("at least one uppercase letter")
        
        if self.require_lowercase and not any(c.islower() for c in password):
            errors.append("at least one lowercase letter")
        
        if self.require_digit and not any(c.isdigit() for c in password):
            errors.append("at least one digit")
        
        if self.require_special and not any(c in self.special_chars for c in password):
            errors.append(f"at least one special character ({self.special_chars})")
        
        if errors:
            self.fail(
                message=f"Password must contain: {', '.join(errors)}."
            )
        
        return value


# =============================================================================
# Validador Composto
# =============================================================================

@dataclass
class ComposeValidators(Validator):
    """
    Combina múltiplos validadores.
    
    Exemplo:
        username_validator = ComposeValidators([
            MinLengthValidator(3),
            MaxLengthValidator(30),
            SlugValidator(),
        ])
    """
    
    validators: list[Validator]
    message: str = "Validation failed."
    code: str = "invalid"
    
    def __call__(self, value: Any, **context: Any) -> Any:
        for validator in self.validators:
            value = validator(value, **context)
        return value


@dataclass
class ComposeAsyncValidators(AsyncValidator):
    """Combina múltiplos validadores assíncronos."""
    
    validators: list[AsyncValidator]
    message: str = "Validation failed."
    code: str = "invalid"
    
    async def __call__(
        self,
        value: Any,
        session: "AsyncSession",
        **context: Any,
    ) -> Any:
        for validator in self.validators:
            value = await validator(value, session, **context)
        return value


# =============================================================================
# Funções Utilitárias
# =============================================================================

def validate_all(
    value: Any,
    validators: list[Validator],
    **context: Any,
) -> Any:
    """
    Executa todos os validadores e coleta erros.
    
    Retorna o valor validado ou levanta MultipleValidationErrors.
    """
    errors = []
    
    for validator in validators:
        try:
            value = validator(value, **context)
        except ValidationError as e:
            errors.append(e)
    
    if errors:
        raise MultipleValidationErrors(errors)
    
    return value


async def validate_all_async(
    value: Any,
    validators: list[AsyncValidator],
    session: "AsyncSession",
    **context: Any,
) -> Any:
    """
    Executa todos os validadores assíncronos e coleta erros.
    """
    errors = []
    
    for validator in validators:
        try:
            value = await validator(value, session, **context)
        except ValidationError as e:
            errors.append(e)
    
    if errors:
        raise MultipleValidationErrors(errors)
    
    return value


def clean_cpf(value: str) -> str:
    """Remove formatação de CPF."""
    return re.sub(r'\D', '', value)


def format_cpf(value: str) -> str:
    """Formata CPF: 000.000.000-00"""
    cpf = clean_cpf(value)
    if len(cpf) == 11:
        return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
    return value


def clean_cnpj(value: str) -> str:
    """Remove formatação de CNPJ."""
    return re.sub(r'\D', '', value)


def format_cnpj(value: str) -> str:
    """Formata CNPJ: 00.000.000/0000-00"""
    cnpj = clean_cnpj(value)
    if len(cnpj) == 14:
        return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
    return value


def clean_phone(value: str) -> str:
    """Remove formatação de telefone."""
    return re.sub(r'\D', '', value)


def format_phone(value: str) -> str:
    """Formata telefone brasileiro."""
    phone = clean_phone(value)
    if len(phone) == 11:
        return f"({phone[:2]}) {phone[2:7]}-{phone[7:]}"
    elif len(phone) == 10:
        return f"({phone[:2]}) {phone[2:6]}-{phone[6:]}"
    return value
