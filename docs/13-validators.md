# Validators

Sistema de validacao estilo DRF.

## Validadores Disponiveis

### Unicidade (Banco de Dados)

| Validador | Descricao |
|-----------|-----------|
| `UniqueValidator` | Campo unico no banco |
| `UniqueTogetherValidator` | Combinacao unica |
| `ExistsValidator` | Registro relacionado existe |

### Formato

| Validador | Descricao |
|-----------|-----------|
| `EmailValidator` | Formato de email |
| `URLValidator` | Formato de URL |
| `SlugValidator` | Formato de slug |
| `RegexValidator` | Expressao regular |
| `PhoneValidator` | Telefone brasileiro |
| `CPFValidator` | CPF valido |
| `CNPJValidator` | CNPJ valido |

### Limites

| Validador | Descricao |
|-----------|-----------|
| `MinLengthValidator` | Comprimento minimo |
| `MaxLengthValidator` | Comprimento maximo |
| `MinValueValidator` | Valor minimo |
| `MaxValueValidator` | Valor maximo |
| `RangeValidator` | Valor em range |
| `DecimalPlacesValidator` | Casas decimais |

### Outros

| Validador | Descricao |
|-----------|-----------|
| `ChoiceValidator` | Valor em lista |
| `ProhibitedValidator` | Valor NAO em lista |
| `PasswordValidator` | Forca de senha |
| `FileExtensionValidator` | Extensao de arquivo |
| `FileSizeValidator` | Tamanho de arquivo |

## Usar no ViewSet

### Validacao de Unicidade

```python
# src/apps/users/views.py
from core import ModelViewSet
from core.validators import UniqueValidator, ValidationError
from .models import User

class UserViewSet(ModelViewSet):
    model = User
    
    # Forma simples - campos unicos
    unique_fields = ["email", "username"]
    
    # Forma avancada - validacao customizada
    async def validate(self, data: dict, db, instance=None) -> dict:
        """Validacao cross-field."""
        
        # Valida unicidade do email
        validator = UniqueValidator(
            model=User,
            field_name="email",
            message="Este email ja esta em uso.",
            exclude_pk=instance.id if instance else None,  # Ignora registro atual em update
        )
        await validator(data.get("email"), db)
        
        return data
```

### Validacao por Campo

```python
class UserViewSet(ModelViewSet):
    model = User
    
    async def validate_field(self, field: str, value, db, instance=None):
        """Validacao por campo individual."""
        
        if field == "email":
            from core.validators import EmailValidator
            EmailValidator()(value)
        
        if field == "password":
            from core.validators import PasswordValidator
            PasswordValidator(
                min_length=8,
                require_uppercase=True,
                require_digit=True,
            )(value)
        
        if field == "cpf":
            from core.validators import CPFValidator
            CPFValidator()(value)
        
        return value
```

## Validacao no Schema

```python
# src/apps/users/schemas.py
from core import InputSchema
from pydantic import field_validator
from core.validators import EmailValidator, PasswordValidator, CPFValidator

class UserInput(InputSchema):
    email: str
    password: str
    cpf: str | None = None
    
    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        EmailValidator()(v)
        return v
    
    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        PasswordValidator(min_length=8)(v)
        return v
    
    @field_validator("cpf")
    @classmethod
    def validate_cpf(cls, v):
        if v:
            CPFValidator()(v)
        return v
```

## Criar Validador Customizado

### Validador Sincrono

```python
# src/apps/users/validators.py
from core.validators import Validator, ValidationError

class UsernameValidator(Validator):
    """Valida formato de username."""
    
    message = "Username deve ter 3-20 caracteres, apenas letras, numeros e underscore."
    code = "invalid_username"
    
    def __call__(self, value, **context):
        if value is None:
            return value
        
        import re
        
        if len(value) < 3:
            self.fail(message="Username deve ter pelo menos 3 caracteres.")
        
        if len(value) > 20:
            self.fail(message="Username deve ter no maximo 20 caracteres.")
        
        if not re.match(r'^[a-zA-Z0-9_]+$', value):
            self.fail(message="Username deve conter apenas letras, numeros e underscore.")
        
        # Palavras proibidas
        prohibited = ["admin", "root", "system"]
        if value.lower() in prohibited:
            self.fail(message=f"Username '{value}' nao e permitido.")
        
        return value
```

### Validador Assincrono (Banco de Dados)

```python
# src/apps/users/validators.py
from core.validators import AsyncValidator, ValidationError

class UniqueEmailDomainValidator(AsyncValidator):
    """Valida que o dominio do email e permitido."""
    
    message = "Dominio de email nao permitido."
    code = "invalid_domain"
    
    async def __call__(self, value, session, **context):
        if value is None:
            return value
        
        # Extrai dominio
        domain = value.split("@")[-1]
        
        # Busca dominios bloqueados no banco
        from src.apps.settings.models import BlockedDomain
        
        blocked = await BlockedDomain.objects.using(session).filter(
            domain=domain
        ).exists()
        
        if blocked:
            self.fail(message=f"Dominio '{domain}' nao e permitido.")
        
        return value
```

### Usar Validador Customizado

```python
# src/apps/users/views.py
from .validators import UsernameValidator, UniqueEmailDomainValidator

class UserViewSet(ModelViewSet):
    model = User
    
    async def validate_field(self, field: str, value, db, instance=None):
        if field == "username":
            UsernameValidator()(value)
        
        if field == "email":
            await UniqueEmailDomainValidator()(value, db)
        
        return value
```

## Combinar Validadores

```python
from core.validators import ComposeValidators, MinLengthValidator, MaxLengthValidator, SlugValidator

username_validator = ComposeValidators([
    MinLengthValidator(3),
    MaxLengthValidator(30),
    SlugValidator(),
])

# Uso
username_validator("meu_username")
```

## Coletar Todos os Erros

```python
from core.validators import validate_all, MinLengthValidator, MaxLengthValidator

try:
    validate_all(
        value="ab",
        validators=[
            MinLengthValidator(3),
            MaxLengthValidator(10),
        ],
    )
except MultipleValidationErrors as e:
    print(e.to_dict())
    # {
    #   "detail": "Validation failed",
    #   "errors": [
    #     {"message": "...", "code": "min_length", "field": None}
    #   ]
    # }
```

## Helpers de Formatacao

```python
from core.validators import (
    clean_cpf, format_cpf,
    clean_cnpj, format_cnpj,
    clean_phone, format_phone,
)

# CPF
cpf = clean_cpf("123.456.789-00")  # "12345678900"
cpf = format_cpf("12345678900")    # "123.456.789-00"

# CNPJ
cnpj = clean_cnpj("12.345.678/0001-00")  # "12345678000100"
cnpj = format_cnpj("12345678000100")     # "12.345.678/0001-00"

# Telefone
phone = clean_phone("(11) 99999-9999")  # "11999999999"
phone = format_phone("11999999999")     # "(11) 99999-9999"
```

## Resumo

1. Use `unique_fields` no ViewSet para validacao simples de unicidade
2. Override `validate()` para validacao cross-field
3. Override `validate_field()` para validacao por campo
4. Use validadores no schema com `@field_validator`
5. Crie validadores customizados herdando de `Validator` ou `AsyncValidator`

Next: [QuerySets](14-querysets.md)
