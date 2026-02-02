# Validators

Sistema de validacao inspirado no Django REST Framework. Fornece validadores reutilizaveis para campos individuais e validacao cross-field.

## Validadores Disponiveis

### Unicidade (Requerem Banco de Dados)

| Validador | Uso |
|-----------|-----|
| `UniqueValidator` | Verifica se valor ja existe no banco |
| `UniqueTogetherValidator` | Verifica unicidade de combinacao de campos |
| `ExistsValidator` | Verifica se registro relacionado existe |

### Formato

| Validador | Uso |
|-----------|-----|
| `EmailValidator` | Formato de email valido |
| `URLValidator` | Formato de URL valido |
| `SlugValidator` | Letras, numeros, hifens, underscores |
| `RegexValidator` | Expressao regular customizada |
| `PhoneValidator` | Telefone brasileiro (10-11 digitos) |
| `CPFValidator` | CPF valido (com digitos verificadores) |
| `CNPJValidator` | CNPJ valido (com digitos verificadores) |

### Limites

| Validador | Uso |
|-----------|-----|
| `MinLengthValidator` | Comprimento minimo de string |
| `MaxLengthValidator` | Comprimento maximo de string |
| `MinValueValidator` | Valor numerico minimo |
| `MaxValueValidator` | Valor numerico maximo |
| `RangeValidator` | Valor dentro de range |
| `DecimalPlacesValidator` | Limita casas decimais |

### Outros

| Validador | Uso |
|-----------|-----|
| `ChoiceValidator` | Valor deve estar em lista |
| `ProhibitedValidator` | Valor NAO deve estar em lista |
| `PasswordValidator` | Forca de senha configuravel |
| `FileExtensionValidator` | Extensao de arquivo permitida |
| `FileSizeValidator` | Tamanho maximo de arquivo |

## Usar no ViewSet

### Validacao de Unicidade Simples

A forma mais simples de validar unicidade e via atributo `unique_fields`.

```python
# src/apps/users/views.py
from core import ModelViewSet
from .models import User

class UserViewSet(ModelViewSet):
    model = User
    
    # O framework valida automaticamente antes de create/update
    # Se email ou username ja existir, retorna 400 com mensagem de erro
    unique_fields = ["email", "username"]
```

### Validacao de Unicidade Avancada

Para controle total, use `UniqueValidator` no metodo `validate()`.

```python
from core import ModelViewSet
from core.validators import UniqueValidator
from .models import User

class UserViewSet(ModelViewSet):
    model = User
    
    async def validate(self, data: dict, db, instance=None) -> dict:
        """
        Validacao cross-field.
        
        Chamado APOS validacao do schema Pydantic.
        instance e None em create, objeto existente em update.
        """
        validator = UniqueValidator(
            model=User,
            field_name="email",
            message="Este email ja esta em uso.",
            # Em update, ignora o registro atual
            exclude_pk=instance.id if instance else None,
        )
        
        # Levanta ValidationError se email ja existe
        await validator(data.get("email"), db)
        
        return data
```

### Validacao por Campo

Para validacao especifica de cada campo.

```python
class UserViewSet(ModelViewSet):
    model = User
    
    async def validate_field(self, field: str, value, db, instance=None):
        """
        Chamado para cada campo do payload.
        
        Permite validacao especifica sem afetar outros campos.
        Levante ValidationError para rejeitar o valor.
        """
        if field == "email":
            from core.validators import EmailValidator
            # Validador sincrono - chamado diretamente
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
            # Valida digitos verificadores do CPF
            CPFValidator()(value)
        
        return value
```

**Ordem de execucao**: Schema Pydantic -> `validate_field()` para cada campo -> `validate()` -> `perform_create/update()`

## Validacao no Schema

Validacao pode ser feita no schema Pydantic, executando antes do ViewSet.

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
        """
        Validacao no schema e sincrona.
        Nao tem acesso ao banco de dados.
        """
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
        # Campos opcionais podem ser None
        if v:
            CPFValidator()(v)
        return v
```

**Trade-off Schema vs ViewSet**:
- Schema: Sincrono, sem banco, executa primeiro, erros mais rapidos
- ViewSet: Assincrono, com banco, executa depois, mais flexivel

## Criar Validador Customizado

### Validador Sincrono

Para validacoes que nao precisam de banco de dados.

```python
# src/apps/users/validators.py
from core.validators import Validator
import re

class UsernameValidator(Validator):
    """
    Valida formato de username.
    
    Regras:
    - 3 a 20 caracteres
    - Apenas letras, numeros e underscore
    - Nao pode ser palavra reservada
    """
    
    # Mensagem padrao - pode ser sobrescrita em self.fail()
    message = "Username invalido"
    
    # Codigo de erro - util para i18n no frontend
    code = "invalid_username"
    
    def __call__(self, value, **context):
        """
        Metodo principal de validacao.
        
        Retorna valor (possivelmente transformado) se valido.
        Chama self.fail() para levantar erro.
        """
        if value is None:
            return value
        
        if len(value) < 3:
            self.fail(message="Username deve ter pelo menos 3 caracteres.")
        
        if len(value) > 20:
            self.fail(message="Username deve ter no maximo 20 caracteres.")
        
        if not re.match(r'^[a-zA-Z0-9_]+$', value):
            self.fail(message="Username deve conter apenas letras, numeros e underscore.")
        
        # Lista de palavras proibidas
        prohibited = ["admin", "root", "system", "moderator"]
        if value.lower() in prohibited:
            self.fail(message=f"Username '{value}' nao e permitido.")
        
        return value
```

### Validador Assincrono

Para validacoes que precisam consultar o banco de dados.

```python
# src/apps/users/validators.py
from core.validators import AsyncValidator

class UniqueEmailDomainValidator(AsyncValidator):
    """
    Valida que o dominio do email nao esta bloqueado.
    
    Requer model BlockedDomain no banco.
    """
    
    message = "Dominio de email nao permitido"
    code = "blocked_domain"
    
    async def __call__(self, value, session, **context):
        """
        Validador assincrono recebe session como segundo argumento.
        """
        if value is None:
            return value
        
        # Extrai dominio do email
        domain = value.split("@")[-1]
        
        # Consulta banco para verificar se dominio esta bloqueado
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
            # Validador sincrono - chamado diretamente
            UsernameValidator()(value)
        
        if field == "email":
            # Validador assincrono - precisa de await
            await UniqueEmailDomainValidator()(value, db)
        
        return value
```

## Combinar Validadores

```python
from core.validators import (
    ComposeValidators,
    MinLengthValidator,
    MaxLengthValidator,
    SlugValidator,
)

# Cria validador composto
username_validator = ComposeValidators([
    MinLengthValidator(3),
    MaxLengthValidator(30),
    SlugValidator(),
])

# Uso - executa todos em sequencia
# Para no primeiro erro
username_validator("meu_username")
```

## Coletar Todos os Erros

Por padrao, validacao para no primeiro erro. Para coletar todos:

```python
from core.validators import (
    validate_all,
    MultipleValidationErrors,
    MinLengthValidator,
    MaxLengthValidator,
)

try:
    validate_all(
        value="ab",
        validators=[
            MinLengthValidator(3),
            MaxLengthValidator(10),
        ],
    )
except MultipleValidationErrors as e:
    # Contem lista de todos os erros
    print(e.to_dict())
    # {
    #   "detail": "Validation failed",
    #   "errors": [
    #     {"message": "...", "code": "min_length", "field": None}
    #   ]
    # }
```

## Helpers de Formatacao

Funcoes utilitarias para limpar e formatar documentos brasileiros.

```python
from core.validators import (
    clean_cpf, format_cpf,
    clean_cnpj, format_cnpj,
    clean_phone, format_phone,
)

# CPF: remove formatacao / aplica formatacao
cpf = clean_cpf("123.456.789-00")  # "12345678900"
cpf = format_cpf("12345678900")    # "123.456.789-00"

# CNPJ
cnpj = clean_cnpj("12.345.678/0001-00")  # "12345678000100"
cnpj = format_cnpj("12345678000100")     # "12.345.678/0001-00"

# Telefone brasileiro
phone = clean_phone("(11) 99999-9999")  # "11999999999"
phone = format_phone("11999999999")     # "(11) 99999-9999"
```

**Uso comum**: Limpar antes de salvar no banco, formatar ao exibir.

---

Proximo: [QuerySets](14-querysets.md) - API fluente para queries de banco de dados.
