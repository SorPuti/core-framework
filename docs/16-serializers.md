# Serializers e Schemas

Sistema de validacao e transformacao de dados baseado em Pydantic. Define a estrutura de dados aceitos (entrada) e retornados (saida) pela API.

## Estrutura de Arquivos

```
/my-project
  /src
    /apps
      /users
        schemas.py         # Definicoes de Input/Output
        models.py          # Models SQLAlchemy
        views.py           # ViewSets que usam os schemas
```

## InputSchema vs OutputSchema

| Tipo | Uso | Quando Executado |
|------|-----|------------------|
| `InputSchema` | Valida dados recebidos (POST, PUT, PATCH) | Antes de processar request |
| `OutputSchema` | Formata dados retornados | Antes de enviar response |

## Criar Schemas

```python
# src/apps/users/schemas.py
from core import InputSchema, OutputSchema
from datetime import datetime

class UserInput(InputSchema):
    """
    Define campos aceitos em create/update.
    
    Campos obrigatorios nao tem valor padrao.
    Campos opcionais tem valor padrao (None ou outro).
    """
    email: str              # Obrigatorio
    password: str           # Obrigatorio
    name: str               # Obrigatorio
    phone: str | None = None  # Opcional

class UserOutput(OutputSchema):
    """
    Define campos retornados nas respostas.
    
    IMPORTANTE: Nao inclua campos sensiveis como password_hash.
    Apenas campos listados aqui aparecem na resposta.
    """
    id: int
    email: str
    name: str
    phone: str | None
    is_active: bool
    created_at: datetime
    # password_hash NAO incluido - nunca expor hash de senha
```

## Usar no ViewSet

```python
# src/apps/users/views.py
from core import ModelViewSet
from .models import User
from .schemas import UserInput, UserOutput

class UserViewSet(ModelViewSet):
    model = User
    
    # Schema para validar dados de entrada
    input_schema = UserInput
    
    # Schema para formatar dados de saida
    output_schema = UserOutput
```

**Comportamento**: O framework automaticamente valida request body contra `input_schema` e serializa response com `output_schema`.

## Schemas Diferentes por Acao

Para casos onde create e update precisam de campos diferentes.

```python
class UserViewSet(ModelViewSet):
    model = User
    input_schema = UserInput      # Fallback
    output_schema = UserOutput    # Fallback
    
    def get_input_schema(self):
        """
        Retorna schema de entrada baseado na acao atual.
        
        self.action contem: "list", "create", "retrieve",
        "update", "partial_update", "destroy", ou nome de custom action
        """
        action = getattr(self, "action", None)
        
        if action == "create":
            return UserCreateInput  # Com password obrigatorio
        elif action == "update":
            return UserUpdateInput  # Sem password
        
        return self.input_schema
    
    def get_output_schema(self):
        """
        Retorna schema de saida baseado na acao atual.
        """
        action = getattr(self, "action", None)
        
        if action == "list":
            return UserListOutput    # Campos resumidos
        elif action == "retrieve":
            return UserDetailOutput  # Campos completos
        
        return self.output_schema
```

## Validacao no Schema

Validacao sincrona executada antes do ViewSet processar.

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
        """
        Validacao de campo individual.
        
        Executado para cada campo antes de criar instancia.
        Pode transformar o valor (ex: lowercase).
        """
        if "@" not in v:
            raise ValueError("Email invalido")
        return v.lower()  # Normaliza para lowercase
    
    @field_validator("age")
    @classmethod
    def validate_age(cls, v):
        if v < 18:
            raise ValueError("Deve ter pelo menos 18 anos")
        return v
    
    @model_validator(mode="after")
    def validate_passwords(self):
        """
        Validacao cross-field.
        
        Executado apos todos os field_validators.
        Tem acesso a todos os campos via self.
        """
        if self.password != self.password_confirm:
            raise ValueError("Senhas nao conferem")
        return self
```

**Ordem de execucao**: `field_validator` para cada campo -> `model_validator`

## Campos Computados

Campos calculados a partir de outros campos.

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
        """
        Campo calculado - nao existe no model.
        
        Aparece na resposta JSON como campo normal.
        """
        return f"{self.first_name} {self.last_name}"
```

## Nested Schemas

Para relacionamentos e objetos aninhados.

```python
class AddressOutput(OutputSchema):
    street: str
    city: str
    state: str

class UserOutput(OutputSchema):
    id: int
    name: str
    # Objeto aninhado - requer que User tenha relacionamento address
    address: AddressOutput | None
```

## Lista de Objetos

```python
class OrderItemOutput(OutputSchema):
    product_id: int
    quantity: int
    price: float

class OrderOutput(OutputSchema):
    id: int
    total: float
    # Lista de objetos aninhados
    items: list[OrderItemOutput]
```

## Serializer (Casos Complexos)

Para transformacoes que precisam de logica assincrona ou acesso ao banco.

```python
# src/apps/users/serializers.py
from core import Serializer
from .schemas import UserInput, UserOutput

class UserSerializer(Serializer):
    input_schema = UserInput
    output_schema = UserOutput
    
    async def to_representation(self, instance, db=None):
        """
        Customiza serializacao (model -> dict).
        
        Chamado ao retornar dados.
        Pode adicionar campos calculados que precisam de queries.
        """
        data = await super().to_representation(instance, db)
        
        # Adiciona campo que requer query ao banco
        data["posts_count"] = await instance.posts.count()
        
        return data
    
    async def to_internal_value(self, data, db=None):
        """
        Customiza deserializacao (dict -> dados para model).
        
        Chamado ao receber dados.
        Pode transformar dados antes de salvar.
        """
        data = await super().to_internal_value(data, db)
        
        # Normaliza email
        if "email" in data:
            data["email"] = data["email"].lower()
        
        return data
```

### Usar Serializer no ViewSet

```python
class UserViewSet(ModelViewSet):
    model = User
    # serializer_class substitui input_schema/output_schema
    serializer_class = UserSerializer
```

## Campos Opcionais para PATCH

Em PATCH, apenas campos enviados devem ser atualizados.

```python
class UserUpdateInput(InputSchema):
    """
    Todos os campos opcionais para suportar PATCH.
    
    Campos nao enviados permanecem com valor atual.
    """
    email: str | None = None
    name: str | None = None
    phone: str | None = None
```

## Excluir Campos do Model

OutputSchema define explicitamente quais campos aparecem na resposta.

```python
class UserOutput(OutputSchema):
    id: int
    email: str
    name: str
    # Campos do model NAO listados aqui NAO aparecem:
    # - password_hash
    # - is_superuser
    # - internal_notes
    
    class Config:
        # Permite criar schema a partir de instancia ORM
        from_attributes = True
```

## Transformar Model em Schema Manualmente

```python
# Em custom actions ou logica customizada
user = await User.objects.using(db).get(id=1)

# model_validate() cria instancia do schema a partir do model
# model_dump() converte para dict (JSON-serializavel)
output = UserOutput.model_validate(user)
return output.model_dump()

# Forma compacta
return UserOutput.model_validate(user).model_dump()

# Para lista de models
users = await User.objects.using(db).all()
return [UserOutput.model_validate(u).model_dump() for u in users]
```

---

Proximo: [DateTime](17-datetime.md) - Manipulacao de datas e timezones.
