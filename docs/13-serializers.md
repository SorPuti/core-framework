# Serializers

Schemas de entrada/saída e ponto único de contrato (Serializer) para request/response. A validação ocorre **uma vez** na borda (FastAPI); o ViewSet não revalida quando recebe instância do schema.

## InputSchema vs OutputSchema

Use `InputSchema` e `OutputSchema`, não `BaseModel` puro.

| Recurso | `InputSchema` | `OutputSchema` |
|---------|---------------|-----------------|
| Campos desconhecidos | Ignorados (`extra="ignore"`) | Permitidos |
| Strip whitespace | Sim | — |
| Uso | Validação do body | Serialização da response |

## InputSchema

Para o body das requisições.

```python
from strider.serializers import InputSchema

class ItemCreateInput(InputSchema):
    name: str
    price: float
    description: str | None = None
```

Comportamento padrão:

- `extra="ignore"` — campos não declarados no schema são ignorados (evita 422 por campos extras).
- `str_strip_whitespace=True` — remove espaços em branco em strings.
- `from_attributes=True` — compatível com ORM.

Para rejeitar campos extras (opt-in):

```python
from pydantic import ConfigDict

class StrictInput(InputSchema):
    model_config = ConfigDict(extra="forbid")
    name: str
```

## OutputSchema

Para o corpo das respostas.

```python
from strider.serializers import OutputSchema
from datetime import datetime

class ItemOutput(OutputSchema):
    id: int
    name: str
    price: float
    created_at: datetime
```

Recursos:

- `from_attributes=True` — criação a partir de instância ORM.
- `dump_for_list(obj)` — serializa com `list_include`/`list_exclude` e `@computed_orm_field`.
- `from_orm()` e `from_orm_list()` — helpers para criar instâncias a partir de ORM.

## Contrato centralizado: UnifiedModelSerializer (sem InputSchema/OutputSchema)

Para não definir InputSchema nem OutputSchema separados, use **UnifiedModelSerializer**: o contrato fica só no Serializer, com `fields` e `read_only_fields`. Os schemas de input e output são gerados a partir do model.

```python
from strider import UnifiedModelSerializer, ModelViewSet
from .models import Post

class PostSerializer(UnifiedModelSerializer):
    model = Post
    fields = ["id", "title", "content", "published", "created_at"]
    read_only_fields = ["id", "created_at"]

class PostViewSet(ModelViewSet):
    model = Post
    serializer_class = PostSerializer
```

- **fields**: lista de nomes de colunas do model a expor.
- **read_only_fields**: campos que só aparecem na saída (não aceitos no body de create/update). Geralmente `id` e timestamps.

Quando há pelo menos um campo gravável, o framework gera automaticamente as classes de input e output (herdando de InputSchema/OutputSchema). Para validadores ou campos computados customizados, use [Serializer com input_schema/output_schema](#serializer-ponto-único-de-contrato).

## Uso no ViewSet: Serializer como fonte única

O recomendado é definir um **Serializer** e usá-lo no ViewSet via `serializer_class`. Os schemas de input/output vêm do Serializer (`input_cls`/`output_cls` ou `input_schema`/`output_schema`).

```python
from strider import ModelViewSet
from .models import Item
from .serializers import ItemSerializer

class ItemViewSet(ModelViewSet):
    model = Item
    serializer_class = ItemSerializer
```

Sem Serializer, você pode definir direto no ViewSet:

```python
class ItemViewSet(ModelViewSet):
    model = Item
    input_schema = ItemCreateInput
    output_schema = ItemOutput
```

## Serializer: ponto único de contrato

O **Serializer** concentra input e output. O Router e o ViewSet usam `serializer_class` para obter os schemas (OpenAPI e validação).

```python
from strider.serializers import Serializer

class ItemSerializer(Serializer[Item, ItemCreateInput, ItemOutput]):
    input_schema = ItemCreateInput
    output_schema = ItemOutput
    # Opcional: input_cls / output_cls (aliases para Router/OpenAPI)
```

Métodos principais:

| Método | Descrição |
|--------|-----------|
| `validate_input(data: dict)` | Valida e retorna instância do input schema. |
| `serialize(obj)` | Retorna instância do output schema a partir do objeto. |
| `to_representation(obj)` | Serializa para dict (list/detail), com list_include/list_exclude e @computed_orm_field. |
| `to_representation_many(objects)` | Lista de dicts para listagem. |

O ViewSet usa `_serialize_for_response(obj)` e `_serialize_many_for_response(objects)`, que chamam o Serializer quando `serializer_class` está definido.

## ModelSerializer

Serializer com create/update encapsulados.

```python
from strider.serializers import ModelSerializer

class ItemSerializer(ModelSerializer[Item, ItemCreateInput, ItemOutput]):
    model = Item
    input_schema = ItemCreateInput
    output_schema = ItemOutput

    exclude_on_create = ["id", "created_at"]
    exclude_on_update = ["id"]
    read_only_fields = ["created_at", "updated_at"]
```

Não é obrigatório sobrescrever `create`/`update`; o ViewSet usa os dados validados e chama o model diretamente. O ModelSerializer serve quando você quer lógica de create/update em um único lugar.

## Validadores de campo

```python
from strider.serializers import InputSchema
from pydantic import field_validator

class UserCreateInput(InputSchema):
    email: str
    name: str
    password: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if len(v) < 2:
            raise ValueError("Name must be at least 2 characters")
        return v.strip()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v
```

## Validadores de modelo (cross-field)

```python
from strider.serializers import InputSchema
from pydantic import model_validator

class PasswordChangeInput(InputSchema):
    password: str
    password_confirm: str

    @model_validator(mode="after")
    def passwords_match(self) -> "PasswordChangeInput":
        if self.password != self.password_confirm:
            raise ValueError("Passwords don't match")
        return self
```

## Computed fields

```python
from strider.serializers import OutputSchema
from pydantic import computed_field

class PostOutput(OutputSchema):
    id: int
    title: str
    content: str

    @computed_field
    @property
    def excerpt(self) -> str:
        if len(self.content) <= 100:
            return self.content
        return self.content[:100] + "..."
```

## list_include e list_exclude

Para listagem, você pode restringir campos no output:

```python
class PostOutput(OutputSchema):
    id: int
    title: str
    content: str
    created_at: datetime

    list_include = ("id", "title", "created_at")  # só estes na listagem
    # ou list_exclude = ("content",)
```

`dump_for_list` (e portanto `to_representation`) respeitam esses atributos.

## Campos computados com ORM (@computed_orm_field)

Quando o valor depende do objeto ORM (relacionamentos, etc.):

```python
from strider.serializers import OutputSchema, computed_orm_field

class StrategyOutput(OutputSchema):
    id: int
    name: str

    @computed_orm_field
    def user_email(self, orm_obj: Strategy) -> str | None:
        return orm_obj.user.email if orm_obj.user else None
```

## Schemas aninhados

```python
class UserOutput(OutputSchema):
    id: int
    name: str

class PostOutput(OutputSchema):
    id: int
    title: str
    author: UserOutput | None = None

# Input aninhado
class AddressInput(InputSchema):
    street: str
    city: str

class UserCreateInput(InputSchema):
    name: str
    address: AddressInput
```

## Atualização parcial (PATCH)

O ViewSet gera automaticamente um schema parcial para PATCH (todos os campos opcionais) a partir do `input_schema`. Não é necessário definir um schema de update separado só para PATCH.

## Padrões comuns

### Create vs Update

Use o mesmo input_schema e deixe o PATCH usar o schema parcial, ou defina schemas separados:

```python
class ItemCreateInput(InputSchema):
    name: str
    price: float
    category_id: int

class ItemUpdateInput(InputSchema):
    name: str | None = None
    price: float | None = None
```

### Password no input, não no output

```python
class UserCreateInput(InputSchema):
    email: str
    password: str

class UserOutput(OutputSchema):
    id: int
    email: str
    # password não incluído
```

## Fluxo de validação e serialização

1. **Request**: FastAPI valida o body com o schema de input (do Serializer ou do ViewSet) → uma única validação Pydantic.
2. **Handler**: O ViewSet recebe `data` já como instância do schema (ou dict em actions sem schema); não chama `model_validate` de novo.
3. **Regras de negócio**: `validate_data`, `validate_*` por campo, `validate()` global.
4. **Resposta**: `_serialize_for_response(obj)` → Serializer `to_representation` ou `output_schema.dump_for_list`.

Ver também: [Criar uma aplicação](00-criar-aplicacao.md#6-serializers-e-validação).

## Próximos passos

- [Validators](14-validators.md) — Validação de dados e unicidade
- [ViewSets](04-viewsets.md) — CRUD e actions
- [FAQ](99-faq-troubleshooting.md) — Erros comuns (ex.: extra_forbidden)
