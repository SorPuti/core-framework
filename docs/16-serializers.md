# Serializers e Schemas

Validacao e transformacao de dados.

## Estrutura de Arquivos

```
/my-project
  /src
    /apps
      /users
        schemas.py         # Input/Output schemas
        models.py
        views.py
```

## InputSchema vs OutputSchema

| Tipo | Uso |
|------|-----|
| `InputSchema` | Dados recebidos (POST, PUT, PATCH) |
| `OutputSchema` | Dados retornados (GET, respostas) |

## Criar Schemas

```python
# src/apps/users/schemas.py
from core import InputSchema, OutputSchema
from datetime import datetime

class UserInput(InputSchema):
    """Dados para criar/atualizar usuario."""
    email: str
    password: str
    name: str
    phone: str | None = None

class UserOutput(OutputSchema):
    """Dados retornados do usuario."""
    id: int
    email: str
    name: str
    phone: str | None
    is_active: bool
    created_at: datetime
    
    # NAO inclui password!
```

## Usar no ViewSet

```python
# src/apps/users/views.py
from core import ModelViewSet
from .models import User
from .schemas import UserInput, UserOutput

class UserViewSet(ModelViewSet):
    model = User
    input_schema = UserInput
    output_schema = UserOutput
```

## Schemas Diferentes por Acao

```python
class UserViewSet(ModelViewSet):
    model = User
    input_schema = UserInput
    output_schema = UserOutput
    
    # Schemas especificos
    def get_input_schema(self):
        action = getattr(self, "action", None)
        
        if action == "create":
            return UserCreateInput  # Com password
        elif action == "update":
            return UserUpdateInput  # Sem password
        
        return self.input_schema
    
    def get_output_schema(self):
        action = getattr(self, "action", None)
        
        if action == "list":
            return UserListOutput  # Resumido
        elif action == "retrieve":
            return UserDetailOutput  # Completo
        
        return self.output_schema
```

## Validacao no Schema

```python
from core import InputSchema
from pydantic import field_validator, model_validator

class UserInput(InputSchema):
    email: str
    password: str
    password_confirm: str
    age: int
    
    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        if "@" not in v:
            raise ValueError("Email invalido")
        return v.lower()
    
    @field_validator("age")
    @classmethod
    def validate_age(cls, v):
        if v < 18:
            raise ValueError("Deve ter pelo menos 18 anos")
        return v
    
    @model_validator(mode="after")
    def validate_passwords(self):
        if self.password != self.password_confirm:
            raise ValueError("Senhas nao conferem")
        return self
```

## Campos Computados

```python
from core import OutputSchema
from pydantic import computed_field

class UserOutput(OutputSchema):
    id: int
    first_name: str
    last_name: str
    
    @computed_field
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"
```

## Nested Schemas

```python
# schemas.py
class AddressOutput(OutputSchema):
    street: str
    city: str
    state: str

class UserOutput(OutputSchema):
    id: int
    name: str
    address: AddressOutput | None
```

## Lista de Schemas

```python
class OrderOutput(OutputSchema):
    id: int
    total: float
    items: list[OrderItemOutput]

class OrderItemOutput(OutputSchema):
    product_id: int
    quantity: int
    price: float
```

## Serializer (Alternativa)

Para casos mais complexos, use Serializer:

```python
# src/apps/users/serializers.py
from core import Serializer
from .schemas import UserInput, UserOutput

class UserSerializer(Serializer):
    input_schema = UserInput
    output_schema = UserOutput
    
    async def to_representation(self, instance, db=None):
        """Customiza serializacao."""
        data = await super().to_representation(instance, db)
        
        # Adiciona campos extras
        data["posts_count"] = await instance.posts.count()
        
        return data
    
    async def to_internal_value(self, data, db=None):
        """Customiza deserializacao."""
        data = await super().to_internal_value(data, db)
        
        # Transforma dados
        if "email" in data:
            data["email"] = data["email"].lower()
        
        return data
```

### Usar Serializer no ViewSet

```python
class UserViewSet(ModelViewSet):
    model = User
    serializer_class = UserSerializer
```

## Campos Opcionais para Update

```python
class UserUpdateInput(InputSchema):
    """Todos os campos opcionais para PATCH."""
    email: str | None = None
    name: str | None = None
    phone: str | None = None
```

## Excluir Campos do Model

```python
class UserOutput(OutputSchema):
    id: int
    email: str
    name: str
    # password_hash NAO incluido
    # is_superuser NAO incluido
    
    class Config:
        from_attributes = True  # Permite criar de ORM model
```

## Transformar Model em Schema

```python
# No ViewSet
user = await User.objects.using(db).get(id=1)
output = UserOutput.model_validate(user)
return output.model_dump()

# Ou diretamente
return UserOutput.model_validate(user).model_dump()
```

## Lista de Models

```python
users = await User.objects.using(db).all()
return [UserOutput.model_validate(u).model_dump() for u in users]
```

## Resumo

1. Crie `schemas.py` em cada app
2. Use `InputSchema` para dados de entrada
3. Use `OutputSchema` para dados de saida
4. Configure no ViewSet com `input_schema` e `output_schema`
5. Use `@field_validator` para validacao de campo
6. Use `@model_validator` para validacao cross-field
7. Use `Serializer` para casos complexos

Next: [DateTime](17-datetime.md)
