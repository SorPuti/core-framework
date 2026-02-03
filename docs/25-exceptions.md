# Exceptions - Tratamento de Erros

O Core Framework fornece um sistema centralizado de exceptions para tratamento consistente de erros em toda a aplicação.

## Visão Geral

As exceptions estão organizadas em categorias:

```
CoreException (base)
├── ValidationException
├── DatabaseException  
├── AuthException
├── BusinessException
├── ConfigurationError
└── HTTP Exceptions (wrappers)
```

## Importação

```python
# Importar exceptions específicas
from core.exceptions import NotFound, ValidationException, PermissionDenied

# Ou importar do core diretamente
from core import NotFound, BadRequest, Forbidden
```

## HTTP Exceptions

Wrappers convenientes para erros HTTP comuns:

### BadRequest (400)

```python
from core.exceptions import BadRequest

# Simples
raise BadRequest("Invalid JSON payload")

# Com campo
raise BadRequest.with_field("email", "Invalid format")
```

### Unauthorized (401)

```python
from core.exceptions import Unauthorized

raise Unauthorized("Invalid or expired token")
```

### Forbidden (403)

```python
from core.exceptions import Forbidden

# Simples
raise Forbidden("Access denied")

# Para recurso específico
raise Forbidden.for_resource("Post", action="delete")
# -> "You do not have permission to delete this Post"
```

### NotFound (404)

```python
from core.exceptions import NotFound

# Simples
raise NotFound("User not found")

# Para model
raise NotFound.for_model("User", id=123)
# -> "User with id=123 not found"

raise NotFound.for_model("Post", slug="hello-world")
# -> "Post with slug=hello-world not found"
```

### MethodNotAllowed (405)

```python
from core.exceptions import MethodNotAllowed

raise MethodNotAllowed("DELETE", allowed=["GET", "POST"])
# -> "Method DELETE not allowed. Allowed: GET, POST"
```

### Conflict (409)

```python
from core.exceptions import Conflict

# Simples
raise Conflict("Resource already exists")

# Para duplicata
raise Conflict.duplicate("email", "user@example.com")
# -> "A record with email='user@example.com' already exists"
```

### UnprocessableEntity (422)

```python
from core.exceptions import UnprocessableEntity

# Simples
raise UnprocessableEntity("Invalid data format")

# Para validação
raise UnprocessableEntity.validation_error("password", "Too short")
```

### TooManyRequests (429)

```python
from core.exceptions import TooManyRequests

raise TooManyRequests(retry_after=60)
# -> "Too many requests. Retry after 60 seconds"
# Header: Retry-After: 60
```

### InternalServerError (500)

```python
from core.exceptions import InternalServerError

raise InternalServerError("An unexpected error occurred")
```

### ServiceUnavailable (503)

```python
from core.exceptions import ServiceUnavailable

raise ServiceUnavailable("Database is temporarily unavailable", retry_after=30)
```

## Validation Exceptions

Para erros de validação de dados:

### ValidationException

```python
from core.exceptions import ValidationException

raise ValidationException(
    message="Email format is invalid",
    field="email",
    code="invalid_email",
)
```

### FieldValidationError

```python
from core.exceptions import FieldValidationError

raise FieldValidationError(
    field="password",
    message="Must be at least 8 characters",
    code="min_length",
)
```

### UniqueConstraintError

```python
from core.exceptions import UniqueConstraintError

raise UniqueConstraintError(
    field="email",
    value="user@example.com",
)
# -> "A record with this email already exists"
```

### MultipleValidationErrors

```python
from core.exceptions import MultipleValidationErrors, FieldValidationError

errors = [
    FieldValidationError("email", "Invalid format"),
    FieldValidationError("password", "Too short"),
]
raise MultipleValidationErrors(errors)
```

## Database Exceptions

Para erros relacionados ao banco de dados:

### DoesNotExist

```python
from core.exceptions import DoesNotExist

raise DoesNotExist(model="User", lookup={"id": 123})
# -> "User with id=123 does not exist"
```

### MultipleObjectsReturned

```python
from core.exceptions import MultipleObjectsReturned

raise MultipleObjectsReturned(model="User", count=5)
# -> "get() returned multiple User objects (5 found)"
```

### IntegrityError

```python
from core.exceptions import IntegrityError

raise IntegrityError(
    message="Foreign key violation",
    constraint="fk_posts_author",
    table="posts",
)
```

### ConnectionError

```python
from core.exceptions import ConnectionError

raise ConnectionError("Database connection failed")
```

## Auth Exceptions

Para erros de autenticação e autorização:

### AuthenticationFailed

```python
from core.exceptions import AuthenticationFailed

raise AuthenticationFailed("Invalid email or password")
```

### InvalidCredentials

```python
from core.exceptions import InvalidCredentials

raise InvalidCredentials("Email or password is incorrect")
```

### InvalidToken

```python
from core.exceptions import InvalidToken

raise InvalidToken("Token signature is invalid")
```

### TokenExpired

```python
from core.exceptions import TokenExpired

raise TokenExpired("Access token has expired")
```

### PermissionDenied

```python
from core.exceptions import PermissionDenied

raise PermissionDenied(
    message="You cannot delete this resource",
    permission="posts.delete",
    resource="Post",
)
```

### UserInactive

```python
from core.exceptions import UserInactive

raise UserInactive("User account is inactive")
```

### UserNotFound

```python
from core.exceptions import UserNotFound

raise UserNotFound("User not found")
```

## Business Exceptions

Para erros de lógica de negócio:

### BusinessException (base)

```python
from core.exceptions import BusinessException

# Criar exception customizada
class InsufficientFunds(BusinessException):
    message = "Insufficient funds for this transaction"
    code = "insufficient_funds"

raise InsufficientFunds()
```

### ResourceLocked

```python
from core.exceptions import ResourceLocked

raise ResourceLocked("This document is being edited by another user")
```

### PreconditionFailed

```python
from core.exceptions import PreconditionFailed

raise PreconditionFailed("Order must be paid before shipping")
```

### OperationNotAllowed

```python
from core.exceptions import OperationNotAllowed

raise OperationNotAllowed("Cannot delete published posts")
```

### QuotaExceeded

```python
from core.exceptions import QuotaExceeded

raise QuotaExceeded("Monthly API limit exceeded")
```

## Configuration Exceptions

Para erros de configuração:

### ConfigurationError

```python
from core.exceptions import ConfigurationError

raise ConfigurationError("DATABASE_URL is not set")
```

### MissingDependency

```python
from core.exceptions import MissingDependency

raise MissingDependency("bcrypt", "pip install bcrypt")
# -> "Required package 'bcrypt' is not installed. Install with: pip install bcrypt"
```

## Uso em Views

### Exemplo em ViewSet

```python
from core import ModelViewSet
from core.exceptions import NotFound, Forbidden, BadRequest

class PostViewSet(ModelViewSet):
    model = Post
    
    async def destroy(self, request, db, id, **kwargs):
        post = await self.get_object(db, id)
        
        # Verificar permissão
        if post.author_id != request.state.user.id:
            raise Forbidden.for_resource("Post", action="delete")
        
        # Verificar estado
        if post.is_published:
            raise BadRequest("Cannot delete published posts")
        
        await post.delete(db)
        return {"message": "Post deleted"}
```

### Exemplo em Service

```python
from core.exceptions import (
    NotFound,
    UniqueConstraintError,
    OperationNotAllowed,
)

class UserService:
    async def create_user(self, email: str, password: str, db):
        # Verificar duplicata
        existing = await User.objects.using(db).filter(email=email).first()
        if existing:
            raise UniqueConstraintError(field="email", value=email)
        
        user = User(email=email)
        user.set_password(password)
        await user.save(db)
        return user
    
    async def deactivate_user(self, user_id: int, db):
        user = await User.objects.using(db).filter(id=user_id).first()
        if not user:
            raise NotFound.for_model("User", id=user_id)
        
        if user.is_superuser:
            raise OperationNotAllowed("Cannot deactivate superuser")
        
        user.is_active = False
        await user.save(db)
        return user
```

## Serialização para JSON

Todas as exceptions têm método `to_dict()`:

```python
from core.exceptions import ValidationException

exc = ValidationException(
    message="Invalid email",
    field="email",
    code="invalid_format",
)

print(exc.to_dict())
# {
#     "message": "Invalid email",
#     "code": "invalid_format",
#     "field": "email"
# }
```

## Exception Handlers Globais

O `CoreApp` já configura handlers globais para converter exceptions em respostas HTTP apropriadas:

```python
from core import CoreApp

app = CoreApp(title="My API")

# Handlers já configurados automaticamente:
# - ValidationException -> 422
# - UniqueConstraintError -> 409
# - DoesNotExist -> 404
# - PermissionDenied -> 403
# - AuthException -> 401
# - IntegrityError -> 409/400/422
# - Exception -> 500
```

## Criando Exceptions Customizadas

### Exception de Negócio

```python
from core.exceptions import BusinessException

class InsufficientBalance(BusinessException):
    message = "Insufficient balance"
    code = "insufficient_balance"
    status_code = 400
    
    def __init__(self, required: float, available: float):
        super().__init__(
            message=f"Insufficient balance. Required: {required}, Available: {available}",
            details={"required": required, "available": available},
        )

# Uso
raise InsufficientBalance(required=100.0, available=50.0)
```

### Exception de Validação

```python
from core.exceptions import ValidationException

class InvalidCPF(ValidationException):
    message = "Invalid CPF"
    code = "invalid_cpf"
    
    def __init__(self, value: str):
        super().__init__(
            message=f"Invalid CPF: {value}",
            field="cpf",
            value=value,
        )

# Uso
raise InvalidCPF("123.456.789-00")
```

## Tabela de Referência

| Exception | Status Code | Uso |
|-----------|-------------|-----|
| `BadRequest` | 400 | Request malformado |
| `Unauthorized` | 401 | Autenticação necessária |
| `Forbidden` | 403 | Sem permissão |
| `NotFound` | 404 | Recurso não encontrado |
| `MethodNotAllowed` | 405 | Método HTTP não suportado |
| `Conflict` | 409 | Conflito (duplicata) |
| `UnprocessableEntity` | 422 | Erro de validação |
| `TooManyRequests` | 429 | Rate limit |
| `InternalServerError` | 500 | Erro interno |
| `ServiceUnavailable` | 503 | Serviço indisponível |

## Boas Práticas

1. **Use exceptions específicas** em vez de genéricas
2. **Inclua contexto** (field, value, resource) quando possível
3. **Use códigos de erro consistentes** para facilitar i18n
4. **Crie exceptions de negócio** para regras específicas do domínio
5. **Não exponha detalhes internos** em produção (stack traces, queries)
