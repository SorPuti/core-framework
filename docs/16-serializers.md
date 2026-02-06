# Serializers e Schemas

Sistema de validacao e serializacao de dados do Core Framework, baseado em Pydantic.

Se voce vem do Django REST Framework, pense nos schemas como **Serializers tipados** — mas sem magia, sem Meta class, sem reflexao de model. Voce declara exatamente quais campos existem, e o framework faz o resto.

Se voce ja usa Pydantic `BaseModel` em outros projetos, `InputSchema` e `OutputSchema` **sao** BaseModel — com configuracoes otimizadas para APIs. Voce pode usar tudo do Pydantic normalmente.

---

## Indice

1. [Filosofia: Django DRF vs Core Framework](#filosofia-django-drf-vs-core-framework)
2. [InputSchema — Dados de Entrada](#inputschema--dados-de-entrada)
3. [OutputSchema — Dados de Saida](#outputschema--dados-de-saida)
4. [De BaseModel para InputSchema/OutputSchema](#de-basemodel-para-inputschemaoutputschema)
5. [Validacao](#validacao)
6. [Campos Computados](#campos-computados)
7. [Schemas Aninhados (Nested)](#schemas-aninhados-nested)
8. [PaginatedResponse](#paginatedresponse)
9. [Schemas de Resposta de Erro](#schemas-de-resposta-de-erro)
10. [Usar no ViewSet](#usar-no-viewset)
11. [OpenAPI e Postman](#openapi-e-postman)
12. [Serializer (Casos Avancados)](#serializer-casos-avancados)
13. [Padroes e Receitas](#padroes-e-receitas)

---

## Filosofia: Django DRF vs Core Framework

### No Django REST Framework

```python
# Django DRF - serializers.py
from rest_framework import serializers

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "name", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]
        extra_kwargs = {
            "password": {"write_only": True, "min_length": 8},
        }
    
    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email ja existe")
        return value.lower()
    
    def create(self, validated_data):
        return User.objects.create_user(**validated_data)
```

**Problemas do DRF**:
- `Meta.fields` e uma lista de strings — erro de digitacao so aparece em runtime
- Reflexao do model gera campos automaticamente — mas voce nunca sabe quais tipos reais estao sendo usados
- Sem suporte nativo a type hints — IDEs nao conseguem autocompletar
- Serializer faz validacao, criacao e serializacao — violacao de responsabilidade unica

### No Core Framework

```python
# Core Framework - schemas.py
from core import InputSchema, OutputSchema
from pydantic import EmailStr, field_validator
from datetime import datetime

class UserCreateInput(InputSchema):
    """Schema de ENTRADA — valida dados do request body."""
    email: EmailStr
    name: str
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

class UserOutput(OutputSchema):
    """Schema de SAIDA — define campos retornados na response."""
    id: int
    email: str
    name: str
    is_active: bool
    created_at: datetime
    # password NAO aparece aqui — nunca exposto
```

**Vantagens**:
- Cada campo tem tipo explicito — IDE autocompleta, mypy valida
- Separacao clara: `InputSchema` para entrada, `OutputSchema` para saida
- Pydantic nativo — sem camada de abstracao extra
- Erro de tipo detectado em tempo de desenvolvimento, nao em runtime

### Tabela Comparativa

| Conceito | Django DRF | Core Framework |
|----------|-----------|----------------|
| Definir campos de entrada | `ModelSerializer` + `Meta.fields` | `InputSchema` com type hints |
| Definir campos de saida | Mesmo serializer (ou `read_only`) | `OutputSchema` separado |
| Validar campo | `def validate_<field>(self, value)` | `@field_validator("<field>")` |
| Validacao cross-field | `def validate(self, attrs)` | `@model_validator(mode="after")` |
| Campos computados | `SerializerMethodField` | `@computed_field` |
| Tipos | Strings em `Meta.fields` | Type hints Python nativos |
| Nested serializer | `UserSerializer()` como campo | `UserOutput` como tipo do campo |
| Campos opcionais | `required=False` em `extra_kwargs` | `campo: str \| None = None` |
| Desempenho | Reflexao em runtime | Zero reflexao, Pydantic compilado |

---

## InputSchema — Dados de Entrada

`InputSchema` herda de `pydantic.BaseModel` com configuracoes otimizadas para request bodies.

### Definicao Basica

```python
from core import InputSchema

class ProductInput(InputSchema):
    name: str                    # Obrigatorio, string
    price: float                 # Obrigatorio, float
    description: str | None = None  # Opcional, default None
    is_active: bool = True       # Opcional, default True
    tags: list[str] = []         # Opcional, default lista vazia
```

### O que InputSchema faz automaticamente

```python
# Internamente, InputSchema configura:
class InputSchema(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,   # Remove espacos antes/depois de strings
        validate_default=True,       # Valida valores default tambem
        extra="forbid",              # Rejeita campos nao declarados (422)
        from_attributes=True,        # Permite criar de objetos ORM
    )
```

| Configuracao | Efeito | Exemplo |
|-------------|--------|---------|
| `str_strip_whitespace=True` | `"  John  "` vira `"John"` | Limpeza automatica |
| `validate_default=True` | Valida inclusive campos com default | Garante consistencia |
| `extra="forbid"` | `{"name": "X", "hack": "value"}` retorna 422 | Seguranca: rejeita campos desconhecidos |
| `from_attributes=True` | Pode criar schema a partir de objeto ORM | `ProductInput.model_validate(product_obj)` |

### Campos nao declarados sao rejeitados

```python
class ProductInput(InputSchema):
    name: str
    price: float

# Request com campo extra:
# POST /products {"name": "Widget", "price": 10, "hack": "sql injection"}
# 
# Resposta: 422 Validation Error
# {"detail": "Extra inputs are not permitted", "errors": [...]}
```

Isso e uma protecao de seguranca. No DRF voce precisa declarar `extra_kwargs` ou usar `read_only_fields` para controlar isso. Aqui, qualquer campo nao listado no schema e automaticamente rejeitado.

### Tipos Suportados

```python
from datetime import datetime, date, time
from decimal import Decimal
from uuid import UUID
from enum import Enum
from pydantic import EmailStr, HttpUrl, IPvAnyAddress

class CompleteInput(InputSchema):
    # Basicos
    name: str
    age: int
    price: float
    amount: Decimal
    active: bool
    
    # Data/Hora
    birth_date: date
    event_time: time
    created_at: datetime
    
    # Identificadores
    user_id: int
    uuid: UUID
    
    # Validados pelo Pydantic
    email: EmailStr          # Valida formato de email
    website: HttpUrl         # Valida URL completa
    server_ip: IPvAnyAddress # Valida IPv4 ou IPv6
    
    # Colecoes
    tags: list[str]
    metadata: dict[str, str]
    scores: list[int]
    
    # Opcionais
    nickname: str | None = None
    
    # Enums
    status: StatusEnum
```

---

## OutputSchema — Dados de Saida

`OutputSchema` herda de `pydantic.BaseModel` com configuracoes otimizadas para response bodies.

### Definicao Basica

```python
from core import OutputSchema
from datetime import datetime

class ProductOutput(OutputSchema):
    id: int
    name: str
    price: float
    description: str | None
    is_active: bool
    created_at: datetime
    # Campos do model que NAO estao aqui NAO aparecem na resposta:
    # - internal_cost (campo interno)
    # - supplier_id (dado sensivel)
```

### O que OutputSchema faz automaticamente

```python
# Internamente, OutputSchema configura:
class OutputSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,     # Cria schema direto de objetos ORM
        validate_default=True,    # Valida valores default
    )
```

| Configuracao | Efeito | Motivo |
|-------------|--------|--------|
| `from_attributes=True` | Converte objeto ORM em schema | `ProductOutput.model_validate(product_obj)` funciona |
| Sem `extra="forbid"` | Campos extras do model sao ignorados silenciosamente | Flexibilidade na serializacao |

### Converter Model ORM para Schema

```python
# Dentro de um ViewSet ou action customizada:

# Um unico objeto
product = await Product.objects.using(db).get(id=1)
output = ProductOutput.model_validate(product)
return output.model_dump()

# Forma compacta (mais comum)
return ProductOutput.model_validate(product).model_dump()

# Lista de objetos
products = await Product.objects.using(db).all()
return [ProductOutput.model_validate(p).model_dump() for p in products]

# Usando metodo helper do OutputSchema
output = ProductOutput.from_orm(product)           # Um objeto
outputs = ProductOutput.from_orm_list(products)     # Lista
```

### Seguranca: OutputSchema como whitelist

```python
# Model no banco (tem TODOS os campos)
class User(Model):
    id = Field(Integer, primary_key=True)
    email = Field(String)
    name = Field(String)
    password_hash = Field(String)       # SENSIVEL
    api_secret = Field(String)          # SENSIVEL
    internal_notes = Field(String)      # INTERNO
    failed_login_count = Field(Integer) # INTERNO

# OutputSchema declara APENAS campos seguros
class UserOutput(OutputSchema):
    id: int
    email: str
    name: str
    is_active: bool
    created_at: datetime
    # password_hash, api_secret, internal_notes — NUNCA expostos
```

Diferente do DRF onde voce precisa lembrar de excluir campos sensiveis (`exclude = ["password_hash"]`), aqui voce precisa **incluir explicitamente** cada campo que quer expor. Omitir e seguro.

---

## De BaseModel para InputSchema/OutputSchema

Se voce ja usa `pydantic.BaseModel` em projetos, a migracao e simples. `InputSchema` e `OutputSchema` **sao** BaseModel com configuracoes extras.

### Antes (BaseModel puro)

```python
from pydantic import BaseModel, ConfigDict

class UserCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    
    email: str
    name: str
    password: str

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    email: str
    name: str
    is_active: bool
```

### Depois (Core Framework)

```python
from core import InputSchema, OutputSchema

class UserCreate(InputSchema):
    # model_config ja vem configurado — nao precisa declarar
    email: str
    name: str
    password: str

class UserResponse(OutputSchema):
    # from_attributes=True ja vem configurado
    id: int
    email: str
    name: str
    is_active: bool
```

### O que muda e o que NAO muda

| Feature | BaseModel | InputSchema/OutputSchema |
|---------|-----------|--------------------------|
| Type hints | Funciona igual | Funciona igual |
| `field_validator` | Funciona igual | Funciona igual |
| `model_validator` | Funciona igual | Funciona igual |
| `computed_field` | Funciona igual | Funciona igual |
| `model_dump()` | Funciona igual | Funciona igual |
| `model_validate()` | Funciona igual | Funciona igual |
| `model_json_schema()` | Funciona igual | Funciona igual |
| Nested models | Funciona igual | Funciona igual |
| Generic models | Funciona igual | Funciona igual |
| **`str_strip_whitespace`** | Precisa declarar | **Ja ativo** (InputSchema) |
| **`extra="forbid"`** | Precisa declarar | **Ja ativo** (InputSchema) |
| **`from_attributes`** | Precisa declarar | **Ja ativo** (ambos) |
| **Integracao ViewSet** | Manual | **Automatica** |
| **OpenAPI tipado** | Manual | **Automatico** |
| **Postman com campos** | Manual | **Automatico** |

### Posso usar BaseModel normal tambem?

**Sim.** `InputSchema` e `OutputSchema` sao apenas `BaseModel` com `model_config` pre-configurado. Voce pode:

1. **Usar como BaseModel** em qualquer lugar que aceite Pydantic:

```python
class MyInput(InputSchema):
    name: str
    email: str

# Funciona como qualquer BaseModel:
data = MyInput(name="John", email="john@example.com")
print(data.model_dump())          # {"name": "John", "email": "john@example.com"}
print(data.model_dump_json())     # '{"name":"John","email":"john@example.com"}'
print(MyInput.model_json_schema()) # JSON Schema completo
```

2. **Misturar com BaseModel** quando necessario:

```python
from pydantic import BaseModel
from core import InputSchema

# Schema interno que nao e usado como body da API
class InternalConfig(BaseModel):
    retry_count: int = 3
    timeout: float = 30.0

# Schema de entrada da API — usa InputSchema
class TaskInput(InputSchema):
    name: str
    config: InternalConfig  # Pode usar BaseModel como campo aninhado
```

3. **Herdar e customizar model_config** se precisar:

```python
from core import InputSchema
from pydantic import ConfigDict

class FlexibleInput(InputSchema):
    """InputSchema que aceita campos extras (desabilita extra='forbid')."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="allow",  # Override: aceita campos extras
        from_attributes=True,
    )
    
    name: str
    # Campos extras enviados ficam acessiveis via model_extra
```

---

## Validacao

### Validacao de Campo Individual

```python
from core import InputSchema
from pydantic import field_validator

class UserInput(InputSchema):
    email: str
    password: str
    age: int
    
    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """
        Executado quando 'email' e recebido.
        Pode transformar o valor (retorno e o novo valor).
        Pode rejeitar levantando ValueError.
        """
        if "@" not in v:
            raise ValueError("Email invalido")
        return v.lower().strip()  # Normaliza
    
    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Senha deve ter pelo menos 8 caracteres")
        if not any(c.isupper() for c in v):
            raise ValueError("Senha deve ter pelo menos uma letra maiuscula")
        if not any(c.isdigit() for c in v):
            raise ValueError("Senha deve ter pelo menos um numero")
        return v
    
    @field_validator("age")
    @classmethod
    def validate_age(cls, v: int) -> int:
        if v < 18:
            raise ValueError("Deve ter pelo menos 18 anos")
        if v > 120:
            raise ValueError("Idade invalida")
        return v
```

**Comparacao com Django DRF**:

```python
# DRF
class UserSerializer(serializers.Serializer):
    email = serializers.EmailField()
    
    def validate_email(self, value):  # Metodo de instancia
        return value.lower()

# Core Framework  
class UserInput(InputSchema):
    email: str
    
    @field_validator("email")
    @classmethod
    def validate_email(cls, v):  # Metodo de classe (classmethod)
        return v.lower()
```

### Validacao Cross-Field (model_validator)

```python
from core import InputSchema
from pydantic import model_validator

class TransferInput(InputSchema):
    from_account: str
    to_account: str
    amount: float
    
    @model_validator(mode="after")
    def validate_transfer(self):
        """
        Executado APOS todos os field_validators.
        Tem acesso a todos os campos via self.
        """
        if self.from_account == self.to_account:
            raise ValueError("Contas de origem e destino devem ser diferentes")
        if self.amount <= 0:
            raise ValueError("Valor deve ser positivo")
        return self

class PasswordChangeInput(InputSchema):
    password: str
    password_confirm: str
    
    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.password_confirm:
            raise ValueError("Senhas nao conferem")
        return self
```

**Comparacao com Django DRF**:

```python
# DRF
class TransferSerializer(serializers.Serializer):
    def validate(self, attrs):  # Recebe dict
        if attrs["from_account"] == attrs["to_account"]:
            raise serializers.ValidationError("Contas iguais")
        return attrs

# Core Framework
class TransferInput(InputSchema):
    @model_validator(mode="after")
    def validate_transfer(self):  # Recebe self tipado
        if self.from_account == self.to_account:
            raise ValueError("Contas iguais")
        return self
```

### Ordem de Execucao

```
Request Body JSON
       |
       v
1. Parsing de tipos (str → int, str → datetime, etc.)
       |
       v
2. @field_validator para cada campo (na ordem declarada)
       |
       v
3. @model_validator(mode="after") — cross-field
       |
       v
4. Instancia do schema criada ✓
       |
       v
5. ViewSet.validate_data() — validacao async com banco
```

---

## Campos Computados

Campos calculados a partir de outros campos. Aparecem na resposta JSON como campos normais.

```python
from core import OutputSchema
from pydantic import computed_field
from datetime import datetime

class UserOutput(OutputSchema):
    id: int
    first_name: str
    last_name: str
    email: str
    created_at: datetime
    
    @computed_field
    @property
    def full_name(self) -> str:
        """Aparece na response como 'full_name': 'John Doe'"""
        return f"{self.first_name} {self.last_name}"
    
    @computed_field
    @property
    def initials(self) -> str:
        """Aparece na response como 'initials': 'JD'"""
        return f"{self.first_name[0]}{self.last_name[0]}".upper()

class PostOutput(OutputSchema):
    id: int
    title: str
    content: str
    views_count: int
    created_at: datetime
    
    @computed_field
    @property
    def excerpt(self) -> str:
        """Resumo dos primeiros 100 caracteres."""
        if len(self.content) <= 100:
            return self.content
        return self.content[:100] + "..."
    
    @computed_field
    @property
    def is_popular(self) -> bool:
        """Post com mais de 1000 views e popular."""
        return self.views_count > 1000
```

**Comparacao com Django DRF**:

```python
# DRF — precisa de SerializerMethodField
class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    
    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"

# Core Framework — @computed_field nativo
class UserOutput(OutputSchema):
    first_name: str
    last_name: str
    
    @computed_field
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"
```

Vantagens do `@computed_field`:
- Tipo de retorno explicito (`-> str`)
- Aparece automaticamente no JSON Schema / OpenAPI
- IDE autocompleta o campo

---

## Schemas Aninhados (Nested)

### Objeto Aninhado

```python
class AddressOutput(OutputSchema):
    street: str
    city: str
    state: str
    zip_code: str

class CompanyOutput(OutputSchema):
    id: int
    name: str

class UserOutput(OutputSchema):
    id: int
    name: str
    email: str
    address: AddressOutput | None     # Pode ser null
    company: CompanyOutput             # Obrigatorio
```

**Response JSON**:
```json
{
    "id": 1,
    "name": "John",
    "email": "john@example.com",
    "address": {
        "street": "Rua Principal 123",
        "city": "Sao Paulo",
        "state": "SP",
        "zip_code": "01001-000"
    },
    "company": {
        "id": 10,
        "name": "TechCorp"
    }
}
```

### Lista de Objetos Aninhados

```python
class OrderItemOutput(OutputSchema):
    product_id: int
    product_name: str
    quantity: int
    unit_price: float

class OrderOutput(OutputSchema):
    id: int
    total: float
    status: str
    items: list[OrderItemOutput]  # Lista de objetos
```

### Input com Objetos Aninhados

```python
class AddressInput(InputSchema):
    street: str
    city: str
    state: str
    zip_code: str

class UserCreateInput(InputSchema):
    name: str
    email: str
    address: AddressInput       # Valida objeto aninhado tambem
```

**Request JSON**:
```json
{
    "name": "John",
    "email": "john@example.com",
    "address": {
        "street": "Rua Principal 123",
        "city": "Sao Paulo",
        "state": "SP",
        "zip_code": "01001-000"
    }
}
```

---

## PaginatedResponse

Schema generico para respostas de listagem paginada. Usado automaticamente pelo framework em endpoints `list()`.

```python
from core.serializers import PaginatedResponse

# O framework gera automaticamente PaginatedResponse[SeuOutput]
# para cada ViewSet com output_schema definido.
```

### Estrutura da Resposta

```json
{
    "items": [
        {"id": 1, "name": "Product A", "price": 10.0},
        {"id": 2, "name": "Product B", "price": 20.0}
    ],
    "total": 150,
    "page": 1,
    "page_size": 20,
    "pages": 8
}
```

| Campo | Tipo | Descricao |
|-------|------|-----------|
| `items` | `list[OutputSchema]` | Lista de itens da pagina atual |
| `total` | `int` | Total de registros no banco |
| `page` | `int` | Pagina atual (1-indexed) |
| `page_size` | `int` | Itens por pagina |
| `pages` | `int` | Total de paginas calculado |

### Usar Manualmente

```python
from core.serializers import PaginatedResponse

# Em uma action customizada ou rota manual
@router.get("/products", response_model=PaginatedResponse[ProductOutput])
async def list_products(page: int = 1, page_size: int = 20, db=Depends(get_db)):
    offset = (page - 1) * page_size
    products = await Product.objects.using(db).offset(offset).limit(page_size).all()
    total = await Product.objects.using(db).count()
    
    return {
        "items": [ProductOutput.model_validate(p).model_dump() for p in products],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
    # 'pages' e calculado automaticamente pelo PaginatedResponse
```

---

## Schemas de Resposta de Erro

O framework inclui schemas tipados para respostas de erro. Eles aparecem no OpenAPI e no Postman automaticamente.

### ErrorResponse (generico)

```python
from core import ErrorResponse

# Usado para erros gerais
# Status: varia
{
    "detail": "Something went wrong",
    "code": "error_code",
    "errors": [...]  # Opcional: lista de erros detalhados
}
```

### ValidationErrorResponse (422)

```python
from core.serializers import ValidationErrorResponse

# Retornado quando dados de entrada sao invalidos
# Status: 422
{
    "detail": "Validation error",
    "code": "validation_error",
    "errors": [
        {
            "loc": ["body", "email"],
            "msg": "value is not a valid email address",
            "type": "value_error",
            "input": "not-an-email"
        },
        {
            "loc": ["body", "password"],
            "msg": "Password must be at least 8 characters",
            "type": "value_error",
            "input": "123"
        }
    ]
}
```

### NotFoundResponse (404)

```python
from core.serializers import NotFoundResponse

# Retornado quando recurso nao existe
# Status: 404
{
    "detail": "User not found"
}
```

### ConflictResponse (409)

```python
from core.serializers import ConflictResponse

# Retornado quando ha duplicidade (unique constraint)
# Status: 409
{
    "detail": "A record with this email already exists.",
    "code": "unique_constraint",
    "field": "email",
    "value": "john@example.com"
}
```

### DeleteResponse (200)

```python
from core.serializers import DeleteResponse

# Retornado ao deletar um recurso com sucesso
# Status: 200
{
    "message": "User deleted successfully"
}
```

### SuccessResponse (generico)

```python
from core import SuccessResponse

# Para respostas de sucesso simples
{
    "message": "Operation completed",
    "data": {"key": "value"}  # Opcional
}
```

---

## Usar no ViewSet

### Configuracao Basica

```python
from core import ModelViewSet
from .models import Product
from .schemas import ProductInput, ProductOutput

class ProductViewSet(ModelViewSet):
    model = Product
    input_schema = ProductInput     # POST, PUT, PATCH body
    output_schema = ProductOutput   # GET, POST, PUT, PATCH response
```

**O que acontece automaticamente**:

| Metodo HTTP | Body (entrada) | Response (saida) |
|-------------|---------------|------------------|
| `GET /products/` | — | `PaginatedResponse[ProductOutput]` |
| `POST /products/` | `ProductInput` | `ProductOutput` (201) |
| `GET /products/{id}` | — | `ProductOutput` |
| `PUT /products/{id}` | `ProductInput` | `ProductOutput` |
| `PATCH /products/{id}` | `PartialProductInput` (auto-gerado) | `ProductOutput` |
| `DELETE /products/{id}` | — | `DeleteResponse` |

**PATCH automatico**: O framework gera automaticamente um schema parcial (`PartialProductInput`) onde **todos os campos sao opcionais**. Voce nao precisa criar um schema separado para update parcial.

### Schemas Diferentes por Acao

```python
class UserViewSet(ModelViewSet):
    model = User
    input_schema = UserCreateInput  # Default para create/update
    output_schema = UserOutput      # Default para responses
    
    def get_input_schema(self):
        """Retorna schema de entrada baseado na acao."""
        action = getattr(self, "action", None)
        
        if action == "create":
            return UserCreateInput    # email + password obrigatorios
        elif action in ("update", "partial_update"):
            return UserUpdateInput    # apenas name, phone
        
        return self.input_schema
    
    def get_output_schema(self):
        """Retorna schema de saida baseado na acao."""
        action = getattr(self, "action", None)
        
        if action == "list":
            return UserListOutput     # Campos resumidos
        elif action == "retrieve":
            return UserDetailOutput   # Campos completos + relacoes
        
        return self.output_schema
```

### Actions com Schemas Tipados

O decorator `@action` aceita `input_schema` e `output_schema` para documentar custom actions no OpenAPI/Postman:

```python
from core import ModelViewSet, action, InputSchema, OutputSchema

class ActivateInput(InputSchema):
    reason: str
    notify_user: bool = True

class ActivateOutput(OutputSchema):
    message: str
    activated_at: datetime

class UserViewSet(ModelViewSet):
    model = User
    input_schema = UserCreateInput
    output_schema = UserOutput
    
    @action(
        methods=["POST"],
        detail=True,
        input_schema=ActivateInput,     # Body tipado no OpenAPI
        output_schema=ActivateOutput,   # Response tipado no OpenAPI
    )
    async def activate(self, request, db, data=None, **kwargs):
        user = await self.get_object(db, **kwargs)
        user.is_active = True
        await user.save(db)
        
        if data and data.get("notify_user"):
            # Envia notificacao...
            pass
        
        return {
            "message": f"User {user.email} activated",
            "activated_at": user.updated_at,
        }
```

---

## OpenAPI e Postman

### O Que Muda na Documentacao

Com os schemas tipados, o OpenAPI gerado pelo framework inclui:

**Antes** (sem schemas):
```yaml
/users/:
  post:
    requestBody:
      content:
        application/json:
          schema:
            type: object    # Generico — Postman mostra body vazio
    responses:
      200:
        description: Successful Response
        # Sem schema de response
```

**Depois** (com InputSchema/OutputSchema):
```yaml
/users/:
  post:
    requestBody:
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/UserCreateInput'
            # Postman mostra: email (string), name (string), password (string)
    responses:
      201:
        description: Successful Response
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/UserOutput'
              # Postman mostra: id (int), email (string), name (string), ...
      422:
        description: Erro de validacao
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ValidationErrorResponse'
      409:
        description: Conflito
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ConflictResponse'
```

### Exportar para Postman

1. Acesse a documentacao da sua API: `http://localhost:8000/docs`
2. Clique no link do OpenAPI spec: `http://localhost:8000/openapi.json`
3. No Postman: **Import > Link** > cole a URL do OpenAPI
4. Todos os endpoints vem com:
   - **Request body pre-configurado** com os campos do `InputSchema`
   - **Response body** com os campos do `OutputSchema`
   - **Respostas de erro** documentadas (422, 404, 409)
   - **Query parameters** para paginacao (page, page_size)
   - **Path parameters** tipados (id, uuid, etc.)

### Exemplo de Endpoint no Postman

Apos importar, o endpoint `POST /api/v1/users/` tera:

**Body (raw JSON):**
```json
{
    "email": "string",
    "name": "string",
    "password": "string"
}
```

**Response esperada (201):**
```json
{
    "id": 0,
    "email": "string",
    "name": "string",
    "is_active": true,
    "is_admin": false,
    "created_at": "2025-01-01T00:00:00",
    "display_name": "string"
}
```

---

## Serializer (Casos Avancados)

Para logica complexa que combina input e output com operacoes de banco.

```python
from core import Serializer, ModelSerializer
from .schemas import UserInput, UserOutput
from .models import User

class UserSerializer(Serializer):
    input_schema = UserInput
    output_schema = UserOutput

# Com operacoes CRUD integradas
class UserModelSerializer(ModelSerializer):
    model = User
    input_schema = UserInput
    output_schema = UserOutput
    
    # Campos excluidos na criacao
    exclude_on_create = ["id", "created_at"]
    
    # Campos excluidos na atualizacao
    exclude_on_update = ["id", "email", "created_at"]
    
    # Campos somente leitura (nunca atualizados)
    read_only_fields = ["id", "created_at"]
```

### Quando Usar Serializer vs Schema Direto

| Cenario | Use |
|---------|-----|
| CRUD simples | `input_schema` + `output_schema` no ViewSet |
| Logica de criacao customizada | Override `create()` no ViewSet |
| Transformacao complexa de dados | `Serializer` ou `ModelSerializer` |
| Schema compartilhado entre ViewSets | `Serializer` como camada comum |

Na maioria dos casos, `InputSchema` + `OutputSchema` diretamente no ViewSet e suficiente.

---

## Padroes e Receitas

### Schema de Criacao vs Atualizacao

```python
class UserCreateInput(InputSchema):
    """Criacao: todos os campos obrigatorios."""
    email: EmailStr
    name: str
    password: str

class UserUpdateInput(InputSchema):
    """Atualizacao: apenas campos editaveis, todos opcionais."""
    name: str | None = None
    phone: str | None = None
    # email e password NAO incluidos — nao sao editaveis via update normal
```

### Schema de Lista vs Detalhe

```python
class UserListOutput(OutputSchema):
    """Listagem: campos resumidos (performance)."""
    id: int
    name: str
    email: str

class UserDetailOutput(OutputSchema):
    """Detalhe: campos completos + relacoes."""
    id: int
    name: str
    email: str
    phone: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    posts_count: int = 0
    address: AddressOutput | None = None
```

### Heranca de Schema

```python
class UserBaseOutput(OutputSchema):
    """Campos comuns a todas as variantes."""
    id: int
    email: str
    name: str

class UserListOutput(UserBaseOutput):
    """Lista: apenas campos base."""
    pass

class UserDetailOutput(UserBaseOutput):
    """Detalhe: campos base + extras."""
    phone: str | None
    is_active: bool
    created_at: datetime
    posts: list[PostOutput] = []

class UserAdminOutput(UserDetailOutput):
    """Admin: todos os campos + dados internos."""
    failed_login_count: int
    last_login_at: datetime | None
```

### Schema com Enum

```python
from core import InputSchema, OutputSchema
from core.choices import TextChoices

class OrderStatus(TextChoices):
    PENDING = "pending", "Pendente"
    PROCESSING = "processing", "Processando"
    SHIPPED = "shipped", "Enviado"
    DELIVERED = "delivered", "Entregue"
    CANCELLED = "cancelled", "Cancelado"

class OrderInput(InputSchema):
    product_id: int
    quantity: int
    status: OrderStatus = OrderStatus.PENDING

class OrderOutput(OutputSchema):
    id: int
    product_id: int
    quantity: int
    status: OrderStatus
    total: float
```

### Schema para Upload de Arquivo (metadados)

```python
class FileUploadInput(InputSchema):
    """Metadados do arquivo. O arquivo em si vai via multipart/form-data."""
    filename: str
    description: str | None = None
    folder: str = "uploads"
    
    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        allowed = [".jpg", ".png", ".pdf", ".docx"]
        if not any(v.lower().endswith(ext) for ext in allowed):
            raise ValueError(f"Extensao nao permitida. Use: {', '.join(allowed)}")
        return v

class FileOutput(OutputSchema):
    id: int
    filename: str
    url: str
    size_bytes: int
    uploaded_at: datetime
```

### Schema Reutilizavel (Mixin)

```python
class TimestampMixin(OutputSchema):
    """Mixin que adiciona campos de timestamp."""
    created_at: datetime
    updated_at: datetime

class UserOutput(TimestampMixin):
    id: int
    name: str
    email: str
    # Herda created_at e updated_at automaticamente

class PostOutput(TimestampMixin):
    id: int
    title: str
    content: str
    # Herda created_at e updated_at automaticamente
```

---

Proximo: [DateTime](17-datetime.md) - Manipulacao de datas e timezones.
